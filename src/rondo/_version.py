# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo version — single source of truth.

STD-109: Version follows CalVer+Build format:
    MAJOR.MINOR.PATCH+YYYYMMDD.BUILD

    MAJOR = 0 (pre-release), 1 (OB2 production)
    MINOR = milestone bumps (Mark decides)
    PATCH = 0 (always, we use build counter instead)
    YYYYMMDD = date of build
    BUILD = auto-incrementing counter per day

Example: 0.2.0+20260329.17

The pyproject.toml version is the base (MAJOR.MINOR.PATCH).
The full version with build metadata is computed at runtime.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import version as _pkg_version
from pathlib import Path

# -- Build counter file (persists across sessions)
_BUILD_FILE = Path.home() / ".rondo" / "build-counter.json"


def _read_build_counter() -> tuple[str, int]:
    """Read current date + build counter from file."""
    if _BUILD_FILE.exists():
        try:
            data = json.loads(_BUILD_FILE.read_text(encoding="utf-8"))
            return data.get("date", ""), data.get("build", 0)
        except (json.JSONDecodeError, OSError):
            pass
    return "", 0


def _write_build_counter(date_str: str, build: int) -> None:
    """Write date + build counter to file."""
    try:
        _BUILD_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BUILD_FILE.write_text(
            json.dumps({"date": date_str, "build": build}),
            encoding="utf-8",
        )
    except OSError:
        pass


def bump_build() -> str:
    """Increment build counter and return full version string.

    Called by ace-sprint done or version bump script.
    Same-day builds increment counter. New day resets to 1.
    """
    today = datetime.now(UTC).strftime("%Y%m%d")
    saved_date, saved_build = _read_build_counter()

    if saved_date == today:
        new_build = saved_build + 1
    else:
        new_build = 1

    _write_build_counter(today, new_build)
    base = _get_base_version()
    return f"{base}+{today}.{new_build}"


def _get_base_version() -> str:
    """Get base version from package metadata (pyproject.toml)."""
    from importlib.metadata import PackageNotFoundError  # pylint: disable=import-outside-toplevel

    try:
        return _pkg_version("rondo")
    except PackageNotFoundError:
        # -- RONDO-209 #254: narrowed from broad Exception. PackageNotFoundError
        # -- is the only legitimate failure mode (package not installed in dev env).
        return "0.0.0"


def get_version() -> str:
    """Get full version string: MAJOR.MINOR.PATCH+YYYYMMDD.BUILD.

    Reads base from pyproject.toml, build metadata from counter file.
    If no build counter exists, returns base version only.
    """
    base = _get_base_version()
    saved_date, saved_build = _read_build_counter()
    if saved_date and saved_build > 0:
        return f"{base}+{saved_date}.{saved_build}"
    return base


# -- Module-level version for quick access
__version__ = get_version()


# -- sig: mgh-6201.cd.bd955f.f1a5.96a5b6
