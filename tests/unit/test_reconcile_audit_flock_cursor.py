# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: reconcile MUST hold LOCK_EX on the AUDIT JSONL itself — STD-110 r016.

VER-001 verification matrix — ROAD-TO-8 item 8.6 (re-score finding R6), spec
STD-110 req 016 literal: the reconcile read-modify-write SHALL be serialized
against concurrent appends on the SAME lock _append_jsonl uses (the audit JSONL),
not merely a sidecar.

THE HOLE this file pins (src/rondo/audit.py):
    _append_jsonl (~line 635) takes fcntl.flock(LOCK_EX) on the AUDIT FILE
    (rondo_audit.jsonl) for every append. But _reconcile_cross_process (~line 746)
    locks only a SIDECAR (rondo_audit.jsonl.reconcile.lock) for its scan+write
    critical section. So an appender and a reconciler NEVER contend on the same
    lock: a genuine OUTCOME can land between reconcile's scan and its synthetic
    "stuck" write, and the same dispatch_id ends up with BOTH a real OUTCOME and a
    synthetic status="stuck" OUTCOME — the exact r016 read-modify-write race
    RONDO-359 was meant to close cross-process.

THE CONTRACT (asserted by these tests as OBSERVABLE behaviour, not method shape):
    (a) While reconcile is inside its scan+write critical section it ALSO holds
        LOCK_EX on the audit JSONL — so concurrent appends serialize against it.
    (b) Proof: a foreign process taking LOCK_EX|LOCK_NB on the audit JSONL while
        reconcile is mid-critical-section MUST get EWOULDBLOCK.
    (c) Degradation rails unchanged (pinned by tests/unit/test_reconcile_*).
    (d) Behaviour otherwise unchanged: stuck INTENTs still get synthetic OUTCOMEs;
        paired INTENTs untouched; sidecar peer-skip semantics unchanged.

Tests 1 + 2 are RED on today's code (no lock on the JSONL during reconcile).
Tests 3 + 4 pin behaviour the fix MUST preserve and pass today.

Synchronization is by threading.Event + bounded timeouts ONLY — never sleeps.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import UTC, datetime

import pytest

from rondo.audit import AuditConfig, AuditRecord, AuditTrail

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised only on non-POSIX
    _fcntl = None  # type: ignore[assignment]

# -- The audit-file flock contract is a POSIX fcntl guarantee. On a platform
#    without fcntl the degradation rails (test_reconcile_degradation_cursor.py)
#    govern instead, so these contention proofs are skipped there.
requires_fcntl = pytest.mark.skipif(_fcntl is None, reason="POSIX fcntl required for audit-file flock contract")

# -- The synthetic OUTCOME error_code reconcile stamps on a stuck INTENT — the
#    robust "reconcile actually wrote a stuck outcome" signal in the JSONL.
_STUCK_ERROR_CODE = "ERR_RECONCILED_STUCK"

# -- Hard per-wait ceiling. Every Event.wait / join / subprocess is bounded by
#    this so no test can hang; tests 1/2 stay under the 10s budget, suite < 15s.
_HARD_TIMEOUT_SEC = 9.0

# -- Window we wait to PROVE an append did not complete while reconcile holds the
#    lock. On today's (buggy) code the append finishes in milliseconds so this is
#    never fully consumed; only the GREEN/blocked path waits the whole window.
_CONTENTION_WINDOW_SEC = 2.0

# -- Subprocess exit code meaning "LOCK_EX|LOCK_NB on the JSONL was DENIED
#    (EWOULDBLOCK)" — i.e. reconcile genuinely holds the audit-file lock.
_EXIT_EWOULDBLOCK = 42

