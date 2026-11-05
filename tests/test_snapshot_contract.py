"""Public usage snapshot contract tests."""

import json
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.snapshot_contract import (
    COLLECTION_FIELDS,
    ROSTER_SOURCES,
    STATUS_ORDER,
    SUMMARY_FIELDS,
    TIER_SOURCES,
    TIERS,
    TOP_LEVEL_FIELDS,
    USER_FIELDS,
    status_for,
)
from app.storage import validate_snapshot
from tests.snapshot_factory import valid_snapshot

ROOT = Path(__file__).resolve().parents[1]


class SnapshotContractTests(unittest.TestCase):
    """Keep the public JSON schema aligned with runtime validation."""

    schema: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        """Load the published JSON schema once for the test class."""
        cls.schema = json.loads(
            (ROOT / "contracts" / "usage-snapshot.schema.json").read_text(encoding="utf-8")
        )

    def test_public_schema_matches_runtime_field_sets(self) -> None:
        """Require schema fields and enumerations to match runtime constants."""
        self.assertEqual(TOP_LEVEL_FIELDS, set(self.schema["required"]))
        self.assertEqual(TOP_LEVEL_FIELDS | {"content_hash"}, set(self.schema["properties"]))
        self.assertEqual(SUMMARY_FIELDS, set(self.schema["properties"]["summary"]["required"]))
        self.assertEqual(
            COLLECTION_FIELDS, set(self.schema["properties"]["collection"]["required"])
        )
        user_schema = self.schema["properties"]["users"]["items"]
        self.assertEqual(USER_FIELDS, set(user_schema["required"]))
        self.assertEqual(set(TIERS), set(user_schema["properties"]["tier"]["enum"]))
        self.assertEqual(set(STATUS_ORDER), set(user_schema["properties"]["status"]["enum"]))
        self.assertEqual(TIER_SOURCES, set(user_schema["properties"]["tier_source"]["enum"]))
        self.assertEqual(ROSTER_SOURCES, set(self.schema["properties"]["roster_source"]["enum"]))

    def test_complete_snapshot_passes_runtime_validation(self) -> None:
        """Accept a complete internally consistent fixture snapshot."""
        candidate = valid_snapshot()
        self.assertIs(candidate, validate_snapshot(candidate))


if __name__ == "__main__":
    unittest.main()


class UsageStatusBoundaryTests(unittest.TestCase):
    """Verify the agreed non-overlapping usage percentage intervals."""

    def test_usage_intervals_treat_eighty_percent_as_high(self) -> None:
        """Keep zero separate and use left-closed, right-open nonzero intervals."""
        capacity = 10_000
        self.assertEqual("zero", status_for(Decimal("0"), capacity))
        self.assertEqual("low", status_for(Decimal("1"), capacity))
        self.assertEqual("low", status_for(Decimal("999"), capacity))
        self.assertEqual("medium", status_for(Decimal("1000"), capacity))
        self.assertEqual("medium", status_for(Decimal("4999"), capacity))
        self.assertEqual("normal", status_for(Decimal("5000"), capacity))
        self.assertEqual("normal", status_for(Decimal("7999"), capacity))
        self.assertEqual("high", status_for(Decimal("8000"), capacity))
