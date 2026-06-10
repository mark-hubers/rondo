# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression tests for quality-checklist item 21: WRITE LOCK on idempotency appends.

``src/rondo/idempotency.py`` ``_append_cache_entry()`` writes one JSONL line with a
bare ``open(path, "a") + write``. Its comment claimed PIPE_BUF atomicity, which is
FALSE for entries larger than ~4-8KB: two processes appending large entries
concurrently can interleave bytes and tear lines.

Mark's ruling: ADD A WRITE LOCK — mirror the proven ``audit.py`` ``_append_jsonl()``
pattern (``fcntl.flock(LOCK_EX)`` held around write+flush, with
``except (ImportError, OSError)`` falling back to a best-effort write + warning so
Windows stays safe).

The fix is NOT written yet, so these pin the OBSERVABLE contract:
  (a) cache_result of a LARGE entry acquires an exclusive ``fcntl.flock`` (LOCK_EX)
      around the append — MUST FAIL on current code (no flock call happens).
  (b) with the fcntl import blocked, cache_result of a large entry still succeeds and
      the entry reads back — Windows/ImportError degradation (may pass today).
  (c) functional rail: a ~64KB entry round-trips through the JSONL file intact
      (passes today; pins no-regression).

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import sys
from unittest import mock

# -- ~64KB payload: comfortably past PIPE_BUF, the size at which a bare append tears.
_LARGE_RAW_OUTPUT = "x" * (64 * 1024)
_LARGE_RESULT = {"status": "done", "raw_output": _LARGE_RAW_OUTPUT}


def _fresh_idem(monkeypatch, tmp_path):
    """Return the idempotency module on a hermetic tmp file with caches cleared.

    Mirrors test_idempotency.py: RONDO_TEST_DIR isolation + clear_cache() drops
    both the in-memory and file layers so each test starts clean.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    import rondo.idempotency as idem

    idem.clear_cache()
    idem._cache.clear()
    return idem


def test_large_append_acquires_exclusive_flock(monkeypatch, tmp_path) -> None:
    """(a) cache_result of a LARGE entry must flock(LOCK_EX) the JSONL handle.

    MUST FAIL on current code: the bare open(path, "a") + write takes no lock.
    After the fix (mirroring audit._append_jsonl), an exclusive flock is held
    around the append.
    """
    import fcntl

    idem = _fresh_idem(monkeypatch, tmp_path)

    with mock.patch("fcntl.flock") as mock_flock:
        idem.cache_result("big-key", _LARGE_RESULT)

    lock_ex_calls = [call for call in mock_flock.call_args_list if fcntl.LOCK_EX in call.args]
    assert lock_ex_calls, "expected an exclusive fcntl.flock(LOCK_EX) around the large JSONL append"


def test_large_append_degrades_without_fcntl(monkeypatch, tmp_path) -> None:
    """(b) With fcntl import blocked, a large cache_result still succeeds and reads back.

    Pins the Windows/ImportError fallback: the append degrades to a best-effort
    write rather than raising. May pass today (no fcntl usage in the append yet);
    it locks the degradation contract for after the fix.
    """
    idem = _fresh_idem(monkeypatch, tmp_path)

    with mock.patch.dict(sys.modules, {"fcntl": None}):
        idem.cache_result("nofcntl-key", _LARGE_RESULT)
        idem._cache.clear()  # -- force the FILE path so the on-disk append is exercised
        recovered = idem.get_cached_result("nofcntl-key")

    assert recovered == _LARGE_RESULT, "large entry must persist + read back even with fcntl unavailable"


def test_large_entry_roundtrips_intact(monkeypatch, tmp_path) -> None:
    """(c) Functional rail: a ~64KB entry round-trips through the JSONL file intact.

    Passes today — pins no-regression: cache_result then get_cached_result (after
    a memory wipe to force the disk scan) returns the entry byte-for-byte.
    """
    idem = _fresh_idem(monkeypatch, tmp_path)

    idem.cache_result("roundtrip-key", _LARGE_RESULT)
    idem._cache.clear()  # -- drop in-memory layer so the FILE scan must reconstruct it
    recovered = idem.get_cached_result("roundtrip-key")

    assert recovered == _LARGE_RESULT, "large entry must survive the JSONL round-trip unchanged"
    assert recovered["raw_output"] == _LARGE_RAW_OUTPUT, "64KB payload must be byte-for-byte intact"


# -- sig: mgh-6201.cd.bd955f.633e.ba7254