# -- A real second process (sys.executable -c) that opens the audit JSONL and
#    attempts a non-blocking exclusive flock on it. Exit 42 => denied
#    (EWOULDBLOCK, the contract); exit 0 => it GOT the lock (today's hole);
#    exit 1 => some other flock error.
_SUBPROC_FLOCK_PROBE = """
import errno
import fcntl
import os
import sys

fd = os.open(sys.argv[1], os.O_RDWR)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as exc:
    sys.exit(42 if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN) else 1)
sys.exit(0)
"""


def _jsonl_path(audit_dir: str) -> str:
    """Absolute path of the audit JSONL inside audit_dir."""
    return os.path.join(audit_dir, "rondo_audit.jsonl")


def _seed_trail_with_stuck_intent(audit_dir: str) -> tuple[AuditTrail, str]:
    """Build a trail with one unpaired (stuck) INTENT; return (trail, dispatch_id).

    auto_reconcile=False so construction does NOT pre-write the stuck OUTCOME, and
    stuck_after_sec=0 so the INTENT is immediately reconcile-eligible (not treated
    as a fresh in-flight peer dispatch).
    """
    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0), auto_reconcile=False)
    rec = trail.record_intent(task_name="crashed", round_name="r", model="m", prompt="p")
    return trail, rec.dispatch_id


def _stuck_outcomes(audit_dir: str, dispatch_id: str) -> list[dict]:
    """All synthetic stuck OUTCOME records reconcile manufactured for a dispatch_id."""
    import json  # pylint: disable=import-outside-toplevel

    out: list[dict] = []
    with open(_jsonl_path(audit_dir), encoding="utf-8") as f:
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


@requires_fcntl
def test_reconcile_holds_audit_flock_blocks_foreign_locker(tmp_path) -> None:
    """EXCLUSION KILL: a foreign LOCK_EX|LOCK_NB on the JSONL must be DENIED mid-reconcile.

    Drive reconcile into its scan step (monkeypatch the scan to signal an Event and
    block until released) so it is parked INSIDE the scan+write critical section.
    From a REAL second process, attempt fcntl.flock(audit_jsonl, LOCK_EX|LOCK_NB):
    STD-110 r016 says reconcile must hold LOCK_EX on the JSONL itself there, so the
    probe MUST get EWOULDBLOCK (exit 42). Today reconcile locks only the sidecar, so
    the probe ACQUIRES the lock (exit 0) — this MUST FAIL today. Events + bounded
    timeouts only; total < 10s.
    """
    audit_dir = str(tmp_path)
    trail, _dispatch_id = _seed_trail_with_stuck_intent(audit_dir)
    jsonl = _jsonl_path(audit_dir)

    scan_entered = threading.Event()
    release = threading.Event()
    original_scan = trail._scan_intents_and_outcomes

    def blocking_scan() -> tuple[dict, set, bool]:
        scan_entered.set()
        if not release.wait(timeout=_HARD_TIMEOUT_SEC):  # -- timeout, never a sleep-for-sync
            raise AssertionError("release was never signalled — test orchestration timed out")
        return original_scan()

    trail._scan_intents_and_outcomes = blocking_scan  # type: ignore[method-assign]

    recon_errors: list[BaseException] = []

    def run_reconcile() -> None:
        try:
            trail.reconcile_stuck_intents(stuck_after_sec=0)
        except BaseException as exc:  # noqa: BLE001 - surfaced via recon_errors for the assert
            recon_errors.append(exc)

    recon = threading.Thread(target=run_reconcile, daemon=True)
    recon.start()
    try:
        assert scan_entered.wait(timeout=_HARD_TIMEOUT_SEC), "reconcile never entered its scan critical section"
        probe = subprocess.run(
            [sys.executable, "-c", _SUBPROC_FLOCK_PROBE, jsonl],
            capture_output=True,
            timeout=_HARD_TIMEOUT_SEC,
            check=False,
        )
    finally:
        release.set()
        recon.join(timeout=_HARD_TIMEOUT_SEC)

    assert not recon_errors, f"reconcile thread raised: {recon_errors!r}"
    assert probe.returncode == _EXIT_EWOULDBLOCK, (
        f"STD-110 r016: while reconcile is inside its scan+write critical section it MUST hold "
        f"LOCK_EX on the audit JSONL ({jsonl}); a foreign process taking LOCK_EX|LOCK_NB there "
        f"must be DENIED (exit {_EXIT_EWOULDBLOCK}=EWOULDBLOCK), but got exit {probe.returncode} "
        f"(0 = it ACQUIRED the lock → reconcile holds no lock on the JSONL, only the sidecar — "
        f"the r016 hole; appender vs reconciler never contend)."
    )


