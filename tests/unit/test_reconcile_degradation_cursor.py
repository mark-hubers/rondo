# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: reconcile MUST degrade — never crash, never silently skip.

VER-001 verification matrix — RONDO-359 reconcile (cursor-review findings #3 + #4,
spec STD-110 req 019). One code block, two failure modes.

THE BUG (observable failures this file pins):
    src/rondo/audit.py reconcile_stuck_intents() does an UNGUARDED `import fcntl`
    then `fcntl.flock(LOCK_EX | LOCK_NB)` on a `.reconcile.lock` sidecar.

    Finding #3 (Windows): on a platform with no fcntl, `import fcntl` raises
    ImportError. reconcile runs on every AuditTrail.__init__ when a jsonl exists,
    and __init__ only catches (OSError, TypeError, ValueError, AttributeError) —
    NOT ImportError — so it propagates and EVERY dispatch crashes at audit
    construction. STD-110 req 019 (MUST): where flock is unavailable (NFS/Windows)
    the code SHALL fall back to single-writer mode and emit a WARNING — never crash.

    Finding #4 (NFS): the `except OSError` around the flock acquire collapses
    EWOULDBLOCK (a peer holds the lock → correct to skip) with ENOLCK/EOPNOTSUPP
    (the filesystem cannot do flock at all, e.g. NFS) — both become "peer in
    progress; skip; return 0" at DEBUG. On NFS reconcile then NEVER runs and NEVER
    warns — the "silently skip" that req 019 forbids.

