"""Usage collector tests."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from app.aws_cli import AthenaResult, JsonObject
from app.collector import (
    collect_snapshot,
    highest_tier,
    normalize_tier,
    parse_subscription_csv,
    usage_sql,
)
from app.config import AwsConfig
from app.snapshot_contract import status_for
from app.storage import validate_snapshot


def query(rows: list[dict[str, str]], scanned: int = 10) -> AthenaResult:
    """Build a minimal Athena response with predictable execution statistics."""
    return AthenaResult(rows, "qid", scanned, 1, 2)


class FakeAws:
    """Provide a concrete in-memory AWS client fixture for collector tests."""

    def __init__(self, no_month_data: bool = False) -> None:
        """Configure whether the monthly cutoff query returns data."""
        self.no_month_data = no_month_data
        self.queries: list[str] = []
        self.json_calls: list[tuple[str, str]] = []
        self.paginated_calls: list[tuple[str, str, str]] = []
        self.s3_reads: list[tuple[str, str]] = []

    def athena_query(self, sql: str, _workgroup: str) -> AthenaResult:
        """Return canned Athena results based on the requested query."""
        self.queries.append(sql)
        if "MAX(TRY(date_parse" in sql:
            return query([{"data_cutoff": "" if self.no_month_data else "2026-10-27"}])
        if "CAST(SUM(credits)" in sql:
            return query(
                [
                    {
                        "user_id": "u-active",
                        "credits": "50",
                        "overage": "0",
                        "first_active": "2026-10-20",
                        "last_active": "2026-10-27",
                        "active_days": "2",
                        "latest_tier": "Pro",
                    }
                ]
            )
        return query(
            [
                {"user_id": "u-active", "latest_tier": "Pro"},
                {"user_id": "u-zero", "latest_tier": "Pro+"},
            ]
        )

    def s3_bytes(self, bucket: str, key: str) -> bytes:
        """Return a fixed identity mapping CSV while recording its location."""
        self.s3_reads.append((bucket, key))
        return (
            b"userid,username,email\n"
            b"u-active,Active,active@example.com\n"
            b"u-zero,Zero,zero@example.com\n"
        )

    def json(self, service: str, operation: str, *_arguments: str) -> JsonObject:
        """Return the account identity needed by collection."""
        self.json_calls.append((service, operation))
        if (service, operation) == ("sts", "get-caller-identity"):
            return {"Account": "123"}
        raise AssertionError((service, operation))

    def paginated_json(
        self, service: str, operation: str, collection_key: str, *_arguments: str
    ) -> list[JsonObject]:
        """Return assigned users and IAM Identity Center users."""
        self.paginated_calls.append((service, operation, collection_key))
        if (service, operation) == ("sso-admin", "list-application-assignments"):
            return [
                {"PrincipalType": "USER", "PrincipalId": "u-active"},
                {"PrincipalType": "USER", "PrincipalId": "u-zero"},
            ]
        if (service, operation) == ("identitystore", "list-users"):
            return [
                {
                    "UserId": "u-active",
                    "DisplayName": "Active",
                    "Emails": [{"Value": "active@example.com", "Primary": True}],
                },
                {
                    "UserId": "u-zero",
                    "DisplayName": "Zero",
                    "Emails": [{"Value": "zero@example.com", "Primary": True}],
                },
            ]
        raise AssertionError((service, operation))


class GroupMembershipFakeAws(FakeAws):
    """Provide an AWS fixture whose application assignment is a group."""

    def json(self, service: str, operation: str, *arguments: str) -> JsonObject:
        """Describe the test membership group before other fake responses."""
        if (service, operation) == ("identitystore", "describe-group"):
            self.json_calls.append((service, operation))
            return {"DisplayName": "Kiro Pro+ Users"}
        return super().json(service, operation, *arguments)

    def paginated_json(
        self, service: str, operation: str, collection_key: str, *arguments: str
    ) -> list[JsonObject]:
        """Return group assignments and memberships before default fake responses."""
        if (service, operation) == ("sso-admin", "list-application-assignments"):
            self.paginated_calls.append((service, operation, collection_key))
            return [{"PrincipalType": "GROUP", "PrincipalId": "group-id"}]
        if (service, operation) == ("identitystore", "list-group-memberships"):
            self.paginated_calls.append((service, operation, collection_key))
            return [
                {"MemberId": {"UserId": "u-active"}},
                {"MemberId": {"UserId": "u-zero"}},
            ]
        return super().paginated_json(service, operation, collection_key, *arguments)


CONFIG = AwsConfig(
    region="us-east-1",
    profile="test",
    account_id="123",
    data_bucket="bucket",
    database="kiro_analytics",
    workgroup="wg",
    identity_store_id="store",
    application_arn="app",
    subscription_csv_key="",
    identity_mapping_key="mapping.csv",
)


class CollectorTests(unittest.TestCase):
    """Verify snapshot collection and roster interpretation."""

    def test_tier_and_threshold_rules(self) -> None:
        """Apply tier normalization, thresholds, and tier ordering."""
        self.assertEqual("Pro+", normalize_tier("Pro+"))
        self.assertEqual("Pro+", normalize_tier("PRO_PLUS"))
        self.assertEqual("Power", highest_tier(["Pro", "Pro+", "Power"]))
        self.assertEqual("unknown", status_for(Decimal(0), 0))
        self.assertEqual("zero", status_for(Decimal(0), 1000))
        self.assertEqual("low", status_for(Decimal("99.99"), 1000))
        self.assertEqual("medium", status_for(Decimal(100), 1000))
        self.assertEqual("high", status_for(Decimal(800), 1000))
        self.assertEqual("high", status_for(Decimal("800.01"), 1000))
        sql = usage_sql("kiro_analytics", "2026-10", datetime(2026, 10, 27).date())
        self.assertLess(sql.index("LIKE '%PRO+%'"), sql.rindex("LIKE '%PRO%'"))
        self.assertIn("2026-10-28 00:00:00", sql)

    def test_authoritative_csv_excludes_inactive_and_active_duplicate_wins(self) -> None:
        """Use active CSV records and retain the first active duplicate."""
        roster = parse_subscription_csv(
            b"userid,name,email,plan,status\n"
            b"u1,Alice,a@example.com,Pro,ACTIVE\n"
            b"u1,u1,,Power,CANCELLED\n"
            b"u2,Former,f@example.com,Power,INACTIVE\n"
        )
        self.assertEqual({"u1"}, set(roster))
        self.assertEqual("Pro", roster["u1"]["subscription_tier"])
        with self.assertRaisesRegex(ValueError, "unsupported subscription_status"):
            parse_subscription_csv(b"userid,plan,status\nu3,Pro,FUTURE\n")
        with self.assertRaisesRegex(ValueError, "unsupported subscription_status"):
            parse_subscription_csv(b"userid,plan,status\nu4,Pro,\n")
        default_active = parse_subscription_csv(b"userid,plan\nu5,Pro\n")
        self.assertEqual({"u5"}, set(default_active))

    def test_full_iic_snapshot_includes_zero_user_and_query_cost(self) -> None:
        """Collect direct assignments, including zero-usage users and query cost."""
        aws = FakeAws()
        snapshot = collect_snapshot(CONFIG, aws=aws, now=datetime(2026, 10, 28, 2, 0, tzinfo=UTC))
        self.assertIs(snapshot, validate_snapshot(snapshot))
        self.assertEqual("2026-10", snapshot["month"])
        self.assertEqual("2026-10-27", snapshot["data_cutoff"])
        self.assertEqual(2, snapshot["summary"]["users"])
        self.assertEqual(1, snapshot["summary"]["zero"])
        self.assertEqual(0, snapshot["summary"]["unknown"])
        self.assertEqual(1, snapshot["summary"]["low"])
        self.assertEqual(3, snapshot["collection"]["query_count"])
        self.assertEqual(30, snapshot["collection"]["data_scanned_bytes"])
        zero = next(user for user in snapshot["users"] if user["user_id"] == "u-zero")
        self.assertEqual(0, zero["credits"])
        self.assertEqual("zero", zero["status"])
        self.assertEqual("Pro+", zero["tier"])
        self.assertEqual(40, zero["monthly_cost_usd"])
        self.assertEqual({("sts", "get-caller-identity")}, set(aws.json_calls))
        self.assertEqual(
            {
                ("sso-admin", "list-application-assignments", "ApplicationAssignments"),
                ("identitystore", "list-users", "Users"),
            },
            set(aws.paginated_calls),
        )
        self.assertEqual([("bucket", "mapping.csv")], aws.s3_reads)

    def test_iic_group_roster_reads_paginated_memberships(self) -> None:
        """Expand a group assignment through paginated membership records."""
        aws = GroupMembershipFakeAws()
        snapshot = collect_snapshot(CONFIG, aws=aws, now=datetime(2026, 10, 28, 2, 0, tzinfo=UTC))
        self.assertEqual({"u-active", "u-zero"}, {user["user_id"] for user in snapshot["users"]})
        self.assertTrue(all(user["tier"] == "Pro+" for user in snapshot["users"]))
        self.assertIn(
            ("identitystore", "list-group-memberships", "GroupMemberships"),
            aws.paginated_calls,
        )

    def test_no_month_data_keeps_roster_and_warns_against_inference(self) -> None:
        """Keep roster users when the month has no data and flag the limitation."""
        aws = FakeAws(no_month_data=True)
        snapshot = collect_snapshot(CONFIG, aws=aws, now=datetime(2026, 10, 1, 2, 0, tzinfo=UTC))
        self.assertIs(snapshot, validate_snapshot(snapshot))
        self.assertIsNone(snapshot["data_cutoff"])
        self.assertTrue(snapshot["no_month_data"])
        self.assertIn("零值不能证明", snapshot["usage_interpretation"])
        self.assertEqual(0, snapshot["summary"]["unknown"])
        self.assertEqual(2, snapshot["summary"]["zero"])
        self.assertEqual(2, snapshot["collection"]["query_count"])


if __name__ == "__main__":
    unittest.main()
