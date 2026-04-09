# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo runner — sequential orchestration: pre-gates → tasks → post-gates.

Rondo-REQ-100 reqs 6, 7, 40, 45, 46.
This is the L2 layer: orchestrates dispatch (L1) using engine types (L0).

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
    runner.py → imports engine + config + dispatch
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

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
    validate_round,
)
from rondo.notify import notify_round_complete

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  run_round() — Rondo-REQ-100 req 45 (primary library entry point)
# ──────────────────────────────────────────────────────────────────


def run_round(
    round_def: Round,
    config: RondoConfig | None = None,
) -> RoundResult:
    """Execute a round and return a RoundResult.

    Rondo-REQ-100 req 45: primary library entry point.
    Rondo-REQ-100 req 40: auto-detect sequential vs parallel.

    Args:
        round_def: The Round to execute.
        config: Optional config. Defaults to RondoConfig() (zero-config).

    Returns:
        RoundResult with all task results, gate results, usage, and status.
    """
    if config is None:
        config = RondoConfig()

    # -- Round pre-flight validation (Rondo-STD-108 defensive check)
    round_errors = validate_round(round_def)
    if round_errors:
        msg = "; ".join(round_errors)
        logger.warning("Round '%s' failed validation: %s", round_def.name, msg)
        return RoundResult(
            round_name=round_def.name,
            status="error",
            summary=f"Validation failed: {msg}",
        )

    # -- Rondo-REQ-100 req 40: auto-detect sequential vs parallel
    if config.workers > 1:
        from rondo.parallel import run_parallel  # pylint: disable=import-outside-toplevel

        return run_parallel(round_def, config)
    return run_sequential(round_def, config)


# ──────────────────────────────────────────────────────────────────
#  Sequential Runner — helpers (RONDO-225: extracted for complexity)
# ──────────────────────────────────────────────────────────────────


def _make_skip_result(task: Task, message: str, config: RondoConfig) -> TaskResult:
    """Create a skipped TaskResult for timeout/circuit-breaker paths.

    RONDO-225: extracted to deduplicate 2 near-identical blocks in run_sequential.
    """
    task.status = "skipped"
    return TaskResult(
        task_name=task.name,
        status="skipped",
        error_message=message,
        model=config.default_model,
        auth_mode=config.auth,
        timestamp=datetime.now(UTC).isoformat(),
    )


def _update_circuit_breaker(
    error_code: str | None,
    consecutive_errors: int,
    last_error_code: str,
    round_name: str,
) -> tuple[int, str, bool]:
    """Track consecutive same-error pattern and trip circuit breaker.

    RONDO-225: extracted state machine from run_sequential for testability.
    REQ-100 reqs 057-059: circuit breaker logic.

    Returns (consecutive_errors, last_error_code, tripped).
    """
    if error_code and error_code == last_error_code:
        consecutive_errors += 1
    elif error_code:
        consecutive_errors = 1
        last_error_code = error_code
    else:
        consecutive_errors = 0
        last_error_code = ""

    tripped = consecutive_errors >= 3
    if tripped:
        logger.warning(
            "Circuit breaker tripped: 3 consecutive %s in round '%s'",
            last_error_code,
            round_name,
        )
    return consecutive_errors, last_error_code, tripped


def _finalize_round(result: RoundResult, start_time: float, results_dir: str) -> None:
    """Finalize round: compute status, summary, timing, save, notify.

    RONDO-225: extracted from run_sequential to reduce statement count.
    """
    result.status = calculate_round_status(result.task_results)

    done_count = sum(1 for tr in result.task_results if tr.status == "done")
    total = len(result.task_results)
    result.summary = f"{done_count}/{total} tasks done"

    result.completed_at = datetime.now(UTC).isoformat()
    result.duration_sec = time.monotonic() - start_time

    _save_round_summary(result, results_dir)
    _notify_round(result)


# ──────────────────────────────────────────────────────────────────
#  Sequential Runner
# ──────────────────────────────────────────────────────────────────


