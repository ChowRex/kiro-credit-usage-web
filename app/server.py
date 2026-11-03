"""Dependency-free private-network HTTP server and dashboard API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import mimetypes
import os
import queue
import stat
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .config import AppConfig, load_config
from .refresh import refresh_once
from .snapshot_contract import USER_FIELD_NAMES
from .storage import RefreshAlreadyRunning, SnapshotStore

SHANGHAI = ZoneInfo("Asia/Shanghai")
CSV_FIELDS = list(USER_FIELD_NAMES)


def _json_body(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _rounded_credit(value: Any) -> int | str:
    if value is None or value == "":
        return ""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _display_percent(value: Any) -> int | str:
    if value is None or value == "":
        return ""
    rounded = int(Decimal(str(value)).to_integral_value(rounding=ROUND_CEILING))
    return min(100, max(0, rounded))


def _csv_safe(value: Any) -> Any:
    """Prefix spreadsheet formula-like text, including after Unicode whitespace."""
    if isinstance(value, str):
        first_content = value.lstrip()
        if value.startswith(("\t", "\r")) or first_content.startswith(("=", "+", "-", "@")):
            return "'" + value
    return value


def _csv_body(snapshot: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for user in snapshot.get("users", []):
        row = {field: _csv_safe(user.get(field)) for field in CSV_FIELDS}
        row["credits"] = _rounded_credit(user.get("credits"))
        row["overage"] = _rounded_credit(user.get("overage"))
        capacity = user.get("capacity")
        raw_percent = (
            Decimal(str(user.get("credits"))) * 100 / Decimal(str(capacity)) if capacity else None
        )
        row["usage_percent"] = _display_percent(raw_percent)
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def _parse_time(value: Any) -> datetime | None:
    """Parse an optional persisted timestamp and normalize naive values to UTC."""
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def health_payload(
    config: AppConfig,
    store: SnapshotStore,
    admin_token: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return public health data derived from persisted state and snapshot age."""
    current = store.load_current()
    state = store.load_state()
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    last_success = _parse_time(state.get("last_success_at"))
    age_hours = (
        max(
            0,
            round((current_time - last_success.astimezone(UTC)).total_seconds() / 3600, 2),
        )
        if last_success
        else None
    )
    stale = bool(
        current
        and (
            state.get("status") == "error"
            or age_hours is None
            or age_hours > config.server.stale_after_hours
        )
    )
    return {
        "status": state.get("status", "not_initialized"),
        "has_snapshot": current is not None,
        "serving_stale_snapshot": stale,
        "snapshot_age_hours": age_hours,
        "stale_after_hours": config.server.stale_after_hours,
        "last_checked_at": state.get("last_checked_at"),
        "last_success_at": state.get("last_success_at"),
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "next_retry_at": state.get("next_retry_at"),
        "last_error": state.get("last_error"),
        "manual_refresh_enabled": len(admin_token) >= 16,
        "snapshot_generated_at": current.get("generated_at") if current else None,
        "snapshot_data_cutoff": current.get("data_cutoff") if current else None,
    }


