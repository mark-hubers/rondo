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
import urllib.error
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
    """Retry configuration — tunable per provider.

    RONDO-349: flat patient schedule — first retry waits initial_delay_sec,
    every retry after waits subsequent_delay_sec. So with the defaults the
    waits are 3, 5, 5, 5 (across 5 attempts) — patient enough for rate
    limits without a special case, gentle on AI-dispatch latency. The
    server's Retry-After header still overrides when present.
    """

    max_attempts: int = 5
    initial_delay_sec: float = 3.0  # -- RONDO-349: first retry wait (was 0.5 — too fast for rate limits)
    subsequent_delay_sec: float = 5.0  # -- RONDO-349: every retry after the first
    max_delay_sec: float = 60.0  # -- ceiling (also bounds a server Retry-After)
    jitter: bool = True


def _scheduled_delay(attempt: int, cfg: RetryConfig) -> float:
    """Wait before the next retry — RONDO-349 flat schedule (3 then 5 flat)."""
    return cfg.initial_delay_sec if attempt == 1 else cfg.subsequent_delay_sec


# -- RONDO-348: cap simultaneous in-flight requests to ONE provider. Found via a
# -- live mistral micro-burst — 8 concurrent tasks overran the rate limit and 4
# -- died with ERR_RATE_LIMIT even WITH Retry-After. The gate spreads the burst
# -- into waves; different providers keep running fully in parallel (one
# -- semaphore PER provider name). 4 is generous enough never to throttle normal
# -- single dispatches, low enough to tame a pathological fan-out.
_MAX_INFLIGHT_PER_PROVIDER = 4
_provider_gates: dict[str, threading.BoundedSemaphore] = {}
_provider_gates_lock = threading.Lock()


def _provider_gate(provider_name: str) -> threading.BoundedSemaphore:
    """Lazily get the per-provider concurrency semaphore — RONDO-348."""
    with _provider_gates_lock:
        gate = _provider_gates.get(provider_name)
        if gate is None:
            gate = threading.BoundedSemaphore(_MAX_INFLIGHT_PER_PROVIDER)
            _provider_gates[provider_name] = gate
        return gate


def _reset_provider_gates() -> None:
    """Drop all gates so a new _MAX_INFLIGHT_PER_PROVIDER takes effect — tests only."""
    with _provider_gates_lock:
        _provider_gates.clear()


