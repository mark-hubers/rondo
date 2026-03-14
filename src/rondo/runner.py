"""Rondo runner — sequential orchestration: pre-gates → tasks → post-gates.

REQ-001 reqs 6, 7, 40, 45, 46.
This is the L2 layer: orchestrates dispatch (L1) using engine types (L0).

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
    runner.py → imports engine + config + dispatch
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from rondo.config import RondoConfig
from rondo.dispatch import dispatch_task, save_result
from rondo.engine import (
    Round,
    RoundResult,
    calculate_round_status,
    run_gates,
    should_proceed,
)


# ──────────────────────────────────────────────────────────────────
#  run_round() — REQ-001 req 45 (primary library entry point)
# ──────────────────────────────────────────────────────────────────

def run_round(
    round: Round,
    config: RondoConfig | None = None,
) -> RoundResult:
    """Execute a round and return a RoundResult.

    REQ-001 req 45: primary library entry point.
    REQ-001 req 40: auto-detect sequential vs parallel.

    Args:
        round: The Round to execute.
        config: Optional config. Defaults to RondoConfig() (zero-config).

    Returns:
        RoundResult with all task results, gate results, usage, and status.
    """
    if config is None:
        config = RondoConfig()

    # -- REQ-001 req 40: auto-detect runner
    # -- parallel.py not built yet — sequential for now
    # -- When parallel.py exists: if config.workers > 1, delegate there
    return run_sequential(round, config)


# ──────────────────────────────────────────────────────────────────
#  Sequential Runner
# ──────────────────────────────────────────────────────────────────

def run_sequential(round: Round, config: RondoConfig) -> RoundResult:
    """Execute a round sequentially: pre-gates → tasks → post-gates.

    REQ-001 reqs 6, 7: gate ordering and blocking behavior.
    STD-001 rule 6: single task failure doesn't crash framework.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()

    result = RoundResult(
        round_name=round.name,
        started_at=started_at,
        parallelism=1,
    )

    # -- Handle empty round
    if not round.tasks:
        result.status = "skipped"
        result.summary = "No tasks in round"
        result.completed_at = datetime.now(timezone.utc).isoformat()
        result.duration_sec = time.monotonic() - start_time
        return result

    # -- Phase 1: Pre-gates (REQ-001 req 6)
    if round.pre_gates:
        result.pre_gate_results = run_gates(round.pre_gates)
        if not should_proceed(result.pre_gate_results):
            # -- Blocking gate failed → skip all tasks
            result.status = "skipped"
            failed = [g for g in result.pre_gate_results if not g.passed and g.blocking]
            names = ", ".join(g.gate_name for g in failed)
            result.summary = f"Blocked by pre-gate: {names}"
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.duration_sec = time.monotonic() - start_time
            return result

    # -- Phase 2: Dispatch tasks sequentially
    for task in round.tasks:
        # -- Set task to running (REQ-001 req 8)
        task.status = "running"

        # -- Dispatch (STD-001 rule 6: failure doesn't crash others)
        try:
            task_result, usage = dispatch_task(task, config)
        except Exception as exc:
            # -- Shouldn't happen (dispatch catches all), but safety net
            from rondo.engine import TaskResult, DispatchUsage
            task_result = TaskResult(
                task_name=task.name,
                status="error",
                error_code="ERR_INTERNAL",
                error_message=f"Runner exception: {exc}",
                model=config.default_model,
                auth_mode=config.auth,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            usage = DispatchUsage(task_name=task.name, model=config.default_model)

        # -- Update task status from result
        task.status = task_result.status

        # -- Collect results
        result.task_results.append(task_result)
        result.usage.append(usage)

        # -- Save individual result to disk
        try:
            save_result(task_result, usage, config.results_dir)
        except Exception:
            pass  # -- File save failure shouldn't block the round

    # -- Phase 3: Post-gates (REQ-001 req 7)
    if round.post_gates:
        result.post_gate_results = run_gates(round.post_gates)

    # -- Calculate round status (REQ-001 req 46 — DRY: reuse engine function)
    result.status = calculate_round_status(result.task_results)

    # -- Summary
    done_count = sum(1 for tr in result.task_results if tr.status == "done")
    total = len(result.task_results)
    result.summary = f"{done_count}/{total} tasks done"

    # -- Timing
    result.completed_at = datetime.now(timezone.utc).isoformat()
    result.duration_sec = time.monotonic() - start_time

    # -- Save round summary
    _save_round_summary(result, config.results_dir)

    return result


def _save_round_summary(result: RoundResult, results_dir: str) -> None:
    """Save round summary JSON to results_dir."""
    try:
        out_dir = Path(results_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / "round-summary.json"

        # -- Serialize RoundResult (skip non-serializable fields)
        data = {
            "round_name": result.round_name,
            "status": result.status,
            "summary": result.summary,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "duration_sec": result.duration_sec,
            "parallelism": result.parallelism,
            "task_count": len(result.task_results),
            "tasks": [
                {"task_name": tr.task_name, "status": tr.status}
                for tr in result.task_results
            ],
            "pre_gates": [
                {"gate_name": gr.gate_name, "passed": gr.passed, "detail": gr.detail}
                for gr in result.pre_gate_results
            ],
            "post_gates": [
                {"gate_name": gr.gate_name, "passed": gr.passed, "detail": gr.detail}
                for gr in result.post_gate_results
            ],
            "total_cost_usd": sum(u.cost_usd for u in result.usage),
        }

        filepath.write_text(json.dumps(data, indent=2, default=str))
        filepath.chmod(0o600)
    except Exception:
        pass  # -- Summary save failure shouldn't crash