class DashboardServer(ThreadingHTTPServer):
    """Bound concurrent private HTTP connections around the standard server."""

    daemon_threads = True
    request_queue_size = 32

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        config: AppConfig,
        store: SnapshotStore,
        admin_token: str,
    ) -> None:
        """Create the server with its validated configuration and snapshot store."""
        self.connection_slots = queue.Queue[None](maxsize=config.server.max_connections)
        for _ in range(config.server.max_connections):
            self.connection_slots.put_nowait(None)
        super().__init__(address, handler)
        self.config = config
        self.store = store
        self._admin_token = admin_token
        self.manual_lock = threading.Lock()
        self.manual_refresh_running = False
        self.last_manual_refresh: float | None = None

    def manual_refresh_enabled(self) -> bool:
        """Return whether this server has a sufficiently long refresh token."""
        return len(self._admin_token) >= 16

    def is_valid_admin_token(self, supplied: str) -> bool:
        """Compare a supplied refresh token against this server's private token."""
        return hmac.compare_digest(
            hashlib.sha256(supplied.encode()).digest(),
            hashlib.sha256(self._admin_token.encode()).digest(),
        )

    def health_payload(self) -> dict[str, Any]:
        """Return health data using the token configured for this server instance."""
        return health_payload(self.config, self.store, self._admin_token)

    def process_request(self, request: Any, client_address: Any) -> None:
        try:
            self.connection_slots.get_nowait()
        except queue.Empty:
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connection_slots.put_nowait(None)
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.put_nowait(None)


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve dashboard assets and the private snapshot HTTP API."""

    server: DashboardServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.config.server.request_timeout_seconds)

    def log_message(  # pylint: disable=arguments-differ
        self, format_string: str, *args: Any
    ) -> None:
        """Write base-handler access logs to standard error using its required signature."""
        sys.stderr.write(
            f"{self.address_string()} [{self.log_date_time_string()}] {format_string % args}\n"
        )

    def _send(
        self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'",
        )
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, value: Any) -> None:
        self._send(
            status,
            _json_body(value),
            "application/json; charset=utf-8",
            {"Cache-Control": "no-store"},
        )

    def _current(self) -> None:
        snapshot = self.server.store.load_current()
        if snapshot is None:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "snapshot_unavailable",
                    "message": "尚无成功快照，请先执行数据刷新。",  # noqa: RUF001
                },
            )
            return
        self._json(HTTPStatus.OK, snapshot)

    def do_HEAD(self) -> None:  # pylint: disable=invalid-name
        """Handle HEAD using the GET route required by BaseHTTPRequestHandler."""
        self.do_GET()

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle the HTTP GET route name required by BaseHTTPRequestHandler."""
        path = urlparse(self.path).path
        if path == "/api/current":
            self._current()
            return
        if path == "/api/health":
            payload = self.server.health_payload()
            with self.server.manual_lock:
                payload["manual_refresh_running"] = self.server.manual_refresh_running
            self._json(HTTPStatus.OK, payload)
            return
        if path == "/api/history":
            self._json(HTTPStatus.OK, {"entries": self.server.store.list_history()})
            return
        if path == "/api/export.csv":
            snapshot = self.server.store.load_current()
            if snapshot is None:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "snapshot_unavailable"})
                return
            body = _csv_body(snapshot)
            month = snapshot.get("month", "current")
            self._send(
                HTTPStatus.OK,
                body,
                "text/csv; charset=utf-8",
                {
                    "Cache-Control": "no-store",
                    "Content-Disposition": f'attachment; filename="kiro-credit-usage-{month}.csv"',
                },
            )
            return
        self._static(path)

    def _static(self, path: str) -> None:
        relative = {"/": "index.html", "/index.html": "index.html"}.get(path, path.lstrip("/"))
        if relative not in {"index.html", "app.js", "styles.css"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        target = self.server.config.web_dir / relative
        if not target.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "asset_not_found"})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), content_type, {"Cache-Control": "no-cache"})

    def _reject_framed_post_body(self) -> bool:
        """Reject POST body framing and close the connection before residual bytes can be reused."""
        transfer_encoding = self.headers.get_all("Transfer-Encoding", [])
        content_lengths = self.headers.get_all("Content-Length", [])
        valid_zero_length = len(content_lengths) <= 1 and (
            not content_lengths or content_lengths[0].strip() == "0"
        )
        if not transfer_encoding and valid_zero_length:
            return False
        self.close_connection = True
        self._send(
            HTTPStatus.BAD_REQUEST,
            _json_body({"error": "request_body_not_allowed"}),
            "application/json; charset=utf-8",
            {"Cache-Control": "no-store", "Connection": "close"},
        )
        return True

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Handle the HTTP POST route name required by BaseHTTPRequestHandler."""
        if self._reject_framed_post_body():
            return
        path = urlparse(self.path).path
        if path == "/api/reload":
            self._current()
            return
        if path != "/api/refresh":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        supplied = self.headers.get("X-Refresh-Token", "")
        if not self.server.manual_refresh_enabled():
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "manual_refresh_disabled",
                    "message": "服务端未配置管理员刷新 Token。",
                },
            )
            return
        if not self.server.is_valid_admin_token(supplied):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_refresh_token"})
            return
        with self.server.manual_lock:
            now = time.monotonic()
            if self.server.manual_refresh_running:
                self._json(HTTPStatus.CONFLICT, {"error": "refresh_already_running"})
                return
            previous_refresh = self.server.last_manual_refresh
            remaining = (
                self.server.config.server.manual_refresh_cooldown_seconds - (now - previous_refresh)
                if previous_refresh is not None
                else 0.0
            )
            if remaining > 0:
                self._json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {
                        "error": "refresh_cooldown",
                        "retry_after_seconds": round(remaining),
                    },
                )
                return
            self.server.manual_refresh_running = True
            self.server.last_manual_refresh = now
        threading.Thread(target=self._manual_refresh, daemon=True).start()
        self._json(HTTPStatus.ACCEPTED, {"status": "refresh_started"})

    def _manual_refresh(self) -> None:
        """Run a background refresh and record only a redacted failure classification."""
        try:
            refresh_once(self.server.config, self.server.store)
        except RefreshAlreadyRunning:
            sys.stderr.write("manual refresh skipped: RefreshAlreadyRunning\n")
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            sys.stderr.write(f"manual refresh failed: {type(exc).__name__}\n")
        finally:
            with self.server.manual_lock:
                self.server.manual_refresh_running = False


def create_server(config: AppConfig, admin_token: str) -> DashboardServer:
    """Create the HTTP server after verifying its static asset directory."""
    if not config.web_dir.is_dir():
        raise FileNotFoundError(f"web directory not found: {config.web_dir}")
    store = SnapshotStore(config.data_dir)
    store.ensure()
    store.reconcile()
    return DashboardServer(
        (config.server.host, config.server.port),
        DashboardHandler,
        config,
        store,
        admin_token,
    )


def _is_loopback_host(host: str) -> bool:
    """Return whether a bind host is a known loopback address or localhost."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _load_admin_token(path: Path) -> str:
    """Read an owner-only local manual-refresh token."""
    source = path.expanduser().resolve()
    info = source.stat()
    if info.st_uid != os.getuid():
        raise PermissionError("admin token file must be owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("admin token file permissions must be 0600 or stricter")
    token = source.read_text(encoding="utf-8").strip()
    if len(token) < 16:
        raise ValueError("admin token file must contain at least 16 characters")
    return token


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse dashboard configuration, bind overrides, and token-file options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.local.toml"))
    parser.add_argument("--host", help="override the configured bind host")
    parser.add_argument("--port", type=int, help="override the configured TCP port")
    parser.add_argument(
        "--admin-token-file",
        type=Path,
        help="read the manual-refresh token from an owner-only local file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the private dashboard server and report startup failures safely."""
    args = parse_args(argv)
    try:
        admin_token = (
            _load_admin_token(args.admin_token_file)
            if args.admin_token_file is not None
            else os.environ.get("KIRO_REFRESH_ADMIN_TOKEN", "")
        )
        config = load_config(args.config)
        if args.host is not None or args.port is not None:
            host = args.host.strip() if args.host is not None else config.server.host
            port = args.port if args.port is not None else config.server.port
            if not host:
                raise ValueError("server host override must not be empty")
            if not 1 <= port <= 65535:
                raise ValueError("server port override must be between 1 and 65535")
            config = replace(config, server=replace(config.server, host=host, port=port))
        server = create_server(config, admin_token)
        if not _is_loopback_host(config.server.host):
            print(
                "warning: non-loopback bind exposes unauthenticated HTTP; use TLS, access "
                "controls, and avoid PII.",
                file=sys.stderr,
            )
        print(f"Kiro usage dashboard listening on http://{config.server.host}:{config.server.port}")
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        print("server stopped")
        return 0
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"server failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
