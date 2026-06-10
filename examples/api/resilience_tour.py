# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=local provider=none category=reliability value="Breaker trip/recovery + Retry-After + idempotency dedup in one deterministic story"

"""Rondo API example: the reliability primitives, end to end, no network.

What this demonstrates
----------------------
The three primitives every rondo dispatch rides on — exercised DIRECTLY and
deterministically (no AI call, no network, no API key):

* **Circuit breaker** (RONDO-145/361/372): failures trip it OPEN, OPEN
  short-circuits instantly, cooldown expiry auto-closes it. State persists to
  a file the same way the MCP server and CLI share trips cross-process.
* **retry_http + Retry-After** (RONDO-347/349): a transient 429 carrying a
  server Retry-After header sets a FLOOR on the wait — rondo never retries
  sooner than the provider asked (the patient schedule may wait longer,
  capped at max_delay_sec) — then the call succeeds.
* **Idempotency cache** (RONDO-147/360): the same prompt+model within the TTL
  is a cache HIT — the second identical dispatch never pays.

Everything prints honestly from the real modules — this is the production
machinery, just pointed at a temp directory.

Run::

    cd rondo && uv run python examples/api/resilience_tour.py
"""

from __future__ import annotations

import email.message
import os
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from example_dispatch import banner


def _tour_breaker(tmp: Path) -> bool:
    """Trip the breaker, watch it short-circuit, then recover after cooldown."""
    from rondo.retry import CircuitBreaker

    print(banner("1) Circuit breaker: trip -> OPEN -> cooldown -> recovery"))
    breaker = CircuitBreaker(failure_threshold=2, cooldown_sec=1.0, persist_path=tmp / "breaker.json")

    print(f"   fresh:        is_open={breaker.is_open('demo')}")
    breaker.record_failure("demo")
    breaker.record_failure("demo")  # -- threshold reached -> trips OPEN
    tripped = breaker.is_open("demo")
    print(f"   2 failures:   is_open={tripped}   (dispatches now short-circuit, no network)")

    # -- a SECOND instance on the same file sees the trip (cross-process share)
    peer = CircuitBreaker(failure_threshold=2, cooldown_sec=1.0, persist_path=tmp / "breaker.json")
    peer_sees = peer.is_open("demo")
    print(f"   peer process: is_open={peer_sees}   (persisted state, RONDO-372 safe on Windows)")

    time.sleep(1.1)  # -- cooldown expires
    recovered = not breaker.is_open("demo")
    print(f"   after 1.1s:   is_open={not recovered}   (auto-closed — provider gets another chance)")
    return tripped and peer_sees and recovered


def _tour_retry_after() -> bool:
    """A 429's Retry-After FLOORS the wait (never sooner than asked) — RONDO-347.

    The flat schedule would wait 3s here; the server asks 4s — rondo waits
    >= 4s. The header can lengthen a wait, never shorten one (max(), capped).
    """
    from rondo.retry import RetryConfig, retry_http

    print(banner("2) retry_http: Retry-After floors the wait — never retry sooner than asked"))
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            hdrs = email.message.Message()
            hdrs["Retry-After"] = "4"  # -- server asks 4s (> the 3s schedule -> floor binds)
            raise urllib.error.HTTPError(url="https://example", code=429, msg="rate limited", hdrs=hdrs, fp=None)
        return "second attempt succeeded"

    started = time.monotonic()
    outcome = retry_http(flaky, config=RetryConfig(jitter=False), provider_name="demo")
    waited = time.monotonic() - started
    print(f"   attempts={calls['n']}  waited={waited:.1f}s (schedule 3s, server asked 4s)  outcome={outcome!r}")
    return calls["n"] == 2 and waited >= 4.0


def _tour_idempotency() -> bool:
    """Identical prompt+model within TTL = cache hit, no second spend — RONDO-360."""
    from rondo.idempotency import cache_result, compute_idempotency_key, get_cached_result

    print(banner("3) Idempotency: the same dispatch twice only pays once"))
    key = compute_idempotency_key(prompt="Summarize the Q3 report", model="sonnet", execution="subprocess")
    first = get_cached_result(key)
    print(f"   first lookup:  {first!r}  (miss -> this dispatch would PAY)")
    cache_result(key, {"status": "done", "raw_output": "Q3 summary...", "cost_usd": 0.04})
    second = get_cached_result(key)
    hit = second is not None
    print(f"   second lookup: status={second.get('status') if hit else None!r}  (HIT -> no second spend)")
    return first is None and hit


def main() -> int:
    """Run the three-primitive resilience tour; exit 0 only if all behave."""
    with tempfile.TemporaryDirectory(prefix="rondo-resilience-") as tmp_str:
        # -- keep ALL state (breaker file, idempotency jsonl) in the temp dir
        os.environ["RONDO_TEST_DIR"] = tmp_str
        tmp = Path(tmp_str)
        results = [
            _tour_breaker(tmp),
            _tour_retry_after(),
            _tour_idempotency(),
        ]
    if all(results):
        print(banner("-PASS- all three reliability primitives behaved as documented"))
        return 0
    print(banner("-ERROR- a primitive misbehaved — see output above"))
    return 1


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.aa04.dbb2b4
