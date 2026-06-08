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


class TestIdempotencyBoundaries:
    """RONDO-364: kill the real survivors the mutation gate (RONDO-363) found.

    The single-flight tests above never exercised TTL expiry, disk persistence,
    the default path, or compaction — so mutating those lines left tests green
    (17 survivors). These pin the actual behavior; each assertion below is here
    because `bin/mutate` proved a mutant survived without it.
    """

    def test_memory_ttl_boundary_is_inclusive(self, monkeypatch, tmp_path) -> None:
        """In-memory layer: age == ttl is still VALID (kills `<=`→`<` at line 253)."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        import rondo.idempotency as idem

        clock = {"t": 1000.0}
        monkeypatch.setattr(idem.time, "time", lambda: clock["t"])
        idem.clear_cache()
        idem.cache_result("k", {"v": 1})  # -- cached_at = 1000

        clock["t"] = 1000.0 + idem.DEFAULT_TTL_SEC  # -- age == ttl exactly
        assert idem.get_cached_result("k") == {"v": 1}, "age==ttl must still be valid (inclusive)"
        clock["t"] = 1000.0 + idem.DEFAULT_TTL_SEC + 1  # -- age > ttl
        assert idem.get_cached_result("k") is None, "age>ttl must be expired"

    def test_file_scan_ttl_boundary_is_exclusive(self, monkeypatch, tmp_path) -> None:
        """File layer: cached_at == cutoff is EXPIRED (kills `<=`→`<` at line 158)."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        import rondo.idempotency as idem

        clock = {"t": 1000.0}
        monkeypatch.setattr(idem.time, "time", lambda: clock["t"])
        idem.clear_cache()
        idem.cache_result("k", {"v": 1})  # -- cached_at_wall = 1000

        idem._cache.clear()  # -- drop in-memory layer so the FILE scan is exercised
        clock["t"] = 1000.0 + idem.DEFAULT_TTL_SEC  # -- cutoff == cached_at -> skipped
        assert idem.get_cached_result("k") is None, "cached_at==cutoff must be treated as expired"

    def test_dict_result_persists_to_disk(self, monkeypatch, tmp_path) -> None:
        """A dict result survives a memory wipe via the JSONL file (kills line 225)."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        import rondo.idempotency as idem

        idem.clear_cache()
        idem.cache_result("k", {"a": 1})
        idem._cache.clear()  # -- force the disk path
        assert idem.get_cached_result("k") == {"a": 1}, "dict result not persisted to disk"

    def test_dataclass_result_persists_as_dict(self, monkeypatch, tmp_path) -> None:
        """A dataclass result is asdict()-serialized to disk (kills line 222)."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from dataclasses import dataclass

        import rondo.idempotency as idem

        @dataclass
        class _R:
            status: str = "done"
            cost: float = 0.5

        idem.clear_cache()
        idem.cache_result("k", _R())
        idem._cache.clear()  # -- force the disk path
        assert idem.get_cached_result("k") == {"status": "done", "cost": 0.5}, "dataclass not serialized to disk"

    def test_default_cache_file_without_test_dir(self, monkeypatch) -> None:
        """Default path resolves under ~/.rondo when RONDO_TEST_DIR is unset (kills line 100)."""
        monkeypatch.delenv("RONDO_TEST_DIR", raising=False)
        import rondo.idempotency as idem

        path = idem._default_cache_file()
        assert path.name == "idempotency.jsonl", f"wrong default filename: {path}"
        assert ".rondo" in str(path), f"default not under ~/.rondo: {path}"

    def test_compaction_collapses_duplicate_keys(self, monkeypatch, tmp_path) -> None:
        """Over threshold, compaction rewrites to one live line per key (kills line 197 concat)."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        import rondo.idempotency as idem

        monkeypatch.setattr(idem, "_COMPACT_THRESHOLD_BYTES", 50)  # -- tiny: trigger compaction
        idem.clear_cache()
        for i in range(20):
            idem.cache_result("samekey", {"v": i})  # -- 20 appends, ONE live key

        path = idem._default_cache_file()
        live = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(live) == 1, f"compaction did not collapse duplicate appends: {len(live)} lines"
        assert idem.get_cached_result("samekey") == {"v": 19}, "latest value lost after compaction"


# -- sig: mgh-6201.cd.bd955f.8b1c.48ea2d
