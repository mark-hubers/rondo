# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Idempotency key-lock eviction — RONDO-360 finding #9 (cursor-review).

VER-001 verification matrix: per-key lock map must stay bounded.

cursor-review memory lens: key_lock() does
    with _key_locks_guard:
        lk = _key_locks.setdefault(key, threading.Lock())
    with lk:
        yield
Every DISTINCT idempotency key (a SHA-256 of every unique prompt+model+
execution) inserts a threading.Lock into the module-global _key_locks dict
that is NEVER evicted. The MCP server is a long-lived process; over days of
varied prompts _key_locks grows without bound — an unbounded memory leak.

These regression tests pin the OBSERVABLE contract the eviction fix must
satisfy, independent of HOW it evicts (ref-count, LRU, or TTL):
  1. After many distinct keys go in-and-out sequentially, _key_locks is
     bounded (NOT one entry per key). FAILS on current code.
  2. The RONDO-360 single-flight guarantee survives eviction: same-key
     callers serialize (peak == 1), different keys run concurrently (peak >= 2).
  3. A lock that is currently in-flight (held) is retained, never evicted out
     from under a waiting caller.
"""

from __future__ import annotations

import threading
import time

# -- Bound the fix may not exceed. The leak makes len == n_keys (e.g. 1000);
# -- any sane eviction strategy keeps far fewer than this around at rest.
_BOUND = 8


def _reset_key_locks() -> None:
    """Clear the module-global _key_locks under its guard so prior tests don't pollute the count."""
    import rondo.idempotency as idem

    with idem._key_locks_guard:
        idem._key_locks.clear()


def test_distinct_keys_do_not_leak_locks() -> None:
    """1000 distinct keys cycled sequentially must NOT each leave a retained lock — bounded map.

    FAILS against current code: the map equals the distinct-key count (1000).
    """
    import rondo.idempotency as idem

    _reset_key_locks()

    n_keys = 1000
    for i in range(n_keys):
        with idem.key_lock(f"leak-key-{i}"):
            pass  # -- enter + exit; key is no longer in-flight after this block

    retained = len(idem._key_locks)
    assert retained <= _BOUND, (
        f"key-lock memory leak: {retained} locks retained for {n_keys} distinct keys "
        f"(expected bounded <= {_BOUND}; map must not grow per-key)"
    )


def test_single_flight_preserved_under_eviction() -> None:
    """Eviction must not break RONDO-360: same key serializes (peak==1), different keys run concurrently (peak>=2)."""
    import rondo.idempotency as idem

    _reset_key_locks()

    same = {"now": 0, "peak": 0}
    diff = {"now": 0, "peak": 0}
    guard = threading.Lock()

    def _work(state: dict, key: str) -> None:
        with idem.key_lock(key):
            with guard:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with guard:
                state["now"] -= 1

    same_threads = [threading.Thread(target=_work, args=(same, "SAME")) for _ in range(4)]
    for t in same_threads:
        t.start()
    for t in same_threads:
        t.join()
    assert same["peak"] == 1, f"same-key not serialized after eviction change: peak {same['peak']}"

    diff_threads = [threading.Thread(target=_work, args=(diff, f"DIFF-{i}")) for i in range(3)]
    for t in diff_threads:
        t.start()
    for t in diff_threads:
        t.join()
    assert diff["peak"] >= 2, f"different keys must still run concurrently: peak {diff['peak']}"


def test_in_flight_lock_is_retained() -> None:
    """A key held in its critical section must keep its lock entry — eviction only when no longer in use."""
    import rondo.idempotency as idem

    _reset_key_locks()

    entered = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with idem.key_lock("HELD"):
            entered.set()
            release.wait(timeout=2.0)

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert entered.wait(timeout=2.0), "holder thread never entered the critical section"

        # -- The in-use lock must still be present (not evicted out from under the holder).
        with idem._key_locks_guard:
            present = "HELD" in idem._key_locks
        assert present, "in-flight key lock was evicted while still held"
    finally:
        release.set()
        holder.join(timeout=2.0)


# -- sig: mgh-6201.cd.bd955f.f8d5.80d2aa
