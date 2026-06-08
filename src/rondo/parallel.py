# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo parallel — concurrent task dispatch via ThreadPoolExecutor.

Rondo-REQ-101 reqs 1-9, Rondo-STD-110 C1-C7.
This is an L2 layer: orchestrates dispatch (L1) using engine types (L0).

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
    parallel.py → imports engine + config + dispatch
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from rondo.config import RondoConfig
from rondo.dispatch import save_result
from rondo.dispatch_routing import dispatch_task_routed
from rondo.engine import (
    DispatchUsage,
    Round,
    RoundResult,
    Task,
    TaskResult,
    calculate_round_status,
    run_gates,
    should_proceed,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  Conflict detection — Rondo-REQ-101 reqs 5-6, Rondo-STD-110 C4-C5
# ──────────────────────────────────────────────────────────────────


def detect_conflicts(results: list[TaskResult]) -> list[str]:
    """Find files touched by multiple tasks (Rondo-STD-110 C4).

    Returns list of conflict strings, one per conflicted file.
    Conflicts are ADVISORY (C5) — warnings, not blockers.
    """
    file_tasks: dict[str, list[str]] = {}
    for result in results:
        for filepath in result.files_modified:
            file_tasks.setdefault(filepath, []).append(result.task_name)

    return [f"{path} modified by: {', '.join(tasks)}" for path, tasks in file_tasks.items() if len(tasks) > 1]


# ──────────────────────────────────────────────────────────────────
#  run_parallel() — Rondo-REQ-101 reqs 1-9
# ──────────────────────────────────────────────────────────────────


def run_parallel(
    round_def: Round,
    config: RondoConfig,
) -> RoundResult:
    """Execute a round with parallel task dispatch.

    Rondo-REQ-101 req 1: ThreadPoolExecutor for I/O-bound subprocess work.
    Rondo-REQ-101 req 2: Configurable worker count from config.workers.
    Rondo-REQ-101 req 3: Throttle delay between submissions.
    Rondo-REQ-101 req 4: Collect results as futures complete.
    Rondo-REQ-101 req 8: Single task failure doesn't crash others.
    Rondo-REQ-101 req 9: Returns same RoundResult format as sequential.
    """
    started_at = datetime.now(UTC).isoformat()
    start_time = time.monotonic()

    result = RoundResult(
        round_name=round_def.name,
        started_at=started_at,
        parallelism=config.workers,
    )

    # -- Handle empty round
    if not round_def.tasks:
        result.status = "skipped"
        result.summary = "No tasks in round"
        result.completed_at = datetime.now(UTC).isoformat()
        result.duration_sec = time.monotonic() - start_time
        return result

    # -- Phase 1: Pre-gates (same contract as sequential)
    if round_def.pre_gates:
        result.pre_gate_results = run_gates(round_def.pre_gates)
        if not should_proceed(result.pre_gate_results):
            result.status = "skipped"
            failed = [g for g in result.pre_gate_results if not g.passed and g.blocking]
            names = ", ".join(g.gate_name for g in failed)
            result.summary = f"Blocked by pre-gate: {names}"
            result.completed_at = datetime.now(UTC).isoformat()
            result.duration_sec = time.monotonic() - start_time
            return result

    # -- Phase 2: Parallel dispatch (Rondo-REQ-101 reqs 1-4, 8)
    task_results, usage_list = _execute_parallel(round_def.tasks, config)
    result.task_results = task_results
    result.usage = usage_list

    # -- Phase 2b: Conflict detection (Rondo-REQ-101 reqs 5-6, Rondo-STD-110 C4-C5)
    result.conflicts = detect_conflicts(task_results)

    # -- Phase 3: Post-gates (same contract as sequential)
    if round_def.post_gates:
        result.post_gate_results = run_gates(round_def.post_gates)

    # -- Calculate round status (Rondo-REQ-100 req 46 — DRY: reuse engine function)
    result.status = calculate_round_status(result.task_results)

    # -- Summary (Rondo-REQ-101 req 7)
    done_count = sum(1 for tr in result.task_results if tr.status == "done")
    total = len(result.task_results)
    result.summary = f"{done_count}/{total} tasks done"

    # -- Timing
    result.completed_at = datetime.now(UTC).isoformat()
    result.duration_sec = time.monotonic() - start_time

    return result


# ──────────────────────────────────────────────────────────────────
#  Parallel execution — extracted for statement count + clarity
# ──────────────────────────────────────────────────────────────────


def _execute_parallel(
    tasks: list[Task],
    config: RondoConfig,
) -> tuple[list[TaskResult], list[DispatchUsage]]:
    """Submit tasks to ThreadPoolExecutor and collect results.

    Rondo-STD-110 C3: Throttle delay between submissions.
    Rondo-STD-110 C7: Exception in thread → error result, not crash.
    """
    task_results: list[TaskResult] = []
    usage_list: list[DispatchUsage] = []
    task_map = {t.name: t for t in tasks}
    # -- RONDO-354: one shared budget gate for the whole round (cap from config).
    gate = _BudgetGate(config.max_budget_usd)

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        # -- Submit tasks with throttle delay (Rondo-REQ-101 req 3, Rondo-STD-110 C3)
        futures: dict[Future[tuple[TaskResult, DispatchUsage]], str] = {}
        for i, task in enumerate(tasks):
            task.status = "in_progress"
            if i > 0 and config.throttle_sec > 0:
                time.sleep(config.throttle_sec)
            future = pool.submit(_dispatch_worker, task, config, gate)
            futures[future] = task.name

        # -- Collect results as they complete (Rondo-REQ-101 req 4)
        for future in as_completed(futures):
            task_name = futures[future]
            task_result, task_usage = _collect_future(future, task_name, config)
            task_results.append(task_result)
            usage_list.append(task_usage)

            # -- Update task status from result (O(1) via map)
            if task_name in task_map:
                task_map[task_name].status = task_result.status

            # -- Save individual result to disk
            _save_result_safe(task_result, task_usage, config.results_dir)

    return task_results, usage_list


def _collect_future(
    future: Future[tuple[TaskResult, DispatchUsage]],
    task_name: str,
    config: RondoConfig,
) -> tuple[TaskResult, DispatchUsage]:
    """Collect result from a completed future. Converts exceptions to error results."""
    try:
        return future.result()
    except (OSError, ValueError, RuntimeError) as exc:
        # -- Rondo-STD-110 C7: exception in thread → error result, not crash
        logger.warning("Thread exception for task %s: %s", task_name, exc)
        return (
            TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_INTERNAL",
                error_message=f"Thread exception: {exc}",
                model=config.default_model,
                auth_mode=config.auth,
                timestamp=datetime.now(UTC).isoformat(),
            ),
            DispatchUsage(
                task_name=task_name,
                model=config.default_model,
            ),
        )