@requires_fcntl
def test_append_blocks_while_reconcile_holds_audit_flock(tmp_path) -> None:
    """DOUBLE-OUTCOME PIN: an _append_jsonl must BLOCK while reconcile holds the lock.

    Park reconcile inside its scan+write critical section (scan monkeypatched to
    signal + block), then call _append_jsonl from another thread. STD-110 r016 says
    the append must serialize against reconcile on the audit-file lock, so it MUST
    NOT complete while reconcile is held open — it completes only after release.
    Today reconcile holds no lock on the JSONL, so the append finishes immediately —
    this MUST FAIL today. Measured by Events + a bounded contention window, no sleeps.
    """
    audit_dir = str(tmp_path)
    trail, _dispatch_id = _seed_trail_with_stuck_intent(audit_dir)

    scan_entered = threading.Event()
    release = threading.Event()
    append_done = threading.Event()
    original_scan = trail._scan_intents_and_outcomes

    def blocking_scan() -> tuple[dict, set, bool]:
        scan_entered.set()
        if not release.wait(timeout=_HARD_TIMEOUT_SEC):
            raise AssertionError("release was never signalled — test orchestration timed out")
        return original_scan()

    trail._scan_intents_and_outcomes = blocking_scan  # type: ignore[method-assign]

    recon_errors: list[BaseException] = []

    def run_reconcile() -> None:
        try:
            trail.reconcile_stuck_intents(stuck_after_sec=0)
        except BaseException as exc:  # noqa: BLE001 - surfaced via recon_errors for the assert
            recon_errors.append(exc)

    def run_append() -> None:
        record = AuditRecord(
            dispatch_id="dsp_concurrent_append",
            status="done",
            exit_code=0,
            completed_at=datetime.now(UTC).isoformat(),
        )
        trail._append_jsonl(record)
        append_done.set()

    recon = threading.Thread(target=run_reconcile, daemon=True)
    recon.start()
    assert scan_entered.wait(timeout=_HARD_TIMEOUT_SEC), "reconcile never entered its scan critical section"

    appender = threading.Thread(target=run_append, daemon=True)
    appender.start()
    # -- While reconcile holds the audit-file lock, the append MUST NOT complete.
    #    True here = it completed during the hold = the r016 race window is open.
    completed_during_hold = append_done.wait(timeout=_CONTENTION_WINDOW_SEC)

    release.set()
    recon.join(timeout=_HARD_TIMEOUT_SEC)
    appender.join(timeout=_HARD_TIMEOUT_SEC)

    assert not recon_errors, f"reconcile thread raised: {recon_errors!r}"
    assert not completed_during_hold, (
        "STD-110 r016: an _append_jsonl issued while reconcile holds its scan+write critical "
        "section MUST block on the audit-file lock until reconcile finishes, but it completed "
        "immediately — reconcile and the appender never contend on the same lock (the r016 "
        "hole that lets a real OUTCOME land between reconcile's scan and its synthetic write)."
    )
    assert append_done.is_set(), "append never completed even after reconcile released — possible deadlock in the fix"


