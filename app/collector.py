"""Independent Kiro usage collector using Athena, S3 and IAM Identity Center."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from .aws_cli import (
    ACCESS_DENIED_CODES,
    NOT_FOUND_CODES,
    AthenaResult,
    AwsCli,
    AwsCliError,
    JsonObject,
)
from .config import AwsConfig
from .snapshot_contract import STATUS_ORDER, TIERS, status_for

SHANGHAI = ZoneInfo("Asia/Shanghai")
ACTIVE_STATUSES = {"ACTIVE", "ENABLED", "SUBSCRIBED", "PENDING"}
INACTIVE_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "INACTIVE",
    "DELETED",
    "DISABLED",
    "EXPIRED",
    "SUSPENDED",
    "UNASSIGNED",
    "UNSUBSCRIBED",
    "REVOKED",
}
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
FORMULA_PREFIXES = ("=", "+", "-", "@")
USER_ID_SQL = "".join(
    (
        "CASE WHEN strpos(userid, '.') > 0 THEN split_part(userid, '.', 2) ",
        "ELSE userid END",
    )
)
TIER_RANK_SQL = (
    "CASE tier_label WHEN 'Power' THEN 4 WHEN 'Pro Max' THEN 3 "
    "WHEN 'Pro+' THEN 2 WHEN 'Pro' THEN 1 ELSE 0 END"
)


class AwsClient(Protocol):
    """AWS operations required by the snapshot collector."""

    def athena_query(self, sql: str, workgroup: str) -> AthenaResult:
        """Run an Athena query and return its bounded result."""

    def json(self, service: str, operation: str, *arguments: str) -> JsonObject:
        """Run one AWS CLI JSON operation."""

    def paginated_json(
        self, service: str, operation: str, collection_key: str, *arguments: str
    ) -> list[JsonObject]:
        """Read every page from one AWS CLI JSON collection."""

    def s3_bytes(self, bucket: str, key: str) -> bytes:
        """Read one bounded S3 object."""


CSV_ALIASES = {
    "userid": ("userid", "user_id"),
    "user_name": ("user_name", "username", "name"),
    "email": ("email",),
    "subscription_status": ("subscription_status", "status"),
    "subscription_tier": ("subscription_tier", "kiro_plan", "plan"),
    "activation_date": ("activation_date",),
    "plan_source": ("plan_source", "source"),
}


def sanitize(value: Any) -> str:
    """Normalize external text and neutralize spreadsheet formula prefixes."""
    if value is None:
        return ""
    text = CONTROL_CHARS.sub("", str(value)).replace("\r", " ").replace("\n", " ").strip()
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def canonical_user_id(value: Any) -> str:
    """Return a stable user identifier without an Identity Center directory prefix."""
    uid = sanitize(value)
    if uid.startswith("d-") and "." in uid:
        uid = uid.split(".", 1)[1]
    return uid.strip()


def decimal(value: Any) -> Decimal:
    """Convert optional source data to a non-raising Decimal value."""
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def number(value: Any) -> int | float:
    """Return a JSON-compatible representation of a source number."""
    amount = decimal(value)
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def normalize_tier(value: Any) -> str:
    """Map a source subscription label to a supported display tier."""
    raw = sanitize(value).lower()
    compact = re.sub(r"[^a-z0-9+]", "", raw)
    if not compact:
        return "Unknown"
    if "power" in compact:
        return "Power"
    if "promax" in compact or compact in {"max", "kiropromaxusers"}:
        return "Pro Max"
    if "proplus" in compact or "pro+" in raw or compact in {"plus", "kiroprousers+"}:
        return "Pro+"
    if compact in {"pro", "kiroprousers"} or compact.startswith("pro"):
        return "Pro"
    return "Unknown"


def _tier_meta(tier: str) -> dict[str, int | None]:
    """Return one statically typed subscription-tier metadata record."""
    return cast(dict[str, int | None], TIERS[tier])


def highest_tier(values: Iterable[Any]) -> str:
    """Return the highest supported tier represented in source values."""
    return max(
        (normalize_tier(value) for value in values),
        default="Unknown",
        key=lambda tier: cast(int, _tier_meta(tier)["rank"]),
    )


def month_bounds(month: str) -> tuple[date, date]:
    """Return inclusive month start and exclusive following-month start."""
    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    return start, (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def _tier_sql() -> str:
    """Return the fixed SQL expression that canonicalizes subscription tiers."""
    raw = "upper(COALESCE(subscription_tier, ''))"
    compact = f"regexp_replace({raw}, '[^A-Z0-9]', '')"
    return (
        f"CASE WHEN {compact} LIKE '%POWER%' THEN 'Power' "
        f"WHEN {compact} LIKE '%PROMAX%' THEN 'Pro Max' "
        f"WHEN {raw} LIKE '%PRO+%' OR {compact} LIKE '%PROPLUS%' THEN 'Pro+' "
        f"WHEN {compact} LIKE '%PRO%' THEN 'Pro' ELSE 'Unknown' END"
    )


def _database_name(database: str) -> str:
    """Validate an Athena identifier before interpolating it into fixed SQL text."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise ValueError("database must be a valid Athena identifier")
    return database


