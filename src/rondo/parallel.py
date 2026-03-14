"""Rondo parallel — concurrent task dispatch via ThreadPoolExecutor.

REQ-002 reqs 1-9, STD-003 C1-C7.
This is an L2 layer: orchestrates dispatch (L1) using engine types (L0).

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
    parallel.py → imports engine + config + dispatch
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from datetime import datetime, timezone

from rondo.config import RondoConfig
from rondo.dispatch import dispatch_task, save_result
from rondo.engine import (
    DispatchUsage,
    Round,
    RoundResult,
    TaskResult,
    calculate_round_status,
    run_gates,
    should_proceed,
)


# ──────────────────────────────────────────────────────────────────
#  Conflict detection — REQ-002 reqs 5-6, STD-003 C4-C5
# ──────────────────────────────────────────────────────────────────

def detect_conflicts(results: list[TaskResult]) -> list[str]:
    """Find files touched by multiple tasks (STD-003 C4).

    Returns list of conflict strings, one per conflicted file.
    Conflicts are ADVISORY (C5) — warnings, not blockers.
    """
    file_tasks: dict[str, list[str]] = {}
    for result in results:
        for filepath in result.files_modified:
            file_tasks.setdefault(filepath, []).append(result.task_name)

    return [
        f"{path} modified by: {', '.join(tasks)}"
        for path, tasks in file_tasks.items()
        if len(tasks) > 1
    ]


# ──────────────────────────────────────────────────────────────────
#  run_parallel() — REQ-002 reqs 1-9
# ──────────────────────────────────────────────────────────────────

def run_parallel(
    round: Round,
    config: RondoConfig,
) -> RoundResult:
    """Execute a round with parallel task dispatch.

    REQ-002 req 1: ThreadPoolExecutor for I/O-bound subprocess work.
    REQ-002 req 2: Configurable worker count from config.workers.
    REQ-002 req 3: Throttle delay between submissions.
    REQ-002 req 4: Collect results as futures complete.
    REQ-002 req 8: Single task failure doesn't crash others.
    REQ-002 req 9: Returns same RoundResult format as sequential.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()

    result = RoundResult(
        round_name=round.name,
        started_at=started_at,
        parallelism=config.workers,
    )

    # -- Handle empty round
    if not round.tasks:
        result.status = "skipped"
        result.summary = "No tasks in round"
        result.completed_at = datetime.now(timezone.utc).isoformat()
        result.duration_sec = time.monotonic() - start_time
        return result

    # -- Phase 1: Pre-gates (same contract as sequential)
    if round.pre_gates:
        result.pre_gate_results = run_gates(round.pre_gates)
        if not should_proceed(result.pre_gate_results):
            result.status = "skipped"
            failed = [g for g in result.pre_gate_results if not g.passed and g.blocking]
            names = ", ".join(g.gate_name for g in failed)
            result.summary = f"Blocked by pre-gate: {names}"
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.duration_sec = time.monotonic() - start_time
            return result

    # -- Phase 2: Parallel dispatch (REQ-002 reqs 1-4, 8)
    task_results: list[TaskResult] = []
    usage_list: list[DispatchUsage] = []

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        # -- Submit tasks with throttle delay (REQ-002 req 3, STD-003 C3)
        futures: dict[Future, str] = {}
        for i, task in enumerate(round.tasks):
            task.status = "running"

            # -- Throttle between launches (skip first)
            if i > 0 and config.throttle_sec > 0:
                time.sleep(config.throttle_sec)

            future = pool.submit(_dispatch_worker, task, config)
            futures[future] = task.name

        # -- Collect results as they complete (REQ-002 req 4)
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                task_result, task_usage = future.result()
            except Exception as exc:
                # -- STD-003 C7: exception in thread → error result, not crash
                task_result = TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code="ERR_INTERNAL",
                    error_message=f"Thread exception: {exc}",
                    model=config.default_model,
                    auth_mode=config.auth,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                task_usage = DispatchUsage(
                    task_name=task_name, model=config.default_model,
                )

            task_results.append(task_result)
            usage_list.append(task_usage)

            # -- Update task status from result
            for task in round.tasks:
                if task.name == task_name:
                    task.status = task_result.status
                    break

            # -- Save individual result to disk
            try:
                save_result(task_result, task_usage, config.results_dir)
            except Exception:
                pass  # -- File save failure shouldn't block the round

    # -- Assign collected results
    result.task_results = task_results
    result.usage = usage_list

    # -- Phase 2b: Conflict detection (REQ-002 reqs 5-6, STD-003 C4-C5)
    result.conflicts = detect_conflicts(task_results)

    # -- Phase 3: Post-gates (same contract as sequential)
    if round.post_gates:
        result.post_gate_results = run_gates(round.post_gates)

    # -- Calculate round status (REQ-001 req 46 — DRY: reuse engine function)
    result.status = calculate_round_status(result.task_results)

    # -- Summary (REQ-002 req 7)
    done_count = sum(1 for tr in result.task_results if tr.status == "done")
    total = len(result.task_results)
    result.summary = f"{done_count}/{total} tasks done"

    # -- Timing
    result.completed_at = datetime.now(timezone.utc).isoformat()
    result.duration_sec = time.monotonic() - start_time

    return result


# ──────────────────────────────────────────────────────────────────
#  Worker function — STD-003 C2 (no shared state)
# ──────────────────────────────────────────────────────────────────

def _dispatch_worker(
    task,
    config: RondoConfig,
) -> tuple[TaskResult, DispatchUsage]:
    """Worker function for ThreadPoolExecutor.

    STD-003 C2: Each thread calls dispatch_task independently,
    returns its own (TaskResult, DispatchUsage) tuple.
    No shared mutable state.
    """
    return dispatch_task(task, config)
