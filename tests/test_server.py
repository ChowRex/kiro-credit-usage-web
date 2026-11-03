"""Dashboard HTTP server tests."""

import http.client
import io
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from app.config import AppConfig, AwsConfig, RefreshConfig, ServerConfig
from app.server import (
    DashboardHandler,
    DashboardServer,
    _csv_body,
    _load_admin_token,
    health_payload,
    main,
    parse_args,
)
from app.storage import SnapshotStore
from tests.snapshot_factory import valid_snapshot


def config(root: str | Path) -> AppConfig:
    """Build a temporary application configuration for HTTP server tests."""
    root = Path(root)
    return AppConfig(
        source_path=root / "config.toml",
        data_dir=root / "data",
        web_dir=root / "web",
        aws=AwsConfig(
            "us-east-1", "test", "123", "bucket", "db", "wg", "store", "app", "", "mapping.csv"
        ),
        server=ServerConfig("127.0.0.1", 0, 30, 300),
        refresh=RefreshConfig("10:00", (60, 300, 900, 1800), 0.2),
    )


def snapshot() -> dict[str, Any]:
    """Build a fixture snapshot representing an unknown tier user."""
    return valid_snapshot(credit_amount=0, tier="Unknown")


class ServerTests(unittest.TestCase):
    """Exercise dashboard APIs and HTTP safety behavior."""

    def test_cli_accepts_safe_preview_bind_overrides(self) -> None:
        """Accept explicit local host, port, and token-file CLI overrides."""
        args = parse_args(
            [
                "--config",
                "config.local.toml",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
                "--admin-token-file",
                ".admin-token",
            ]
        )
        self.assertEqual("127.0.0.1", args.host)
        self.assertEqual(8080, args.port)
        self.assertEqual(Path(".admin-token"), args.admin_token_file)

    def test_admin_token_file_requires_owner_only_permissions(self) -> None:
        """Reject refresh token files that grant permissions to other users."""
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token"
            token_file.write_text("a-secure-refresh-token\n", encoding="utf-8")
            token_file.chmod(0o600)
            self.assertEqual("a-secure-refresh-token", _load_admin_token(token_file))
            token_file.chmod(0o644)
            with self.assertRaises(PermissionError):
                _load_admin_token(token_file)

    def test_main_keeps_admin_token_on_the_server_instance(self) -> None:
        """Use the file or environment token without changing the parent environment."""
        token_file = self.temp_dir / "admin-token"
        token_file.write_text("file-refresh-token-value\n", encoding="utf-8")
        token_file.chmod(0o600)
        dashboard = MagicMock()
        with (
            patch.dict(
                os.environ,
                {"KIRO_REFRESH_ADMIN_TOKEN": "environment-refresh-token"},
                clear=True,
            ),
            patch("app.server.load_config", return_value=self.config),
            patch("app.server.create_server", return_value=dashboard) as create,
        ):
            self.assertEqual(
                0,
                main(["--config", "ignored.toml", "--admin-token-file", str(token_file)]),
            )
            self.assertEqual("environment-refresh-token", os.environ["KIRO_REFRESH_ADMIN_TOKEN"])
        create.assert_called_once_with(self.config, "file-refresh-token-value")
        dashboard.serve_forever.assert_called_once_with()

        dashboard = MagicMock()
        with (
            patch.dict(
                os.environ,
                {"KIRO_REFRESH_ADMIN_TOKEN": "environment-refresh-token"},
                clear=True,
            ),
            patch("app.server.load_config", return_value=self.config),
            patch("app.server.create_server", return_value=dashboard) as create,
        ):
            self.assertEqual(0, main(["--config", "ignored.toml"]))
        create.assert_called_once_with(self.config, "environment-refresh-token")

    def test_main_warns_for_non_loopback_binds_only(self) -> None:
        """Warn about unauthenticated HTTP only when the configured bind is non-loopback."""
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                config_with_host = replace(
                    self.config, server=replace(self.config.server, host=host)
                )
                output = io.StringIO()
                with (
                    patch("app.server.load_config", return_value=config_with_host),
                    patch("app.server.create_server", return_value=MagicMock()),
                    patch("sys.stderr", output),
                ):
                    self.assertEqual(0, main(["--config", "ignored.toml"]))
                self.assertEqual("", output.getvalue())

        token = "private-refresh-token-value"
        unsafe_config = replace(self.config, server=replace(self.config.server, host="0.0.0.0"))
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"KIRO_REFRESH_ADMIN_TOKEN": token}, clear=True),
            patch("app.server.load_config", return_value=unsafe_config),
            patch("app.server.create_server", return_value=MagicMock()),
            patch("sys.stderr", output),
        ):
            self.assertEqual(0, main(["--config", "ignored.toml"]))
        self.assertIn("unauthenticated HTTP", output.getvalue())
        self.assertIn("TLS", output.getvalue())
        self.assertIn("PII", output.getvalue())
        self.assertNotIn(token, output.getvalue())

    def setUp(self) -> None:
        """Start an isolated dashboard server with a published fixture snapshot."""
        self.temp_dir: Path = Path(tempfile.mkdtemp())
        self.config: AppConfig = config(self.temp_dir)
        self.config.web_dir.mkdir()
        (self.config.web_dir / "index.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
        (self.config.web_dir / "app.js").write_text("'use strict';", encoding="utf-8")
        (self.config.web_dir / "styles.css").write_text("body{}", encoding="utf-8")
        self.store: SnapshotStore = SnapshotStore(self.config.data_dir)
        self.store.publish(snapshot())
        self.store.save_state(
            {
                "status": "healthy",
                "last_success_at": "2026-10-28T10:00:00+08:00",
                "last_checked_at": "2026-10-28T10:00:00+08:00",
                "consecutive_failures": 0,
            }
        )
        self.server: DashboardServer = DashboardServer(
            ("127.0.0.1", 0), DashboardHandler, self.config, self.store, ""
        )
        self.thread: threading.Thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.port: int = self.server.server_address[1]

    def _restart_server(self, admin_token: str) -> None:
        """Restart the test server with the supplied instance-owned token."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = DashboardServer(
            ("127.0.0.1", 0), DashboardHandler, self.config, self.store, admin_token
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        """Stop the test server and remove its temporary filesystem state."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        shutil.rmtree(self.temp_dir)

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        """Send an HTTP request to the running test server."""
        with closing(http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)) as connection:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            body = response.read()
            response_headers = dict(response.getheaders())
        return response.status, response_headers, body

    def _raw_request(self, request: bytes) -> bytes:
        """Send one raw HTTP request and read until its required connection close."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as connection:
            connection.sendall(request)
            chunks: list[bytes] = []
            while chunk := connection.recv(4096):
                chunks.append(chunk)
        return b"".join(chunks)

    def test_current_health_static_and_utf8_bom_csv(self) -> None:
        """Serve snapshot, health, history, static files, and a BOM-prefixed CSV."""
        status, headers, body = self.request("GET", "/api/current")
        self.assertEqual(200, status)
        self.assertEqual("2026-10", json.loads(body)["month"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

        status, _, body = self.request("GET", "/api/health")
        self.assertEqual(200, status)
        health = json.loads(body)
        self.assertTrue(health["has_snapshot"])
        self.assertEqual("2026-10-27", health["snapshot_data_cutoff"])

        status, _, body = self.request("GET", "/api/history")
        self.assertEqual(200, status)
        self.assertEqual(1, len(json.loads(body)["entries"]))

        status, _, body = self.request("POST", "/api/reload")
        self.assertEqual(200, status)
        self.assertEqual("2026-10", json.loads(body)["month"])

        status, headers, body = self.request("GET", "/api/export.csv")
        self.assertEqual(200, status)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("kiro-credit-usage-2026-10.csv", headers["Content-Disposition"])

        status, headers, body = self.request("GET", "/")
        self.assertEqual(200, status)
        self.assertIn(b"Dashboard", body)
        self.assertEqual("no-cache", headers["Cache-Control"])
        status, headers, _ = self.request("GET", "/app.js")
        self.assertEqual(200, status)
        self.assertEqual("no-cache", headers["Cache-Control"])
        self.assertEqual(404, self.request("GET", "/../../etc/passwd")[0])

    def test_health_marks_failed_snapshot_stale(self) -> None:
        """Mark a failed-refresh snapshot stale when it exceeds the age threshold."""
        self.store.save_state(
            {
                "status": "error",
                "last_success_at": "2026-10-28T10:00:00+08:00",
                "last_checked_at": "2026-10-29T10:00:00+08:00",
                "consecutive_failures": 2,
            }
        )
        payload = health_payload(
            self.config,
            self.store,
            "",
            datetime(2026, 10, 29, 2, 0, tzinfo=UTC),
        )
        self.assertTrue(payload["serving_stale_snapshot"])
        self.assertEqual(2, payload["consecutive_failures"])

    def test_manual_refresh_is_disabled_or_token_protected_and_rate_limited(self) -> None:
        """Require a token for background refreshes and enforce their cooldown."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(503, self.request("POST", "/api/refresh")[0])
        token = "a-secure-refresh-token"
        release = threading.Event()
        refresh_calls = 0

        def wait_for_release(*_args: object, **_kwargs: object) -> dict[str, Any]:
            """Record the background refresh and wait until the test releases it."""
            nonlocal refresh_calls
            refresh_calls += 1
            release.wait(timeout=2)
            return snapshot()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.server.refresh_once", side_effect=wait_for_release),
            patch("app.server.time.monotonic", side_effect=[1.0, 2.0]),
        ):
            self._restart_server(token)
            self.assertEqual(
                401,
                self.request(
                    "POST",
                    "/api/refresh",
                    {"X-Refresh-Token": "wrong-token-value"},
                )[0],
            )
            self.assertEqual(
                202,
                self.request(
                    "POST",
                    "/api/refresh",
                    {"X-Refresh-Token": token},
                )[0],
            )
            status, _, body = self.request("GET", "/api/health")
            self.assertEqual(200, status)
            self.assertTrue(json.loads(body)["manual_refresh_running"])
            self.assertTrue(json.loads(body)["manual_refresh_enabled"])
            release.set()
            deadline = time.time() + 2
            while self.server.manual_refresh_running and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(1, refresh_calls)
            self.assertFalse(self.server.manual_refresh_running)
            self.assertEqual(
                429,
                self.request(
                    "POST",
                    "/api/refresh",
                    {"X-Refresh-Token": token},
                )[0],
            )

    def test_manual_refresh_records_redacted_background_failure(self) -> None:
        """Write a stable error classification when the daemon refresh fails."""
        token = "a-secure-refresh-token"
        failed = threading.Event()
        output = io.StringIO()

        def failing_refresh(*_args: object, **_kwargs: object) -> dict[str, Any]:
            """Record the background invocation and raise a private failure."""
            failed.set()
            raise RuntimeError("private detail")

        with (
            patch("app.server.refresh_once", side_effect=failing_refresh),
            patch.object(DashboardHandler, "log_message"),
            patch("sys.stderr", output),
        ):
            self._restart_server(token)
            self.assertEqual(
                202,
                self.request("POST", "/api/refresh", {"X-Refresh-Token": token})[0],
            )
            self.assertTrue(failed.wait(timeout=2))
            deadline = time.time() + 2
            while self.server.manual_refresh_running and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual("manual refresh failed: RuntimeError\n", output.getvalue())
        self.assertFalse(self.server.manual_refresh_running)

    def test_csv_rounds_credits_and_uses_unrounded_values_for_percent(self) -> None:
        """Round displayed credits while calculating percentages from raw credit values."""
        rounded = _csv_body(valid_snapshot(credit_amount=10.5)).decode("utf-8-sig").splitlines()
        header = rounded[0].split(",")
        values = dict(zip(header, rounded[1].split(","), strict=True))
        self.assertEqual("11", values["credits"])
        self.assertEqual("2", values["usage_percent"])

        boundary = _csv_body(valid_snapshot(credit_amount=100.001)).decode("utf-8-sig").splitlines()
        values = dict(zip(boundary[0].split(","), boundary[1].split(","), strict=True))
        self.assertEqual("11", values["usage_percent"])

        capped = _csv_body(valid_snapshot(credit_amount=1100)).decode("utf-8-sig").splitlines()
        values = dict(zip(capped[0].split(","), capped[1].split(","), strict=True))
        self.assertEqual("100", values["usage_percent"])

    def test_csv_neutralizes_formula_leading_identity_fields(self) -> None:
        """Prefix direct and whitespace-prefixed spreadsheet formula fields."""
        candidate = valid_snapshot()
        candidate["users"][0]["user_name"] = "=SUM(1,1)"
        text = _csv_body(candidate).decode("utf-8-sig")
        self.assertIn("'", text)
        self.assertNotIn(",=SUM", text)
        for prefix, formula in (("\u00a0", "=1+1"), ("\u2003", "+1"), ("\n", "@cmd")):
            candidate["users"][0]["user_name"] = prefix + formula
            self.assertIn("'" + prefix + formula, _csv_body(candidate).decode("utf-8-sig"))

    def test_post_rejects_body_framing_and_closes_connection(self) -> None:
        """Reject framed POSTs before residual bytes can become another request."""
        requests = (
            b"POST /api/reload HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\n\r\nx"
            b"GET /api/current HTTP/1.1\r\nHost: localhost\r\n\r\n",
            b"POST /api/reload HTTP/1.1\r\nHost: localhost\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
            b"POST /api/reload HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n"
            b"Content-Length: 0\r\n\r\n",
        )
        for request in requests:
            response = self._raw_request(request)
            self.assertTrue(response.startswith(b"HTTP/1.1 400"))
            self.assertIn(b"Connection: close", response)
            self.assertEqual(1, response.count(b"HTTP/1.1"))

    def test_csv_body_never_serializes_unknown_cost_as_zero(self) -> None:
        """Leave unknown subscription cost blank instead of serializing it as zero."""
        body = _csv_body(snapshot())
        text = body.decode("utf-8-sig")
        self.assertIn("tier_source,overage,first_active", text)
        self.assertIn("unknown,,unknown_direct_assignment,0,", text)
        self.assertNotIn("unknown,0,unknown_direct_assignment", text)


if __name__ == "__main__":
    unittest.main()