def _save_result_safe(
    task_result: TaskResult,
    task_usage: DispatchUsage,
    results_dir: str,
) -> None:
    """Save task result to disk. Logs on failure but never raises."""
    try:
        save_result(task_result, task_usage, results_dir)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Failed to save result for %s: %s", task_result.task_name, exc)


# ──────────────────────────────────────────────────────────────────
#  Worker function — Rondo-STD-110 C2 (no shared state)
# ──────────────────────────────────────────────────────────────────


# -- RONDO-366: backstop wait while a cold-start probe settles. settle() always
# -- fires (worker uses try/finally), so this timeout is only a safety net
# -- against a wedged probe — never the normal path.
_GATE_PROBE_WAIT_SEC = 30.0


class _BudgetGate:
    """Thread-safe budget enforcement for the parallel path — RONDO-354 + RONDO-366.

    The sequential path enforced max_budget_usd but run_parallel did not, so N
    workers could overrun N x — a violation of IFS-101 r028 / STD-107 r018 /
    STD-101 r212 (all MUST). cap=None disables the gate (no behavior change
    without a budget).

    RONDO-366 (cursor review #2): the old over_budget()/record() pair was
    check-then-act — W workers all passed the check before any recorded, then all
    spent, overrunning by ~(W-1)x. Fixed two ways, both essential:
      1. RESERVE-then-settle: try_admit() atomically reserves the per-task
         estimate against the cap in ONE locked section; settle() releases the
         reservation and commits the actual cost. So reserved budget is visible
         to peers the instant a task is admitted — no admission race.
      2. COLD-START PROBE: the estimate is unknown until a real cost lands
         (it starts at 0). Without this, the first wave would all reserve ~0 and
         overrun. So until one cost has settled, exactly ONE task runs (the
         probe) while the rest WAIT (not refused — they may well fit); once the
         probe's cost is known, the rest admit-or-refuse against it.
    """

    def __init__(self, cap: float | None) -> None:
        self.cap = cap
        self._cond = threading.Condition()
        self._spent = 0.0  # -- committed actual cost
        self._reserved = 0.0  # -- in-flight reservations (admitted, not yet settled)
        self._estimate = 0.0  # -- per-task cost estimate; 0.0 == no sample yet
        self._inflight = 0  # -- admitted-but-unsettled count
        self._have_sample = False

    def try_admit(self) -> float | None:
        """Reserve budget for one dispatch, or refuse. Returns reserved amount, or None.

        None == refused (would exceed cap): the caller must NOT dispatch. A float
        (possibly 0.0 for the cold-start probe) == admitted; the caller MUST pass
        it back to settle() exactly once.
        """
        if self.cap is None:
            return 0.0
        with self._cond:
            # -- Cold start: let one probe run alone so we learn the real cost
            # -- before fanning out; peers wait for it rather than overrun blind.
            while not self._have_sample and self._inflight > 0:
                if not self._cond.wait(timeout=_GATE_PROBE_WAIT_SEC):
                    break  # -- probe wedged — fall through rather than hang forever
            est = self._estimate if self._have_sample else 0.0
            if self._spent + self._reserved + est > self.cap:
                return None
            self._reserved += est
            self._inflight += 1
            return est

    def settle(self, reserved: float, cost: float) -> None:
        """Release a reservation and commit the observed cost; wake any waiters."""
        if self.cap is None:
            return
        with self._cond:
            self._reserved = max(0.0, self._reserved - reserved)
            self._inflight = max(0, self._inflight - 1)
            self._spent += cost
            if cost > 0:
                self._estimate = max(cost, 0.001)
                self._have_sample = True
            self._cond.notify_all()


