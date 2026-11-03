"""Normalize a legacy local snapshot to the strict schema-v1 contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.snapshot_contract import STATUS_ORDER, TIERS, status_for
from app.storage import SnapshotStore, atomic_write, validate_snapshot

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"legacy {field} is not numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"legacy {field} must be finite and non-negative")
    return amount


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def normalize_snapshot(source: dict[str, Any], generated_at: datetime) -> dict[str, Any]:
    """Return a strict snapshot without mutating the legacy source object."""
    candidate = copy.deepcopy(source)
    candidate.pop("content_hash", None)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    candidate["generated_at"] = generated_at.astimezone(SHANGHAI).isoformat(timespec="seconds")
    candidate["source_lag_warning"] = "Kiro 源数据通常存在 1–2 天延迟"  # noqa: RUF001
    candidate["usage_interpretation"] = (
        "本月暂无可用源数据；零值不能证明实际未使用"  # noqa: RUF001
        if candidate.get("data_cutoff") is None
        else "用量累计至数据截止日"
    )

    counts = {status: 0 for status in STATUS_ORDER}
    total_credits = Decimal(0)
    known_cost = Decimal(0)
    unknown_cost_users = 0
    users = candidate.get("users")
    if not isinstance(users, list):
        raise ValueError("legacy snapshot users must be an array")

    for user in users:
        if not isinstance(user, dict):
            raise ValueError("legacy snapshot user must be an object")
        user = cast(dict[str, Any], user)
        raw_tier_name = user.get("tier")
        tier_name = raw_tier_name if isinstance(raw_tier_name, str) else "Unknown"
        if tier_name not in TIERS:
            tier_name = "Unknown"
            user["tier"] = tier_name
        tier = cast(dict[str, Any], TIERS[tier_name])
        usage_credits = _decimal(user.get("credits"), "credits")
        _decimal(user.get("overage"), "overage")
        capacity = int(tier["capacity"])
        user["capacity"] = capacity
        user["monthly_cost_usd"] = tier["price"]
        user["usage_percent"] = (
            round(float(usage_credits / Decimal(capacity) * 100), 2) if capacity else None
        )
        user["status"] = status_for(usage_credits, capacity)

        status = cast(str, user["status"])
        counts[status] += 1
        total_credits += usage_credits
        if tier["price"] is None:
            unknown_cost_users += 1
        else:
            known_cost += Decimal(tier["price"])

    candidate["summary"] = {
        "users": len(users),
        **counts,
        "total_credits": _number(total_credits),
        "known_monthly_cost_usd": _number(known_cost),
        "unknown_cost_users": unknown_cost_users,
    }
    return validate_snapshot(candidate)


def migrate(data_dir: Path, *, apply: bool, now: datetime | None = None) -> dict[str, Any]:
    """Preview or migrate current.json while excluding concurrent refreshes during apply."""
    store = SnapshotStore(data_dir)
    if not apply:
        raw = store.current_path.read_bytes()
        source = json.loads(raw.decode("utf-8"))
        migrated = normalize_snapshot(source, now or datetime.now(UTC))
        return {
            "status": "ready",
            "users": migrated["summary"]["users"],
            **{status: migrated["summary"][status] for status in STATUS_ORDER},
        }

    with store.refresh_lock():
        raw = store.current_path.read_bytes()
        source = json.loads(raw.decode("utf-8"))
        migrated = normalize_snapshot(source, now or datetime.now(UTC))
        result: dict[str, Any] = {
            "status": "migrated",
            "users": migrated["summary"]["users"],
            **{status: migrated["summary"][status] for status in STATUS_ORDER},
        }
        source_digest = hashlib.sha256(raw).hexdigest()
        legacy_path = data_dir / "legacy" / f"current-{source_digest[:12]}.json"
        if legacy_path.exists():
            if hashlib.sha256(legacy_path.read_bytes()).hexdigest() != source_digest:
                raise RuntimeError("legacy archive path collision")
        else:
            atomic_write(legacy_path, raw)

        publication = store.publish_locked(migrated)
        state = store.load_state()
        store.save_state_locked(
            {
                **state,
                "current_content_hash": publication["content_hash"],
                "last_migrated_at": migrated["generated_at"],
                "legacy_source_hash": source_digest,
                "history_written": publication["history_written"],
                "history_path": publication["history_path"],
            }
        )
        result.update(
            {
                "content_hash": publication["content_hash"],
                "history_written": publication["history_written"],
                "legacy_archive": legacy_path.relative_to(data_dir).as_posix(),
            }
        )
        return result


def parse_args() -> argparse.Namespace:
    """Parse the local snapshot migration command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--apply", action="store_true", help="archive current and publish migrated data"
    )
    return parser.parse_args()


def main() -> int:
    """Run the migration command and print its structured result."""
    args = parse_args()
    result = migrate(args.data_dir, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
