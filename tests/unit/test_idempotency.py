# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Single-flight idempotency — RONDO-360.

VER-001 verification matrix: dispatch-dedup concurrency contract.

cursor-review concurrency lens: lookup and store were each locked, but the
lookup→dispatch→store SEQUENCE was not. Two identical concurrent dispatches
both missed the cache and both PAID (duplicate billable call). The fix is a
single-flight per-key lock: identical concurrent dispatches serialize, only
the first pays, the rest find the cached result.
"""

from __future__ import annotations

import threading
import time


class TestKeyLockSingleFlight:
    """key_lock serializes same-key callers but not different keys."""

    def test_same_key_serialized(self) -> None:
        from rondo.idempotency import key_lock

        state = {"now": 0, "peak": 0}
        guard = threading.Lock()

        def _work() -> None:
            with key_lock("K"):
                with guard:
                    state["now"] += 1
                    state["peak"] = max(state["peak"], state["now"])
                time.sleep(0.05)
                with guard:
                    state["now"] -= 1

        threads = [threading.Thread(target=_work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert state["peak"] == 1, f"same-key not serialized: peak {state['peak']}"

    def test_different_keys_concurrent(self) -> None:
        from rondo.idempotency import key_lock

        state = {"now": 0, "peak": 0}
        guard = threading.Lock()

        def _work(k: str) -> None:
            with key_lock(k):
                with guard:
                    state["now"] += 1
                    state["peak"] = max(state["peak"], state["now"])
                time.sleep(0.05)
                with guard:
                    state["now"] -= 1

        threads = [threading.Thread(target=_work, args=(f"K{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert state["peak"] >= 2, "different keys must run concurrently"


class TestDispatchAndCacheDedup:
    """RONDO-360: two identical concurrent dispatches → ONE real dispatch."""

    def test_concurrent_same_key_dispatches_once(self, monkeypatch) -> None:
        import rondo.idempotency as _idem
        from rondo.mcp_dispatch import _dispatch_and_cache

        # -- hermetic cache (no real file/state bleed)
        monkeypatch.setattr(_idem, "_cache", {})
        paid = {"n": 0}
        paid_lock = threading.Lock()
        # -- barrier syncs the LAUNCH so all 3 contend on the key lock together;
        # -- it must NOT be inside dispatch_fn (single-flight runs that once).
        launch = threading.Barrier(3)

        def _dispatch_fn() -> dict:
            with paid_lock:
                paid["n"] += 1
            time.sleep(0.05)  # -- hold the critical section so peers pile up
            return {"status": "done", "raw_output": "ok"}

        results: list[str] = []
        res_lock = threading.Lock()

        def _go() -> None:
            launch.wait()
            out = _dispatch_and_cache("SHARED_KEY", _dispatch_fn, [])
            with res_lock:
                results.append(out)

        threads = [threading.Thread(target=_go) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert paid["n"] == 1, f"single-flight broken: {paid['n']} paid dispatches for one key"
        assert len(results) == 3, "all callers must get a result"


# -- sig: mgh-6201.cd.bd955f.8b1c.e0aa76
