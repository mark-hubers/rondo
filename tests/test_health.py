# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.adapters.health — REQ-109 reqs 015, 017, 018, 019.

VER-001 verification matrix: provider health checks, caching, fallback.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

# -- ──────────────────────────────────────────────────────────────
# --  HealthStatus dataclass
# -- ──────────────────────────────────────────────────────────────


class TestHealthStatus:
    """HealthStatus carries provider, healthy, latency_ms, checked_at, error."""

    def test_healthy_status(self) -> None:
        from rondo.adapters.health import HealthStatus

        hs = HealthStatus(provider="gemini", healthy=True, latency_ms=42.0, checked_at=time.time())
        assert hs.healthy is True
        assert hs.provider == "gemini"
        assert hs.latency_ms == 42.0

    def test_unhealthy_status_has_error(self) -> None:
        from rondo.adapters.health import HealthStatus

        hs = HealthStatus(provider="openai", healthy=False, latency_ms=0.0, checked_at=time.time(), error="timeout")
        assert hs.healthy is False
        assert "timeout" in hs.error

    def test_default_error_is_empty(self) -> None:
        from rondo.adapters.health import HealthStatus

        hs = HealthStatus(provider="gemini", healthy=True, latency_ms=10.0, checked_at=time.time())
        assert hs.error == ""


# -- ──────────────────────────────────────────────────────────────
# --  check_health — REQ-109 req 017
# -- ──────────────────────────────────────────────────────────────


class TestCheckHealth:
    """check_health() calls adapter.health() with timeout, measures latency."""

    def test_healthy_adapter_returns_healthy_status(self) -> None:
        from rondo.adapters.health import check_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = check_health("gemini")
        assert result.healthy is True
        assert result.provider == "gemini"
        assert result.latency_ms >= 0.0

    def test_unhealthy_adapter_returns_unhealthy_status(self) -> None:
        from rondo.adapters.health import check_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = False
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = check_health("openai")
        assert result.healthy is False

    def test_adapter_exception_returns_unhealthy(self) -> None:
        from rondo.adapters.health import check_health

        mock_adapter = MagicMock()
        mock_adapter.health.side_effect = OSError("connection refused")
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = check_health("grok")
        assert result.healthy is False
        assert result.error != ""

    def test_unknown_provider_returns_unhealthy(self) -> None:
        from rondo.adapters.health import check_health

        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=None):
            result = check_health("unknown_provider")
        assert result.healthy is False

    def test_checked_at_is_recent(self) -> None:
        from rondo.adapters.health import check_health

        before = time.time()
        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = check_health("gemini")
        assert result.checked_at >= before


# -- ──────────────────────────────────────────────────────────────
# --  get_provider_health — REQ-109 req 018: 5-min TTL cache
# -- ──────────────────────────────────────────────────────────────


class TestGetProviderHealth:
    """get_provider_health() caches results for 5 min TTL."""

    def setup_method(self) -> None:
        from rondo.adapters.health import clear_health_cache
        clear_health_cache()

    def test_returns_health_status(self) -> None:
        from rondo.adapters.health import get_provider_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = get_provider_health("gemini")
        assert isinstance(result.healthy, bool)

    def test_cached_result_not_rechecked_within_ttl(self) -> None:
        from rondo.adapters.health import get_provider_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            get_provider_health("gemini")
            get_provider_health("gemini")
        # -- Should only have called health() once (second call from cache)
        assert mock_adapter.health.call_count == 1

    def test_stale_cache_rechecks(self) -> None:
        from rondo.adapters.health import _HEALTH_CACHE, _HEALTH_TTL_SECONDS, HealthStatus

        # -- Inject a stale cache entry
        _HEALTH_CACHE["gemini"] = HealthStatus(
            provider="gemini",
            healthy=True,
            latency_ms=10.0,
            checked_at=time.time() - _HEALTH_TTL_SECONDS - 1,
        )
        mock_adapter = MagicMock()
        mock_adapter.health.return_value = False
        from rondo.adapters.health import get_provider_health
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            result = get_provider_health("gemini")
        # -- Stale → should recheck → new result
        assert mock_adapter.health.call_count == 1
        assert result.healthy is False


# -- ──────────────────────────────────────────────────────────────
# --  is_provider_healthy — simple bool wrapper
# -- ──────────────────────────────────────────────────────────────


class TestIsProviderHealthy:
    """is_provider_healthy() returns bool."""

    def setup_method(self) -> None:
        from rondo.adapters.health import clear_health_cache
        clear_health_cache()

    def test_returns_true_for_healthy(self) -> None:
        from rondo.adapters.health import is_provider_healthy

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            assert is_provider_healthy("gemini") is True

    def test_returns_false_for_unhealthy(self) -> None:
        from rondo.adapters.health import is_provider_healthy

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = False
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            assert is_provider_healthy("openai") is False