def run_sequential(round_def: Round, config: RondoConfig) -> RoundResult:
    """Execute a round sequentially: pre-gates → tasks → post-gates.

    Rondo-REQ-100 reqs 6, 7: gate ordering and blocking behavior.
    Rondo-STD-108 rule 6: single task failure doesn't crash framework.
    """
    started_at = datetime.now(UTC).isoformat()
    start_time = time.monotonic()

    result = RoundResult(
        round_name=round_def.name,
        started_at=started_at,
        parallelism=1,
    )

    # -- Handle empty round
    if not round_def.tasks:
        result.status = "skipped"
        result.summary = "No tasks in round"
        result.completed_at = datetime.now(UTC).isoformat()
        result.duration_sec = time.monotonic() - start_time
        return result

    # -- STD-110 req 004-005: file conflict detection (advisory)
    _warn_file_conflicts(round_def.tasks)

    # -- Phase 1: Pre-gates (Rondo-REQ-100 req 6)
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

    # -- Phase 2: Dispatch tasks sequentially (with circuit breaker — REQ-100 reqs 057-059)
    consecutive_errors = 0
    last_error_code = ""
    breaker_tripped = False

    for task in round_def.tasks:
        # -- REQ-100 req 075: round timeout enforcement
        elapsed = time.monotonic() - start_time
        if elapsed > config.round_timeout_sec:
            result.task_results.append(
                _make_skip_result(task, f"round_timeout: {elapsed:.1f}s > {config.round_timeout_sec}s limit", config)
            )
            result.usage.append(DispatchUsage(task_name=task.name))
            continue

        # -- Circuit breaker: skip remaining tasks after 3 consecutive same-error
        if breaker_tripped:
            result.task_results.append(
                _make_skip_result(task, f"circuit_breaker: halted after 3 consecutive {last_error_code}", config)
            )
            result.usage.append(DispatchUsage(task_name=task.name))
            continue

        task_result, usage = _dispatch_with_safety_net(task, config, round_name=round_def.name)
        task.status = task_result.status
        result.task_results.append(task_result)
        result.usage.append(usage)
        _save_result_safe(task_result, usage, config.results_dir)

        # -- REQ-105 req 002: notify on dispatch failure
        if task_result.error_code:
            _notify_failure(task_result)

        # -- FIX-684: threshold alerting (REQ-105 reqs 011-013) — wired into production
        _check_thresholds(task_result, usage, result)

        # -- Finding #189: rate limit backoff
        _handle_rate_limit(usage, config)

        # -- Finding #192: overage flow control
        overage_action = _check_overage(usage, config)
        if overage_action == "stop":
            logger.warning("Overage: stopping round early (on_overage=stop)")
            break

        # -- Circuit breaker tracking (REQ-100 req 057-058)
        consecutive_errors, last_error_code, breaker_tripped = _update_circuit_breaker(
            task_result.error_code, consecutive_errors, last_error_code, round_def.name
        )

    # -- Phase 3: Post-gates (Rondo-REQ-100 req 7)
    if round_def.post_gates:
        result.post_gate_results = run_gates(round_def.post_gates)

    # -- Phase 4: Finalize
    _finalize_round(result, start_time, config.results_dir)
    return result


# ──────────────────────────────────────────────────────────────────
#  Internal helpers — extracted for DRY + pylint statement count
# ──────────────────────────────────────────────────────────────────


def _check_overage(usage: DispatchUsage, config: RondoConfig) -> str:
    """Finding #192: check overage and return action (continue/pause/stop)."""
    if usage.is_using_overage and config.on_overage != "continue":
        logger.warning("Overage detected. Action: %s", config.on_overage)
        return config.on_overage
    return "continue"


def _handle_rate_limit(usage: DispatchUsage, config: RondoConfig) -> None:
    """Finding #189: pause on rate limit before next dispatch."""
    if usage.rate_limit_status == "blocked" and config.rate_limit_backoff_sec > 0:
        logger.warning("Rate limited. Backing off %ds.", config.rate_limit_backoff_sec)
        time.sleep(config.rate_limit_backoff_sec)


def _check_thresholds(task_result: TaskResult, usage: DispatchUsage, round_result: RoundResult) -> None:
    """FIX-684: wire threshold alerting into production dispatch path.

    REQ-105 reqs 011-013: latency, cost spike alerts with hysteresis.
    Uses completed task_results in round_result to compute running averages.
    """
    try:
        from rondo.notify import notify_cost_spike, notify_latency_threshold  # pylint: disable=import-outside-toplevel

        # -- Compute running averages from completed tasks so far
        completed = [tr for tr in round_result.task_results if tr.duration_sec > 0 and tr.status == "done"]
        sample_count = len(completed)

        if sample_count >= 2 and task_result.duration_sec > 0:
            avg_duration = sum(tr.duration_sec for tr in completed) / sample_count
            notify_latency_threshold(
                task_name=task_result.task_name,
                duration_sec=task_result.duration_sec,
                avg_duration_sec=avg_duration,
                sample_count=sample_count,
            )

        if sample_count >= 2 and usage.cost_usd > 0:
            avg_cost = sum(u.cost_usd for u in round_result.usage if u.cost_usd > 0) / max(
                sum(1 for u in round_result.usage if u.cost_usd > 0), 1
            )
            notify_cost_spike(
                task_name=task_result.task_name,
                cost_usd=usage.cost_usd,
                avg_cost_usd=avg_cost,
                sample_count=sample_count,
            )
    except (ImportError, OSError, TypeError) as exc:
        logger.debug("Threshold alerting unavailable: %s", exc)


def _warn_file_conflicts(tasks: list[Task]) -> None:
    """Log warnings for file conflicts (advisory)."""
    for c in detect_file_conflicts(tasks):
        logger.warning("File conflict: %s", c)


def detect_file_conflicts(tasks: list[Task]) -> list[str]:
    """STD-110 req 004: detect tasks that touch the same files.

    Returns list of conflict descriptions. Empty = no conflicts.
    Advisory only (req 005) — warns but doesn't block.
    """
    file_to_tasks: dict[str, list[str]] = {}
    for task in tasks:
        for f in task.context_files:
            file_to_tasks.setdefault(f, []).append(task.name)

    conflicts: list[str] = []
    for filepath, task_names in file_to_tasks.items():
        if len(task_names) > 1:
            conflicts.append(f"{filepath} touched by: {', '.join(task_names)}")
    return conflicts


