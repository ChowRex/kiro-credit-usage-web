#!/usr/bin/env python3
"""Render, but never install, the macOS daily refresh LaunchAgent."""

from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import subprocess  # nosec B404: only a fixed local administrative command is invoked below.
import sys
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape  # nosec B406: escapes values; it does not parse untrusted XML.

from app.config import load_config

ROOT = Path(__file__).resolve().parents[1]
MARKERS = {"__PROJECT__", "__CONFIG__", "__PYTHON__", "__PATH__", "__HOUR__", "__MINUTE__"}
MARKER_PATTERN = re.compile(r"__[A-Z][A-Z0-9_]*__")
BEIJING_TIMEZONE = "Asia/Shanghai"


def _timezone_from_localtime() -> str | None:
    """Return the configured macOS IANA zone from its readable localtime symlink."""
    try:
        zoneinfo_root = Path("/var/db/timezone/zoneinfo").resolve(strict=True)
        return Path("/etc/localtime").resolve(strict=True).relative_to(zoneinfo_root).as_posix()
    except (OSError, ValueError):
        return None


def host_timezone() -> str | None:
    """Return the macOS configured IANA timezone without changing system settings."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "/usr/sbin/systemsetup",
                "-gettimezone",
            ],  # nosec B603: fixed executable and arguments, shell disabled.
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return _timezone_from_localtime()
    match = re.fullmatch(r"Time Zone:\s*([^\s]+)\s*", result.stdout)
    return match.group(1) if result.returncode == 0 and match else _timezone_from_localtime()


def _schedule_parts(daily_time: str) -> tuple[int, int]:
    """Parse a validated zero-padded 24-hour schedule for plist integer fields."""
    match = re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_time)
    if not match:
        raise ValueError("refresh.daily_time must be HH:MM")
    hour, minute = daily_time.split(":")
    return int(hour), int(minute)


def render(
    template: str,
    project: Path,
    config: Path,
    python: Path,
    path_value: str,
    daily_time: str,
) -> str:
    """Render and validate a launchd plist from a supported marker template."""
    unknown_markers = set(MARKER_PATTERN.findall(template)) - MARKERS
    if unknown_markers:
        raise ValueError(f"unresolved launchd template marker: {sorted(unknown_markers)[0]}")
    hour, minute = _schedule_parts(daily_time)
    values = {
        "__PROJECT__": str(project.resolve()),
        "__CONFIG__": str(config.resolve()),
        "__PYTHON__": str(python.resolve()),
        "__PATH__": path_value,
        "__HOUR__": str(hour),
        "__MINUTE__": str(minute),
    }
    for marker, value in values.items():
        template = template.replace(marker, escape(value))
    plistlib.loads(template.encode("utf-8"))
    return template


def _require_beijing_timezone(timezone_detector: Callable[[], str | None]) -> None:
    """Refuse rendering unless the host's configured timezone is Asia/Shanghai."""
    timezone = timezone_detector()
    if timezone == BEIJING_TIMEZONE:
        return
    if timezone is None:
        detail = "host timezone could not be verified"
    else:
        detail = f"host timezone is {timezone!r}"
    raise SystemExit(
        f"Refusing to generate: {detail}; expected {BEIJING_TIMEZONE}. "
        "No plist was generated and nothing was installed."
    )


def main(
    argv: list[str] | None = None,
    *,
    timezone_detector: Callable[[], str | None] = host_timezone,
) -> int:
    """Render a validated plist only when the host runs in Beijing's IANA timezone."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.local.toml")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "com.kiro.credit-usage.refresh.plist",
    )
    args = parser.parse_args(argv)
    _require_beijing_timezone(timezone_detector)
    config = load_config(args.config)
    aws = shutil.which("aws")
    if not aws:
        raise SystemExit("aws CLI was not found in PATH")
    path_value = os.pathsep.join(
        dict.fromkeys(
            [
                str(Path(aws).parent),
                str(Path(sys.executable).parent),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
            ]
        )
    )
    template = (ROOT / "ops" / "com.kiro.credit-usage.refresh.plist.template").read_text(
        encoding="utf-8"
    )
    body = render(
        template,
        ROOT,
        args.config,
        Path(sys.executable),
        path_value,
        config.refresh.daily_time,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    print(args.output)
    print("Not installed. Review the plist before loading it with launchctl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
