# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Provider health checks — REQ-109 reqs 015, 017, 018, 019.

Health checking for all configured providers with 5-minute TTL cache.
Callers use get_provider_health() for cached results, check_health() for fresh.

Import direction:
    adapters/health.py → imports adapters/* (health() method), config
    providers.py → imports adapters/health (is_provider_healthy)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# -- REQ-109 req 018: 5-minute TTL for health cache
_HEALTH_TTL_SECONDS: float = 300.0

# -- In-process cache: provider name → HealthStatus
_HEALTH_CACHE: dict[str, HealthStatus] = {}


@dataclass
class HealthStatus:
    """Result of a provider health check — REQ-109 req 017.

    Fields:
        provider:    Provider name (gemini, openai, grok, etc.)
        healthy:     True if API is reachable and responding.
        latency_ms:  Round-trip time in milliseconds (0 if unhealthy).
        checked_at:  Unix timestamp of when check was performed.
        error:       Error description if unhealthy, empty string if healthy.
    """

    provider: str
    healthy: bool
    latency_ms: float
    checked_at: float
    error: str = ""


def _get_adapter_for_provider(provider_name: str) -> object | None:
    """Return an adapter instance for the given provider name.

    Maps bare provider name (gemini, openai, grok, mistral, anthropic, local)
    to an adapter using the default model for that provider. Returns None if
    provider is not recognised or has no adapter.
    """
    try:
        from rondo.providers import (  # pylint: disable=import-outside-toplevel
            _get_anthropic_adapter,
            _get_chat_completions_adapter,
            _get_gemini_adapter,
            get_ollama_adapter,
        )
    except ImportError:
        return None

    if provider_name == "gemini":
        return _get_gemini_adapter("")
    if provider_name in ("openai", "grok", "mistral"):
        return _get_chat_completions_adapter(provider_name, "")
    if provider_name == "anthropic":
        return _get_anthropic_adapter("")
    if provider_name == "local":
        return get_ollama_adapter()
    return None


def _get_configured_providers() -> list[str]:
    """Return list of provider names from ~/.rondo/config.toml [providers] section.

    Falls back to empty list if config not found or malformed.
    Uses shared config reader (single TOML load, cached).
    """
    try:
        from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

        data = get_rondo_config()
        providers_cfg = data.get("providers", {})
        return [name for name, cfg in providers_cfg.items() if isinstance(cfg, dict) and cfg.get("enabled", True)]
    except (OSError, KeyError, TypeError):
        return []


def check_health(provider_name: str, timeout: float = 5.0) -> HealthStatus:  # noqa: ARG001
    """Call adapter.health() and return a fresh HealthStatus.

    REQ-109 req 017: key present + API reachable.
    The timeout parameter is reserved for future async implementation;
    the synchronous adapters use their own internal timeouts.

    Args:
        provider_name: Provider name (gemini, openai, grok, etc.).
        timeout:       Max seconds to wait (advisory — adapters set own limits).

    Returns:
        HealthStatus with healthy=True/False, latency_ms, checked_at, error.
    """
    adapter = _get_adapter_for_provider(provider_name)
    if adapter is None:
        return HealthStatus(
            provider=provider_name,
            healthy=False,
            latency_ms=0.0,
            checked_at=time.time(),
            error=f"No adapter for provider '{provider_name}'",
        )

    start = time.monotonic()
    try:
        result = adapter.health()
        latency_ms = (time.monotonic() - start) * 1000.0
        if result:
            return HealthStatus(
                provider=provider_name,
                healthy=True,
                latency_ms=latency_ms,
                checked_at=time.time(),
            )
        return HealthStatus(
            provider=provider_name,
            healthy=False,
            latency_ms=latency_ms,
            checked_at=time.time(),
            error="health() returned False",
        )
    except (OSError, ConnectionError, TimeoutError, Exception) as exc:  # noqa: BLE001
        latency_ms = (time.monotonic() - start) * 1000.0
        logger.warning("Health check failed for provider '%s': %s", provider_name, exc)
        return HealthStatus(
            provider=provider_name,
            healthy=False,
            latency_ms=latency_ms,
            checked_at=time.time(),
            error=str(exc),
        )


def get_provider_health(provider_name: str) -> HealthStatus:
    """Return cached HealthStatus, refreshing if stale (TTL = 5 min).

    REQ-109 req 018: cache result, re-check only when TTL expires.
    """
    cached = _HEALTH_CACHE.get(provider_name)
    if cached is not None:
        age = time.time() - cached.checked_at
        if age < _HEALTH_TTL_SECONDS:
            return cached

    # -- Cache miss or stale — perform fresh check
    status = check_health(provider_name)
    _HEALTH_CACHE[provider_name] = status

    if not status.healthy:
        # -- REQ-109 req 019: log WARNING when provider is down
        logger.warning(
            "Provider '%s' is DOWN (latency=%.0fms, error=%s)",
            provider_name,
            status.latency_ms,
            status.error or "health check failed",
        )

    return status


def is_provider_healthy(provider_name: str) -> bool:
    """Return True if provider is healthy (cached, 5-min TTL).

    REQ-109 req 019: callers check this before dispatch to decide fallback.
    """
    return get_provider_health(provider_name).healthy


def get_all_providers_health() -> dict[str, HealthStatus]:
    """Check all configured providers and return health map.

    REQ-109 req 017: preflight checks ALL configured providers.
    Returns dict mapping provider name → HealthStatus.
    """
    providers = _get_configured_providers()
    return {name: get_provider_health(name) for name in providers}


def clear_health_cache() -> None:
    """Clear the in-process health cache. Used by tests and on config reload."""
    _HEALTH_CACHE.clear()


# -- sig: mgh-6201.cd.bd955f.a801.c34b91
