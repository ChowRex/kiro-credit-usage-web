"""Launchd plist rendering tests."""

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.parsers.expat import ExpatError

from scripts.render_launchd import ROOT, main, render

CONFIG = """
[server]
host = "127.0.0.1"
[storage]
data_dir = "data"
[aws]
account_id = "123456789012"
data_bucket = "bucket"
identity_store_id = "d-store"
application_arn = "arn:app"
[refresh]
daily_time = "23:59"
"""


class LaunchdTests(unittest.TestCase):
    """Verify safe launchd configuration rendering."""

    def template(self) -> str:
        """Load the repository launchd plist template for renderer assertions."""
        return (ROOT / "ops" / "com.kiro.credit-usage.refresh.plist.template").read_text(
            encoding="utf-8"
        )

    def test_renders_schedule_from_daily_time_and_validates_plist(self) -> None:
        """Render parsed plist integer fields from the supplied configuration schedule."""
        body = render(
            self.template(),
            Path("/tmp/project & test"),
            Path("/tmp/config.toml"),
            Path("/usr/bin/python3"),
            "/usr/bin:/bin",
            "08:05",
        )
        parsed = plistlib.loads(body.encode())
        self.assertEqual({"Hour": 8, "Minute": 5}, parsed["StartCalendarInterval"])
        self.assertIn("--retry", parsed["ProgramArguments"])
        self.assertEqual("/usr/bin:/bin", parsed["EnvironmentVariables"]["PATH"])

    def test_allows_double_underscores_in_legal_replacement_values(self) -> None:
        """Do not mistake marker-like text in configured paths for an unresolved marker."""
        body = render(
            self.template(),
            Path("/tmp/project__legal"),
            Path("/tmp/config__legal.toml"),
            Path("/usr/bin/python3"),
            "/usr/bin:/bin__legal",
            "10:00",
        )
        parsed = plistlib.loads(body.encode())
        self.assertIn("project__legal", parsed["WorkingDirectory"])
        self.assertTrue(parsed["ProgramArguments"][4].endswith("config__legal.toml"))
        self.assertIn("bin__legal", parsed["EnvironmentVariables"]["PATH"])

    def test_rejects_unknown_template_marker_before_rendering(self) -> None:
        """Reject only unsupported marker tokens present in the source template."""
        template = self.template().replace("__MINUTE__", "__UNKNOWN__")
        with self.assertRaisesRegex(ValueError, "__UNKNOWN__"):
            render(
                template,
                Path("/tmp/project"),
                Path("/tmp/config.toml"),
                Path("/usr/bin/python3"),
                "/usr/bin:/bin",
                "10:00",
            )

    def test_rejects_invalid_template_syntax_during_rendering(self) -> None:
        """Parse the rendered product before any caller can write the malformed plist."""
        template = self.template().replace("</plist>", "")
        with self.assertRaises(ExpatError):
            render(
                template,
                Path("/tmp/project"),
                Path("/tmp/config.toml"),
                Path("/usr/bin/python3"),
                "/usr/bin:/bin",
                "10:00",
            )

    def test_main_refuses_unverified_or_non_beijing_timezone_without_writing(self) -> None:
        """Refuse generation before output side effects for unverified timezones."""
        for timezone in ("UTC", None):
            with self.subTest(timezone=timezone), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "missing" / "refresh.plist"

                def timezone_detector(detected_timezone: str | None = timezone) -> str | None:
                    """Return the loop's timezone value without late binding."""
                    return detected_timezone

                with self.assertRaisesRegex(SystemExit, "Asia/Shanghai.*nothing was installed"):
                    main(
                        ["--config", str(Path(directory) / "unused.toml"), "--output", str(output)],
                        timezone_detector=timezone_detector,
                    )
                self.assertFalse(output.exists())
                self.assertFalse(output.parent.exists())

    def test_main_renders_but_never_installs_for_beijing_timezone(self) -> None:
        """Allow output-only generation when an injected detector confirms Asia/Shanghai."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            output = Path(directory) / "output" / "refresh.plist"
            config.write_text(CONFIG, encoding="utf-8")
            with patch("scripts.render_launchd.shutil.which", return_value="/usr/bin/aws"):
                self.assertEqual(
                    0,
                    main(
                        ["--config", str(config), "--output", str(output)],
                        timezone_detector=lambda: "Asia/Shanghai",
                    ),
                )
            parsed = plistlib.loads(output.read_bytes())
            self.assertEqual({"Hour": 23, "Minute": 59}, parsed["StartCalendarInterval"])


if __name__ == "__main__":
    unittest.main()