These tests assert the OBSERVABLE guarantee — construction never raises, the stuck
INTENT actually gets a synthetic OUTCOME when flock is unavailable, and a genuine
peer-held lock (EWOULDBLOCK) still skips idempotently — NOT any internal method
name or branch shape, so any correct fix (errno triage + ImportError guard
mirroring _append_jsonl's `except (ImportError, OSError)`) satisfies them.
"""

import errno
import json
import os
import sys
from unittest.mock import patch

import pytest

from rondo.audit import AuditConfig, AuditTrail

# -- The synthetic OUTCOME error_code reconcile writes for a stuck INTENT. Its
#    presence in the jsonl is the robust "reconcile actually ran" signal.
_STUCK_ERROR_CODE = "ERR_RECONCILED_STUCK"


def _seed_stuck_intent(audit_dir: str) -> str:
    """Seed a jsonl with one stuck INTENT (no matching OUTCOME) and return its id.

    Uses auto_reconcile=False and stuck_after_sec=0 so the INTENT is immediately
    eligible for reconcile (not treated as a fresh in-flight peer dispatch).
    """
    seed = AuditTrail(
        config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0),
        auto_reconcile=False,
    )
    rec = seed.record_intent(task_name="crashed", round_name="r", model="m", prompt="p")
    return rec.dispatch_id


def _stuck_outcomes(audit_dir: str, dispatch_id: str) -> list[dict]:
    """Return all synthetic stuck OUTCOME records for dispatch_id in the jsonl."""
    jsonl = os.path.join(audit_dir, "rondo_audit.jsonl")
    out: list[dict] = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("dispatch_id") == dispatch_id and rec.get("error_code") == _STUCK_ERROR_CODE:
                out.append(rec)
    return out


def test_reconcile_degrades_when_fcntl_unimportable(tmp_path) -> None:
    """Finding #3: no fcntl (Windows) must NOT crash __init__ — reconcile still runs.

    Block `import fcntl` (None in sys.modules raises ImportError, exactly like a
    platform without the module), seed a stuck INTENT, then build an AuditTrail
    with auto_reconcile=True. On current code the unguarded import raises
    ImportError, which __init__ does not catch, so construction blows up — and
    every dispatch with it. A correct fix degrades to single-writer mode, so
    construction succeeds AND the stuck INTENT still gets its synthetic OUTCOME.
    """
    audit_dir = str(tmp_path)
    dispatch_id = _seed_stuck_intent(audit_dir)

    with patch.dict(sys.modules, {"fcntl": None}):
        try:
            AuditTrail(
                config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0),
                auto_reconcile=True,
            )
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"AuditTrail construction crashed when fcntl is unavailable: {exc!r} "
                f"— must fall back to single-writer mode (STD-110 req 019), not propagate"
            )

    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert len(stuck) == 1, (
        f"reconcile did not run in single-writer fallback: expected 1 stuck OUTCOME "
        f"for {dispatch_id}, found {len(stuck)} (STD-110 req 019 — never silently skip)"
    )


def test_reconcile_runs_when_flock_unsupported_enolck(tmp_path) -> None:
    """Finding #4: flock ENOLCK (NFS, unsupported) must fall back — not silent-skip.

    Make every fcntl.flock call raise OSError(ENOLCK), simulating a filesystem
    that cannot do advisory locks at all. On current code the `except OSError`
    around the LOCK_NB acquire swallows this as "peer in progress; skip; return 0",
    so reconcile NEVER runs and NEVER warns. A correct fix distinguishes
    "unsupported" from "peer holds" and proceeds in single-writer mode, so the
    stuck INTENT still gets its synthetic OUTCOME.
    """
    audit_dir = str(tmp_path)
    dispatch_id = _seed_stuck_intent(audit_dir)

    enolck = OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))
    trail = AuditTrail(
        config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0),
        auto_reconcile=False,
    )
    with patch("fcntl.flock", side_effect=enolck):
        trail.reconcile_stuck_intents(stuck_after_sec=0)

    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert len(stuck) == 1, (
        f"reconcile silently skipped on ENOLCK (flock unsupported): expected 1 stuck "
        f"OUTCOME for {dispatch_id}, found {len(stuck)} (STD-110 req 019)"
    )


def test_reconcile_runs_when_flock_unsupported_eopnotsupp(tmp_path) -> None:
    """Finding #4: flock EOPNOTSUPP (NFS, unsupported) must fall back too.

    Same contract as the ENOLCK case for the other errno some kernels return when
    flock is not supported on the mount. Current code swallows it as a skip; a
    correct fix runs reconcile in single-writer mode.
    """
    audit_dir = str(tmp_path)
    dispatch_id = _seed_stuck_intent(audit_dir)

    eopnotsupp = OSError(errno.EOPNOTSUPP, os.strerror(errno.EOPNOTSUPP))
    trail = AuditTrail(
        config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0),
        auto_reconcile=False,
    )
    with patch("fcntl.flock", side_effect=eopnotsupp):
        trail.reconcile_stuck_intents(stuck_after_sec=0)

    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert len(stuck) == 1, (
        f"reconcile silently skipped on EOPNOTSUPP (flock unsupported): expected 1 "
        f"stuck OUTCOME for {dispatch_id}, found {len(stuck)} (STD-110 req 019)"
    )


def test_reconcile_skips_when_peer_holds_lock_ewouldblock(tmp_path) -> None:
    """Finding #4 (the OTHER side): EWOULDBLOCK (peer holds lock) MUST still skip.

    The fix must not over-correct: a genuine LOCK_NB contention — a peer process
    is mid-reconcile — should still skip idempotently (one process doing the
    housekeeping is enough), NOT fall back and double-write. Make flock raise
    OSError(EWOULDBLOCK); assert reconcile returns 0 and writes NO stuck OUTCOME.
    This passes on current code too; it pins the behaviour the fix must preserve.
    """
    audit_dir = str(tmp_path)
    dispatch_id = _seed_stuck_intent(audit_dir)

    ewouldblock = OSError(errno.EWOULDBLOCK, os.strerror(errno.EWOULDBLOCK))
    trail = AuditTrail(
        config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0),
        auto_reconcile=False,
    )
    with patch("fcntl.flock", side_effect=ewouldblock):
        reconciled = trail.reconcile_stuck_intents(stuck_after_sec=0)

    assert reconciled == 0, f"peer-held lock (EWOULDBLOCK) must skip, but reconcile claimed {reconciled} records"
    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert not stuck, (
        f"peer-held lock (EWOULDBLOCK) must skip idempotently, but a stuck OUTCOME "
        f"was written for {dispatch_id} — fix over-corrected the skip path"
    )


# -- sig: mgh-6201.cd.bd955f.2392.67d73c
