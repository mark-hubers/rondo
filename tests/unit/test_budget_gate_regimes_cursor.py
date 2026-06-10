# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: parallel budget gate fails in production timing/cost regimes.

VER-001 verification matrix — holistic-review finding #1 (cursor-review lens).

The earlier TOCTOU test (tests/unit/test_budget_toctou_cursor.py) used INSTANT
mocks with a fixed $1.00 cost, so it could only ever see the check-then-act
overrun. Two production regimes slip past instant/non-zero mocks entirely; this
file pins both as observable failures, plus a design rail for failed probes.

THE BUGS in src/rondo/parallel.py _BudgetGate (pinned here, NOT fixed here):

(a) SLOW PROBE — try_admit()'s cold-start wait loop breaks after
    _GATE_PROBE_WAIT_SEC and falls through with est=0.0. When the probe dispatch
    is SLOWER than that wait, every waiting worker times out, admits blind
    against a 0 estimate, and the round overruns the cap by ~(W-1) x cost.

(b) ZERO-COST PATH — settle() only records a sample when cost > 0. The PRIMARY
    Claude max-auth path has cost_usd == 0, so _have_sample never flips: every
    try_admit waits for the prior task to finish and the whole round silently
    serializes one task at a time whenever a budget is set.

All three tests drive the REAL run_parallel end-to-end and assert OBSERVABLE
outcomes (total spend, task statuses, peak concurrency) — never an internal
method name — so a fix that reshapes _BudgetGate still satisfies them. The lone
internal touch is monkeypatching _GATE_PROBE_WAIT_SEC, which is the regime knob
the slow-probe bug is defined in terms of.
"""

import threading
import time
from unittest.mock import patch

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, Task, TaskResult

import rondo.parallel as parallel
from rondo.parallel import run_parallel

# -- Slow-probe regime: the probe dispatch (0.6s) is far slower than the wait
#    backstop (0.15s), so on buggy code every waiter times out and admits blind.
_SLOW_PROBE_WAIT_SEC = 0.15
_SLOW_DISPATCH_SEC = 0.6
_SLOW_COST = 1.0
_SLOW_WORKERS = 5
_SLOW_CAP = 2.5  # -- only 2 x $1.00 fit; buggy code lets all 5 through for $5.00

# -- Zero-cost regime: max-auth tasks cost $0.00, sleep long enough that genuine
#    parallelism shows up as overlap in the concurrency tracker.
_ZERO_DISPATCH_SEC = 0.3
_ZERO_WORKERS = 4
_ZERO_CAP = 5.0  # -- a budget is set, yet $0 tasks can never exceed it

# -- Failed-probe regime: first dispatch errors at $0, the rest cost $1.00.
_PROBE_FAIL_SLEEP_SEC = 0.2
_PROBE_OK_SLEEP_SEC = 0.2
_PROBE_OK_COST = 1.0
_PROBE_WORKERS = 4
_PROBE_CAP = 2.5


def _make_tasks(n: int) -> list[Task]:
    """Build n minimal valid interactive tasks."""
    return [Task(name=f"t{i + 1}", instruction=f"do {i + 1}", done_when=f"done {i + 1}") for i in range(n)]


def _result(task: Task, cost: float, status: str = "done") -> tuple[TaskResult, DispatchUsage]:
    """Build the (TaskResult, DispatchUsage) pair a dispatch seam returns."""
    return (
        TaskResult(
            task_name=task.name,
            status=status,
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-06-08T00:00:00Z",
            cost_usd=cost,
        ),
        DispatchUsage(task_name=task.name, model="sonnet", cost_usd=cost),
    )


def _total_spent(result) -> float:
    """Sum the actual cost of every successfully dispatched task in the round."""
    return sum(tr.cost_usd or 0.0 for tr in result.task_results if tr.status == "done")


class _ConcurrencyTracker:
    """Lock-guarded peak-overlap counter sampled from inside the dispatch seam."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._now = 0
        self.peak = 0

    def enter(self) -> None:
        """Mark one dispatch as in-flight and update the observed peak."""
        with self._lock:
            self._now += 1
            self.peak = max(self.peak, self._now)

    def leave(self) -> None:
        """Mark one in-flight dispatch as finished."""
        with self._lock:
            self._now -= 1


def _slow_dispatch(task: Task, config: RondoConfig, **kwargs) -> tuple[TaskResult, DispatchUsage]:
    """Dispatch seam whose work (0.6s) outlasts the probe wait backstop (0.15s)."""
    time.sleep(_SLOW_DISPATCH_SEC)
    return _result(task, _SLOW_COST)


def _zero_cost_dispatch_factory(tracker: _ConcurrencyTracker):
    """Build a $0-cost (max-auth) dispatch seam that records peak concurrency."""

    def _dispatch(task: Task, config: RondoConfig, **kwargs) -> tuple[TaskResult, DispatchUsage]:
        tracker.enter()
        try:
            time.sleep(_ZERO_DISPATCH_SEC)
        finally:
            tracker.leave()
        return _result(task, 0.0)

    return _dispatch


