"""Configuration parsing tests."""

import tempfile
import unittest
from pathlib import Path

from app.config import load_config

VALID = """
[server]
host = "127.0.0.1"
port = 8080
stale_after_hours = 30
manual_refresh_cooldown_seconds = 300
[storage]
data_dir = "data"
[aws]
profile = "test"
region = "us-east-1"
account_id = "123456789012"
data_bucket = "bucket"
database = "kiro_analytics"
workgroup = "wg"
identity_store_id = "d-store"
application_arn = "arn:app"
subscription_csv_key = ""
identity_mapping_key = "mapping.csv"
[refresh]
daily_time = "10:00"
retry_delays_seconds = [60, 300, 900, 1800]
jitter_ratio = 0.2
"""


class ConfigTests(unittest.TestCase):
    """Verify configuration validation and path resolution."""

    def write(self, directory: str | Path, text: str = VALID) -> Path:
        """Write a configuration fixture and return its path."""
        path = Path(directory) / "config.local.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_example_config_uses_loopback_host(self) -> None:
        """Keep the documented sample aligned with the loopback server default."""
        example = (Path(__file__).parent.parent / "config.example.toml").read_text(encoding="utf-8")
        self.assertIn('host = "127.0.0.1"', example)

    def test_loads_valid_portable_config_and_relative_paths(self) -> None:
        """Load a valid configuration and resolve its relative paths."""
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(self.write(directory))
            self.assertEqual("127.0.0.1", config.server.host)
            self.assertEqual(8080, config.server.port)
            self.assertEqual("10:00", config.refresh.daily_time)
            self.assertEqual((60, 300, 900, 1800), config.refresh.retry_delays_seconds)
            self.assertEqual((Path(directory) / "data").resolve(), config.data_dir)
            self.assertEqual((Path(directory) / "web").resolve(), config.web_dir)
            self.assertEqual("test", config.aws.profile)

    def test_rejects_bad_database_time_port_and_missing_roster_source(self) -> None:
        """Reject invalid database, time, port, and roster settings."""
        cases = [
            (VALID.replace("kiro_analytics", "db; DROP"), "Athena identifier"),
            (VALID.replace('daily_time = "10:00"', 'daily_time = "25:00"'), "HH:MM"),
            (VALID.replace("port = 8080", "port = 70000"), "host and server.port"),
            (
                VALID.replace('application_arn = "arn:app"', 'application_arn = ""'),
                "application_arn",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for text, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    load_config(self.write(directory, text))

    def test_rejects_non_table_sections_without_attribute_errors(self) -> None:
        """Reject scalars where each required top-level TOML table belongs."""
        with tempfile.TemporaryDirectory() as directory:
            for section in ("aws", "server", "storage", "refresh"):
                with self.subTest(section=section):
                    text = VALID.replace(f"[{section}]", f'{section} = "not-a-table"')
                    with self.assertRaisesRegex(ValueError, f"{section} must be a TOML table"):
                        load_config(self.write(directory, text))

    def test_rejects_implicit_boolean_and_numeric_coercions(self) -> None:
        """Reject booleans and non-string account IDs at configuration boundaries."""
        cases = [
            (
                VALID.replace('account_id = "123456789012"', "account_id = 123456789012"),
                "account_id",
            ),
            (VALID.replace('account_id = "123456789012"', "account_id = true"), "account_id"),
            (VALID.replace("port = 8080", "port = true"), "server.port must be an integer"),
            (
                VALID.replace("stale_after_hours = 30", "stale_after_hours = true"),
                "server.stale_after_hours must be an integer",
            ),
            (
                VALID.replace(
                    "manual_refresh_cooldown_seconds = 300",
                    "manual_refresh_cooldown_seconds = true",
                ),
                "server.manual_refresh_cooldown_seconds must be an integer",
            ),
            (
                VALID.replace(
                    "retry_delays_seconds = [60, 300, 900, 1800]", "retry_delays_seconds = [true]"
                ),
                "refresh.retry_delays_seconds must be an array of integers",
            ),
            (
                VALID.replace("jitter_ratio = 0.2", "jitter_ratio = true"),
                "refresh.jitter_ratio must be a number",
            ),
            (
                VALID.replace(
                    'identity_mapping_key = "mapping.csv"', "max_query_scan_bytes = true"
                ),
                "aws.max_query_scan_bytes must be an integer",
            ),
            (
                VALID.replace('identity_mapping_key = "mapping.csv"', "max_s3_object_bytes = true"),
                "aws.max_s3_object_bytes must be an integer",
            ),
            (
                VALID.replace('identity_mapping_key = "mapping.csv"', "max_athena_rows = true"),
                "aws.max_athena_rows must be an integer",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for text, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    load_config(self.write(directory, text))

    def test_rejects_non_positive_aws_limits(self) -> None:
        """Keep AWS resource limits positive after enforcing their TOML integer type."""
        with tempfile.TemporaryDirectory() as directory:
            for key in ("max_query_scan_bytes", "max_s3_object_bytes", "max_athena_rows"):
                with self.subTest(key=key):
                    text = VALID.replace('identity_mapping_key = "mapping.csv"', f"{key} = 0")
                    with self.assertRaisesRegex(ValueError, "limits must be positive"):
                        load_config(self.write(directory, text))


if __name__ == "__main__":
    unittest.main()
