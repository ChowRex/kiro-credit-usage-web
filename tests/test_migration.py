"""Snapshot migration tests."""

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.storage import RefreshAlreadyRunning, SnapshotStore, validate_snapshot
from scripts.migrate_snapshot_v1 import migrate, normalize_snapshot
from tests.snapshot_factory import valid_snapshot


class MigrationTests(unittest.TestCase):
    """Verify legacy snapshots migrate without changing their source data."""

    @staticmethod
    def legacy_snapshot() -> dict[str, Any]:
        """Build a legacy snapshot with an outdated unknown-user status."""
        legacy = valid_snapshot(credit_amount=0, tier="Unknown")
        legacy["users"][0]["status"] = "zero"
        legacy["summary"]["zero"] = 1
        legacy["summary"]["unknown"] = 0
        return legacy

    def test_normalize_recalculates_unknown_status_without_mutating_source(self) -> None:
        """Recalculate unknown statuses while preserving the input snapshot."""
        source = self.legacy_snapshot()
        migrated = normalize_snapshot(source, datetime(2026, 10, 30, 2, 0, tzinfo=UTC))
        self.assertEqual("zero", source["users"][0]["status"])
        self.assertEqual("unknown", migrated["users"][0]["status"])
        self.assertEqual(1, migrated["summary"]["unknown"])
        self.assertIs(migrated, validate_snapshot(migrated))

    def test_apply_archives_source_and_publishes_valid_history(self) -> None:
        """Archive a migrated source and publish it into normal history."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            source = self.legacy_snapshot()
            (data_dir / "current.json").write_text(json.dumps(source), encoding="utf-8")

            result = migrate(
                data_dir,
                apply=True,
                now=datetime(2026, 10, 30, 2, 0, tzinfo=UTC),
            )

            self.assertEqual("migrated", result["status"])
            archive_path = data_dir / result["legacy_archive"]
            self.assertEqual(json.dumps(source).encode("utf-8"), archive_path.read_bytes())
            store = SnapshotStore(data_dir)
            self.assertIsNotNone(store.load_current())
            history = store.list_history()
            self.assertEqual(1, len(history))
            state = store.load_state()
            self.assertEqual(result["content_hash"], state["current_content_hash"])
            self.assertEqual("2026-10-30T10:00:00+08:00", state["last_migrated_at"])
            self.assertEqual(str(data_dir / "history" / history[0]["path"]), state["history_path"])
            self.assertEqual(
                hashlib.sha256(json.dumps(source).encode("utf-8")).hexdigest(),
                state["legacy_source_hash"],
            )
            self.assertTrue(state["history_written"])

    def test_apply_holds_lock_during_publish_and_preserves_archive_and_state(self) -> None:
        """Block another refresh during migration publication without losing metadata."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            source = self.legacy_snapshot()
            raw = json.dumps(source).encode("utf-8")
            (data_dir / "current.json").write_bytes(raw)
            original_publish_locked = SnapshotStore.publish_locked

            def publish_while_locked(
                store: SnapshotStore, snapshot: dict[str, Any]
            ) -> dict[str, Any]:
                """Verify another refresh cannot enter while migration is publishing."""
                with (
                    self.assertRaises(RefreshAlreadyRunning),
                    SnapshotStore(data_dir).refresh_lock(),
                ):
                    pass
                return original_publish_locked(store, snapshot)

            with (
                patch.object(SnapshotStore, "publish_locked", new=publish_while_locked),
                patch.object(SnapshotStore, "publish", side_effect=AssertionError),
                patch.object(SnapshotStore, "save_state", side_effect=AssertionError),
            ):
                result = migrate(
                    data_dir,
                    apply=True,
                    now=datetime(2026, 10, 30, 2, 0, tzinfo=UTC),
                )

            archive_path = data_dir / result["legacy_archive"]
            state = SnapshotStore(data_dir).load_state()
            self.assertEqual(raw, archive_path.read_bytes())
            self.assertEqual(result["content_hash"], state["current_content_hash"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), state["legacy_source_hash"])
            self.assertTrue(state["history_written"])
            current = SnapshotStore(data_dir).load_current()
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(result["content_hash"], current["content_hash"])


if __name__ == "__main__":
    unittest.main()