def _probe_fail_dispatch_factory():
    """Build a seam whose FIRST call errors at $0; later calls cost $1.00."""
    lock = threading.Lock()
    calls = {"n": 0}

    def _dispatch(task: Task, config: RondoConfig, **kwargs) -> tuple[TaskResult, DispatchUsage]:
        with lock:
            calls["n"] += 1
            is_first = calls["n"] == 1
        if is_first:
            time.sleep(_PROBE_FAIL_SLEEP_SEC)
            return _result(task, 0.0, status="error")
        time.sleep(_PROBE_OK_SLEEP_SEC)
        return _result(task, _PROBE_OK_COST)

    return _dispatch


def test_slow_probe_does_not_overrun_budget(monkeypatch) -> None:
    """A probe slower than the wait backstop must not let waiters admit blind.

    With _GATE_PROBE_WAIT_SEC shrunk to 0.15s and each dispatch taking 0.6s, the
    cold-start probe is still in-flight when the other workers' wait loop times
    out. On current code they fall through with est=0.0, all admit, and the round
    spends 5 x $1.00 = $5.00 against a $2.50 cap — this assertion fails, which is
    exactly the regression we are pinning.
    """
    monkeypatch.setattr(parallel, "_GATE_PROBE_WAIT_SEC", _SLOW_PROBE_WAIT_SEC)
    round_def = Round(name="slow-probe", tasks=_make_tasks(_SLOW_WORKERS))
    config = RondoConfig(workers=_SLOW_WORKERS, throttle_sec=0.0, max_budget_usd=_SLOW_CAP)

    with patch("rondo.parallel.dispatch_task_routed", side_effect=_slow_dispatch):
        result = run_parallel(round_def, config)

    spent = _total_spent(result)
    assert spent <= _SLOW_CAP, (
        f"slow-probe overrun: spent ${spent:.2f} exceeds cap ${_SLOW_CAP:.2f} — "
        f"waiters timed out on the probe and admitted with est=0 (finding #1a)"
    )


def test_zero_cost_round_runs_in_parallel() -> None:
    """A $0-cost (max-auth) round under a budget must NOT serialize.

    settle() only records a sample when cost > 0, so on the primary max-auth path
    (cost_usd == 0) _have_sample never flips and every worker waits for the prior
    task to finish — the round serializes one task at a time. We assert two
    observable facts: all four $0 tasks complete (they can never exceed the cap),
    and the peak in-flight overlap is >= 2. On current code the peak is 1, so this
    fails — the serialization regression (finding #1b).
    """
    tracker = _ConcurrencyTracker()
    round_def = Round(name="zero-cost", tasks=_make_tasks(_ZERO_WORKERS))
    config = RondoConfig(workers=_ZERO_WORKERS, throttle_sec=0.0, max_budget_usd=_ZERO_CAP)

    with patch(
        "rondo.parallel.dispatch_task_routed",
        side_effect=_zero_cost_dispatch_factory(tracker),
    ):
        result = run_parallel(round_def, config)

    done = [tr for tr in result.task_results if tr.status == "done"]
    assert len(done) == _ZERO_WORKERS, (
        f"$0 tasks must always complete: only {len(done)}/{_ZERO_WORKERS} done "
        f"under a budget cap (finding #1b)"
    )
    assert tracker.peak >= 2, (
        f"zero-cost serialization: peak concurrency was {tracker.peak}, expected >= 2 — "
        f"the round ran one task at a time because no $0 sample was ever recorded (finding #1b)"
    )


def test_failed_probe_neither_poisons_admission_nor_overruns() -> None:
    """A failed cold-start probe must not block all later tasks or overrun the cap.

    The first dispatch errors at $0 (a wedged/failed probe); later dispatches cost
    $1.00. The gate must recover: at least one later task still runs to done, and
    total committed spend stays within the $2.50 cap. This is a design rail — it
    guards against a fix that either poisons admission forever (zero tasks done)
    or lets the recovery path overrun.
    """
    round_def = Round(name="probe-fail", tasks=_make_tasks(_PROBE_WORKERS))
    config = RondoConfig(workers=_PROBE_WORKERS, throttle_sec=0.0, max_budget_usd=_PROBE_CAP)

    with patch(
        "rondo.parallel.dispatch_task_routed",
        side_effect=_probe_fail_dispatch_factory(),
    ):
        result = run_parallel(round_def, config)

    done = [tr for tr in result.task_results if tr.status == "done"]
    spent = _total_spent(result)
    assert done, "a failed probe poisoned admission — no later task ever ran done (finding #1 rail)"
    assert spent <= _PROBE_CAP, (
        f"failed-probe recovery overran: spent ${spent:.2f} exceeds cap ${_PROBE_CAP:.2f} (finding #1 rail)"
    )


# -- sig: mgh-6201.cd.bd955f.0f57.27983f