def cutoff_sql(database: str, month: str) -> str:
    """Build the fixed cutoff query after validating its only SQL identifier."""
    database = _database_name(database)
    start, end = month_bounds(month)
    # B608: fixed SQL only interpolates a validated Athena identifier and ISO dates.
    query = f"""
SELECT CAST(MAX(TRY(date_parse(date, '%Y-%m-%d'))) AS VARCHAR) AS data_cutoff
FROM \"{database}\".\"user_report\"
WHERE TRY(date_parse(date, '%Y-%m-%d')) >= TIMESTAMP '{start.isoformat()} 00:00:00'
  AND TRY(date_parse(date, '%Y-%m-%d')) < TIMESTAMP '{end.isoformat()} 00:00:00'
""".strip()  # nosec B608
    return query


def usage_sql(database: str, month: str, cutoff: date) -> str:
    """Build the fixed monthly usage query after validating its SQL identifier."""
    database = _database_name(database)
    start, month_end = month_bounds(month)
    end = min(month_end, cutoff + timedelta(days=1))
    tier = _tier_sql()
    rank = TIER_RANK_SQL
    # B608: fixed SQL only interpolates a validated Athena identifier and ISO dates.
    query = f"""
WITH typed AS (
 SELECT {USER_ID_SQL} AS user_id,
        TRY(date_parse(date, '%Y-%m-%d')) AS usage_date,
        TRY_CAST(credits_used AS DECIMAL(18,4)) AS credits,
        TRY_CAST(overage_credits_used AS DECIMAL(18,4)) AS overage,
        {tier} AS tier_label
 FROM \"{database}\".\"user_report\"
 WHERE TRY(date_parse(date, '%Y-%m-%d')) >= TIMESTAMP '{start.isoformat()} 00:00:00'
   AND TRY(date_parse(date, '%Y-%m-%d')) < TIMESTAMP '{end.isoformat()} 00:00:00'
), ranked AS (
 SELECT *, {rank} AS tier_rank FROM typed
 WHERE user_id IS NOT NULL AND user_id <> '' AND usage_date IS NOT NULL
), by_day AS (
 SELECT user_id, usage_date, SUM(COALESCE(credits, 0)) credits,
        SUM(COALESCE(overage, 0)) overage,
        CASE MAX(tier_rank) WHEN 4 THEN 'Power' WHEN 3 THEN 'Pro Max'
             WHEN 2 THEN 'Pro+' WHEN 1 THEN 'Pro' ELSE 'Unknown' END AS day_tier
 FROM ranked GROUP BY user_id, usage_date
)
SELECT user_id, CAST(SUM(credits) AS VARCHAR) credits,
       CAST(SUM(overage) AS VARCHAR) overage,
       CAST(MIN(usage_date) AS VARCHAR) first_active,
       CAST(MAX(usage_date) AS VARCHAR) last_active,
       CAST(COUNT(DISTINCT usage_date) AS VARCHAR) active_days,
       max_by(day_tier, usage_date) latest_tier
FROM by_day GROUP BY user_id ORDER BY user_id
""".strip()  # nosec B608
    return query


