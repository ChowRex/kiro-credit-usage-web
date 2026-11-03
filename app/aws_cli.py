"""Bounded, redacted AWS CLI adapter and Athena result reader."""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404: commands below are bounded argument lists with shell disabled.
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypeAlias, cast

ERROR_CODE = re.compile(r"\(([A-Za-z0-9][A-Za-z0-9._-]+)\)")
NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound", "ResourceNotFoundException"}
ACCESS_DENIED_CODES = {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}
INITIAL_PAGE_TOKEN: Final = ""

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


def _child_environment() -> dict[str, str]:
    """Build the AWS CLI child environment without the dashboard admin token."""
    environment = dict(os.environ)
    environment.pop("KIRO_REFRESH_ADMIN_TOKEN", None)
    return environment


class AwsCliError(RuntimeError):
    """Raised when a bounded AWS CLI operation cannot complete safely."""

    def __init__(self, operation: str, code: str = "UnknownError"):
        """Create a redacted error identified by operation and stable code."""
        self.operation = operation
        self.code = code
        super().__init__(f"AWS CLI {operation} failed ({code})")


@dataclass(frozen=True)
class AthenaResult:
    """The bounded rows and execution statistics for an Athena query."""

    rows: list[dict[str, str]]
    query_id: str
    data_scanned_bytes: int
    engine_execution_ms: int
    total_execution_ms: int