def _budget_blocked_result(task: Task, config: RondoConfig, cap: float) -> tuple[TaskResult, DispatchUsage]:
    """Result for a task skipped because the round budget cap was reached."""
    return (
        TaskResult(
            task_name=task.name,
            status="error",
            error_code="ERR_BUDGET_EXCEEDED",
            error_message=f"Round budget cap ${cap:.4f} reached — task not dispatched (RONDO-354)",
            model=config.default_model,
            auth_mode=config.auth,
            timestamp=datetime.now(UTC).isoformat(),
        ),
        DispatchUsage(task_name=task.name, model=config.default_model),
    )


def _dispatch_worker(
    task: Task,
    config: RondoConfig,
    gate: _BudgetGate | None = None,
) -> tuple[TaskResult, DispatchUsage]:
    """Worker function for ThreadPoolExecutor.

    Rondo-STD-110 C2: each thread calls dispatch_task_routed independently.
    RONDO-342: routed so per-task cloud models reach provider adapters.
    RONDO-354 + RONDO-366: atomically RESERVE budget before dispatch (skip if
    over), then settle the actual cost after — reservation closes the
    check-then-act overrun. settle() runs in finally so a raising dispatch still
    refunds its reservation (never leaks budget).
    """
    gated = gate is not None and gate.cap is not None
    reserved = gate.try_admit() if gated else None
    if gated and reserved is None:
        return _budget_blocked_result(task, config, gate.cap)  # type: ignore[union-attr]
    try:
        tr, usage = dispatch_task_routed(task, config)
    except BaseException:
        if reserved is not None:
            gate.settle(reserved, 0.0)  # type: ignore[union-attr]  -- refund on failure
        raise
    if reserved is not None:
        gate.settle(reserved, tr.cost_usd or 0.0)  # type: ignore[union-attr]
    return tr, usage


# -- sig: mgh-6201.cd.bd955f.1e5a.399461
