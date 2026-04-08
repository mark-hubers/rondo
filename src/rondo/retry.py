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

import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _default_breaker_path() -> Path:
    """Path to the persistent circuit breaker state file.

    RONDO-205 Finding #236: persist across process restart so that a
    tripped breaker survives Rondo restarting during a provider outage.
    Defaults to ~/.rondo/circuit_breaker.json; honors RONDO_TEST_DIR.
    """
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return Path(test_dir) / "circuit_breaker.json"
    return Path(os.path.expanduser("~/.rondo/circuit_breaker.json"))


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

    RONDO-205 Finding #236: state persists to disk on OPEN/CLOSE
    transitions (not every failure — would hammer disk). open_until
    stores wall-clock seconds (time.time()) so it survives restart.
    Clock skew of <60s from NTP jitter is acceptable for a 60s cooldown.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_sec: float = 60.0,
        persist_path: Path | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self._states: dict[str, CircuitBreakerState] = {}
        self._global_lock = threading.Lock()
        # -- #236: persistent state file for cross-restart safety
        self._persist_path = persist_path if persist_path is not None else _default_breaker_path()
        self._load_state()

    def _get_state(self, provider: str) -> CircuitBreakerState:
        with self._global_lock:
            if provider not in self._states:
                self._states[provider] = CircuitBreakerState()
            return self._states[provider]

    def _save_state(self) -> None:
        """Persist OPEN circuit states to disk — #236 + #246.

        RONDO-209 #246: uses fcntl.flock() for cross-process exclusive lock
        around the read-modify-write of the JSON state file. Without this,
        two processes could race: A reads {}, B reads {}, A writes {X}, B
        writes {Y} — losing A's entry. With flock, only one process holds
        the write-lock at a time. The existing atomic tmp+replace ensures
        no partial reads.

        Only persists providers whose cooldown has not yet expired.
        Called on transitions only (OPEN/CLOSE), not every failure.
        """
        import fcntl  # pylint: disable=import-outside-toplevel

        try:
            now = time.time()
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

            # -- #246: merge with existing on-disk state to avoid losing
            # -- entries written by other processes. Hold an exclusive lock
            # -- from read through write to make the merge atomic cross-process.
            lock_path = self._persist_path.with_suffix(".lock")
            with open(lock_path, "a+", encoding="utf-8") as lock_f:
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                except OSError as lock_exc:
                    # -- Lock failed — fall back to best-effort write (rare, non-fatal)
                    logger.debug("Breaker file lock failed (non-fatal): %s", lock_exc)

                # -- Read existing state (other processes may have written here)
                existing: dict[str, dict[str, float]] = {}
                if self._persist_path.exists():
                    try:
                        existing_raw = self._persist_path.read_text(encoding="utf-8")
                        loaded = json.loads(existing_raw)
                        if isinstance(loaded, dict):
                            existing = loaded
                    except (OSError, ValueError, json.JSONDecodeError):
                        existing = {}

                # -- Merge: our in-memory state overrides existing for our providers
                payload: dict[str, dict[str, float]] = {}
                # -- Keep other processes' still-valid entries
                for provider, entry in existing.items():
                    if not isinstance(entry, dict):
                        continue
                    open_until = float(entry.get("open_until", 0.0))
                    if open_until > now:
                        payload[provider] = {
                            "open_until": open_until,
                            "failure_count": float(entry.get("failure_count", 0.0)),
                        }

                # -- Add/update our in-memory OPEN states
                with self._global_lock:
                    for provider, state in self._states.items():
                        if state.open_until > now:
                            payload[provider] = {
                                "open_until": state.open_until,
                                "failure_count": float(state.failure_count),
                            }
                        elif provider in payload:
                            # -- Our state says CLOSED — remove from merged payload
                            del payload[provider]

                # -- Atomic write via tmp+replace (lock still held)
                tmp_path = self._persist_path.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                os.replace(tmp_path, self._persist_path)

                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Circuit breaker persist failed (non-fatal): %s", exc)

    def _load_state(self) -> None:
        """Restore OPEN circuit states from disk — #236 + #246.

        Only loads states where open_until is still in the future (by
        wall clock). Expired entries are ignored. Non-fatal on any error.
        """
        try:
            if not self._persist_path.exists():
                return
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            now = time.time()
            for provider, entry in data.items():
                if not isinstance(entry, dict):
                    continue
                open_until = float(entry.get("open_until", 0.0))
                if open_until > now:
                    state = CircuitBreakerState(
                        failure_count=int(entry.get("failure_count", self.failure_threshold)),
                        open_until=open_until,
                    )
                    self._states[provider] = state
                    logger.info(
                        "Circuit breaker RESTORED for %s (cooldown %.0fs remaining)",
                        provider,
                        open_until - now,
                    )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.debug("Circuit breaker load failed (non-fatal): %s", exc)

    def is_open(self, provider: str) -> bool:
        """Check if circuit is open for this provider."""
        state = self._get_state(provider)
        transitioned = False
        with state.lock:
            if state.open_until == 0.0:
                return False
            if time.time() >= state.open_until:
                # -- Cooldown expired — auto-close (#236: wall-clock)
                state.failure_count = 0
                state.open_until = 0.0
                transitioned = True
        if transitioned:
            self._save_state()  # -- #236: persist auto-close
        return False if transitioned else True

    def record_failure(self, provider: str) -> None:
        """Record a failure for this provider. Trip circuit if threshold reached."""
        state = self._get_state(provider)
        tripped = False
        with state.lock:
            state.failure_count += 1
            if state.failure_count >= self.failure_threshold and state.open_until == 0.0:
                state.open_until = time.time() + self.cooldown_sec  # -- #236: wall-clock
                tripped = True
                logger.warning(
                    "Circuit breaker OPENED for %s after %d failures (cooldown %.0fs)",
                    provider,
                    state.failure_count,
                    self.cooldown_sec,
                )
        if tripped:
            self._save_state()  # -- #236: persist OPEN transition only

    def record_success(self, provider: str) -> None:
        """Record a success — reset failure count."""
        state = self._get_state(provider)
        was_open = False
        with state.lock:
            was_open = state.open_until > 0.0
            state.failure_count = 0
            state.open_until = 0.0
        if was_open:
            self._save_state()  # -- #236: persist CLOSE transition only

    def reset(self, provider: str | None = None) -> None:
        """Reset breaker state for a provider (or all if None)."""
        with self._global_lock:
            if provider is None:
                self._states.clear()
            else:
                self._states.pop(provider, None)
        self._save_state()  # -- #236: persist reset


# -- Global shared circuit breaker for all adapters + dispatch
_GLOBAL_BREAKER = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    """Public accessor for the shared circuit breaker."""
    return _GLOBAL_BREAKER


# -- sig: mgh-6201.cd.bd955f.f1b0.f0b061
