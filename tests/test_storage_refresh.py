"""Snapshot storage and refresh workflow tests."""

import tempfile
import unittest
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.aws_cli import AwsCliError
from app.config import AppConfig, AwsConfig, RefreshConfig, ServerConfig
from app.refresh import refresh_once, run_with_retry
from app.storage import (
    RefreshAlreadyRunning,
    SnapshotStore,
    atomic_write_json,
    snapshot_fingerprint,
    validate_snapshot,
)
from tests.snapshot_factory import valid_snapshot


def snapshot(generated_at: str, credit_amount: int | float = 10) -> dict[str, Any]:
    """Build a test snapshot with the requested timestamp and credit amount."""
    return valid_snapshot(generated_at=generated_at, credit_amount=credit_amount)


def config(data_dir: str | Path) -> AppConfig:
    """Build an application configuration rooted in a temporary data directory."""
    return AppConfig(
        source_path=Path("config.toml"),
        data_dir=Path(data_dir),
        web_dir=Path("web"),
        aws=AwsConfig(
            "us-east-1", "test", "123", "bucket", "db", "wg", "store", "app", "", "mapping.csv"
        ),
        server=ServerConfig("127.0.0.1", 8080, 30, 300),
        refresh=RefreshConfig("10:00", (60, 300, 900, 1800), 0.2),
    )