def _dispatch_with_safety_net(
    task: Task,
    config: RondoConfig,
    round_name: str = "",
) -> tuple[TaskResult, DispatchUsage]:
    """Dispatch a task with Rondo-STD-108 rule 6 safety net.

    If dispatch_task raises (shouldn't — it catches internally),
    convert to error result so subsequent tasks still run.

    RONDO-227: pre/post dispatch hooks integrated (REQ-100-addendum reqs 100-114).
    Pre-hooks transform the prompt before dispatch.
    Post-hooks transform the result after dispatch.
    """
    from rondo.hooks import (  # pylint: disable=import-outside-toplevel
        HookError,
        run_post_dispatch_hooks,
        run_pre_dispatch_hooks,
    )

    task.status = "in_progress"

    # -- Pre-dispatch hooks (REQ-100-addendum req 100-105)
    if task.pre_dispatch:
        try:
            hooked_prompt, _pre_trace = run_pre_dispatch_hooks(task.instruction, task, config)
            task.instruction = hooked_prompt
        except HookError as exc:
            return (
                TaskResult(
                    task_name=task.name,
                    status="error",
                    error_code="ERR_HOOK_FAILED",
                    error_message=str(exc),
                    model=config.default_model,
                    auth_mode=config.auth,
                    timestamp=datetime.now(UTC).isoformat(),
                ),
                DispatchUsage(task_name=task.name, model=config.default_model),
            )

    try:
        task_result, usage = dispatch_task(task, config, round_name=round_name)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        logger.warning("Dispatch safety net caught %s for task %s: %s", type(exc).__name__, task.name, exc)
        return (
            TaskResult(
                task_name=task.name,
                status="error",
                error_code="ERR_INTERNAL",
                error_message=f"Runner exception: {exc}",
                model=config.default_model,
                auth_mode=config.auth,
                timestamp=datetime.now(UTC).isoformat(),
            ),
            DispatchUsage(task_name=task.name, model=config.default_model),
        )

    # -- Post-dispatch hooks (REQ-100-addendum reqs 110-114)
    if task.post_dispatch:
        task_result, _post_trace = run_post_dispatch_hooks(task_result, usage, task)

    return task_result, usage


def _save_result_safe(
    task_result: TaskResult,
    usage: DispatchUsage,
    results_dir: str,
) -> None:
    """Save task result to disk. Logs on failure but never raises."""
    try:
        save_result(task_result, usage, results_dir)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Failed to save result for %s: %s", task_result.task_name, exc)


def _notify_failure(task_result: TaskResult) -> None:
    """Send notification on dispatch failure — Rondo-REQ-105 req 002.

    FIX-674: passes recovery guidance from ErrorPayload if present.
    """
    try:
        from rondo.notify import notify_failure  # pylint: disable=import-outside-toplevel

        recovery = ""
        if task_result.error_payload:
            recovery = task_result.error_payload.recovery
        notify_failure(
            task_name=task_result.task_name,
            error_code=task_result.error_code,
            error_message=task_result.error_message,
            recovery=recovery,
        )
    except (ImportError, OSError, TypeError) as exc:
        logger.debug("Failure notification failed (non-fatal): %s", exc)


def _notify_round(result: RoundResult) -> None:
    """Send notification on round completion — Rondo-REQ-105 req 001."""
    try:
        total_cost = sum(u.cost_usd for u in result.usage)
        notify_round_complete(
            round_name=result.round_name,
            status=result.status,
            duration_sec=result.duration_sec,
            cost_usd=total_cost,
        )
    except (ImportError, OSError, TypeError) as exc:
        logger.debug("Notification failed (non-fatal): %s", exc)


def _save_round_summary(result: RoundResult, results_dir: str) -> None:
    """Save round summary JSON to results_dir. Logs on failure but never raises."""
    try:
        out_dir = Path(results_dir)
        out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        filepath = out_dir / "round-summary.json"

        data = _build_summary_dict(result)
        filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        filepath.chmod(0o600)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Failed to save round summary: %s", exc)


def _build_summary_dict(result: RoundResult) -> dict:
    """Build serializable summary dict from RoundResult."""
    return {
        "round_name": result.round_name,
        "status": result.status,
        "summary": result.summary,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "duration_sec": result.duration_sec,
        "parallelism": result.parallelism,
        "task_count": len(result.task_results),
        "tasks": [{"task_name": tr.task_name, "status": tr.status} for tr in result.task_results],
        "pre_gates": [
            {"gate_name": gr.gate_name, "passed": gr.passed, "detail": gr.detail} for gr in result.pre_gate_results
        ],
        "post_gates": [
            {"gate_name": gr.gate_name, "passed": gr.passed, "detail": gr.detail} for gr in result.post_gate_results
        ],
        "total_cost_usd": sum(u.cost_usd for u in result.usage),
    }


# -- sig: mgh-6201.cd.bd955f.34cd.35e2e7