def _retry_after_sec(exc: Exception) -> float | None:
    """Read the HTTP `Retry-After` header (seconds) off an HTTPError — RONDO-347.

    Returns the requested wait in seconds, or None when the header is absent,
    non-numeric, or the exception isn't an HTTPError. Only the integer-seconds
    form is honored (the form every cloud provider sends on 429); the rarer
    HTTP-date form returns None and the caller falls back to backoff.
    """
    if not isinstance(exc, urllib.error.HTTPError):
        return None
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def is_transient_http_error(exc: Exception) -> bool:
    """Determine if an HTTP exception is transient (worth retrying).

    Retry: 5xx server errors, 429 rate limit, network/connection errors.
    Do NOT retry: 4xx client errors (auth, bad request, not found).
    """
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

    RONDO-349: flat schedule (first retry 3s, then 5s flat) with optional
    jitter; a server Retry-After header overrides it (capped). Non-transient
    errors (4xx client errors other than 429) fail immediately.
    """
    cfg = config or RetryConfig()
    last_exc: Exception | None = None

    # -- RONDO-209 #254: narrowed catch from 'Exception' to specific HTTP/network
    # -- types so a programmer error (NameError, TypeError, etc.) inside fn() is
    # -- NOT silently caught and treated as transient. Bug class: silent retry on
    # -- typo. Now those propagate immediately as crashes — louder = better.
    transient_types = (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        OSError,
    )

    # -- RONDO-348: hold a per-provider slot only during the actual call; the
    # -- gate is released across backoff sleeps so a waiting task can use the
    # -- slot, and different providers never block each other.
    gate = _provider_gate(provider_name)
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            with gate:
                return fn()
        except transient_types as exc:
            last_exc = exc
            if not is_transient_http_error(exc):
                # -- Non-transient (e.g., 4xx other than 429) → fail immediately
                raise
            if attempt >= cfg.max_attempts:
                # -- Last attempt — don't sleep, just fail
                break
            # -- RONDO-349: flat schedule (3s then 5s) with optional jitter.
            sleep_for = _scheduled_delay(attempt, cfg)
            if cfg.jitter:
                # -- secrets.randbelow is deterministic-safe; scale to [0.85, 1.15)
                jitter_factor = 0.85 + (secrets.randbelow(300) / 1000.0)
                sleep_for *= jitter_factor
            # -- RONDO-347: a server Retry-After (429) overrides the schedule —
            # -- wait exactly what the provider asks, capped so it can't hang us.
            asked = _retry_after_sec(exc)
            if asked is not None:
                sleep_for = max(sleep_for, asked)
            sleep_for = min(sleep_for, cfg.max_delay_sec)
            logger.info(
                "Retry %d/%d for %s after transient error: %s (sleeping %.2fs)",
                attempt,
                cfg.max_attempts,
                provider_name,
                str(exc)[:100],
                sleep_for,
            )
            time.sleep(sleep_for)

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
    # -- WALL-CLOCK (time.time()) so it survives restart/persist (#236). NOT
    # -- monotonic — an NTP step can mis-time a cooldown; accepted trade-off
    # -- (documented, RONDO-374 fixed this comment which lied "monotonic").
    open_until: float = 0.0  # -- wall-clock timestamp when circuit reopens
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
        # -- RONDO-361 #5/#7: (mtime, size) signature of the state file at last
        # -- load. is_open() re-reads only when the signature changed, so a peer's
        # -- later trip becomes visible to this LIVE instance. RONDO-368 #7: a
        # -- bare mtime missed a same-tick peer write (coarse/NFS clocks); pairing
        # -- it with file SIZE catches a trip that lands in the same mtime tick
        # -- (a new/changed entry always changes the size). Guarded by _sig_lock.
        self._sig_lock = threading.Lock()
        self._persist_sig: tuple[float, int] = (0.0, -1)
        self._load_state()

    def _get_state(self, provider: str) -> CircuitBreakerState:
        with self._global_lock:
            if provider not in self._states:
                self._states[provider] = CircuitBreakerState()
            return self._states[provider]

    def _save_state(self, force_drop: set[str] | None = None) -> None:
        """Persist OPEN circuit states to disk — #236 + #246.

        RONDO-209 #246: uses fcntl.flock() for cross-process exclusive lock
        around the read-modify-write of the JSON state file. Without this,
        two processes could race: A reads {}, B reads {}, A writes {X}, B
        writes {Y} — losing A's entry. With flock, only one process holds
        the write-lock at a time. The existing atomic tmp+replace ensures
        no partial reads.

        Only persists providers whose cooldown has not yet expired.
        Called on transitions only (OPEN/CLOSE), not every failure.

        force_drop (RONDO-361 #1): providers to remove from the merged payload
        even if still valid on disk — the ONLY way an entry is deliberately
        cleared (reset). The normal merge never deletes, so it can't clobber a
        peer's live cooldown; reset is the explicit, intentional exception.

        RONDO-372 (cursor holistic #2): the import is GUARDED — on Windows
        (no fcntl) a breaker transition MUST NOT crash (STD-110 r019). Falls
        back to single-writer persist with a WARNING: tmp+os.replace stays
        atomic; only the cross-process merge lock is lost. Exact twin of the
        RONDO-367 audit-reconcile fix.
        """
        try:
            import fcntl  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.warning("Breaker persist flock unavailable (no fcntl, e.g. Windows) — single-writer persist")
            self._persist_payload(force_drop)
            return

        try:
            # -- #246: merge with existing on-disk state to avoid losing
            # -- entries written by other processes. Hold an exclusive lock
            # -- from read through write to make the merge atomic cross-process.
            self._persist_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_path = self._persist_path.with_suffix(".lock")
            with open(lock_path, "a+", encoding="utf-8") as lock_f:
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                except OSError as lock_exc:
                    # -- RONDO-216 C3: ABORT persist if lock fails.
                    # -- Without the lock, read-merge-write overwrites peer state.
                    # -- Was "non-fatal continue" — changed to abort.
                    logger.warning("Breaker persist ABORTED — file lock failed: %s", lock_exc)
                    return
                try:
                    self._persist_payload(force_drop)
                finally:
                    try:
                        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Circuit breaker persist failed (non-fatal): %s", exc)

    def _persist_payload(self, force_drop: set[str] | None) -> None:
        """Read-merge-write the breaker state file — persist body (RONDO-372).

        Caller holds the cross-process flock when available; without fcntl
        (Windows) this runs single-writer — tmp+os.replace is still atomic.
        Non-fatal on I/O errors, like every persist path in this class.
        """
        try:
            now = time.time()
            self._persist_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            payload = self._read_existing_payload(now)
            self._apply_memory_states(payload, now)
            # -- RONDO-361 #1: explicit clears (reset) are the ONLY deletions.
            for provider in force_drop or ():
                payload.pop(provider, None)
            # -- Atomic write via tmp+replace.
            tmp_path = self._persist_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp_path, self._persist_path)
            # -- RONDO-361 #5: our own write is "seen" — don't reload it back.
            self._record_mtime()
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Circuit breaker persist failed (non-fatal): %s", exc)

    def _read_existing_payload(self, now: float) -> dict[str, dict[str, float]]:
        """Read still-valid peer entries from disk into a fresh payload — #246.

        Keeps entries written by OTHER processes whose cooldown hasn't expired,
        so our write merges with theirs instead of clobbering it.
        """
        existing: dict[str, Any] = {}
        if self._persist_path.exists():
            try:
                loaded = json.loads(self._persist_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            except (OSError, ValueError, json.JSONDecodeError):
                existing = {}
        payload: dict[str, dict[str, float]] = {}
        for provider, entry in existing.items():
            if not isinstance(entry, dict):
                continue
            open_until = float(entry.get("open_until", 0.0))
            if open_until > now:
                payload[provider] = {
                    "open_until": open_until,
                    "failure_count": float(entry.get("failure_count", 0.0)),
                }
        return payload

    def _apply_memory_states(self, payload: dict[str, dict[str, float]], now: float) -> None:
        """Merge in-memory OPEN states into payload, fail-closed — RONDO-361 #5/#6/#1.

        #6: open_until/failure_count are guarded by state.lock everywhere they
        are WRITTEN, so read them under that SAME lock here — not under
        _global_lock alone. We snapshot the dict items under _global_lock,
        release it, then take each state.lock individually (never both at once
        → no lock-order deadlock with _get_state, which holds only _global_lock).
        #5: fail-closed — if a peer's on-disk entry has a LATER cooldown, keep
        theirs (a reload/merge may extend backoff, never shorten it).
        #1 (cursor review): this method NEVER deletes a still-valid entry. The
        old `elif ... del payload[provider]` cleared a provider whenever OUR
        memory said CLOSED — but our memory is often stale-CLOSED while a PEER
        holds it OPEN on disk, so an unrelated save erased the peer's live trip
        (fail-OPEN). Expired entries are already dropped by _read_existing_payload
        (open_until > now filter); a deliberate clear goes through
        _save_state(force_drop=...). So a CLOSED in-memory state simply does not
        contribute — it can never remove a peer's live cooldown.
        """
        with self._global_lock:
            states_items = list(self._states.items())
        for provider, state in states_items:
            with state.lock:
                s_open_until = state.open_until
                s_failure = state.failure_count
            if s_open_until > now:
                prev = payload.get(provider, {})
                payload[provider] = {
                    "open_until": max(s_open_until, float(prev.get("open_until", 0.0))),
                    "failure_count": float(max(s_failure, int(prev.get("failure_count", 0)))),
                }

    def _persist_signature(self) -> tuple[float, int]:
        """Return the state file's (mtime, size) — the reload-change signal — RONDO-368 #7."""
        try:
            st = self._persist_path.stat()
        except OSError:
            return (0.0, -1)
        return (st.st_mtime, st.st_size)

    def _record_mtime(self) -> None:
        """Remember the state file's (mtime, size) so we only reload on change — #5/#7."""
        sig = self._persist_signature()
        with self._sig_lock:
            self._persist_sig = sig

    def _merge_disk_entry(self, provider: str, entry: object, now: float) -> None:
        """Merge one on-disk breaker entry into memory, FAIL-CLOSED — RONDO-361 #5.

        A provider's open_until only ever moves LATER (longer backoff), never
        earlier — so a reload can reveal a peer's trip but can never shorten a
        cooldown this instance already holds. Updates the existing state object
        in place so live references (held by is_open) stay valid.
        """
        if not isinstance(entry, dict):
            return
        open_until = float(entry.get("open_until", 0.0))
        if open_until <= now:
            return
        failure_count = int(entry.get("failure_count", self.failure_threshold))
        with self._global_lock:
            existing = self._states.get(provider)
            if existing is None:
                self._states[provider] = CircuitBreakerState(failure_count=failure_count, open_until=open_until)
                return
        # -- Update in place, fail-closed (keep the later cooldown).
        with existing.lock:
            if open_until > existing.open_until:
                existing.open_until = open_until
                existing.failure_count = max(existing.failure_count, failure_count)

    def _load_state(self) -> None:
        """Restore/refresh OPEN circuit states from disk — #236 + #246 + RONDO-361 #5.

        Merges disk state into memory fail-closed (see _merge_disk_entry). Called
        once at construction AND opportunistically by _maybe_reload when a peer
        process changes the file. Only loads entries still in their cooldown.
        Non-fatal on any error.
        """
        try:
            if not self._persist_path.exists():
                return
            raw = self._persist_path.read_text(encoding="utf-8")
            self._record_mtime()
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            now = time.time()
            for provider, entry in data.items():
                self._merge_disk_entry(provider, entry, now)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.debug("Circuit breaker load failed (non-fatal): %s", exc)

    def _maybe_reload(self) -> None:
        """Re-read disk state if a peer changed the file since our last load — #5/#7.

        One cheap stat() per call; full reparse only when the (mtime, size)
        signature changed. Pairing size with mtime (RONDO-368 #7) catches a peer
        trip that lands in the SAME mtime tick on a coarse/NFS clock — a new entry
        always grows the file even when the clock doesn't move.
        """
        current = self._persist_signature()
        if current == (0.0, -1):  # -- stat failed (file gone) — nothing to reload
            return
        with self._sig_lock:
            changed = current != self._persist_sig
        if changed:
            self._load_state()

    def is_open(self, provider: str) -> bool:
        """Check if circuit is open for this provider."""
        self._maybe_reload()  # -- RONDO-361 #5: see a peer's trip on a live instance
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
        return not transitioned

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
        """Reset breaker state for a provider (or all if None).

        RONDO-361 #1: reset is the ONE deliberate clear, so it passes force_drop
        to actually remove the entry from disk (the normal merge never deletes).
        For reset-all, drop every provider known in memory OR on disk.
        """
        with self._global_lock:
            known = set(self._states)
            if provider is None:
                self._states.clear()
            else:
                self._states.pop(provider, None)
        if provider is None:
            drop = known | set(self._read_existing_payload(time.time()))
        else:
            drop = {provider}
        self._save_state(force_drop=drop)  # -- #236 + #1: persist + clear on disk


# -- Global shared circuit breaker for all adapters + dispatch
_GLOBAL_BREAKER = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    """Public accessor for the shared circuit breaker."""
    return _GLOBAL_BREAKER


# -- sig: mgh-6201.cd.bd955f.3a15.adcfb3