class StorageRefreshTests(unittest.TestCase):
    """Verify durable snapshot publication, state updates, and retries."""

    def test_validator_rejects_unknown_capacity_as_zero(self) -> None:
        """Reject zero status when an unknown tier has no capacity."""
        invalid = valid_snapshot(credit_amount=0, tier="Unknown")
        invalid["users"][0]["status"] = "zero"
        invalid["summary"]["zero"] = 1
        invalid["summary"]["unknown"] = 0
        with self.assertRaisesRegex(ValueError, "status is inconsistent"):
            validate_snapshot(invalid)

    def test_validator_rejects_incomplete_snapshot(self) -> None:
        """Reject snapshots missing a required collection field."""
        invalid = valid_snapshot()
        del invalid["collection"]["total_execution_ms"]
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            validate_snapshot(invalid)

    def test_validator_rejects_contradictory_activity_metadata(self) -> None:
        """Reject active credit records without matching activity metadata."""
        invalid = valid_snapshot()
        invalid["users"][0].update(
            {
                "first_active": "",
                "last_active": "",
                "active_days": 0,
            }
        )
        with self.assertRaisesRegex(ValueError, "positive credits require activity metadata"):
            validate_snapshot(invalid)

    def test_reconcile_preserves_missing_daily_snapshot_with_unchanged_content(self) -> None:
        """Restore an interrupted current snapshot to history when content is unchanged."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            store.publish(valid_snapshot("2026-10-28T10:00:00+08:00"))
            interrupted = valid_snapshot("2026-10-29T10:00:00+08:00")
            interrupted = {**interrupted, "content_hash": snapshot_fingerprint(interrupted)}
            atomic_write_json(store.current_path, interrupted)

            result = store.reconcile()

            self.assertEqual(2, result["valid_history_entries"])
            self.assertEqual(
                ["2026-10-29T10:00:00+08:00", "2026-10-28T10:00:00+08:00"],
                [entry["generated_at"] for entry in store.list_history()],
            )

    def test_reconcile_keeps_parseable_legacy_history_in_manifest(self) -> None:
        """Report legacy history files without treating them as current schema snapshots."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            legacy = valid_snapshot()
            del legacy["summary"]["high"]
            path = Path(directory) / "history" / "2026" / "10" / "legacy.json"
            atomic_write_json(path, legacy)

            result = store.reconcile()

            self.assertEqual(0, result["valid_history_entries"])
            self.assertEqual(1, result["legacy_history_entries"])
            self.assertTrue(store.list_history()[0]["legacy"])

    def test_publish_does_not_replace_current_when_history_write_fails(self) -> None:
        """Keep the current snapshot when its associated history write fails."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            store.publish(valid_snapshot(credit_amount=10))
            with (
                patch.object(store, "_write_history_if_missing", side_effect=OSError("disk")),
                self.assertRaises(OSError),
            ):
                store.publish(valid_snapshot(credit_amount=20))
            current = store.load_current()
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(10, current["users"][0]["credits"])

    def test_atomic_current_and_history_on_change_or_new_day(self) -> None:
        """Write history only for changed content or a newly observed day."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            first = store.publish(snapshot("2026-10-28T10:00:00+08:00"))
            self.assertTrue(first["history_written"])
            self.assertEqual(1, len(store.list_history()))
            same_day = store.publish(snapshot("2026-10-28T12:00:00+08:00"))
            self.assertFalse(same_day["history_written"])
            self.assertEqual(1, len(store.list_history()))
            changed = store.publish(snapshot("2026-10-28T14:00:00+08:00", credit_amount=20))
            self.assertTrue(changed["history_written"])
            self.assertEqual(2, len(store.list_history()))
            next_day = store.publish(snapshot("2026-10-29T10:00:00+08:00", credit_amount=20))
            self.assertTrue(next_day["history_written"])
            self.assertEqual(3, len(store.list_history()))
            current = store.load_current()
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(20, current["users"][0]["credits"])
            self.assertFalse(list(Path(directory).rglob(".*.json.*")))

    def test_refresh_failure_preserves_last_success_and_records_error(self) -> None:
        """Keep the last snapshot and store a redacted collector failure."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            store.publish(snapshot("2026-10-28T10:00:00+08:00"))
            old = store.load_current()

            def failing_collector(*_args: object, **_kwargs: object) -> dict[str, Any]:
                """Raise a collector error containing private details."""
                raise RuntimeError("private details")

            with self.assertRaises(RuntimeError):
                refresh_once(
                    config(directory),
                    store=store,
                    collector=failing_collector,
                    now=lambda: datetime(2026, 10, 29, 2, 0, tzinfo=UTC),
                )
            self.assertEqual(old, store.load_current())
            state = store.load_state()
            self.assertEqual("error", state["status"])
            self.assertEqual(1, state["consecutive_failures"])
            self.assertNotIn("private details", state["last_error"]["message"])

    def test_aws_refresh_error_is_redacted_in_state(self) -> None:
        """Persist a generic AWS failure rather than operation or error detail."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            private_marker = "customer-id-and-operation"

            def failing_collector(*_args: object, **_kwargs: object) -> dict[str, Any]:
                """Raise an AWS error that carries a private identifier."""
                raise AwsCliError(private_marker, "SensitiveCode")

            with self.assertRaises(AwsCliError):
                refresh_once(config(directory), store=store, collector=failing_collector)

            error = store.load_state()["last_error"]
            self.assertEqual("AwsCliError", error["code"])
            self.assertNotIn(private_marker, error["message"])
            self.assertNotIn("SensitiveCode", error["message"])

    def test_retry_uses_configured_delays_and_eventually_succeeds(self) -> None:
        """Retry collector errors using durable scheduling state."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            attempts: Iterator[RuntimeError | dict[str, Any]] = iter(
                [
                    RuntimeError("one"),
                    RuntimeError("two"),
                    snapshot("2026-10-28T10:00:00+08:00"),
                ]
            )
            collector_calls = 0
            sleep_delays: list[float] = []

            def collector(*_args: object, **_kwargs: object) -> dict[str, Any]:
                """Return the next fixture result or raise its configured error."""
                nonlocal collector_calls
                collector_calls += 1
                result = next(attempts)
                if isinstance(result, Exception):
                    raise result
                return result

            def sleep(delay: float) -> None:
                """Record retry delay without waiting during the test."""
                sleep_delays.append(delay)

            result = run_with_retry(
                config(directory),
                store=store,
                collector=collector,
                now=lambda: datetime(2026, 10, 28, 2, 0, tzinfo=UTC),
                sleep=sleep,
                random_value=lambda: 0.5,
            )
            self.assertEqual([60, 300], sleep_delays)
            self.assertEqual(3, collector_calls)
            self.assertEqual("healthy", result["state"]["status"])
            self.assertEqual(0, store.load_state()["consecutive_failures"])

    def test_retry_releases_process_lock_before_sleeping(self) -> None:
        """Allow another worker to acquire the lock during failed-refresh backoff."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            attempts: Iterator[RuntimeError | dict[str, Any]] = iter(
                [RuntimeError("temporary"), snapshot("2026-10-28T10:00:00+08:00")]
            )

            def collector(*_args: object, **_kwargs: object) -> dict[str, Any]:
                """Return the next retry result or raise its configured failure."""
                result = next(attempts)
                if isinstance(result, Exception):
                    raise result
                return result

            def release_check(_delay: float) -> None:
                """Confirm a second worker can acquire the released process lock."""
                with SnapshotStore(Path(directory)).refresh_lock():
                    pass

            result = run_with_retry(
                config(directory),
                store=store,
                collector=collector,
                sleep=release_check,
                random_value=lambda: 0.5,
            )

            self.assertEqual("healthy", result["state"]["status"])

    def test_malformed_state_and_manifest_fall_back_safely(self) -> None:
        """Reject malformed metadata while serving a validated physical history fallback."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            expected = snapshot("2026-10-28T10:00:00+08:00")
            store.publish(expected)
            atomic_write_json(store.state_path, [])
            atomic_write_json(store.current_path, [])
            atomic_write_json(store.manifest_path, [])

            recovered = SnapshotStore(Path(directory))
            self.assertEqual("error", recovered.load_state()["status"])
            self.assertEqual("InvalidStateFile", recovered.load_state()["last_error"]["code"])
            self.assertEqual([], recovered.list_history())
            current = recovered.load_current()
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(expected["generated_at"], current["generated_at"])

    def test_lock_contention_retries_without_mutating_state(self) -> None:
        """Treat an occupied process lock as retryable without recording a failure."""
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(Path(directory))
            initial_state = {"status": "healthy", "consecutive_failures": 0}
            store.save_state(initial_state)
            sleep_delays: list[float] = []
            collector_calls = 0

            def collector(*_args: object, **_kwargs: object) -> dict[str, Any]:
                """Record unexpected collector invocation during lock contention."""
                nonlocal collector_calls
                collector_calls += 1
                return snapshot("2026-10-28T10:00:00+08:00")

            def sleep(delay: float) -> None:
                """Record lock-contention retry delays without waiting."""
                sleep_delays.append(delay)

            with store.refresh_lock(), self.assertRaises(RefreshAlreadyRunning):
                run_with_retry(
                    config(directory),
                    store=SnapshotStore(Path(directory)),
                    collector=collector,
                    sleep=sleep,
                    random_value=lambda: 0.5,
                )

            self.assertEqual([60, 300, 900, 1800], sleep_delays)
            self.assertEqual(0, collector_calls)
            self.assertEqual(initial_state, store.load_state())


if __name__ == "__main__":
    unittest.main()