def latest_tiers_sql(database: str, cutoff: date) -> str:
    """Build the fixed latest-tier query after validating its SQL identifier."""
    database = _database_name(database)
    end = cutoff + timedelta(days=1)
    tier = _tier_sql()
    rank = TIER_RANK_SQL
    # B608: fixed SQL only interpolates a validated Athena identifier and ISO dates.
    query = f"""
WITH typed AS (
 SELECT {USER_ID_SQL} AS user_id,
        TRY(date_parse(date, '%Y-%m-%d')) AS usage_date,
        {tier} AS tier_label
 FROM \"{database}\".\"user_report\"
 WHERE TRY(date_parse(date, '%Y-%m-%d')) < TIMESTAMP '{end.isoformat()} 00:00:00'
), ranked AS (
 SELECT *, {rank} AS tier_rank FROM typed
 WHERE user_id IS NOT NULL AND user_id <> '' AND usage_date IS NOT NULL
), by_day AS (
 SELECT user_id, usage_date,
        CASE MAX(tier_rank) WHEN 4 THEN 'Power' WHEN 3 THEN 'Pro Max'
             WHEN 2 THEN 'Pro+' WHEN 1 THEN 'Pro' ELSE 'Unknown' END AS day_tier
 FROM ranked GROUP BY user_id, usage_date
)
SELECT user_id, max_by(day_tier, usage_date) AS latest_tier
FROM by_day GROUP BY user_id ORDER BY user_id
""".strip()  # nosec B608
    return query


def _canonical_subscription(raw: dict[str, Any]) -> dict[str, str]:
    """Map one CSV subscription row to its normalized canonical fields."""
    lowered = {
        sanitize(key).lower(): sanitize(value) for key, value in raw.items() if key is not None
    }
    row = {
        canonical: next((lowered[alias] for alias in aliases if alias in lowered), "")
        for canonical, aliases in CSV_ALIASES.items()
    }
    row["userid"] = canonical_user_id(row["userid"])
    row["subscription_tier"] = normalize_tier(row["subscription_tier"])
    status_supplied = any(alias in lowered for alias in CSV_ALIASES["subscription_status"])
    if not status_supplied:
        row["subscription_status"] = "ACTIVE"
    row["plan_source"] = row["plan_source"] or "S3 CSV"
    return row


def _active(row: dict[str, Any]) -> bool:
    status = sanitize(row.get("subscription_status")).upper()
    if status in ACTIVE_STATUSES:
        return True
    if status in INACTIVE_STATUSES:
        return False
    raise ValueError(f"unsupported subscription_status: {status or 'EMPTY'}")


def parse_subscription_csv(data: bytes) -> dict[str, dict[str, str]]:
    """Parse active subscription records from an authoritative CSV object."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="strict"), newline=""))
    if reader.fieldnames is None:
        raise ValueError("subscription CSV requires a header")
    headers = {sanitize(value).lower() for value in reader.fieldnames if value}
    if not headers.intersection(CSV_ALIASES["userid"]):
        raise ValueError("subscription CSV requires userid or user_id")
    roster: dict[str, dict[str, str]] = {}
    for raw in reader:
        row = _canonical_subscription(raw)
        uid = row["userid"]
        if not uid:
            continue
        previous = roster.get(uid)
        if previous is None:
            roster[uid] = row
            continue
        selected, other = (
            (row, previous)
            if (_active(row), cast(int, _tier_meta(row["subscription_tier"])["rank"]))
            >= (_active(previous), cast(int, _tier_meta(previous["subscription_tier"])["rank"]))
            else (previous, row)
        )
        selected = dict(selected)
        for field in ("user_name", "email"):
            if (
                (not selected.get(field) or (field == "user_name" and selected[field] == uid))
                and other.get(field)
                and not (field == "user_name" and other[field] == uid)
            ):
                selected[field] = other[field]
        roster[uid] = selected
    return {uid: row for uid, row in roster.items() if _active(row)}


def load_subscription_roster(
    aws: AwsClient, config: AwsConfig
) -> tuple[dict[str, dict[str, str]] | None, bool]:
    """Load the authoritative S3 roster when its configured object exists."""
    if not config.subscription_csv_key:
        return None, False
    try:
        return (
            parse_subscription_csv(aws.s3_bytes(config.data_bucket, config.subscription_csv_key)),
            True,
        )
    except AwsCliError as exc:
        if exc.code in NOT_FOUND_CODES:
            return None, False
        raise


def parse_identity_mapping(data: bytes) -> dict[str, dict[str, str]]:
    """Parse optional display identity overrides from a CSV object."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="strict"), newline=""))
    if reader.fieldnames is None:
        raise ValueError("identity mapping CSV requires a header")
    result: dict[str, dict[str, str]] = {}
    for raw in reader:
        lowered = {
            sanitize(key).lower(): sanitize(value) for key, value in raw.items() if key is not None
        }
        uid = canonical_user_id(lowered.get("userid") or lowered.get("user_id"))
        if not uid:
            continue
        identity = result.setdefault(uid, {"user_name": "", "email": ""})
        name = sanitize(lowered.get("user_name") or lowered.get("username") or lowered.get("name"))
        if name and name != uid:
            identity["user_name"] = name
        if lowered.get("email"):
            identity["email"] = lowered["email"]
    return result


