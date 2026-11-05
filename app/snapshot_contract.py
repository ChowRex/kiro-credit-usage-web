"""Shared schema-v1 snapshot fields and business rules."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

TIERS: Final = {
    "Unknown": {"rank": 0, "capacity": 0, "price": None},
    "Pro": {"rank": 1, "capacity": 1000, "price": 20},
    "Pro+": {"rank": 2, "capacity": 2000, "price": 40},
    "Pro Max": {"rank": 3, "capacity": 5000, "price": 100},
    "Power": {"rank": 4, "capacity": 10000, "price": 200},
}
STATUS_ORDER: Final = {
    "zero": 0,
    "low": 1,
    "medium": 2,
    "normal": 3,
    "high": 4,
    "unknown": 5,
}
ROSTER_SOURCES: Final = {"authoritative_subscription_csv", "iam_identity_center"}
TIER_SOURCES: Final = {
    "current_authoritative_snapshot",
    "current_iic_group",
    "latest_at_data_cutoff",
    "unknown_direct_assignment",
}
TOP_LEVEL_FIELDS: Final = {
    "schema_version",
    "generated_at",
    "month",
    "data_cutoff",
    "no_month_data",
    "roster_source",
    "source_lag_warning",
    "usage_interpretation",
    "summary",
    "collection",
    "users",
}
SUMMARY_FIELDS: Final = {
    "users",
    "zero",
    "low",
    "medium",
    "normal",
    "high",
    "unknown",
    "total_credits",
    "known_monthly_cost_usd",
    "unknown_cost_users",
}
COLLECTION_FIELDS: Final = {
    "query_count",
    "data_scanned_bytes",
    "engine_execution_ms",
    "total_execution_ms",
}
USER_FIELD_NAMES: Final = (
    "user_id",
    "user_name",
    "email",
    "tier",
    "credits",
    "capacity",
    "usage_percent",
    "last_active",
    "active_days",
    "status",
    "monthly_cost_usd",
    "tier_source",
    "overage",
    "first_active",
)
USER_FIELDS: Final = set(USER_FIELD_NAMES)


def status_for(usage_credits: Decimal, capacity: int) -> str:
    """Classify usage, treating an unknown capacity as unknown before zero usage."""
    if capacity <= 0:
        return "unknown"
    if usage_credits == 0:
        return "zero"
    rate = usage_credits / Decimal(capacity)
    if rate < Decimal("0.10"):
        return "low"
    if rate < Decimal("0.50"):
        return "medium"
    if rate < Decimal("0.80"):
        return "normal"
    return "high"
