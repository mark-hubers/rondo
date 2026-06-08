# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.retry — HTTP retry/backoff + Retry-After honoring.

VER-001 verification matrix: transient-retry contract.

RONDO-347 (found LIVE): a real 80-vote cloud panel lost 9 mistral votes to
HTTP 429. retry_http DID retry, but ignored the server's `Retry-After`
header — it slept a fixed 0.5/1/2s and gave up while mistral was asking for
much longer. The fix: honor Retry-After (capped), so we wait exactly as long
as the provider tells us. These tests pin both the new behavior AND the
unmocked real-HTTPError shape the parser depends on.
"""

from __future__ import annotations

import email.message
import time
import urllib.error

import pytest

from rondo.retry import RetryConfig, _retry_after_sec, is_transient_http_error, retry_http


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    """Build a real urllib HTTPError, optionally carrying a Retry-After header."""
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(url="https://x", code=code, msg="boom", hdrs=hdrs, fp=None)


class TestRetryAfterParsing:
    """_retry_after_sec reads the header off a REAL HTTPError (unmocked seam)."""

    def test_reads_integer_seconds(self) -> None:
        assert _retry_after_sec(_http_error(429, "30")) == 30.0

    def test_absent_header_is_none(self) -> None:
        assert _retry_after_sec(_http_error(429)) is None

    def test_garbage_header_is_none(self) -> None:
        assert _retry_after_sec(_http_error(429, "soon-ish")) is None

    def test_non_httperror_is_none(self) -> None:
        assert _retry_after_sec(TimeoutError("net")) is None


class TestRetryHonorsRetryAfter:
    """retry_http waits what the server asks on 429 — the RONDO-347 fix."""

    def test_honors_retry_after_over_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, "5")
            return "ok"

        assert retry_http(fn, provider_name="mistral") == "ok"
        assert slept and slept[0] >= 5.0, f"expected >=5s wait from Retry-After, got {slept}"

    def test_retry_after_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, "99999")
            return "ok"

        retry_http(fn, provider_name="mistral")
        assert slept[0] <= 60.0, f"a hostile Retry-After must be capped, slept {slept[0]}"

    def test_flat_schedule_3_then_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RONDO-349: waits follow 3s then 5s flat (no Retry-After header)."""
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] < 4:  # -- fail 3 times → 3 waits recorded
                raise _http_error(503)
            return "ok"

        retry_http(fn, provider_name="grok", config=RetryConfig(jitter=False))
        assert slept == [3.0, 5.0, 5.0], f"schedule must be 3 then 5 flat, got {slept}"

    def test_non_transient_fails_without_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)

        def fn() -> str:
            raise _http_error(400)

        with pytest.raises(urllib.error.HTTPError):
            retry_http(fn, provider_name="mistral")
        assert not slept, "4xx (non-429) must fail immediately, no sleep"

    def test_429_no_header_is_patient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RONDO-349: a 429 without Retry-After (mistral) waits >=3s.

        The old 0.5s first wait exhausted before the window cleared, losing
        live votes; the patient schedule gives the limit time to reset.
        """
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429)
            return "ok"

        retry_http(fn, provider_name="mistral", config=RetryConfig(jitter=False))
        assert slept and slept[0] >= 3.0, f"429 not patient enough, slept {slept}"

    def test_429_is_transient(self) -> None:
        assert is_transient_http_error(_http_error(429))


class TestPerProviderConcurrencyGate:
    """Per-provider concurrency gate — RONDO-348.

    Found via a live mistral micro-burst: 8 concurrent tasks overran the limit
    and 4 died with ERR_RATE_LIMIT even with Retry-After. The gate spreads the
    burst; different providers still run fully in parallel.
    """

    def test_same_provider_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No more than the cap of one provider's calls run at once."""
        import threading

        from rondo import retry as _retry

        monkeypatch.setattr(_retry, "_MAX_INFLIGHT_PER_PROVIDER", 2)
        _retry._reset_provider_gates()  # -- fresh semaphores at the new cap

        lock = threading.Lock()
        state = {"now": 0, "peak": 0}

        def fn() -> str:
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return "ok"

        threads = [threading.Thread(target=lambda: retry_http(fn, provider_name="mistral")) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert state["peak"] <= 2, f"gate breached: {state['peak']} mistral calls ran at once (cap 2)"

    def test_different_providers_not_serialized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The gate is PER provider — gemini and grok still run concurrently."""
        import threading

        from rondo import retry as _retry

        monkeypatch.setattr(_retry, "_MAX_INFLIGHT_PER_PROVIDER", 1)
        _retry._reset_provider_gates()

        lock = threading.Lock()
        state = {"now": 0, "peak": 0}

        def fn() -> str:
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return "ok"

        # -- one mistral + one gemini: cap-1 EACH, but cross-provider concurrent
        threads = [
            threading.Thread(target=lambda: retry_http(fn, provider_name="mistral")),
            threading.Thread(target=lambda: retry_http(fn, provider_name="gemini")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert state["peak"] == 2, f"different providers must overlap, peak was {state['peak']}"


class TestBreakerLiveShare:
    """RONDO-361 (cursor concurrency #5): a LIVE breaker sees a peer's later trip.

    Not just trips that existed at its construction.
    The existing multiprocess test only checks an instance built AFTER the
    trip (it loads at construction). This pins the uncovered gap: instance B
    exists FIRST, then A trips. B.is_open() must re-read disk and report OPEN,
    otherwise B keeps hammering a provider a peer already knows is down.
    """

    def test_live_instance_sees_peer_trip(self, tmp_path) -> None:
        from rondo.retry import CircuitBreaker

        persist = tmp_path / "breaker.json"
        # -- Two instances share one file = two processes. B is built BEFORE
        # -- the trip, so its construction-time load saw an empty/closed state.
        breaker_a = CircuitBreaker(failure_threshold=2, cooldown_sec=300.0, persist_path=persist)
        breaker_b = CircuitBreaker(failure_threshold=2, cooldown_sec=300.0, persist_path=persist)

        assert breaker_b.is_open("prod") is False  # -- nothing tripped yet

        # -- Peer A trips the breaker AFTER B already exists.
        breaker_a.record_failure("prod")
        breaker_a.record_failure("prod")
        assert breaker_a.is_open("prod") is True

        # -- B never re-read before the fix → would say CLOSED and keep hammering.
        assert breaker_b.is_open("prod") is True, "live instance blind to peer trip"

    def test_reload_is_fail_closed_keeps_longer_cooldown(self, tmp_path) -> None:
        """A disk reload must never SHORTEN an in-memory open_until (fail-closed).

        If this instance has a longer local cooldown than what's on disk, a
        reload must keep the longer one — backing off MORE is always safe.
        """
        from rondo.retry import CircuitBreaker

        persist = tmp_path / "breaker.json"
        breaker_a = CircuitBreaker(failure_threshold=2, cooldown_sec=10.0, persist_path=persist)
        breaker_b = CircuitBreaker(failure_threshold=2, cooldown_sec=10000.0, persist_path=persist)

        # -- B trips with a long cooldown (in memory + on disk).
        breaker_b.record_failure("prod")
        breaker_b.record_failure("prod")
        long_open_until = breaker_b._states["prod"].open_until

        # -- A trips with a SHORT cooldown, overwriting disk with a sooner time.
        breaker_a.record_failure("prod")
        breaker_a.record_failure("prod")

        # -- B re-reads on is_open; must NOT adopt A's sooner open_until.
        assert breaker_b.is_open("prod") is True
        assert breaker_b._states["prod"].open_until == long_open_until, "reload shortened cooldown"


class TestBreakerSaveUnderLock:
    """RONDO-361 (cursor concurrency #6): _save_state reads each state under its own lock.

    Not a different lock.
    open_until/failure_count are guarded by state.lock everywhere they are
    WRITTEN, but the persist merge read them under _global_lock only — a
    formal data race (in CPython the GIL masks torn primitive reads, so this
    is a convergence guard: under concurrent trips, every trip must land on
    disk with no lost entries).
    """

    def test_concurrent_trips_all_persist(self, tmp_path) -> None:
        import json as _json
        import threading as _threading

        from rondo.retry import CircuitBreaker

        persist = tmp_path / "breaker.json"
        breaker = CircuitBreaker(failure_threshold=1, cooldown_sec=300.0, persist_path=persist)

        providers = [f"p{i}" for i in range(24)]
        launch = _threading.Barrier(len(providers))

        def _trip(name: str) -> None:
            launch.wait()
            breaker.record_failure(name)  # -- threshold=1 → trips + persists immediately

        threads = [_threading.Thread(target=_trip, args=(p,)) for p in providers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        on_disk = _json.loads(persist.read_text(encoding="utf-8"))
        missing = [p for p in providers if p not in on_disk]
        assert not missing, f"concurrent trips lost on disk: {missing}"


# -- sig: mgh-6201.cd.bd955f.87bf.2fde94
