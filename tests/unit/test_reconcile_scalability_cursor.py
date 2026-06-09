# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: per-task reconcile storm in the parallel dispatch path.

VER-001 verification matrix — RONDO-359 finding #10 (cursor-review scalability lens).

THE BUG (observable failure this file pins):
    Every parallel worker builds its OWN AuditTrail (src/rondo/dispatch.py:112
    via _get_audit_trail, and src/rondo/dispatch_routing.py:532), and
    AuditTrail.__init__ auto-reconciles whenever a jsonl already exists. So a
    round of T tasks fires T separate reconcile_stuck_intents() runs — each
    taking the blocking module-level _reconcile_lock around an O(N) read of the
    WHOLE jsonl. That is O(T*N) I/O plus a hidden serialization point (T full
    scans queued on one mutex at construction) that the unlocked scan never
    imposed.

THE INTENDED FIX (this test pins the OBSERVABLE contract, not the mechanism):
    A parallel round must NOT reconcile once-per-task. Either the per-dispatch
    worker AuditTrails do not auto-reconcile (reconcile is round/process startup
    housekeeping, not per-task), or reconcile-on-init is gated so a burst of
    AuditTrails in one round scans at most once. The test asserts on the PARALLEL
    DISPATCH PATH only — it counts how often reconcile runs during run_parallel —
    so it stays green for BOTH fix shapes and never demands a global gate.

The guard test below pins the contract that MUST NOT regress: an explicitly
constructed AuditTrail(auto_reconcile=True) over a jsonl with a stuck INTENT
still reconciles it. A fix that simply disabled reconcile everywhere would break
that — this catches it.

The dispatch seam (rondo.parallel.dispatch_task_routed) is stubbed to a cheap
fake so no real provider work happens; the fake faithfully reproduces what a
real worker does to the audit trail by calling the REAL production factory
rondo.dispatch._get_audit_trail (dispatch.py:112). That keeps the per-worker
AuditTrail construction — the thing under test — on the genuine code path, so a
fix applied to that factory or to AuditTrail.__init__ is actually exercised.
"""

import json
import threading
from pathlib import Path
from unittest.mock import patch

import rondo.audit as audit_mod
import rondo.dispatch as dispatch_mod
from rondo.audit import AuditConfig, AuditTrail
from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, Task, TaskResult
from rondo.parallel import run_parallel

# -- Several tasks so "one reconcile per task" is unmistakably distinct from the
#    bounded "<= 1 per round" contract. N workers == N tasks so the whole round
#    fans out in a single concurrent batch (the contention the bug creates).
_TASK_COUNT = 5

_AUDIT_JSONL = "rondo_audit.jsonl"


def _make_tasks(n: int) -> list[Task]:
    """Build n minimal valid interactive tasks."""
    return [Task(name=f"t{i + 1}", instruction=f"do {i + 1}", done_when=f"done {i + 1}") for i in range(n)]


def _seed_stuck_intent(audit_dir: Path) -> None:
    """Create a jsonl holding one INTENT with no OUTCOME (a crashed dispatch).

    Uses auto_reconcile=False so seeding itself neither reconciles nor pollutes
    the call count we measure later.
    """
    seed = AuditTrail(
        config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
        auto_reconcile=False,
    )
    seed.record_intent(
        task_name="crashed",
        round_name="prior",
        model="sonnet",
        prompt="orphaned dispatch with no outcome",
    )


def _cheap_fake_dispatch(task: Task, config: RondoConfig) -> tuple[TaskResult, DispatchUsage]:
    """Stand-in for dispatch_task_routed: no provider work, real audit construction.

    A genuine worker builds its own AuditTrail per task (dispatch.py:112). We
    reproduce exactly that by calling the production factory _get_audit_trail,
    then return a fixed cheap result — so the audit-trail-per-worker behavior
    under test runs on real code while no subprocess or network happens.
    """
    dispatch_mod._get_audit_trail(config)
    return (
        TaskResult(
            task_name=task.name,
            status="done",
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-06-08T00:00:00Z",
        ),
        DispatchUsage(task_name=task.name, model="sonnet"),
    )


def test_parallel_round_reconciles_at_most_once(tmp_path: Path) -> None:
    """A parallel round must reconcile a bounded number of times, NOT once per task.

    Drives the real run_parallel with N workers over a pre-seeded audit jsonl and
    counts calls to reconcile_stuck_intents during the round (thread-safe
    wrapper). Current code builds one auto-reconciling AuditTrail per worker, so
    the count equals the task count (N) — this assertion FAILS, which is the
    regression. Either intended fix (no auto-reconcile on the worker path, or a
    once-per-round gate) drives the count to <= 1 and turns it green.
    """
    audit_dir = tmp_path / "audit"
    results_dir = tmp_path / "results"
    _seed_stuck_intent(audit_dir)

    calls = {"n": 0}
    count_lock = threading.Lock()
    original = AuditTrail.reconcile_stuck_intents

    def _counting(self: AuditTrail, *args: object, **kwargs: object) -> int:
        with count_lock:
            calls["n"] += 1
        return original(self, *args, **kwargs)

    config = RondoConfig(
        workers=_TASK_COUNT,
        throttle_sec=0.0,
        audit_dir=str(audit_dir),
        results_dir=str(results_dir),
    )
    round_def = Round(name="recon-scale", tasks=_make_tasks(_TASK_COUNT))

    with (
        patch.object(audit_mod.AuditTrail, "reconcile_stuck_intents", _counting),
        patch("rondo.parallel.dispatch_task_routed", side_effect=_cheap_fake_dispatch),
    ):
        run_parallel(round_def, config)

    assert calls["n"] <= 1, (
        f"reconcile storm: reconcile_stuck_intents ran {calls['n']} times for a "
        f"{_TASK_COUNT}-task round (one full O(N) jsonl scan per worker, serialized "
        f"on _reconcile_lock) — must be <= 1 per round (RONDO-359 finding #10)"
    )


def test_explicit_audit_trail_still_reconciles_stuck_intent(tmp_path: Path) -> None:
    """Guard: an explicit AuditTrail(auto_reconcile=True) MUST still reconcile.

    Pins the contract the fix must not regress: constructing an AuditTrail with
    auto_reconcile=True over a jsonl that has a stuck INTENT writes the synthetic
    ERR_RECONCILED_STUCK OUTCOME on init. Passes before AND after the fix — a fix
    that merely disabled reconcile everywhere would break this and be caught.
    """
    audit_dir = tmp_path / "audit"
    _seed_stuck_intent(audit_dir)

    AuditTrail(
        config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
        auto_reconcile=True,
    )

    jsonl = audit_dir / _AUDIT_JSONL
    records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    reconciled = [r for r in records if r.get("status") == "stuck" and r.get("error_code") == "ERR_RECONCILED_STUCK"]

    assert reconciled, (
        "explicit AuditTrail(auto_reconcile=True) over a stuck INTENT must still "
        "write an ERR_RECONCILED_STUCK outcome on init — the fix must not disable "
        "reconcile on the explicit path (RONDO-359 finding #10)"
    )


# -- sig: mgh-6201.cd.bd955f.4de9.cc3804
