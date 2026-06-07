# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Packaging reproducibility lock — RONDO-341.

VER-001 verification matrix: a stranger can recreate the test environment
from pyproject.toml alone.

Found during the first Linux container run: the venv was hand-grown — no
declared test dependencies anywhere. ``pip install -e .[dev]`` on a fresh
OS had nothing to install. SOP-106 dims 6/7 both assume a reproducible
environment; this lock makes the assumption real.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

RONDO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = RONDO_ROOT / "pyproject.toml"

# -- The suite's real imports + the 6-gate toolchain (bin/build).
REQUIRED_DEV = ("pytest", "pytest-xdist", "hypothesis", "ruff", "mypy", "pylint", "bandit")


def _dev_deps() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data.get("project", {}).get("optional-dependencies", {}).get("dev", [])


class TestPackagingLock:
    """pyproject.toml declares everything the build gates need."""

    def test_dev_extra_exists(self) -> None:
        """A [project.optional-dependencies] dev extra is declared."""
        assert _dev_deps(), "no dev extra in pyproject.toml — stranger cannot recreate the test env"

    def test_dev_extra_covers_suite_and_gates(self) -> None:
        """Every suite/gate tool appears in the dev extra."""
        deps = " ".join(_dev_deps()).lower()
        missing = [p for p in REQUIRED_DEV if p not in deps]
        assert not missing, f"dev extra missing: {missing}"

    def test_ruff_is_version_pinned(self) -> None:
        """bin/build pins ruff 0.15.5 — the extra must agree (format baseline)."""
        ruff = [d for d in _dev_deps() if d.lower().startswith("ruff")]
        assert ruff and "==" in ruff[0], "ruff must be ==pinned in dev extra (RONDO-338 format baseline)"


# -- sig: mgh-6201.cd.bd955f.6f07.c62567
