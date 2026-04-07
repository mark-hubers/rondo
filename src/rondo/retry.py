# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""HTTP retry with exponential backoff + circuit breaker — RONDO-145.

Rondo-REQ-109 req 074: reliability primitives (retry + circuit breaker)
for all provider dispatch paths — HTTP adapters and subprocess Claude CLI.

Finding #211: HTTP adapters had no retry/backoff/circuit breaker logic.
Finding #235 (RONDO-204): subprocess Claude path needed same reliability
pattern — promoted this module from adapters/ to top-level rondo/ so
both L1 (dispatch.py) and L2 (HTTP adapters) can share the primitives.

This module provides:
    retry_http(fn) — call fn() with retries on transient failures
    CircuitBreaker — per-provider state that opens after N consecutive failures

Import direction:
    retry.py → pure Python stdlib only (no rondo imports)
    Callers: dispatch.py (subprocess), adapters/*.py (HTTP)
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Retry with exponential backoff
# -- ──────────────────────────────────────────────────────────────


@dataclass
class RetryConfig:
    """Retry configuration — tunable per provider."""

    max_attempts: int = 3
    initial_delay_sec: float = 0.5
    max_delay_sec: float = 10.0
    backoff_multiplier: float = 2.0
    jitter: bool = True


def is_transient_http_error(exc: Exception) -> bool:
    """Determine if an HTTP exception is transient (worth retrying).

    Retry: 5xx server errors, 429 rate limit, network/connection errors.
    Do NOT retry: 4xx client errors (auth, bad request, not found).
    """
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        # -- 5xx server errors and 429 rate limit are transient
        return exc.code >= 500 or exc.code == 429
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        # -- Network-level errors are transient
        return True
    return False


def retry_http(
    fn: Callable[[], Any],
    config: RetryConfig | None = None,
    provider_name: str = "unknown",
) -> Any:
    """Call fn() with retries on transient HTTP failures.

    Exponential backoff with optional jitter. Non-transient errors
    (4xx client errors other than 429) fail immediately.
    """
    cfg = config or RetryConfig()
    delay = cfg.initial_delay_sec
    last_exc: Exception | None = None

    for attempt in range(1, cfg.max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not is_transient_http_error(exc):
                # -- Non-transient → fail immediately
                raise
            if attempt >= cfg.max_attempts:
                # -- Last attempt — don't sleep, just fail
                break
            # -- Sleep with optional jitter before retry (secrets for non-predictable jitter)
            sleep_for = delay
            if cfg.jitter:
                # -- secrets.randbelow is deterministic-safe; scale to [0.5, 1.5)
                jitter_factor = 0.5 + (secrets.randbelow(1000) / 1000.0)
                sleep_for = delay * jitter_factor
            logger.info(
                "Retry %d/%d for %s after transient error: %s (sleeping %.2fs)",
                attempt,
                cfg.max_attempts,
                provider_name,
                str(exc)[:100],
                sleep_for,
            )
            time.sleep(sleep_for)
            delay = min(delay * cfg.backoff_multiplier, cfg.max_delay_sec)

    # -- Exhausted retries — raise the last exception
    if last_exc is None:
        raise RuntimeError(f"retry_http exhausted without exception for {provider_name}")
    raise last_exc


# -- ──────────────────────────────────────────────────────────────
# --  Circuit breaker (per-provider)
# -- ──────────────────────────────────────────────────────────────


@dataclass
class CircuitBreakerState:
    """Per-provider circuit breaker state."""

    failure_count: int = 0
    open_until: float = 0.0  # -- monotonic timestamp when circuit reopens
    lock: threading.Lock = field(default_factory=threading.Lock)


class CircuitBreaker:
    """Per-provider circuit breaker — RONDO-145.

    Trips open after N consecutive failures. While open, calls fail
    immediately without hitting the network. Auto-closes after cooldown.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_sec: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self._states: dict[str, CircuitBreakerState] = {}
        self._global_lock = threading.Lock()

    def _get_state(self, provider: str) -> CircuitBreakerState:
        with self._global_lock:
            if provider not in self._states:
                self._states[provider] = CircuitBreakerState()
            return self._states[provider]

    def is_open(self, provider: str) -> bool:
        """Check if circuit is open for this provider."""
        state = self._get_state(provider)
        with state.lock:
            if state.open_until == 0.0:
                return False
            if time.monotonic() >= state.open_until:
                # -- Cooldown expired — auto-close
                state.failure_count = 0
                state.open_until = 0.0
                return False
            return True

    def record_failure(self, provider: str) -> None:
        """Record a failure for this provider. Trip circuit if threshold reached."""
        state = self._get_state(provider)
        with state.lock:
            state.failure_count += 1
            if state.failure_count >= self.failure_threshold:
                state.open_until = time.monotonic() + self.cooldown_sec
                logger.warning(
                    "Circuit breaker OPENED for %s after %d failures (cooldown %.0fs)",
                    provider,
                    state.failure_count,
                    self.cooldown_sec,
                )

    def record_success(self, provider: str) -> None:
        """Record a success — reset failure count."""
        state = self._get_state(provider)
        with state.lock:
            state.failure_count = 0
            state.open_until = 0.0

    def reset(self, provider: str | None = None) -> None:
        """Reset breaker state for a provider (or all if None)."""
        with self._global_lock:
            if provider is None:
                self._states.clear()
            else:
                self._states.pop(provider, None)


# -- Global shared circuit breaker for all adapters + dispatch
_GLOBAL_BREAKER = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    """Public accessor for the shared circuit breaker."""
    return _GLOBAL_BREAKER


# -- sig: mgh-6201.cd.bd955f.f1b0.f0b061