class AwsCli:
    """Run AWS CLI commands without a shell and enforce collector safety limits."""

    def __init__(
        self,
        profile: str,
        region: str,
        executable: str = "aws",
        timeout: int = 60,
        max_s3_object_bytes: int = 5 * 1024 * 1024,
        max_query_scan_bytes: int = 100 * 1024 * 1024,
        max_athena_rows: int = 100_000,
        max_athena_pages: int = 100,
        max_json_pages: int = 100,
    ) -> None:
        """Configure the AWS CLI executable and bounded read/query limits."""
        self.base = [executable]
        if profile:
            self.base.extend(["--profile", profile])
        if region:
            self.base.extend(["--region", region])
        self.timeout = timeout
        self.max_s3_object_bytes = max_s3_object_bytes
        self.max_query_scan_bytes = max_query_scan_bytes
        self.max_athena_rows = max_athena_rows
        self.max_athena_pages = max_athena_pages
        self.max_json_pages = max_json_pages
        self._validated_workgroups: set[str] = set()

    @staticmethod
    def _error(operation: str, stderr: str) -> AwsCliError:
        """Convert AWS CLI stderr into a stable error without exposing its content."""
        match = ERROR_CODE.search(stderr)
        return AwsCliError(operation, match.group(1) if match else "CommandFailed")

    @staticmethod
    def _object(value: JsonValue | object, operation: str) -> JsonObject:
        """Return a JSON object or reject a response with an unexpected shape."""
        if not isinstance(value, dict):
            raise AwsCliError(operation, "InvalidJsonResponse")
        return cast(JsonObject, value)

    @staticmethod
    def _integer(value: JsonValue, operation: str) -> int:
        """Return an integer JSON value or reject a malformed AWS response."""
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AwsCliError(operation, "InvalidJsonResponse")
        try:
            return int(value)
        except ValueError as exc:
            raise AwsCliError(operation, "InvalidJsonResponse") from exc

    def json(self, service: str, operation: str, *arguments: str) -> JsonObject:
        """Run one AWS CLI JSON operation with a timeout and redacted failures."""
        command = [*self.base, service, operation, *arguments, "--output", "json"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout,
                shell=False,
                env=_child_environment(),
            )  # nosec B603: command is a list of validated AWS parameters and never uses a shell.
        except subprocess.TimeoutExpired as exc:
            raise AwsCliError(f"{service} {operation}", "ClientTimeout") from exc
        except OSError as exc:
            raise AwsCliError(f"{service} {operation}", "ClientUnavailable") from exc
        if result.returncode:
            raise self._error(f"{service} {operation}", result.stderr)
        try:
            decoded: object = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise AwsCliError(f"{service} {operation}", "InvalidJsonResponse") from exc
        return self._object(decoded, f"{service} {operation}")

    def paginated_json(
        self,
        service: str,
        operation: str,
        collection_key: str,
        *arguments: str,
    ) -> list[JsonObject]:
        """Read a bounded AWS JSON collection while detecting repeated NextTokens."""
        operation_name = f"{service} {operation}"
        items: list[JsonObject] = []
        token = INITIAL_PAGE_TOKEN
        seen_tokens: set[str] = set()
        for _ in range(1, self.max_json_pages + 1):
            page_arguments = [*arguments, "--no-paginate"]
            if token:
                page_arguments.extend(["--next-token", token])
            page = self.json(service, operation, *page_arguments)
            raw_items = page.get(collection_key, [])
            if not isinstance(raw_items, list):
                raise AwsCliError(operation_name, "InvalidJsonResponse")
            for item in raw_items:
                items.append(self._object(item, operation_name))
            next_token = page.get("NextToken", "")
            if next_token in (None, ""):
                return items
            if not isinstance(next_token, str):
                raise AwsCliError(operation_name, "InvalidJsonResponse")
            if next_token in seen_tokens:
                raise AwsCliError(operation_name, "PaginationTokenLoopDetected")
            seen_tokens.add(next_token)
            token = next_token
        raise AwsCliError(operation_name, "PageLimitExceeded")

    def _validate_workgroup_scan_cutoff(self, workgroup: str) -> None:
        """Confirm the WorkGroup has a positive scan cutoff within the local limit."""
        if workgroup in self._validated_workgroups:
            return
        response = self.json("athena", "get-work-group", "--work-group", workgroup)
        work_group = response.get("WorkGroup")
        if not isinstance(work_group, dict):
            raise AwsCliError("athena get-work-group", "WorkGroupScanCutoffMissing")
        configuration = work_group.get("Configuration")
        if not isinstance(configuration, dict):
            raise AwsCliError("athena get-work-group", "WorkGroupScanCutoffMissing")
        if "BytesScannedCutoffPerQuery" not in configuration:
            raise AwsCliError("athena get-work-group", "WorkGroupScanCutoffMissing")
        cutoff = configuration["BytesScannedCutoffPerQuery"]
        if isinstance(cutoff, bool) or not isinstance(cutoff, int) or cutoff <= 0:
            raise AwsCliError("athena get-work-group", "WorkGroupScanCutoffInvalid")
        if cutoff > self.max_query_scan_bytes:
            raise AwsCliError("athena get-work-group", "WorkGroupScanCutoffTooHigh")
        self._validated_workgroups.add(workgroup)

    def s3_bytes(self, bucket: str, key: str) -> bytes:
        """Read one S3 object only after HEAD reports an acceptable byte length."""
        metadata = self.json("s3api", "head-object", "--bucket", bucket, "--key", key)
        content_length = metadata.get("ContentLength")
        if (
            isinstance(content_length, bool)
            or not isinstance(content_length, int)
            or content_length < 0
        ):
            raise AwsCliError("s3 read", "InvalidObjectSize")
        if content_length > self.max_s3_object_bytes:
            raise AwsCliError("s3 read", "ObjectTooLarge")
        command = [*self.base, "s3", "cp", f"s3://{bucket}/{key}", "-", "--only-show-errors"]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout,
                shell=False,
                env=_child_environment(),
            )  # nosec B603: command is a list of validated AWS parameters and never uses a shell.
        except subprocess.TimeoutExpired as exc:
            raise AwsCliError("s3 read", "ClientTimeout") from exc
        except OSError as exc:
            raise AwsCliError("s3 read", "ClientUnavailable") from exc
        if result.returncode:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise self._error("s3 read", stderr)
        if len(result.stdout) > self.max_s3_object_bytes:
            raise AwsCliError("s3 read", "ObjectTooLarge")
        return result.stdout

    def athena_query(
        self,
        sql: str,
        workgroup: str,
        timeout_seconds: int = 720,
        sleep: Callable[[float], None] = time.sleep,
    ) -> AthenaResult:
        """Run a bounded Athena query after validating its WorkGroup scan cutoff."""
        self._validate_workgroup_scan_cutoff(workgroup)
        query_id_value = self.json(
            "athena",
            "start-query-execution",
            "--query-string",
            sql,
            "--work-group",
            workgroup,
        ).get("QueryExecutionId")
        if not isinstance(query_id_value, str) or not query_id_value:
            raise AwsCliError("athena start-query-execution", "InvalidJsonResponse")
        query_id = query_id_value
        deadline = time.monotonic() + timeout_seconds
        statistics: JsonObject = {}
        while time.monotonic() < deadline:
            execution = self._object(
                self.json("athena", "get-query-execution", "--query-execution-id", query_id).get(
                    "QueryExecution"
                ),
                "athena get-query-execution",
            )
            status = self._object(execution.get("Status"), "athena get-query-execution")
            state = status.get("State")
            if not isinstance(state, str):
                raise AwsCliError("athena get-query-execution", "InvalidJsonResponse")
            raw_statistics = execution.get("Statistics", {})
            statistics = self._object(raw_statistics, "athena get-query-execution")
            if state == "SUCCEEDED":
                break
            if state in {"FAILED", "CANCELLED"}:
                raise RuntimeError(f"Athena query {state}; inspect query {query_id} for details")
            sleep(1)
        else:
            try:
                self.json("athena", "stop-query-execution", "--query-execution-id", query_id)
            finally:
                raise TimeoutError(f"Athena query timed out after {timeout_seconds}s")

        values: list[list[str]] = []
        token = INITIAL_PAGE_TOKEN
        seen_tokens: set[str] = set()
        for _ in range(self.max_athena_pages):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Athena result retrieval timed out for query {query_id}")
            arguments = [
                "--query-execution-id",
                query_id,
                "--max-results",
                "1000",
                "--no-paginate",
            ]
            if token:
                arguments.extend(["--next-token", token])
            page = self.json("athena", "get-query-results", *arguments)
            result_set = self._object(page.get("ResultSet"), "athena get-query-results")
            raw_rows = result_set.get("Rows", [])
            if not isinstance(raw_rows, list):
                raise AwsCliError("athena get-query-results", "InvalidJsonResponse")
            for raw_row in raw_rows:
                row = self._object(raw_row, "athena get-query-results")
                raw_cells = row.get("Data", [])
                if not isinstance(raw_cells, list):
                    raise AwsCliError("athena get-query-results", "InvalidJsonResponse")
                values.append(
                    [
                        str(self._object(cell, "athena get-query-results").get("VarCharValue", ""))
                        for cell in raw_cells
                    ]
                )
                if len(values) - 1 > self.max_athena_rows:
                    raise AwsCliError("athena get-query-results", "RowLimitExceeded")
            next_token = page.get("NextToken", "")
            if next_token in (None, ""):
                break
            if not isinstance(next_token, str):
                raise AwsCliError("athena get-query-results", "InvalidJsonResponse")
            if next_token in seen_tokens:
                raise AwsCliError("athena get-query-results", "PaginationTokenLoopDetected")
            seen_tokens.add(next_token)
            token = next_token
        else:
            raise AwsCliError("athena get-query-results", "PageLimitExceeded")

        rows: list[dict[str, str]] = []
        if values:
            headers = values[0]
            rows = [
                dict(zip(headers, row + [""] * (len(headers) - len(row)), strict=False))
                for row in values[1:]
            ]
        scanned = self._integer(statistics.get("DataScannedInBytes", 0), "athena query")
        if scanned > self.max_query_scan_bytes:
            raise AwsCliError("athena query", "ScanLimitExceeded")
        return AthenaResult(
            rows=rows,
            query_id=query_id,
            data_scanned_bytes=scanned,
            engine_execution_ms=self._integer(
                statistics.get("EngineExecutionTimeInMillis", 0), "athena query"
            ),
            total_execution_ms=self._integer(
                statistics.get("TotalExecutionTimeInMillis", 0), "athena query"
            ),
        )
