# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-1: BOUNDED in-memory idempotency cache.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor hit its monthly usage limit;
separation of duties preserved — a different AI authored these judges, Claude
implements; transcribed verbatim from the dispatch, cost $0.005, audit-logged).

THE BUG (re-score finding #1, review-20260610-184904.md, MED-HIGH): module
_cache is UNBOUNDED — one tuple holding a full result payload per unique key,
forever, on the long-lived MCP server; eviction only on same-key re-lookup.
The in-memory twin of the RONDO-369/396 disk/lock leaks.

THE CONTRACT: (a) bounded at _MAX_MEMORY_ENTRIES, oldest-out by cached_at;
(b) TTL-expired entries swept during inserts; (c) memory eviction is never a
correctness loss (JSONL layer re-promotes); (d) fresh inserts survive their
own insertion; (e) thread-safe under concurrent inserts.

Tests access idem._cache directly — it IS the subject under test.
"""

from __future__ import annotations

import threading

import pytest

import rondo.idempotency as idem


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Redirect the JSONL layer to tmp and clear both layers around each test."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    idem.clear_cache()
    yield
    idem.clear_cache()


@pytest.fixture
def fake_time(monkeypatch):
    """Deterministic time source — controls cached_at ordering and TTL aging."""

    class FakeTimeModule:
        """Stands in for the stdlib time module inside rondo.idempotency."""

        def __init__(self) -> None:
            self.t = 1000.0

        def time(self) -> float:
            self.t += 1.0
            return self.t

        def monotonic(self) -> float:  # -- bounded-lock path safety
            return self.t

        def sleep(self, _sec: float) -> None:  # -- bounded-lock path safety
            self.t += _sec

    fake = FakeTimeModule()
    monkeypatch.setattr("rondo.idempotency.time", fake)
    return fake


def test_cache_memory_is_bounded() -> None:
    """(a) Insert past the bound evicts OLDEST by cached_at; insert never fails."""
    bound = getattr(idem, "_MAX_MEMORY_ENTRIES", 512)
    for i in range(bound + 10):
        idem.cache_result(f"key_{i}", {"data": i})

    # -- idem._cache accessed directly: it is the subject of the test.
    assert len(idem._cache) <= bound
    for i in range(10):
        assert f"key_{i}" not in idem._cache
    assert f"key_{bound + 9}" in idem._cache


def test_expired_sweep_on_insert(fake_time) -> None:
    """(b) TTL-expired entries get removed during inserts (no same-key re-lookup needed)."""
    idem.cache_result("old_key", "old_val")

    fake_time.t += idem.DEFAULT_TTL_SEC + 10.0

    idem.cache_result("new_key", "new_val")

    assert "old_key" not in idem._cache
    assert "new_key" in idem._cache


def test_disk_fallback_for_evicted_keys() -> None:
    """(c) A memory-evicted key still resolves via get_cached_result (JSONL re-promotes).

    Harness note (documented re-point, not an assertion change): the author's
    original fixture was a bare string, but _serialize_result persists only
    dataclasses/dicts to the JSONL — strings are memory-only BY DESIGN. Real
    cached values are serialized-TaskResult dicts, so the fixture is a dict.
    """
    bound = getattr(idem, "_MAX_MEMORY_ENTRIES", 512)

    idem.cache_result("target_key", {"v": "target_val"})

    for i in range(bound + 5):
        idem.cache_result(f"filler_{i}", {"v": "filler_val"})

    assert "target_key" not in idem._cache

    result = idem.get_cached_result("target_key")
    assert result == {"v": "target_val"}
    assert "target_key" in idem._cache


def test_fresh_survives_eviction() -> None:
    """(d) A just-inserted key is never evicted by its own insert; oldest goes first."""
    bound = getattr(idem, "_MAX_MEMORY_ENTRIES", 512)

    for i in range(bound):
        idem.cache_result(f"initial_{i}", "val")

    idem.cache_result("fresh_key", "fresh_val")

    assert "fresh_key" in idem._cache
    assert len(idem._cache) <= bound


def test_concurrent_inserts_thread_safe() -> None:
    """(e) Concurrent cache_result from 8 threads x 200 keys: no exception, len <= bound."""
    bound = getattr(idem, "_MAX_MEMORY_ENTRIES", 512)
    threads = []
    exceptions: list[Exception] = []

    def worker(thread_id: int) -> None:
        try:
            for i in range(200):
                idem.cache_result(f"t{thread_id}_k{i}", f"val_{i}")
        except Exception as exc:  # noqa: BLE001 -- collecting for the assertion
            exceptions.append(exc)

    for t_id in range(8):
        t = threading.Thread(target=worker, args=(t_id,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10.0)

    assert not exceptions, f"exceptions during concurrent inserts: {exceptions}"
    assert len(idem._cache) <= bound


# -- sig: mgh-6201.cd.bd955f.9afc.63b17e
