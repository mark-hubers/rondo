# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: budget gate check-then-act TOCTOU in the parallel path.

VER-001 verification matrix — RONDO-354 finding #2 (cursor-review concurrency lens).

THE BUG (observable failure this file pins):
    src/rondo/parallel.py runs the budget check (over_budget) and the spend
    record (record) as TWO separate locked critical sections with the expensive
    dispatch in between and NO reservation. With W parallel workers, when the
    running spend sits just under the cap, ALL W workers pass over_budget()
    (each sees running+estimate < cap because nobody has reserved yet), ALL
    dispatch, and ALL record() afterward — so actual spend overruns the cap by
    roughly (W-1) x cost. That violates the MUST "check budget BEFORE dispatch,
    skip if over" (IFS-101 req 028, STD-107 req 018, STD-101 req 212).

These tests drive the REAL parallel executor (run_parallel) end-to-end and
assert the OBSERVABLE guarantee — total actually-spent cost must not exceed the
cap — NOT any internal method name, so a fix that reshapes _BudgetGate's API
(e.g. a single reserve-then-spend critical section) still satisfies them.

A threading.Barrier forces every worker to clear the pre-dispatch check before
any worker records its cost — that simultaneity is exactly what triggers the
TOCTOU. The barrier waits use a timeout and swallow BrokenBarrierError so a
CORRECT (reservation-based) implementation that skips over-budget tasks never
deadlocks the suite.
"""

import threading

from unittest.mock import patch

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, Task, TaskResult

from rondo.parallel import run_parallel

# -- Fixed, known cost per dispatched task (the task seam returns exactly this).
_COST_PER_TASK = 1.0

# -- N tasks == N workers so every task runs in one concurrent batch and the
#    barrier (sized to the worker count) can rendezvous all of them at once.
_WORKERS = 5

# -- Cap chosen so only K=2 tasks (2 x $1.00 = $2.00) fit under $2.50. A correct
#    implementation must therefore keep total spend <= $2.50; the buggy one lets
#    all 5 through for $5.00.
_CAP_USD = 2.5

# -- Seconds a worker will wait at the rendezvous before giving up. With the bug
#    all workers arrive and release instantly; with a fix the skipped workers
#    never arrive, so the few that do time out and proceed (no hang).
_BARRIER_TIMEOUT_SEC = 2.0


def _make_tasks(n: int) -> list[Task]:
    """Build n minimal valid interactive tasks."""
    return [Task(name=f"t{i + 1}", instruction=f"do {i + 1}", done_when=f"done {i + 1}") for i in range(n)]


def _barrier_paid_dispatch(barrier: threading.Barrier):
    """Build a dispatch seam that rendezvouses workers, then charges a fixed cost.

    Each call blocks on the shared barrier so every worker that passed the
    pre-dispatch budget check is in-flight simultaneously (the TOCTOU window)
    before any of them records a cost. The wait has a timeout and tolerates a
    broken barrier so a correct implementation — which lets fewer workers reach
    this seam — does not stall the test.
    """

    def _dispatch(task: Task, config: RondoConfig, **kwargs):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # -- correct impl skipped some workers; the rest just proceed
        return (
            TaskResult(
                task_name=task.name,
                status="done",
                raw_output='{"status":"done"}',
                model="sonnet",
                auth_mode="max",
                timestamp="2026-06-08T00:00:00Z",
                cost_usd=_COST_PER_TASK,
            ),
            DispatchUsage(task_name=task.name, model="sonnet", cost_usd=_COST_PER_TASK),
        )

    return _dispatch


def _total_spent(result) -> float:
    """Sum the actual cost of every successfully dispatched task in the round."""
    return sum(tr.cost_usd or 0.0 for tr in result.task_results if tr.status == "done")


def test_parallel_spend_never_exceeds_budget_cap() -> None:
    """Total actual spend across overlapping workers must stay within the cap.

    Drives run_parallel with W workers all forced (via a Barrier) to clear the
    budget check before any records its cost. On the current check-then-act code
    every worker dispatches and the round spends W x $1.00 = $5.00, blowing past
    the $2.50 cap — this assertion fails, which is the regression we want.
    """
    barrier = threading.Barrier(_WORKERS, timeout=_BARRIER_TIMEOUT_SEC)
    round_def = Round(name="toctou", tasks=_make_tasks(_WORKERS))
    config = RondoConfig(workers=_WORKERS, throttle_sec=0.0, max_budget_usd=_CAP_USD)

    with patch("rondo.parallel.dispatch_task_routed", side_effect=_barrier_paid_dispatch(barrier)):
        result = run_parallel(round_def, config)

    spent = _total_spent(result)
    assert spent <= _CAP_USD, (
        f"budget cap TOCTOU: spent ${spent:.2f} exceeds cap ${_CAP_USD:.2f} — "
        f"workers passed over_budget() before any recorded (RONDO-354 finding #2)"
    )


def test_over_budget_tasks_are_marked_budget_exceeded() -> None:
    """Tasks skipped for budget must report ERR_BUDGET_EXCEEDED and not be charged.

    Once spend reaches the cap, the remaining tasks MUST be refused before
    dispatch and surfaced as ERR_BUDGET_EXCEEDED — never silently charged. The
    refused count plus the cost of the dispatched tasks must reconcile with a
    spend that stays within the cap.
    """
    barrier = threading.Barrier(_WORKERS, timeout=_BARRIER_TIMEOUT_SEC)
    round_def = Round(name="toctou-codes", tasks=_make_tasks(_WORKERS))
    config = RondoConfig(workers=_WORKERS, throttle_sec=0.0, max_budget_usd=_CAP_USD)

    with patch("rondo.parallel.dispatch_task_routed", side_effect=_barrier_paid_dispatch(barrier)):
        result = run_parallel(round_def, config)

    blocked = [tr for tr in result.task_results if tr.error_code == "ERR_BUDGET_EXCEEDED"]
    spent = _total_spent(result)

    assert blocked, "no task was refused for budget — every worker overran the cap (RONDO-354 finding #2)"
    assert spent <= _CAP_USD, f"spent ${spent:.2f} exceeds cap ${_CAP_USD:.2f} despite refusals"
    assert all(tr.status == "error" for tr in blocked), "budget-refused tasks must be terminal errors, not charged"


# -- sig: mgh-6201.cd.bd955f.8710.df7f83
