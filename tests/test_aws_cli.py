"""AWS CLI adapter tests."""

import os
import subprocess
import unittest
from unittest.mock import patch

from app.aws_cli import AwsCli, AwsCliError


class AwsCliTests(unittest.TestCase):
    """Verify bounded AWS CLI behavior and redacted failures."""

    def test_redacts_stderr_and_bounds_subprocess(self) -> None:
        """Redact command errors while using a bounded shell-free subprocess."""
        aws = AwsCli("profile", "us-east-1", timeout=7)
        failed = subprocess.CompletedProcess(
            args=["aws"],
            returncode=1,
            stdout="",
            stderr="An error occurred (AccessDeniedException): alice@example.com denied",
        )
        with (
            patch("app.aws_cli.subprocess.run", return_value=failed) as run,
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.json("identitystore", "list-users")
        self.assertEqual("AccessDeniedException", caught.exception.code)
        self.assertNotIn("alice@example.com", str(caught.exception))
        self.assertEqual(7, run.call_args.kwargs["timeout"])
        self.assertFalse(run.call_args.kwargs["shell"])

        with (
            patch("app.aws_cli.subprocess.run", side_effect=subprocess.TimeoutExpired(["aws"], 7)),
            self.assertRaisesRegex(AwsCliError, "ClientTimeout"),
        ):
            aws.s3_bytes("bucket", "key")

    def test_child_environment_excludes_admin_token_and_keeps_aws_settings(self) -> None:
        """Pass AWS settings but never the dashboard token to either child process."""
        aws = AwsCli("", "us-east-1")
        completed_json = subprocess.CompletedProcess(
            args=["aws"], returncode=0, stdout="{}", stderr=""
        )
        downloaded = subprocess.CompletedProcess(
            args=["aws"], returncode=0, stdout=b"a", stderr=b""
        )
        with (
            patch.dict(
                os.environ,
                {
                    "AWS_CONFIG_FILE": "/private/aws-config",
                    "KIRO_REFRESH_ADMIN_TOKEN": "a-secure-refresh-token",
                },
                clear=True,
            ),
            patch("app.aws_cli.subprocess.run", return_value=completed_json) as run,
        ):
            self.assertEqual({}, aws.json("sts", "get-caller-identity"))
            child_env = run.call_args.kwargs["env"]
            self.assertEqual("/private/aws-config", child_env["AWS_CONFIG_FILE"])
            self.assertNotIn("KIRO_REFRESH_ADMIN_TOKEN", child_env)

        with (
            patch.dict(
                os.environ,
                {
                    "AWS_CONFIG_FILE": "/private/aws-config",
                    "KIRO_REFRESH_ADMIN_TOKEN": "a-secure-refresh-token",
                },
                clear=True,
            ),
            patch.object(aws, "json", return_value={"ContentLength": 1}),
            patch("app.aws_cli.subprocess.run", return_value=downloaded) as run,
        ):
            self.assertEqual(b"a", aws.s3_bytes("bucket", "key"))
            child_env = run.call_args.kwargs["env"]
            self.assertEqual("/private/aws-config", child_env["AWS_CONFIG_FILE"])
            self.assertNotIn("KIRO_REFRESH_ADMIN_TOKEN", child_env)

    def test_json_and_s3_convert_os_errors_to_redacted_client_error(self) -> None:
        """Map local process errors to stable redacted client errors."""
        aws = AwsCli("", "us-east-1")
        with (
            patch("app.aws_cli.subprocess.run", side_effect=FileNotFoundError),
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.json("sts", "get-caller-identity")
        self.assertEqual("ClientUnavailable", caught.exception.code)

        with (
            patch.object(aws, "json", return_value={"ContentLength": 1}),
            patch("app.aws_cli.subprocess.run", side_effect=OSError),
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.s3_bytes("bucket", "key")
        self.assertEqual("ClientUnavailable", caught.exception.code)

    def test_s3_requires_valid_head_size_and_checks_download_size(self) -> None:
        """Reject malformed object metadata and oversized downloaded objects."""
        aws = AwsCli("", "us-east-1", max_s3_object_bytes=2)
        with (
            patch.object(aws, "json", return_value={}),
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.s3_bytes("bucket", "key")
        self.assertEqual("InvalidObjectSize", caught.exception.code)

        download = subprocess.CompletedProcess(
            args=["aws"], returncode=0, stdout=b"abc", stderr=b""
        )
        with (
            patch.object(aws, "json", return_value={"ContentLength": 2}),
            patch("app.aws_cli.subprocess.run", return_value=download),
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.s3_bytes("bucket", "key")
        self.assertEqual("ObjectTooLarge", caught.exception.code)

    def test_paginated_json_reads_all_pages_and_sends_next_token(self) -> None:
        """Read every JSON page and send the next token to later calls."""
        aws = AwsCli("", "us-east-1")
        with patch.object(
            aws,
            "json",
            side_effect=[
                {"Users": [{"UserId": "first"}], "NextToken": "page-two"},
                {"Users": [{"UserId": "second"}]},
            ],
        ) as json_call:
            users = aws.paginated_json(
                "identitystore", "list-users", "Users", "--identity-store-id", "store"
            )
        self.assertEqual([{"UserId": "first"}, {"UserId": "second"}], users)
        self.assertIn("--no-paginate", json_call.call_args_list[0].args)
        self.assertIn("--next-token", json_call.call_args_list[1].args)
        self.assertIn("page-two", json_call.call_args_list[1].args)

    def test_paginated_json_rejects_token_loops_and_page_limit(self) -> None:
        """Reject repeated pagination tokens and excess JSON pages."""
        aws = AwsCli("", "us-east-1")
        with (
            patch.object(aws, "json", side_effect=[{"Users": [], "NextToken": "repeat"}] * 2),
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.paginated_json("identitystore", "list-users", "Users")
        self.assertEqual("PaginationTokenLoopDetected", caught.exception.code)

        aws = AwsCli("", "us-east-1", max_json_pages=1)
        with (
            patch.object(
                aws, "json", return_value={"Users": [], "NextToken": "page-two"}
            ) as json_call,
            self.assertRaises(AwsCliError) as caught,
        ):
            aws.paginated_json("identitystore", "list-users", "Users")
        self.assertEqual("PageLimitExceeded", caught.exception.code)
        self.assertEqual(1, json_call.call_count)

    def test_athena_rejects_missing_or_excessive_workgroup_scan_cutoff(self) -> None:
        """Reject missing, invalid, and excessive Athena WorkGroup scan cutoffs."""
        cases = [
            ({"WorkGroup": {"Configuration": {}}}, "WorkGroupScanCutoffMissing"),
            (
                {"WorkGroup": {"Configuration": {"BytesScannedCutoffPerQuery": 0}}},
                "WorkGroupScanCutoffInvalid",
            ),
            (
                {"WorkGroup": {"Configuration": {"BytesScannedCutoffPerQuery": 101}}},
                "WorkGroupScanCutoffTooHigh",
            ),
        ]
        for response, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                aws = AwsCli("", "us-east-1", max_query_scan_bytes=100)
                with (
                    patch.object(aws, "json", return_value=response) as json_call,
                    self.assertRaises(AwsCliError) as caught,
                ):
                    aws.athena_query("SELECT", "wg")
                self.assertEqual(expected_code, caught.exception.code)
                self.assertEqual(
                    ("athena", "get-work-group", "--work-group", "wg"), json_call.call_args.args
                )

    def test_athena_validates_workgroup_once_before_multiple_queries(self) -> None:
        """Validate a WorkGroup only once when issuing multiple queries."""
        aws = AwsCli("", "us-east-1")
        with patch.object(
            aws,
            "json",
            side_effect=[
                {"WorkGroup": {"Configuration": {"BytesScannedCutoffPerQuery": 100}}},
                {"QueryExecutionId": "qid-one"},
                {"QueryExecution": {"Status": {"State": "SUCCEEDED"}, "Statistics": {}}},
                {"ResultSet": {"Rows": []}},
                {"QueryExecutionId": "qid-two"},
                {"QueryExecution": {"Status": {"State": "SUCCEEDED"}, "Statistics": {}}},
                {"ResultSet": {"Rows": []}},
            ],
        ) as json_call:
            aws.athena_query("SELECT 1", "wg")
            aws.athena_query("SELECT 2", "wg")
        workgroup_calls = [
            call
            for call in json_call.call_args_list
            if call.args[:2] == ("athena", "get-work-group")
        ]
        self.assertEqual(1, len(workgroup_calls))

    def test_athena_polling_pagination_and_statistics(self) -> None:
        """Poll Athena, read every result page, and preserve statistics."""
        aws = AwsCli("", "us-east-1")
        with (
            patch.object(
                aws,
                "json",
                side_effect=[
                    {"WorkGroup": {"Configuration": {"BytesScannedCutoffPerQuery": 1000}}},
                    {"QueryExecutionId": "qid"},
                    {"QueryExecution": {"Status": {"State": "RUNNING"}}},
                    {
                        "QueryExecution": {
                            "Status": {"State": "SUCCEEDED"},
                            "Statistics": {
                                "DataScannedInBytes": 1000,
                                "EngineExecutionTimeInMillis": 20,
                                "TotalExecutionTimeInMillis": 30,
                            },
                        }
                    },
                    {
                        "ResultSet": {
                            "Rows": [
                                {"Data": [{"VarCharValue": "id"}, {"VarCharValue": "value"}]},
                                {"Data": [{"VarCharValue": "u1"}, {"VarCharValue": "5"}]},
                            ]
                        },
                        "NextToken": "next",
                    },
                    {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "u2"}]}]}},
                ],
            ) as json_call,
            patch("app.aws_cli.time.sleep") as sleep,
        ):
            result = aws.athena_query("SELECT", "wg", sleep=sleep)
        self.assertEqual([{"id": "u1", "value": "5"}, {"id": "u2", "value": ""}], result.rows)
        self.assertEqual(1000, result.data_scanned_bytes)
        self.assertEqual(20, result.engine_execution_ms)
        self.assertEqual(30, result.total_execution_ms)
        sleep.assert_called_once_with(1)
        self.assertIn("--next-token", json_call.call_args_list[-1].args)
        self.assertIn("--no-paginate", json_call.call_args_list[-1].args)

    def test_athena_failure_does_not_expose_state_reason(self) -> None:
        """Include a query identifier but redact the failed query state reason."""
        aws = AwsCli("", "us-east-1")
        with (
            patch.object(
                aws,
                "json",
                side_effect=[
                    {"WorkGroup": {"Configuration": {"BytesScannedCutoffPerQuery": 1000}}},
                    {"QueryExecutionId": "qid-redacted"},
                    {
                        "QueryExecution": {
                            "Status": {
                                "State": "FAILED",
                                "StateChangeReason": "alice@example.com in s3://private",
                            }
                        }
                    },
                ],
            ),
            self.assertRaises(RuntimeError) as caught,
        ):
            aws.athena_query("SELECT", "wg")
        self.assertIn("qid-redacted", str(caught.exception))
        self.assertNotIn("alice@example.com", str(caught.exception))
        self.assertNotIn("s3://private", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
