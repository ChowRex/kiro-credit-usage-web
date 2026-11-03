"""Validated TOML configuration for local and portable deployments."""

from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AwsConfig:
    """Validated AWS source settings and bounded collection limits."""

    region: str
    profile: str
    account_id: str
    data_bucket: str
    database: str
    workgroup: str
    identity_store_id: str
    application_arn: str
    subscription_csv_key: str
    identity_mapping_key: str
    max_query_scan_bytes: int = 104857600
    max_s3_object_bytes: int = 5242880
    max_athena_rows: int = 100000


@dataclass(frozen=True)
class ServerConfig:
    """Validated private HTTP server settings."""

    host: str
    port: int
    stale_after_hours: int
    manual_refresh_cooldown_seconds: int
    request_timeout_seconds: int = 15
    max_connections: int = 32


@dataclass(frozen=True)
class RefreshConfig:
    """Validated scheduled refresh and retry settings."""

    daily_time: str
    retry_delays_seconds: tuple[int, ...]
    jitter_ratio: float


@dataclass(frozen=True)
class AppConfig:
    """All validated application settings with resolved local paths."""

    source_path: Path
    data_dir: Path
    web_dir: Path
    aws: AwsConfig
    server: ServerConfig
    refresh: RefreshConfig


def _table(raw: dict[str, object], name: str) -> dict[str, object]:
    """Return a required TOML table or raise a clear configuration error."""
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a TOML table")
    return value


def _string(value: object, qualified: str) -> str:
    """Return a TOML string after trimming it, rejecting implicit conversions."""
    if not isinstance(value, str):
        raise ValueError(f"{qualified} must be a string")
    return value.strip()


def _required(table: dict[str, object], key: str, qualified: str) -> str:
    """Read a non-empty required TOML string from a configuration table."""
    value = _string(table.get(key, ""), qualified)
    if not value:
        raise ValueError(f"missing required configuration: {qualified}")
    return value


def _integer(table: dict[str, object], key: str, qualified: str, default: int) -> int:
    """Read a TOML integer while rejecting booleans and coercible values."""
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{qualified} must be an integer")
    return value


def _integer_list(
    table: dict[str, object], key: str, qualified: str, default: list[int]
) -> tuple[int, ...]:
    """Read a TOML integer array while rejecting booleans and other element types."""
    value = table.get(key, default)
    if not isinstance(value, list):
        raise ValueError(f"{qualified} must be an array of integers")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError(f"{qualified} must be an array of integers")
    return tuple(value)


def _number(table: dict[str, object], key: str, qualified: str, default: float) -> float:
    """Read a finite TOML number while rejecting booleans and strings."""
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{qualified} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{qualified} must be finite")
    return result


def _local_path(value: str, default: str, source: Path) -> Path:
    """Resolve a configured path relative to the configuration file when needed."""
    configured = Path(value or default).expanduser()
    return (
        configured.resolve() if configured.is_absolute() else (source.parent / configured).resolve()
    )


def load_config(path: Path | str) -> AppConfig:
    """Load and validate a TOML configuration file without implicit type coercion."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"configuration file not found: {source}")
    with source.open("rb") as handle:
        raw = tomllib.load(handle)
    aws_raw = _table(raw, "aws")
    server_raw = _table(raw, "server")
    refresh_raw = _table(raw, "refresh")
    storage_raw = _table(raw, "storage")

    account_id = _required(aws_raw, "account_id", "aws.account_id")
    if not re.fullmatch(r"\d{12}", account_id):
        raise ValueError("aws.account_id must be a 12-digit AWS account ID")
    database = _string(aws_raw.get("database", "kiro_analytics"), "aws.database")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise ValueError("aws.database must be a valid Athena identifier")
    subscription_csv_key = _string(
        aws_raw.get("subscription_csv_key", ""), "aws.subscription_csv_key"
    )
    application_arn = _string(aws_raw.get("application_arn", ""), "aws.application_arn")
    if not subscription_csv_key and not application_arn:
        raise ValueError("configure aws.application_arn or aws.subscription_csv_key")

    host = _string(server_raw.get("host", "127.0.0.1"), "server.host")
    port = _integer(server_raw, "port", "server.port", 8080)
    if not host or not 1 <= port <= 65535:
        raise ValueError("server.host and server.port are invalid")
    stale_hours = _integer(server_raw, "stale_after_hours", "server.stale_after_hours", 30)
    cooldown = _integer(
        server_raw,
        "manual_refresh_cooldown_seconds",
        "server.manual_refresh_cooldown_seconds",
        300,
    )
    request_timeout = _integer(
        server_raw, "request_timeout_seconds", "server.request_timeout_seconds", 15
    )
    max_connections = _integer(server_raw, "max_connections", "server.max_connections", 32)
    if stale_hours <= 0 or cooldown < 0 or request_timeout <= 0 or max_connections <= 0:
        raise ValueError("server stale/cooldown/limit values are invalid")

    daily_time = _string(refresh_raw.get("daily_time", "10:00"), "refresh.daily_time")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_time):
        raise ValueError("refresh.daily_time must be HH:MM")
    delays = _integer_list(
        refresh_raw,
        "retry_delays_seconds",
        "refresh.retry_delays_seconds",
        [60, 300, 900, 1800],
    )
    jitter = _number(refresh_raw, "jitter_ratio", "refresh.jitter_ratio", 0.2)
    if any(value < 0 for value in delays) or not 0 <= jitter <= 1:
        raise ValueError("refresh retry delays or jitter ratio are invalid")

    max_query_scan_bytes = _integer(
        aws_raw, "max_query_scan_bytes", "aws.max_query_scan_bytes", 104857600
    )
    max_s3_object_bytes = _integer(
        aws_raw, "max_s3_object_bytes", "aws.max_s3_object_bytes", 5242880
    )
    max_athena_rows = _integer(aws_raw, "max_athena_rows", "aws.max_athena_rows", 100000)
    if min(max_query_scan_bytes, max_s3_object_bytes, max_athena_rows) <= 0:
        raise ValueError("AWS query and object limits must be positive")

    return AppConfig(
        source_path=source,
        data_dir=_local_path(
            _string(storage_raw.get("data_dir", ""), "storage.data_dir"), "data", source
        ),
        web_dir=_local_path(
            _string(server_raw.get("web_dir", ""), "server.web_dir"), "web", source
        ),
        aws=AwsConfig(
            region=_string(aws_raw.get("region", "us-east-1"), "aws.region"),
            profile=_string(
                aws_raw.get("profile", os.environ.get("AWS_PROFILE", "")), "aws.profile"
            ),
            account_id=account_id,
            data_bucket=_required(aws_raw, "data_bucket", "aws.data_bucket"),
            database=database,
            workgroup=_string(
                aws_raw.get("workgroup", "kiro-analytics-workgroup"), "aws.workgroup"
            ),
            identity_store_id=_required(aws_raw, "identity_store_id", "aws.identity_store_id"),
            application_arn=application_arn,
            subscription_csv_key=subscription_csv_key,
            identity_mapping_key=_string(
                aws_raw.get("identity_mapping_key", "user-mapping/user_mapping.csv"),
                "aws.identity_mapping_key",
            ),
            max_query_scan_bytes=max_query_scan_bytes,
            max_s3_object_bytes=max_s3_object_bytes,
            max_athena_rows=max_athena_rows,
        ),
        server=ServerConfig(host, port, stale_hours, cooldown, request_timeout, max_connections),
        refresh=RefreshConfig(daily_time, delays, jitter),
    )
