"""Atomic current/state/history snapshot storage with a process lock."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from .snapshot_contract import (
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


class RefreshAlreadyRunning(RuntimeError):
    """Indicate that another process currently owns the snapshot-store lock."""


def _json_bytes(value: Any) -> bytes:
    """Serialize JSON deterministically for atomic persistence and hashing."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write(path: Path, body: bytes) -> None:
    """Atomically replace a file and synchronize its containing directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically serialize an object to a UTF-8 JSON file."""
    atomic_write(path, _json_bytes(value))


def read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file or return the caller's default when it is absent."""
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    """Hash stable snapshot content while excluding volatile publication metadata."""
    stable = {
        key: value
        for key, value in snapshot.items()
        if key not in {"generated_at", "collection", "content_hash"}
    }
    return hashlib.sha256(_json_bytes(stable)).hexdigest()


def _require_fields(
    value: Any, required: set[str], allowed: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = required - set(value)
    if missing:
        raise ValueError(f"{label} is missing required fields: {', '.join(sorted(missing))}")
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(f"{label} has unexpected fields: {', '.join(sorted(unexpected))}")
    return value


def _require_number(value: Any, label: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    if integer and not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _parse_date(value: Any, label: str, *, optional: bool = False) -> date | None:
    if optional and value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a date string")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc


def _decimal(value: Any) -> Decimal:
    """Convert an already validated numeric value to Decimal for exact comparisons."""
    return Decimal(str(value))


def _same_number(actual: Any, expected: Any) -> bool:
    return (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and _decimal(actual) == Decimal(str(expected))
    )


def validate_snapshot(snapshot: Any) -> dict[str, Any]:
    """Validate schema-v1 data and its cross-field business invariants."""
    snapshot = _require_fields(
        snapshot,
        set(TOP_LEVEL_FIELDS),
        set(TOP_LEVEL_FIELDS) | {"content_hash"},
        "snapshot",
    )
    if snapshot["schema_version"] != 1:
        raise ValueError("unsupported snapshot schema_version")
    if not isinstance(snapshot["generated_at"], str):
        raise ValueError("snapshot generated_at must be a string")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        snapshot["generated_at"],
    ):
        raise ValueError("snapshot generated_at must be an RFC 3339 date-time")
    try:
        generated = datetime.fromisoformat(snapshot["generated_at"])
    except ValueError as exc:
        raise ValueError("snapshot generated_at is invalid") from exc
    if generated.tzinfo is None:
        raise ValueError("snapshot generated_at must include a timezone")
    if not isinstance(snapshot["month"], str) or not re.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])", snapshot["month"]
    ):
        raise ValueError("snapshot month is invalid")
    cutoff = (
        None
        if snapshot["data_cutoff"] is None
        else _parse_date(snapshot["data_cutoff"], "snapshot data_cutoff")
    )
    if cutoff is not None and cutoff.strftime("%Y-%m") != snapshot["month"]:
        raise ValueError("snapshot data_cutoff must be within snapshot month")
    if not isinstance(snapshot["no_month_data"], bool):
        raise ValueError("snapshot no_month_data must be a boolean")
    if snapshot["no_month_data"] != (cutoff is None):
        raise ValueError("snapshot no_month_data does not match data_cutoff")
    if snapshot["roster_source"] not in ROSTER_SOURCES:
        raise ValueError("snapshot roster_source is invalid")
    for field in ("source_lag_warning", "usage_interpretation"):
        if not isinstance(snapshot[field], str) or not snapshot[field]:
            raise ValueError(f"snapshot {field} must be a non-empty string")

    summary = _require_fields(
        snapshot["summary"], set(SUMMARY_FIELDS), set(SUMMARY_FIELDS), "snapshot summary"
    )
    collection = _require_fields(
        snapshot["collection"],
        set(COLLECTION_FIELDS),
        set(COLLECTION_FIELDS),
        "snapshot collection",
    )
    if not isinstance(snapshot["users"], list):
        raise ValueError("snapshot users must be an array")
    for field in ("users", *STATUS_ORDER, "unknown_cost_users"):
        _require_number(summary[field], f"snapshot summary {field}", integer=True)
    for field in ("total_credits", "known_monthly_cost_usd"):
        _require_number(summary[field], f"snapshot summary {field}")
    for field in COLLECTION_FIELDS:
        _require_number(collection[field], f"snapshot collection {field}", integer=True)

    identifiers: set[str] = set()
    status_counts = {status: 0 for status in STATUS_ORDER}
    total_credits = Decimal(0)
    known_cost = Decimal(0)
    unknown_cost_users = 0
    for index, raw_user in enumerate(snapshot["users"]):
        label = f"snapshot user {index}"
        user = _require_fields(raw_user, set(USER_FIELDS), set(USER_FIELDS), label)
        user_id = user["user_id"]
        if not isinstance(user_id, str) or not user_id or user_id in identifiers:
            raise ValueError("snapshot user_id is invalid or duplicated")
        identifiers.add(user_id)
        for field in (
            "user_name",
            "email",
            "tier",
            "first_active",
            "last_active",
            "status",
            "tier_source",
        ):
            if not isinstance(user[field], str):
                raise ValueError(f"{label} {field} must be a string")
        if user["tier"] not in TIERS:
            raise ValueError(f"{label} tier is invalid")
        if user["status"] not in STATUS_ORDER:
            raise ValueError(f"{label} status is invalid")
        if user["tier_source"] not in TIER_SOURCES:
            raise ValueError(f"{label} tier_source is invalid")
        for field in ("credits", "overage"):
            _require_number(user[field], f"{label} {field}")
        for field in ("capacity", "active_days"):
            _require_number(user[field], f"{label} {field}", integer=True)
        for field in ("usage_percent", "monthly_cost_usd"):
            if user[field] is not None:
                _require_number(user[field], f"{label} {field}")

        first_active = _parse_date(user["first_active"], f"{label} first_active", optional=True)
        last_active = _parse_date(user["last_active"], f"{label} last_active", optional=True)
        if (first_active is None) != (last_active is None):
            raise ValueError(f"{label} activity dates must both be set or empty")
        if user["active_days"] == 0 and first_active is not None:
            raise ValueError(f"{label} activity dates must be empty when active_days is zero")
        if user["active_days"] > 0 and first_active is None:
            raise ValueError(f"{label} activity dates are required when active_days is positive")
        if _decimal(user["credits"]) > 0 and user["active_days"] == 0:
            raise ValueError(f"{label} positive credits require activity metadata")
        if first_active is not None:
            if last_active is None:
                raise ValueError(f"{label} activity dates must both be set or empty")
            if first_active > last_active:
                raise ValueError(f"{label} activity date range is invalid")
            if user["active_days"] > (last_active - first_active).days + 1:
                raise ValueError(f"{label} active_days exceeds the activity date range")
            if first_active.strftime("%Y-%m") != snapshot["month"]:
                raise ValueError(f"{label} activity dates must be within snapshot month")
            if cutoff is None or last_active > cutoff:
                raise ValueError(f"{label} activity dates exceed data_cutoff")

        tier = cast(dict[str, Any], TIERS[cast(str, user["tier"])])
        if user["capacity"] != tier["capacity"] or user["monthly_cost_usd"] != tier["price"]:
            raise ValueError(f"{label} tier capacity or cost is inconsistent")
        usage_credits = _decimal(user["credits"])
        expected_percent = (
            round(float(usage_credits / Decimal(user["capacity"]) * 100), 2)
            if user["capacity"]
            else None
        )
        if expected_percent is None:
            if user["usage_percent"] is not None:
                raise ValueError(f"{label} usage_percent must be null for unknown capacity")
        elif not _same_number(user["usage_percent"], expected_percent):
            raise ValueError(f"{label} usage_percent is inconsistent")
        expected_status = status_for(usage_credits, user["capacity"])
        if user["status"] != expected_status:
            raise ValueError(f"{label} status is inconsistent")

        status = cast(str, user["status"])
        status_counts[status] += 1
        total_credits += usage_credits
        if user["monthly_cost_usd"] is None:
            unknown_cost_users += 1
        else:
            known_cost += _decimal(user["monthly_cost_usd"])

    if summary["users"] != len(snapshot["users"]):
        raise ValueError("snapshot summary user count does not match users")
    for status, expected in status_counts.items():
        if summary[status] != expected:
            raise ValueError(f"snapshot summary {status} count does not match users")
    if not _same_number(summary["total_credits"], total_credits):
        raise ValueError("snapshot summary total_credits does not match users")
    if not _same_number(summary["known_monthly_cost_usd"], known_cost):
        raise ValueError("snapshot summary known_monthly_cost_usd does not match users")
    if summary["unknown_cost_users"] != unknown_cost_users:
        raise ValueError("snapshot summary unknown_cost_users does not match users")

    if "content_hash" in snapshot:
        if not isinstance(snapshot["content_hash"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", snapshot["content_hash"]
        ):
            raise ValueError("snapshot content_hash is invalid")
        if snapshot["content_hash"] != snapshot_fingerprint(snapshot):
            raise ValueError("snapshot content_hash does not match content")
    return cast(dict[str, Any], snapshot)


STATE_FIELDS = {
    "schema_version",
    "status",
    "refresh_started_at",
    "last_checked_at",
    "last_success_at",
    "last_error",
    "consecutive_failures",
    "next_retry_at",
    "current_content_hash",
    "history_written",
    "history_path",
    "retry_attempt",
    "retry_delay_seconds",
    "last_migrated_at",
    "legacy_source_hash",
}
MANIFEST_ENTRY_FIELDS = {
    "generated_at",
    "month",
    "data_cutoff",
    "content_hash",
    "path",
    "summary",
    "legacy",
}


def _invalid_state() -> dict[str, Any]:
    """Return the safe state exposed when state.json is malformed."""
    return {"status": "error", "last_error": {"code": "InvalidStateFile"}}


def _valid_state(state: Any) -> bool:
    """Check the persisted state envelope without imposing snapshot validation."""
    if not isinstance(state, dict) or set(state) - STATE_FIELDS:
        return False
    if "schema_version" in state and state["schema_version"] != 1:
        return False
    if "status" in state and state["status"] not in {"refreshing", "healthy", "error"}:
        return False
    for field in (
        "refresh_started_at",
        "last_checked_at",
        "last_success_at",
        "next_retry_at",
        "current_content_hash",
        "history_path",
        "last_migrated_at",
    ):
        if field in state and state[field] is not None and not isinstance(state[field], str):
            return False
    if "consecutive_failures" in state and (
        isinstance(state["consecutive_failures"], bool)
        or not isinstance(state["consecutive_failures"], int)
        or state["consecutive_failures"] < 0
    ):
        return False
    if "retry_attempt" in state and (
        isinstance(state["retry_attempt"], bool) or not isinstance(state["retry_attempt"], int)
    ):
        return False
    if "retry_delay_seconds" in state and (
        isinstance(state["retry_delay_seconds"], bool)
        or not isinstance(state["retry_delay_seconds"], (int, float))
    ):
        return False
    if "history_written" in state and not isinstance(state["history_written"], bool):
        return False
    if "legacy_source_hash" in state and (
        not isinstance(state["legacy_source_hash"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", state["legacy_source_hash"])
    ):
        return False
    error = state.get("last_error")
    return error is None or (
        isinstance(error, dict)
        and set(error) <= {"type", "code", "message"}
        and all(isinstance(value, str) for value in error.values())
    )


def _valid_manifest(manifest: Any) -> bool:
    """Check that manifest metadata can safely drive history lookups."""
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "entries"}:
        return False
    if manifest["schema_version"] != 1 or not isinstance(manifest["entries"], list):
        return False
    for entry in manifest["entries"]:
        if not isinstance(entry, dict) or set(entry) - MANIFEST_ENTRY_FIELDS:
            return False
        if not isinstance(entry.get("generated_at"), str) or not isinstance(entry.get("path"), str):
            return False
        if not re.fullmatch(r"\d{4}/\d{2}/[^/]+\.json", entry["path"]):
            return False
        if not isinstance(entry.get("summary"), dict):
            return False
        if entry.get("month") is not None and not isinstance(entry["month"], str):
            return False
        if entry.get("data_cutoff") is not None and not isinstance(entry["data_cutoff"], str):
            return False
        if not isinstance(entry.get("content_hash"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["content_hash"]
        ):
            return False
        if "legacy" in entry and not isinstance(entry["legacy"], bool):
            return False
    return True


class SnapshotStore:
    """Persist validated snapshots, state, and manifest-backed history atomically."""

    def __init__(self, data_dir: Path) -> None:
        """Bind the store to a local data directory without modifying it."""
        self.data_dir = Path(data_dir)
        self.current_path = self.data_dir / "current.json"
        self.state_path = self.data_dir / "state.json"
        self.manifest_path = self.data_dir / "history" / "manifest.json"
        self.lock_path = self.data_dir / ".refresh.lock"
        self._last_valid_current: dict[str, Any] | None = None

    def ensure(self) -> None:
        """Create the directory that stores historical snapshots."""
        (self.data_dir / "history").mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def refresh_lock(self) -> Iterator[None]:
        """Acquire the non-blocking lock that excludes concurrent refreshes."""
        self.ensure()
        with self.lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RefreshAlreadyRunning("a refresh is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _manifest_history_path(self, relative: Any) -> Path:
        if not isinstance(relative, str) or not re.fullmatch(r"\d{4}/\d{2}/[^/]+\.json", relative):
            raise ValueError("invalid history path")
        return self.data_dir / "history" / relative

    def _load_manifest(self) -> dict[str, Any]:
        """Load only a structurally valid manifest, otherwise use an empty one."""
        try:
            manifest = read_json(self.manifest_path, {"schema_version": 1, "entries": []})
        except (OSError, TypeError, json.JSONDecodeError):
            return {"schema_version": 1, "entries": []}
        return manifest if _valid_manifest(manifest) else {"schema_version": 1, "entries": []}

    def _history_candidates(self) -> Iterator[Path]:
        """Yield on-disk history candidates newest first, independent of the manifest."""
        history_root = self.data_dir / "history"
        yield from reversed(sorted(history_root.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json")))

    def load_current(self) -> dict[str, Any] | None:
        """Return the validated current snapshot or a validated historical fallback."""
        try:
            current = read_json(self.current_path)
            if current is not None:
                self._last_valid_current = validate_snapshot(current)
                return self._last_valid_current
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        if self._last_valid_current is not None:
            return self._last_valid_current
        seen: set[Path] = set()
        for entry in self.list_history():
            try:
                candidate_path = self._manifest_history_path(entry["path"])
                seen.add(candidate_path)
                candidate = read_json(candidate_path)
                if candidate is not None:
                    self._last_valid_current = validate_snapshot(candidate)
                    return self._last_valid_current
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        for candidate_path in self._history_candidates():
            if candidate_path in seen:
                continue
            try:
                candidate = read_json(candidate_path)
                if candidate is not None:
                    self._last_valid_current = validate_snapshot(candidate)
                    return self._last_valid_current
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return None

    def load_state(self) -> dict[str, Any]:
        """Return structurally valid state or a safe error state for malformed input."""
        try:
            state = read_json(self.state_path, {})
        except (OSError, TypeError, json.JSONDecodeError):
            return _invalid_state()
        return state if _valid_state(state) else _invalid_state()

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        """Persist state while the caller holds refresh_lock."""
        atomic_write_json(self.state_path, state)

    def save_state_locked(self, state: dict[str, Any]) -> None:
        """Persist state when the caller already owns ``refresh_lock``."""
        self._save_state_unlocked(state)

    def save_state(self, state: dict[str, Any]) -> None:
        """Persist state under the shared process lock."""
        with self.refresh_lock():
            self._save_state_unlocked(state)

    def list_history(self) -> list[dict[str, Any]]:
        """Return newest-first entries from a structurally valid manifest."""
        return list(reversed(self._load_manifest()["entries"]))

    @staticmethod
    def _history_entry(snapshot: dict[str, Any], relative: Path) -> dict[str, Any]:
        return {
            "generated_at": snapshot["generated_at"],
            "month": snapshot["month"],
            "data_cutoff": snapshot["data_cutoff"],
            "content_hash": snapshot.get("content_hash") or snapshot_fingerprint(snapshot),
            "path": relative.as_posix(),
            "summary": snapshot["summary"],
        }

    def _history_relative(self, snapshot: dict[str, Any]) -> Path:
        generated = datetime.fromisoformat(snapshot["generated_at"])
        fingerprint = snapshot.get("content_hash") or snapshot_fingerprint(snapshot)
        suffix = generated.strftime("%Y-%m-%dT%H-%M-%S%z")
        return Path(generated.strftime("%Y/%m")) / f"{suffix}-{fingerprint[:8]}.json"

    def _write_history_if_missing(self, snapshot: dict[str, Any]) -> Path:
        relative = self._history_relative(snapshot)
        path = self.data_dir / "history" / relative
        if path.exists():
            existing = validate_snapshot(read_json(path))
            if snapshot_fingerprint(existing) != snapshot_fingerprint(snapshot):
                raise ValueError("history path collision")
        else:
            atomic_write_json(path, snapshot)
        return relative

    @staticmethod
    def _legacy_history_entry(snapshot: Any, relative: Path) -> dict[str, Any] | None:
        if not isinstance(snapshot, dict):
            return None
        generated_at = snapshot.get("generated_at")
        summary = snapshot.get("summary")
        if not isinstance(generated_at, str) or not isinstance(summary, dict):
            return None
        fingerprint = snapshot.get("content_hash")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            fingerprint = hashlib.sha256(_json_bytes(snapshot)).hexdigest()
        return {
            "generated_at": generated_at,
            "month": snapshot.get("month"),
            "data_cutoff": snapshot.get("data_cutoff"),
            "content_hash": fingerprint,
            "path": relative.as_posix(),
            "summary": summary,
            "legacy": True,
        }

    def reconcile(self) -> dict[str, int]:
        """Rebuild manifest metadata while excluding concurrent publishers."""
        with self.refresh_lock():
            return self._reconcile_unlocked()

    def _reconcile_unlocked(self) -> dict[str, int]:
        """Rebuild the manifest while retaining parseable legacy history metadata."""
        self.ensure()
        records: list[tuple[Path, dict[str, Any]]] = []
        history_root = self.data_dir / "history"
        for path in sorted(history_root.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json")):
            try:
                raw = read_json(path)
            except (OSError, TypeError, json.JSONDecodeError):
                continue
            relative = path.relative_to(history_root)
            entry: dict[str, Any] | None
            try:
                snapshot = validate_snapshot(raw)
                entry = self._history_entry(snapshot, relative)
            except (ValueError, TypeError):
                entry = self._legacy_history_entry(raw, relative)
            if entry is not None:
                records.append((path, entry))
        current: dict[str, Any] | None = None
        with contextlib.suppress(OSError, ValueError, TypeError, json.JSONDecodeError):
            current = validate_snapshot(read_json(self.current_path))
        if current is not None:
            expected_relative = self._history_relative(current)
            expected_path = history_root / expected_relative
            if all(path != expected_path for path, _ in records):
                relative = self._write_history_if_missing(current)
                records.append((history_root / relative, self._history_entry(current, relative)))
        records.sort(key=lambda item: str(item[1].get("generated_at", "")))
        entries = [entry for _, entry in records]
        existing = list(reversed(self.list_history()))
        if entries != existing:
            atomic_write_json(self.manifest_path, {"schema_version": 1, "entries": entries})
        return {
            "valid_history_entries": sum(not entry.get("legacy", False) for entry in entries),
            "legacy_history_entries": sum(bool(entry.get("legacy")) for entry in entries),
        }

    def publish(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Validate and atomically publish a snapshot under the shared process lock."""
        with self.refresh_lock():
            return self._publish_unlocked(snapshot)

    def publish_locked(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Publish a snapshot when the caller already owns ``refresh_lock``."""
        return self._publish_unlocked(snapshot)

    def _publish_unlocked(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Publish a validated snapshot while the caller holds refresh_lock."""
        self.ensure()
        validate_snapshot(snapshot)
        fingerprint = snapshot_fingerprint(snapshot)
        snapshot = {**snapshot, "content_hash": fingerprint}
        validate_snapshot(snapshot)
        current = self.load_current()
        manifest = self._load_manifest()
        entries = list(manifest["entries"])
        generated = datetime.fromisoformat(snapshot["generated_at"])
        day = generated.strftime("%Y-%m-%d")
        last_entry = entries[-1] if entries else None
        content_changed = not current or snapshot_fingerprint(current) != fingerprint
        daily_missing = not last_entry or not str(last_entry.get("generated_at", "")).startswith(
            day
        )
        history_written = content_changed or daily_missing
        history_path = None
        if history_written:
            relative = self._write_history_if_missing(snapshot)
            history_path = self.data_dir / "history" / relative
            entries.append(self._history_entry(snapshot, relative))
            atomic_write_json(self.manifest_path, {"schema_version": 1, "entries": entries})
        atomic_write_json(self.current_path, snapshot)
        self._last_valid_current = snapshot
        return {
            "content_hash": fingerprint,
            "content_changed": content_changed,
            "history_written": history_written,
            "history_path": str(history_path) if history_path else None,
        }