def load_identity_mapping(aws: AwsClient, config: AwsConfig) -> dict[str, dict[str, str]]:
    """Load optional S3 identity data, treating a missing object as empty."""
    try:
        return parse_identity_mapping(aws.s3_bytes(config.data_bucket, config.identity_mapping_key))
    except AwsCliError as exc:
        if exc.code in NOT_FOUND_CODES:
            return {}
        raise


def _identity(user: JsonObject, uid: str) -> dict[str, str]:
    """Extract sanitized display-name and primary-email data from an IIC user."""
    raw_emails = user.get("Emails", [])
    emails = (
        [email for email in raw_emails if isinstance(email, dict)]
        if isinstance(raw_emails, list)
        else []
    )
    email = next((item.get("Value", "") for item in emails if item.get("Primary")), "")
    if not email and emails:
        email = emails[0].get("Value", "")
    return {
        "user_name": sanitize(user.get("DisplayName") or user.get("UserName") or uid),
        "email": sanitize(email),
    }


def _all_identities(aws: AwsClient, store_id: str) -> dict[str, dict[str, str]] | None:
    """Return every Identity Center user, unless listing users is forbidden."""
    try:
        users = aws.paginated_json(
            "identitystore", "list-users", "Users", "--identity-store-id", store_id
        )
    except AwsCliError as exc:
        if exc.code in ACCESS_DENIED_CODES:
            return None
        raise
    return {
        canonical_user_id(user.get("UserId")): _identity(
            user, canonical_user_id(user.get("UserId"))
        )
        for user in users
        if canonical_user_id(user.get("UserId"))
    }


def _describe_identity(aws: AwsClient, store_id: str, uid: str) -> dict[str, str]:
    """Describe one IIC user, retaining a safe placeholder if it was deleted."""
    try:
        user = aws.json(
            "identitystore",
            "describe-user",
            "--identity-store-id",
            store_id,
            "--user-id",
            uid,
        )
    except AwsCliError as exc:
        if exc.code in NOT_FOUND_CODES:
            return {"user_name": uid, "email": ""}
        raise
    return _identity(user, uid)


