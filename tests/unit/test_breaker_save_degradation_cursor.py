# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: CircuitBreaker._save_state MUST degrade — never crash on no-fcntl.

VER-001 verification matrix — RONDO-145 circuit breaker (cursor holistic review
finding #2, spec STD-110 req 019). The exact twin of the audit.py reconcile bug
pinned in test_reconcile_degradation_cursor.py.

THE BUG (observable failures this file pins):
    src/rondo/retry.py CircuitBreaker._save_state() does an UNGUARDED
    `import fcntl` (~line 286) BEFORE its try block, and the except clause
    catches only (OSError, TypeError, ValueError) — NOT ImportError.

    On Windows (no fcntl module) the FIRST breaker state transition that calls
    _save_state — record_failure tripping OPEN, is_open auto-closing, or reset() —
    raises ImportError straight out of the adapter error path. A hard crash on the
    FAILURE path: the breaker exists precisely to make failures safe, so blowing up
    while recording one is the worst possible time. STD-110 req 019 (MUST): where
    flock is unavailable (NFS/Windows) the code SHALL fall back to single-writer
    mode and emit a WARNING — never crash.

These tests assert the OBSERVABLE guarantee — a full trip survives with no
ImportError escaping AND the in-process breaker still works (is_open True after the
trip), success/reset survive too, and a second instance's load tolerates the
degraded persist state — NOT any internal method name or branch shape, so any
correct fix (an ImportError guard mirroring _load_state's tolerant except, or a
module-level guarded import + single-writer fallback) satisfies them.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rondo.retry import CircuitBreaker

# -- Block `import fcntl` exactly like a platform without the module: None in
#    sys.modules makes `import fcntl` raise ImportError (CPython import protocol).
_NO_FCNTL = {"fcntl": None}


def _breaker(tmp_path: Path) -> CircuitBreaker:
    """Build a breaker with a low threshold and a tmp_path persist file."""
    return CircuitBreaker(
        failure_threshold=2,
        cooldown_sec=60.0,
        persist_path=tmp_path / "circuit_breaker.json",
    )


def _trip(breaker: CircuitBreaker, provider: str = "openai") -> None:
    """Drive a breaker to its OPEN threshold via record_failure (the trip path)."""
    for _ in range(breaker.failure_threshold):
        breaker.record_failure(provider)


def test_breaker_trip_survives_when_fcntl_unimportable(tmp_path) -> None:
    """Finding #2: no fcntl (Windows) must NOT crash the trip — breaker still works.

    Block `import fcntl`, then build a breaker and drive a FULL trip
    (record_failure to threshold). On current code the unguarded import in
    _save_state raises ImportError on the OPEN transition, which the adapter error
    path does not catch — so recording a failure crashes. A correct fix degrades to
    single-writer mode: (a) no ImportError escapes construction, the trip, or
    is_open, and (b) the in-process guarantee survives the dead persistence layer —
    is_open returns True after the trip.
    """
    provider = "openai"
    with patch.dict(sys.modules, _NO_FCNTL):
        try:
            breaker = _breaker(tmp_path)
            _trip(breaker, provider)
            tripped_open = breaker.is_open(provider)
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"CircuitBreaker crashed when fcntl is unavailable: {exc!r} — the trip "
                f"path must fall back to single-writer mode (STD-110 req 019), not propagate"
            )

    assert tripped_open is True, (
        "breaker lost its in-process guarantee when persistence degraded: is_open "
        "must be True after a full trip even with no fcntl (the in-memory state must "
        "not die with the disk layer)"
    )


def test_breaker_success_and_reset_survive_when_fcntl_unimportable(tmp_path) -> None:
    """Finding #2: in a no-fcntl world record_success and reset() must not raise.

    Both record_success (on an open breaker → CLOSE transition) and reset() persist
    via _save_state, so both hit the same unguarded `import fcntl`. Trip the breaker
    first so record_success takes its was_open persist branch. On current code each
    raises ImportError; a correct fix degrades silently to single-writer mode.
    """
    provider = "grok"
    with patch.dict(sys.modules, _NO_FCNTL):
        try:
            breaker = _breaker(tmp_path)
            _trip(breaker, provider)
            breaker.record_success(provider)
            breaker.reset(provider)
            breaker.reset()
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"record_success/reset crashed when fcntl is unavailable: {exc!r} — "
                f"every transition must degrade to single-writer mode (STD-110 req 019)"
            )

    assert breaker.is_open(provider) is False, "reset must leave the provider closed in memory"


def test_second_instance_load_tolerates_degraded_persist(tmp_path) -> None:
    """Finding #2 (the other side): a fresh instance must construct under no-fcntl.

    Under the fallback the first breaker can't reliably persist its trip, so a
    SECOND instance on the same path cannot be expected to SEE the trip — we do NOT
    assert cross-process visibility here. We assert only the safety property: the
    degraded persist state (file absent, or written single-writer) does NOT crash a
    new instance's _load_state, and its is_open is callable and returns a bool.
    """
    persist = tmp_path / "circuit_breaker.json"
    provider = "mistral"
    with patch.dict(sys.modules, _NO_FCNTL):
        first = CircuitBreaker(failure_threshold=2, cooldown_sec=60.0, persist_path=persist)
        for _ in range(2):
            first.record_failure(provider)

        try:
            second = CircuitBreaker(failure_threshold=2, cooldown_sec=60.0, persist_path=persist)
            second_open = second.is_open(provider)
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"a second breaker instance crashed loading degraded persist state: {exc!r} "
                f"— _load_state must tolerate the no-fcntl fallback (STD-110 req 019)"
            )

    assert isinstance(second_open, bool), "is_open must remain callable and return a bool under fallback"


# -- sig: mgh-6201.cd.bd955f.122c.d3332e
