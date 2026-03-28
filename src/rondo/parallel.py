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
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from rondo.config import RondoConfig
from rondo.dispatch import dispatch_task, save_result
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

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        # -- Submit tasks with throttle delay (Rondo-REQ-101 req 3, Rondo-STD-110 C3)
        futures: dict[Future[tuple[TaskResult, DispatchUsage]], str] = {}
        for i, task in enumerate(tasks):
            task.status = "in_progress"
            if i > 0 and config.throttle_sec > 0:
                time.sleep(config.throttle_sec)
            future = pool.submit(_dispatch_worker, task, config)
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


def _dispatch_worker(
    task: Task,
    config: RondoConfig,
) -> tuple[TaskResult, DispatchUsage]:
    """Worker function for ThreadPoolExecutor.

    Rondo-STD-110 C2: Each thread calls dispatch_task independently,
    returns its own (TaskResult, DispatchUsage) tuple.
    No shared mutable state.
    """
    return dispatch_task(task, config)


# -- sig: mgh-6201.cd.bd955f.1e5a.3424d1
