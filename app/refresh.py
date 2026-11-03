"""Refresh orchestration with durable stale fallback and exponential-style retry."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .aws_cli import AwsCliError
from .collector import collect_snapshot
from .config import AppConfig, load_config
from .storage import RefreshAlreadyRunning, SnapshotStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now(now: Callable[[], datetime]) -> datetime:
    value = now()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _safe_error(exc: Exception) -> dict[str, str]:
    """Return durable error metadata without preserving exception details."""
    if isinstance(exc, AwsCliError):
        return {
            "type": type(exc).__name__,
            "code": type(exc).__name__,
            "message": "refresh failed while querying the configured AWS data source",
        }
    if isinstance(exc, (TimeoutError, RefreshAlreadyRunning)):
        return {
            "type": type(exc).__name__,
            "code": type(exc).__name__,
            "message": f"refresh failed ({type(exc).__name__})",
        }
    return {
        "type": type(exc).__name__,
        "code": type(exc).__name__,
        "message": f"refresh failed ({type(exc).__name__})",
    }


def _refresh_once_locked(
    config: AppConfig,
    store: SnapshotStore,
    collector: Callable[..., dict[str, Any]],
    now: Callable[[], datetime],
) -> dict[str, Any]:
    """Collect, publish, and record state while the store process lock is held."""
    started = _now(now).astimezone(SHANGHAI)
    previous = store.load_state()
    store.save_state_locked(
        {
            **previous,
            "status": "refreshing",
            "refresh_started_at": started.isoformat(timespec="seconds"),
            "last_checked_at": started.isoformat(timespec="seconds"),
            "next_retry_at": None,
        }
    )
    try:
        snapshot = collector(config.aws, now=started)
        publication = store.publish_locked(snapshot)
        finished = _now(now).astimezone(SHANGHAI)
        state = {
            "schema_version": 1,
            "status": "healthy",
            "last_checked_at": finished.isoformat(timespec="seconds"),
            "last_success_at": finished.isoformat(timespec="seconds"),
            "last_error": None,
            "consecutive_failures": 0,
            "next_retry_at": None,
            "current_content_hash": publication["content_hash"],
            "history_written": publication["history_written"],
            "history_path": publication["history_path"],
        }
        store.save_state_locked(state)
        return {"snapshot": snapshot, "publication": publication, "state": state}
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        failed = _now(now).astimezone(SHANGHAI)
        failures = int(previous.get("consecutive_failures", 0)) + 1
        state = {
            **previous,
            "schema_version": 1,
            "status": "error",
            "last_checked_at": failed.isoformat(timespec="seconds"),
            "last_error": _safe_error(exc),
            "consecutive_failures": failures,
            "next_retry_at": None,
        }
        store.save_state_locked(state)
        raise


def refresh_once(
    config: AppConfig,
    store: SnapshotStore | None = None,
    collector: Callable[..., dict[str, Any]] = collect_snapshot,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Execute one refresh transaction under the snapshot-store process lock."""
    store = store or SnapshotStore(config.data_dir)
    with store.refresh_lock():
        return _refresh_once_locked(config, store, collector, now)


def run_with_retry(
    config: AppConfig,
    store: SnapshotStore | None = None,
    collector: Callable[..., dict[str, Any]] = collect_snapshot,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> dict[str, Any]:
    """Retry collection or lock contention without marking contention as a failed refresh."""
    store = store or SnapshotStore(config.data_dir)
    attempts = 1 + len(config.refresh.retry_delays_seconds)
    for attempt in range(attempts):
        try:
            with store.refresh_lock():
                try:
                    return _refresh_once_locked(config, store, collector, now)
                except (OSError, RuntimeError, ValueError, TypeError):
                    if attempt >= len(config.refresh.retry_delays_seconds):
                        raise
                    base = config.refresh.retry_delays_seconds[attempt]
                    factor = 1 + config.refresh.jitter_ratio * (2 * random_value() - 1)
                    delay = max(0, base * factor)
                    retry_at = _now(now).astimezone(SHANGHAI) + timedelta(seconds=delay)
                    state = store.load_state()
                    store.save_state_locked(
                        {
                            **state,
                            "next_retry_at": retry_at.isoformat(timespec="seconds"),
                            "retry_attempt": attempt + 1,
                            "retry_delay_seconds": round(delay, 3),
                        }
                    )
        except RefreshAlreadyRunning:
            if attempt >= len(config.refresh.retry_delays_seconds):
                raise
            delay = max(0, config.refresh.retry_delays_seconds[attempt])
        sleep(delay)
    raise AssertionError("unreachable")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the standalone refresh command's configuration and retry options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.local.toml"))
    parser.add_argument(
        "--retry", action="store_true", help="retry after 1/5/15/30 minutes with jitter"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one refresh command and report a redacted result to standard output."""
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        result = run_with_retry(config) if args.retry else refresh_once(config)
        output = {
            "status": "ok",
            "month": result["snapshot"]["month"],
            "data_cutoff": result["snapshot"]["data_cutoff"],
            "users": result["snapshot"]["summary"]["users"],
            "history_written": result["publication"]["history_written"],
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        print("refresh cancelled", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        safe = _safe_error(exc)
        print(f"refresh failed: {safe['code']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