# -- ──────────────────────────────────────────────────────────────
# --  get_all_providers_health — REQ-109 req 017 (preflight)
# -- ──────────────────────────────────────────────────────────────


class TestGetAllProvidersHealth:
    """get_all_providers_health() checks all configured providers."""

    def setup_method(self) -> None:
        from rondo.adapters.health import clear_health_cache
        clear_health_cache()

    def test_returns_dict(self) -> None:
        from rondo.adapters.health import get_all_providers_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            with patch("rondo.adapters.health._get_configured_providers", return_value=["gemini", "openai"]):
                result = get_all_providers_health()
        assert isinstance(result, dict)

    def test_includes_all_configured_providers(self) -> None:
        from rondo.adapters.health import get_all_providers_health

        mock_adapter = MagicMock()
        mock_adapter.health.return_value = True
        with patch("rondo.adapters.health._get_adapter_for_provider", return_value=mock_adapter):
            with patch("rondo.adapters.health._get_configured_providers", return_value=["gemini", "openai"]):
                result = get_all_providers_health()
        assert "gemini" in result
        assert "openai" in result

    def test_empty_config_returns_empty_dict(self) -> None:
        from rondo.adapters.health import get_all_providers_health

        with patch("rondo.adapters.health._get_configured_providers", return_value=[]):
            result = get_all_providers_health()
        assert result == {}


# -- ──────────────────────────────────────────────────────────────
# --  Fallback chain — REQ-109 req 015, 019
# -- ──────────────────────────────────────────────────────────────


class TestProviderFallback:
    """get_provider_with_fallback() falls back when primary is down."""

    def setup_method(self) -> None:
        from rondo.adapters.health import clear_health_cache
        clear_health_cache()

    def test_uses_primary_when_healthy(self) -> None:
        from rondo.providers import get_provider_with_fallback

        # -- Patch at the import source (lazy import inside function)
        with patch("rondo.adapters.health.is_provider_healthy", return_value=True):
            with patch("rondo.providers.get_provider") as mock_gp:
                mock_gp.return_value = MagicMock()
                adapter, model = get_provider_with_fallback("gemini:flash")
        assert adapter is not None

    def test_uses_fallback_when_primary_down(self) -> None:
        from rondo.providers import get_provider_with_fallback

        # -- gemini down, openai up
        def health_side_effect(provider: str) -> bool:
            return provider != "gemini"

        with patch("rondo.adapters.health.is_provider_healthy", side_effect=health_side_effect):
            with patch("rondo.providers.get_provider") as mock_gp:
                mock_gp.return_value = MagicMock()
                with patch("rondo.providers._get_fallback_provider", return_value="openai"):
                    adapter, model = get_provider_with_fallback("gemini:flash")
        # -- Fallback used — adapter should be non-None
        assert adapter is not None

    def test_returns_none_when_all_providers_down(self) -> None:
        from rondo.providers import get_provider_with_fallback

        with patch("rondo.adapters.health.is_provider_healthy", return_value=False):
            with patch("rondo.providers._get_fallback_provider", return_value=None):
                adapter, model = get_provider_with_fallback("gemini:flash")
        assert adapter is None

    def test_never_falls_back_to_interactive_claude(self) -> None:
        """REQ-109 req 016: NEVER use Mark's interactive account for batch."""
        from rondo.providers import get_provider_with_fallback

        with patch("rondo.adapters.health.is_provider_healthy", return_value=False):
            with patch("rondo.providers._get_fallback_provider", return_value=None):
                adapter, model = get_provider_with_fallback("gemini:flash")
        # -- Result must not be Claude-CLI dispatch (adapter=None means Claude — NOT allowed as fallback)
        # -- The function returns (None, "") to signal "no provider available"
        assert model != "claude"
        assert adapter is None


# -- ──────────────────────────────────────────────────────────────
# --  clear_health_cache — test utility
# -- ──────────────────────────────────────────────────────────────


class TestClearHealthCache:
    """clear_health_cache() empties the in-process cache."""

    def test_clear_removes_entries(self) -> None:
        from rondo.adapters.health import _HEALTH_CACHE, HealthStatus, clear_health_cache

        _HEALTH_CACHE["gemini"] = HealthStatus(provider="gemini", healthy=True, latency_ms=10.0, checked_at=time.time())
        clear_health_cache()
        assert len(_HEALTH_CACHE) == 0

    def test_clear_idempotent_on_empty(self) -> None:
        from rondo.adapters.health import _HEALTH_CACHE, clear_health_cache

        _HEALTH_CACHE.clear()
        clear_health_cache()  # -- Should not raise
        assert len(_HEALTH_CACHE) == 0


# -- sig: mgh-6201.cd.bd955f.9a12.f40b22
