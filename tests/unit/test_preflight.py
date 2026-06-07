# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.preflight — REQ-103 dispatch environment checks.

VER-001 verification matrix: preflight checks.
TDD: tests written BEFORE preflight.py exists.
"""

import os
from unittest.mock import patch

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
            status="YELLOW",
            checks=[],
            warnings=["disk low"],
            errors=[],
        )
        assert r.status == "YELLOW"
        assert r.can_proceed is True

    def test_red_status(self):
        """RED = errors, cannot proceed."""
        r = PreflightResult(
            status="RED",
            checks=[],
            warnings=[],
            errors=["no claude"],
        )
        assert r.status == "RED"
        assert r.can_proceed is False


@pytest.mark.real_claude_check
class TestClaudeBinaryCheck:
    """REQ-103 req 003: claude binary on PATH.

    RONDO-341: marked real_claude_check — these test the binary check
    ITSELF, so the hermetic autouse fake (tests/conftest.py) must stand
    aside. Both directions pinned: found AND missing.
    """

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


class TestDiskSpaceCheck:
    """REQ-103 req 008: disk space > 500MB free."""

    def test_enough_disk_space(self):
        """500MB+ free = passes."""
        import rondo.preflight

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch.object(rondo.preflight.shutil, "disk_usage", return_value=(int(1e12), int(5e11), int(1e9))),
        ):
            result = run_preflight()
        assert not any("disk" in w.lower() for w in result.warnings)

    def test_low_disk_space(self):
        """< 500MB free = YELLOW warning."""
        import rondo.preflight

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch.object(rondo.preflight.shutil, "disk_usage", return_value=(int(1e12), int(9.9e11), int(1e8))),
        ):
            result = run_preflight()
        assert any("disk" in w.lower() for w in result.warnings)


class TestGitCheck:
    """REQ-103 req 009: git available."""

    def test_git_available(self):
        """Git on PATH = passes."""
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/git" if x == "git" else "/usr/local/bin/claude"):
            result = run_preflight()
        assert not any("git" in w.lower() for w in result.warnings)

    def test_git_missing(self):
        """Git not on PATH = YELLOW warning (not RED — git is SHOULD, not MUST)."""

        def _which(name: str) -> str | None:
            if name == "git":
                return None
            return "/usr/local/bin/claude"

        with patch("shutil.which", side_effect=_which):
            result = run_preflight()
        assert any("git" in w.lower() for w in result.warnings)


class TestCCVersionCheck:
    """REQ-103 reqs 004, 017: CC version detection in preflight."""

    def test_version_in_checks_when_available(self):
        """CC version reported in checks list."""
        import rondo.dispatch

        rondo.dispatch._cc_version_cache = None
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 1, 86)),
        ):
            result = run_preflight()
        assert any("2.1.86" in c for c in result.checks)

    def test_old_version_warns(self):
        """CC < 2.1.81 = YELLOW warning (--bare won't work)."""
        import rondo.dispatch

        rondo.dispatch._cc_version_cache = None
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 0, 50)),
        ):
            result = run_preflight()
        assert any("old" in w.lower() or "2.1.81" in w for w in result.warnings)

    def test_version_unavailable_warns(self):
        """Can't detect version = YELLOW warning."""
        import rondo.dispatch

        rondo.dispatch._cc_version_cache = None
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=None),
        ):
            result = run_preflight()
        assert any("version" in w.lower() for w in result.warnings)


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


# -- ──────────────────────────────────────────────────────────────
# --  REQ-103 req 025-026: Preflight caching (RONDO-60)
# -- ──────────────────────────────────────────────────────────────


class TestPreflightCache:
    """REQ-103 req 025-026: cache preflight results, version-keyed."""

    def test_second_run_uses_cache(self):
        """Consecutive runs with same version use cached result."""
        from rondo.preflight import _preflight_cache, run_preflight

        _preflight_cache.clear()
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 1, 87)),
        ):
            r1 = run_preflight()
            r2 = run_preflight()
        ## -- Same object if cached
        assert r1.status == r2.status
        assert len(_preflight_cache) == 1

    def test_version_change_invalidates(self):
        """Different CC version = cache miss = re-run."""
        from rondo.preflight import _preflight_cache, run_preflight

        _preflight_cache.clear()
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 1, 87)),
        ):
            run_preflight()
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 1, 88)),
        ):
            run_preflight()
        ## -- Different versions = 2 cache entries
        assert len(_preflight_cache) == 2

    def test_cache_stores_version(self):
        """Cache key includes CC version string."""
        from rondo.preflight import _preflight_cache, run_preflight

        _preflight_cache.clear()
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.preflight.detect_cc_version", return_value=(2, 1, 90)),
        ):
            run_preflight()
        assert any("2.1.90" in str(k) for k in _preflight_cache)


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 017: provider health in preflight
# -- ──────────────────────────────────────────────────────────────


class TestPreflightProviderHealth:
    """REQ-109 req 017: preflight checks all configured providers."""

    def test_healthy_provider_in_checks(self) -> None:
        import time

        from rondo.adapters.health import HealthStatus
        from rondo.preflight import PreflightResult, _check_provider_health

        result = PreflightResult()
        mock_map = {"gemini": HealthStatus(provider="gemini", healthy=True, latency_ms=42.0, checked_at=time.time())}
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_map):
            _check_provider_health(result)
        assert any("gemini" in c and "UP" in c for c in result.checks)

    def test_unhealthy_provider_in_warnings(self) -> None:
        import time

        from rondo.adapters.health import HealthStatus
        from rondo.preflight import PreflightResult, _check_provider_health

        result = PreflightResult()
        mock_map = {
            "openai": HealthStatus(
                provider="openai", healthy=False, latency_ms=0.0, checked_at=time.time(), error="timeout"
            )
        }
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_map):
            _check_provider_health(result)
        assert any("openai" in w and "DOWN" in w for w in result.warnings)

    def test_no_providers_no_change(self) -> None:
        from rondo.preflight import PreflightResult, _check_provider_health

        result = PreflightResult()
        with patch("rondo.adapters.health.get_all_providers_health", return_value={}):
            _check_provider_health(result)
        assert result.checks == []
        assert result.warnings == []

    def test_exception_becomes_warning(self) -> None:
        from rondo.preflight import PreflightResult, _check_provider_health

        result = PreflightResult()
        with patch("rondo.adapters.health.get_all_providers_health", side_effect=OSError("network down")):
            _check_provider_health(result)
        assert any("Provider health check failed" in w for w in result.warnings)


# -- sig: mgh-6201.cd.bd955f.e4a1.91c5f0
