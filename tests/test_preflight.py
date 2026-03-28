# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.preflight — REQ-103 dispatch environment checks.

VER-001 verification matrix: preflight checks.
TDD: tests written BEFORE preflight.py exists.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from rondo.preflight import PreflightResult, run_preflight


class TestPreflightResult:
    """REQ-103 req 012: health status model."""

    def test_green_status(self):
        """GREEN = all checks pass, no warnings."""
        r = PreflightResult(status="GREEN", checks=[], warnings=[], errors=[])
        assert r.status == "GREEN"
        assert r.can_proceed is True

    def test_yellow_status(self):
        """YELLOW = warnings but can proceed."""
        r = PreflightResult(
            status="YELLOW", checks=[], warnings=["disk low"], errors=[],
        )
        assert r.status == "YELLOW"
        assert r.can_proceed is True

    def test_red_status(self):
        """RED = errors, cannot proceed."""
        r = PreflightResult(
            status="RED", checks=[], warnings=[], errors=["no claude"],
        )
        assert r.status == "RED"
        assert r.can_proceed is False


class TestClaudeBinaryCheck:
    """REQ-103 req 003: claude binary on PATH."""

    def test_claude_found(self):
        """Claude on PATH = passes."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = run_preflight()
        assert "claude binary" not in " ".join(result.errors)

    def test_claude_missing(self):
        """Claude not on PATH = RED."""
        with patch("shutil.which", return_value=None):
            result = run_preflight()
        assert result.status == "RED"
        assert any("claude" in e.lower() for e in result.errors)


class TestNestedSessionCheck:
    """REQ-103 req 010: CLAUDECODE env var not set."""

    def test_claudecode_not_set(self):
        """No CLAUDECODE = passes."""
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        with patch.dict(os.environ, env, clear=True):
            result = run_preflight()
        assert "CLAUDECODE" not in " ".join(result.errors)

    def test_claudecode_set(self):
        """CLAUDECODE present = RED (nested session risk)."""
        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            result = run_preflight()
        assert result.status == "RED"
        assert any("CLAUDECODE" in e or "nested" in e.lower() for e in result.errors)


class TestAuthCheck:
    """REQ-103 req 005: API key or Max plan auth."""

    def test_max_auth_no_key_needed(self):
        """auth=max doesn't need ANTHROPIC_API_KEY."""
        from rondo.config import RondoConfig

        config = RondoConfig(auth="max")
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = run_preflight(config=config)
        assert "api key" not in " ".join(result.errors).lower()

    def test_api_auth_needs_key(self):
        """auth=api with no ANTHROPIC_API_KEY = RED."""
        from rondo.config import RondoConfig

        config = RondoConfig(auth="api")
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch.dict(os.environ, env, clear=True),
        ):
            result = run_preflight(config=config)
        assert result.status == "RED"
        assert any("api key" in e.lower() or "ANTHROPIC_API_KEY" in e for e in result.errors)

    def test_api_auth_with_key_passes(self):
        """auth=api with ANTHROPIC_API_KEY set = passes."""
        from rondo.config import RondoConfig

        config = RondoConfig(auth="api")
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}),
        ):
            result = run_preflight(config=config)
        assert "api key" not in " ".join(result.errors).lower()


class TestPreflightPerformance:
    """REQ-103 req 002: preflight < 3 seconds."""

    def test_completes_quickly(self):
        """Preflight should complete in under 3 seconds."""
        import time

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            start = time.monotonic()
            run_preflight()
            elapsed = time.monotonic() - start
        assert elapsed < 3.0, f"Preflight took {elapsed:.1f}s (max 3s)"


# -- sig: mgh-6201.cd.bd955f.e4a1.91c5f0