def resolve_iic_roster(
    aws: AwsClient, config: AwsConfig, historical_tiers: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Build an active roster from all direct and group IIC assignments."""
    assignments = aws.paginated_json(
        "sso-admin",
        "list-application-assignments",
        "ApplicationAssignments",
        "--application-arn",
        config.application_arn,
    )
    direct: set[str] = set()
    groups: dict[str, list[str]] = defaultdict(list)
    for assignment in assignments:
        principal = canonical_user_id(assignment.get("PrincipalId"))
        if assignment.get("PrincipalType") == "USER":
            direct.add(principal)
        elif assignment.get("PrincipalType") == "GROUP":
            group = aws.json(
                "identitystore",
                "describe-group",
                "--identity-store-id",
                config.identity_store_id,
                "--group-id",
                principal,
            )
            tier = normalize_tier(group.get("DisplayName"))
            memberships = aws.paginated_json(
                "identitystore",
                "list-group-memberships",
                "GroupMemberships",
                "--identity-store-id",
                config.identity_store_id,
                "--group-id",
                principal,
            )
            for membership in memberships:
                raw_member = membership.get("MemberId")
                member = raw_member if isinstance(raw_member, dict) else {}
                uid = canonical_user_id(member.get("UserId"))
                if uid:
                    groups[uid].append(tier)
    identities = _all_identities(aws, config.identity_store_id)
    roster = {}
    for uid in sorted(direct | set(groups)):
        known_groups = [tier for tier in groups.get(uid, []) if tier != "Unknown"]
        tier = highest_tier(known_groups) if known_groups else historical_tiers.get(uid, "Unknown")
        source = "current_iic_group" if known_groups else "latest_at_data_cutoff"
        identity = (
            identities.get(uid, {"user_name": uid, "email": ""})
            if identities is not None
            else _describe_identity(aws, config.identity_store_id, uid)
        )
        roster[uid] = {
            "userid": uid,
            **identity,
            "subscription_status": "ACTIVE",
            "subscription_tier": normalize_tier(tier),
            "subscription_tier_source": source,
            "plan_source": "IIC group" if uid in groups else "IIC direct assignment",
        }
    return roster


def usage_by_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index Athena usage records by their canonical user identifier."""
    result = {}
    for row in rows:
        uid = canonical_user_id(row.get("user_id"))
        if uid:
            result[uid] = {
                "credits": decimal(row.get("credits")),
                "overage": decimal(row.get("overage")),
                "first_active": sanitize(row.get("first_active"))[:10],
                "last_active": sanitize(row.get("last_active"))[:10],
                "active_days": int(decimal(row.get("active_days"))),
                "latest_tier": normalize_tier(row.get("latest_tier")),
            }
    return result


def _user_rows(
    usage: dict[str, dict[str, Any]],
    roster: dict[str, dict[str, Any]],
    authoritative: bool,
    identities: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Combine roster, usage, and identity data into sorted API user records."""
    users = []
    for uid in sorted(roster):
        subscription = roster[uid]
        observed = normalize_tier(usage.get(uid, {}).get("latest_tier"))
        roster_tier = normalize_tier(subscription.get("subscription_tier"))
        if authoritative and roster_tier != "Unknown":
            tier, tier_source = roster_tier, "current_authoritative_snapshot"
        elif (
            subscription.get("subscription_tier_source") == "current_iic_group"
            and roster_tier != "Unknown"
        ):
            tier, tier_source = roster_tier, "current_iic_group"
        else:
            tier = observed if observed != "Unknown" else roster_tier
            tier_source = (
                "latest_at_data_cutoff" if tier != "Unknown" else "unknown_direct_assignment"
            )
        meta = _tier_meta(tier)
        item = usage.get(uid, {})
        usage_credits = decimal(item.get("credits"))
        capacity = cast(int, meta["capacity"])
        rate = usage_credits / Decimal(capacity) if capacity else None
        identity = identities.get(uid, {})
        users.append(
            {
                "user_id": uid,
                "user_name": sanitize(
                    identity.get("user_name") or subscription.get("user_name") or uid
                ),
                "email": sanitize(identity.get("email") or subscription.get("email")),
                "tier": tier,
                "credits": number(usage_credits),
                "overage": number(item.get("overage")),
                "capacity": capacity,
                "usage_percent": round(float(rate * 100), 2) if rate is not None else None,
                "first_active": sanitize(item.get("first_active")),
                "last_active": sanitize(item.get("last_active")),
                "active_days": int(decimal(item.get("active_days"))),
                "status": status_for(usage_credits, capacity),
                "monthly_cost_usd": meta["price"],
                "tier_source": tier_source,
            }
        )
    return sorted(
        users,
        key=lambda row: (
            STATUS_ORDER[row["status"]],
            float("inf") if row["usage_percent"] is None else row["usage_percent"],
            row["credits"],
            row["user_name"].casefold(),
            row["email"].casefold(),
        ),
    )


def _summary(users: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in STATUS_ORDER}
    for user in users:
        counts[user["status"]] += 1
    known_costs = [
        user["monthly_cost_usd"] for user in users if user["monthly_cost_usd"] is not None
    ]
    return {
        "users": len(users),
        **counts,
        "total_credits": number(sum((decimal(user["credits"]) for user in users), Decimal(0))),
        "known_monthly_cost_usd": number(
            sum((decimal(value) for value in known_costs), Decimal(0))
        ),
        "unknown_cost_users": len(users) - len(known_costs),
    }


def collect_snapshot(
    config: AwsConfig, aws: AwsClient | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Collect the current bounded AWS usage snapshot without changing its schema."""
    aws = aws or AwsCli(
        config.profile,
        config.region,
        max_s3_object_bytes=config.max_s3_object_bytes,
        max_query_scan_bytes=config.max_query_scan_bytes,
        max_athena_rows=config.max_athena_rows,
    )
    caller = aws.json("sts", "get-caller-identity")
    if str(caller.get("Account", "")) != config.account_id:
        raise RuntimeError("AWS account mismatch; check configured profile and account_id")
    generated = now or datetime.now(UTC)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    local_time = generated.astimezone(SHANGHAI)
    month = local_time.strftime("%Y-%m")
    query_results: list[AthenaResult] = []

    cutoff_result = aws.athena_query(cutoff_sql(config.database, month), config.workgroup)
    query_results.append(cutoff_result)
    cutoff_value = (
        sanitize(cutoff_result.rows[0].get("data_cutoff"))[:10] if cutoff_result.rows else ""
    )
    cutoff = datetime.strptime(cutoff_value, "%Y-%m-%d").date() if cutoff_value else None
    start, end = month_bounds(month)
    if cutoff is not None and not start <= cutoff < end:
        raise RuntimeError("Athena returned a cutoff outside the current month")

    usage: dict[str, dict[str, Any]] = {}
    if cutoff is not None:
        result = aws.athena_query(usage_sql(config.database, month, cutoff), config.workgroup)
        query_results.append(result)
        usage = usage_by_id(result.rows)

    roster, authoritative = load_subscription_roster(aws, config)
    roster = roster or {}
    needs_history = not authoritative or any(
        normalize_tier(row.get("subscription_tier")) == "Unknown"
        and normalize_tier(usage.get(canonical_user_id(uid), {}).get("latest_tier")) == "Unknown"
        for uid, row in roster.items()
    )
    historical_tiers = {}
    if needs_history:
        tier_cutoff = cutoff or (start - timedelta(days=1))
        result = aws.athena_query(latest_tiers_sql(config.database, tier_cutoff), config.workgroup)
        query_results.append(result)
        historical_tiers = {
            canonical_user_id(row.get("user_id")): normalize_tier(row.get("latest_tier"))
            for row in result.rows
            if canonical_user_id(row.get("user_id"))
        }
    if not authoritative:
        roster = resolve_iic_roster(aws, config, historical_tiers)
    else:
        for uid, row in roster.items():
            canonical = canonical_user_id(uid)
            if (
                normalize_tier(row.get("subscription_tier")) == "Unknown"
                and normalize_tier(usage.get(canonical, {}).get("latest_tier")) == "Unknown"
                and historical_tiers.get(canonical, "Unknown") != "Unknown"
            ):
                usage.setdefault(canonical, {"credits": Decimal(0)})["latest_tier"] = (
                    historical_tiers[canonical]
                )

    identities = load_identity_mapping(aws, config)
    for uid, row in roster.items():
        identity = identities.setdefault(canonical_user_id(uid), {"user_name": "", "email": ""})
        if sanitize(row.get("user_name")) and sanitize(row.get("user_name")) != canonical_user_id(
            uid
        ):
            identity["user_name"] = sanitize(row.get("user_name"))
        if sanitize(row.get("email")):
            identity["email"] = sanitize(row.get("email"))

    users = _user_rows(usage, roster, authoritative, identities)
    return {
        "schema_version": 1,
        "generated_at": local_time.isoformat(timespec="seconds"),
        "month": month,
        "data_cutoff": cutoff.isoformat() if cutoff else None,
        "no_month_data": cutoff is None,
        "roster_source": (
            "authoritative_subscription_csv" if authoritative else "iam_identity_center"
        ),
        "source_lag_warning": "Kiro 源数据通常存在 1–2 天延迟",  # noqa: RUF001
        "usage_interpretation": (
            "本月暂无可用源数据；零值不能证明实际未使用"  # noqa: RUF001
            if cutoff is None
            else "用量累计至数据截止日"
        ),
        "summary": _summary(users),
        "collection": {
            "query_count": len(query_results),
            "data_scanned_bytes": sum(result.data_scanned_bytes for result in query_results),
            "engine_execution_ms": sum(result.engine_execution_ms for result in query_results),
            "total_execution_ms": sum(result.total_execution_ms for result in query_results),
        },
        "users": users,
    }
