"""Complete, internally consistent snapshots for unit tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from app.snapshot_contract import STATUS_ORDER, TIERS, status_for


def valid_snapshot(
    generated_at: str = "2026-10-28T10:00:00+08:00",
    credit_amount: int | float = 10,
    tier: str = "Pro",
) -> dict[str, Any]:
    """Build a complete snapshot with internally consistent derived fields."""
    meta = cast(dict[str, int | None], TIERS[tier])
    capacity_value = meta["capacity"]
    assert capacity_value is not None
    capacity = int(capacity_value)
    status = status_for(Decimal(str(credit_amount)), capacity)
    usage_percent = (
        round(float(Decimal(str(credit_amount)) / Decimal(capacity) * 100), 2) if capacity else None
    )
    has_activity = credit_amount > 0
    counts = {name: int(name == status) for name in STATUS_ORDER}
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "month": "2026-10",
        "data_cutoff": "2026-10-27",
        "no_month_data": False,
        "roster_source": "iam_identity_center",
        "source_lag_warning": "Kiro 源数据通常存在 1-2 天延迟",
        "usage_interpretation": "用量累计至数据截止日",
        "summary": {
            "users": 1,
            **counts,
            "total_credits": credit_amount,
            "known_monthly_cost_usd": meta["price"] or 0,
            "unknown_cost_users": int(meta["price"] is None),
        },
        "collection": {
            "query_count": 3,
            "data_scanned_bytes": 30,
            "engine_execution_ms": 2,
            "total_execution_ms": 4,
        },
        "users": [
            {
                "user_id": "u1",
                "user_name": "用户",
                "email": "user@example.com",
                "tier": tier,
                "credits": credit_amount,
                "overage": 0,
                "capacity": capacity,
                "usage_percent": usage_percent,
                "first_active": "2026-10-27" if has_activity else "",
                "last_active": "2026-10-27" if has_activity else "",
                "active_days": 1 if has_activity else 0,
                "status": status,
                "monthly_cost_usd": meta["price"],
                "tier_source": (
                    "latest_at_data_cutoff" if tier != "Unknown" else "unknown_direct_assignment"
                ),
            }
        ],
    }