def test_clean_reconcile_writes_synthetic_outcomes_for_unpaired_intents(tmp_path) -> None:
    """CLEAN RAIL: a contention-free reconcile still reconciles unpaired INTENTs only.

    Behaviour-unchanged guarantee (contract (d)): with stuck_after_sec=0, two old
    unpaired INTENTs each get exactly one synthetic stuck OUTCOME and reconcile
    returns 2; a paired INTENT (already has an OUTCOME) is left untouched (0 stuck).
    Passes today; the fix MUST keep it passing.
    """
    audit_dir = str(tmp_path)
    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0), auto_reconcile=False)

    stuck_a = trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p")
    stuck_b = trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p")
    paired = trail.record_intent(task_name="t3", round_name="r", model="m", prompt="p")
    trail.record_outcome(dispatch_id=paired.dispatch_id, status="done", exit_code=0)

    count = trail.reconcile_stuck_intents(stuck_after_sec=0)

    assert count == 2, f"two unpaired INTENTs must reconcile to 2 stuck OUTCOMEs, got {count}"
    assert len(_stuck_outcomes(audit_dir, stuck_a.dispatch_id)) == 1, "first unpaired INTENT got no stuck OUTCOME"
    assert len(_stuck_outcomes(audit_dir, stuck_b.dispatch_id)) == 1, "second unpaired INTENT got no stuck OUTCOME"
    assert _stuck_outcomes(audit_dir, paired.dispatch_id) == [], (
        f"a paired INTENT must NOT be reconciled, but a stuck OUTCOME was written for {paired.dispatch_id}"
    )


@requires_fcntl
def test_reconcile_skips_when_peer_holds_sidecar_lock(tmp_path) -> None:
    """SIDECAR UNCHANGED: a peer holding the .reconcile.lock makes reconcile skip (0).

    Reconciler-vs-reconciler mutual exclusion via the sidecar is preserved by the
    fix (contract (c)/(d)). A fake peer holds LOCK_EX on the sidecar from another
    thread (a separate open file description, so the in-reconcile LOCK_EX|LOCK_NB is
    denied as EWOULDBLOCK → skip-as-peer-running). reconcile must return 0 and write
    NO synthetic OUTCOME. Passes today; pins behaviour the fix must keep.
    """
    audit_dir = str(tmp_path)
    trail, dispatch_id = _seed_trail_with_stuck_intent(audit_dir)
    sidecar = _jsonl_path(audit_dir) + ".reconcile.lock"

    peer_holding = threading.Event()
    release_peer = threading.Event()
    peer_errors: list[BaseException] = []

    def hold_sidecar() -> None:
        try:
            with open(sidecar, "w", encoding="utf-8") as lock_f:
                _fcntl.flock(lock_f.fileno(), _fcntl.LOCK_EX)
                peer_holding.set()
                release_peer.wait(timeout=_HARD_TIMEOUT_SEC)
                _fcntl.flock(lock_f.fileno(), _fcntl.LOCK_UN)
        except BaseException as exc:  # noqa: BLE001 - surfaced via peer_errors for the assert
            peer_errors.append(exc)
            peer_holding.set()

    peer = threading.Thread(target=hold_sidecar, daemon=True)
    peer.start()
    try:
        assert peer_holding.wait(timeout=_HARD_TIMEOUT_SEC), "fake peer never acquired the sidecar lock"
        assert not peer_errors, f"fake peer failed to hold the sidecar lock: {peer_errors!r}"
        count = trail.reconcile_stuck_intents(stuck_after_sec=0)
    finally:
        release_peer.set()
        peer.join(timeout=_HARD_TIMEOUT_SEC)

    assert count == 0, f"a peer holding the sidecar lock must make reconcile skip (return 0), got {count}"
    assert _stuck_outcomes(audit_dir, dispatch_id) == [], (
        f"reconcile skipped on a peer-held sidecar yet still wrote a stuck OUTCOME for {dispatch_id} "
        f"— skip-as-peer-running semantics broken"
    )


# -- sig: mgh-6201.cd.bd955f.5f05.b7b31b
