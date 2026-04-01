# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo MCP server — stdio transport for Claude Code integration.

Rondo-IFS-104: MCP Server.
Claude Code starts this via stdio — no daemon, no port, no "always running."
Same engine as CLI and Python import, just a different interface.

Three interfaces, one engine:
    1. Python:  from rondo import dispatch_task
    2. CLI:     rondo run / metrics / audit
    3. MCP:     rondo mcp (this file — stdio transport)

Session 94 split (Finding #195): Read-only/management tools extracted to mcp_tools.py.
This file keeps: dispatch core, AI composition tools, server registration.

Import direction:
    mcp_tools.py → imports metrics, history, spool, providers (reads data)
    mcp_server.py → imports mcp_tools (tool functions), dispatch (finalization)
"""

from __future__ import annotations

import json
import logging
from typing import Any

# -- Import tool functions from mcp_tools (Finding #195 split)
from rondo.mcp_tools import (  # noqa: F401
    _DEFAULT_AUDIT_DIR,
    _resolve_dir,
    rondo_audit_summary,
    rondo_cost,
    rondo_diff,
    rondo_dispatch_info,
    rondo_health,
    rondo_history,
    rondo_metrics,
    rondo_models,
    rondo_schedule_create,
    rondo_schedule_list,
    rondo_spool_consume,
    rondo_templates,
)

logger = logging.getLogger(__name__)

# -- H-07 to H-11: MCP input limits (security hardening)
_MAX_PROMPT_BYTES = 500_000  # -- 500KB
_MAX_CHAIN_STEPS = 20
_MAX_BENCHMARK_MODELS = 10
_MAX_SUMMARIZE_BYTES = 1_000_000  # -- 1MB


# -- ──────────────────────────────────────────────────────────────
# --  Dispatch + composition tools (depend on rondo_run_file)
# -- ──────────────────────────────────────────────────────────────


# -- Background dispatch tracking (RONDO-39)
_background_results: dict[str, dict] = {}
_MAX_BACKGROUND_ENTRIES = 100  # -- H-01


def _prune_background() -> None:
    """H-01/H-02: evict oldest completed entries when over max."""
    if len(_background_results) <= _MAX_BACKGROUND_ENTRIES:
        return
    # -- Sort by completion: running entries kept, oldest completed evicted
    completed = [(k, v) for k, v in _background_results.items() if v.get("status") not in ("running", "dispatched")]
    completed.sort(key=lambda x: x[1].get("ts", 0))
    to_remove = len(_background_results) - _MAX_BACKGROUND_ENTRIES
    for k, _ in completed[:to_remove]:
        del _background_results[k]


def _get_retry_dir() -> str:
    """RONDO-106: resolve retry directory path."""
    return _resolve_dir("~/.rondo/retry", "retry")


def _save_background_result(dispatch_id: str, result: dict) -> None:
    """RONDO-106: persist background result to disk for cross-session retry.

    Only saves if the result has failed tasks — successful dispatches
    don't need retry. Files in ~/.rondo/retry/{dispatch_id}.json.
    """
    from pathlib import Path

    tasks = result.get("tasks", [])
    has_failures = any(t.get("status") in ("error", "blocked", "partial") for t in tasks)
    if not has_failures:
        return

    retry_dir = Path(_get_retry_dir()).expanduser()
    try:
        retry_dir.mkdir(parents=True, exist_ok=True)
        retry_path = retry_dir / f"{dispatch_id}.json"
        retry_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        retry_path.chmod(0o600)  # -- STD-110 S5: restrictive permissions
        # -- Prune old retry files (keep max 50)
        retry_files = sorted(retry_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old_file in retry_files[:-50]:
            old_file.unlink(missing_ok=True)
    except (OSError, TypeError) as exc:
        logger.debug("Retry save failed (non-fatal): %s", exc)


def _load_background_result(dispatch_id: str) -> dict | None:
    """RONDO-106: load a background result from disk if not in memory."""
    from pathlib import Path

    retry_dir = Path(_get_retry_dir()).expanduser()
    retry_path = retry_dir / f"{dispatch_id}.json"
    if retry_path.is_file():
        try:
            return json.loads(retry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def rondo_explain(
    output: str, question: str = "Is this correct?", model: str = "qwen2.5:32b", dry_run: bool = False
) -> str:
    """Second opinion: local model reviews another model's output at zero cost.

    Pass the output from a Claude/other dispatch + a review question.
    Default model is qwen2.5:32b (best local quality).
    """
    prompt = f"""Review this AI-generated output and answer the question.

## Output to review:
{output[:5000]}

## Question:
{question}

Be specific. If you find errors, list them. If correct, say why."""

    return rondo_run_file(
        prompt=prompt, model=model, dry_run=dry_run, done_when="Review complete with specific assessment."
    )


def rondo_benchmark(prompt: str, models: str = "[]", dry_run: bool = False) -> str:
    """Benchmark: dispatch same prompt to multiple models, rank by speed/cost.

    Returns results sorted by duration (fastest first).
    """
    try:
        model_list = json.loads(models) if models else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid models JSON"})

    # -- H-09: benchmark model limit
    if len(model_list) > _MAX_BENCHMARK_MODELS:
        return json.dumps(
            {
                "status": "error",
                "error": f"Too many models ({len(model_list)} > {_MAX_BENCHMARK_MODELS})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    if not model_list:
        model_list = ["llama3.1:8b", "qwen2.5:32b", "sonnet"]

    results: list[dict] = []
    for model_name in model_list:
        if dry_run:
            results.append(
                {
                    "model": model_name,
                    "status": "skipped",
                    "duration_sec": 0,
                    "output_length": 0,
                    "cost_usd": 0,
                }
            )
        else:
            raw = rondo_run_file(prompt=prompt, model=model_name, dry_run=False)
            r = json.loads(raw)
            tasks = r.get("tasks", [])
            task = tasks[0] if tasks else {}
            results.append(
                {
                    "model": model_name,
                    "status": r.get("status", "error"),
                    "duration_sec": task.get("duration_sec", 0),
                    "output_length": len(task.get("raw_output", "")),
                    "cost_usd": r.get("total_cost_usd", 0),
                }
            )

    ranked = sorted(results, key=lambda x: x["duration_sec"])

    return json.dumps(
        {
            "status": "done",
            "prompt": prompt[:100],
            "results": results,
            "ranked": ranked,
            "fastest": ranked[0]["model"] if ranked else "",
        },
        indent=2,
    )


def rondo_chain(steps_json: str, dry_run: bool = False) -> str:
    """Chain dispatch: output of step N feeds as context to step N+1.

    Each step is {prompt, model, done_when?}. Previous output appended to prompt.
    """
    try:
        steps = json.loads(steps_json) if steps_json else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid steps_json"})

    # -- H-08: chain step limit
    if len(steps) > _MAX_CHAIN_STEPS:
        return json.dumps(
            {
                "status": "error",
                "error": f"Too many steps ({len(steps)} > {_MAX_CHAIN_STEPS})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    if not steps:
        return json.dumps({"status": "done", "steps": [], "total_cost_usd": 0})

    results: list[dict] = []
    previous_output = ""
    total_cost = 0.0

    for i, step in enumerate(steps):
        step_prompt = step.get("prompt", "")
        if previous_output:
            step_prompt = f"{step_prompt}\n\n## Previous step output:\n{previous_output}"

        step_model = step.get("model", "sonnet")
        step_done = step.get("done_when", "Task completed.")

        if dry_run:
            results.append(
                {
                    "step": i + 1,
                    "prompt_preview": step_prompt[:300],
                    "model": step_model,
                    "status": "skipped",
                }
            )
            previous_output = f"[dry-run step {i + 1} output]"
        else:
            raw = rondo_run_file(
                prompt=step_prompt,
                model=step_model,
                done_when=step_done,
                dry_run=False,
            )
            step_result = json.loads(raw)
            tasks = step_result.get("tasks", [])
            output = tasks[0].get("raw_output", "") if tasks else ""
            cost = step_result.get("total_cost_usd", 0)
            total_cost += cost
            previous_output = output
            results.append(
                {
                    "step": i + 1,
                    "model": step_model,
                    "status": step_result.get("status", "unknown"),
                    "output_length": len(output),
                    "cost_usd": cost,
                }
            )

    return json.dumps(
        {"status": "done", "steps": results, "total_cost_usd": total_cost},
        indent=2,
    )


def rondo_summarize(dispatch_json: str, dry_run: bool = False, model: str = "haiku") -> str:
    """Condense multiple task results into one summary — via AI dispatch.

    Takes a dispatch result JSON, builds a summarization prompt from all
    task outputs, dispatches to AI, returns the summary.
    """
    try:
        data = json.loads(dispatch_json) if dispatch_json else {}
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid dispatch_json"})

    tasks = data.get("tasks", [])
    if not tasks:
        return json.dumps({"status": "done", "summary": "No tasks to summarize"})

    # -- Build summarization prompt from all task outputs
    parts = ["Summarize these task results into a concise report:\n"]
    for task in tasks:
        name = task.get("name", "unknown")
        full_output = task.get("raw_output", "")
        output = full_output[:3000]
        if len(full_output) > 3000:
            output += f"\n[TRUNCATED: {len(full_output)} chars total, showing first 3000]"
        status = task.get("status", "unknown")
        parts.append(f"## Task: {name} ({status})\n{output}\n")

    prompt = "\n".join(parts)

    if dry_run:
        return json.dumps({"status": "done", "summary_prompt": prompt[:500], "task_count": len(tasks)})

    # -- Dispatch summarization via rondo_run_file
    result = rondo_run_file(prompt=prompt, done_when="Summary report written.", dry_run=False, model=model)
    return result


def rondo_retry(dispatch_id: str, model: str = "") -> str:
    """Re-run failed tasks from a previous dispatch — U-56 to U-58.

    RONDO-106: checks in-memory first, then disk (~/.rondo/retry/).
    Works across sessions — failed dispatch results persist on disk.
    """
    result = _background_results.get(dispatch_id)
    if not result:
        # -- RONDO-106: fall back to disk-based retry
        result = _load_background_result(dispatch_id)
    if not result:
        return json.dumps({"status": "error", "error": f"Unknown dispatch_id: {dispatch_id}"})

    tasks = result.get("tasks", [])
    failed = [t for t in tasks if t.get("status") in ("error", "blocked", "partial")]
    if not failed:
        return json.dumps({"status": "done", "message": "No failed tasks to retry", "retried": 0})

    # -- Build inline prompts for each failed task
    retried: list[dict] = []
    for task in failed:
        task_result = rondo_run_file(
            prompt=f"Retry: {task.get('name', 'unknown')}. Previous error: {task.get('error_message', 'unknown')}",
            dry_run=False,
            model=model or task.get("model", "sonnet"),
        )
        retried.append({"name": task.get("name"), "retry_result": json.loads(task_result)})

    return json.dumps(
        {"status": "done", "retried": len(retried), "skipped": len(tasks) - len(failed), "results": retried},
        indent=2,
    )


def _notify_completion(session: Any, dispatch_id: str, result: dict) -> None:
    """U-47 + REQ-105: notify on completion via MCP session + macOS."""
    msg = (
        f"Rondo dispatch {dispatch_id} completed: "
        f"{result.get('done_count', 0)} done, "
        f"{result.get('error_count', 0)} errors, "
        f"${result.get('total_cost_usd', 0):.2f}"
    )

    # -- REQ-105: fire macOS notification (always, regardless of session)
    try:
        from rondo.notify import NotifyConfig, notify_round_complete

        notify_round_complete(
            round_name=result.get("round_name", dispatch_id),
            status=result.get("status", "unknown"),
            duration_sec=result.get("duration_sec", 0),
            cost_usd=result.get("total_cost_usd", 0),
            config=NotifyConfig(channels=["macos", "file"]),
        )
    except (ImportError, OSError):
        pass

    # -- U-47: push to MCP session (best-effort)
    if session is None:
        return
    try:
        import asyncio

        loop = asyncio.new_event_loop()
        loop.run_until_complete(session.send_log_message(level="info", data=msg))
        loop.close()
    except (AttributeError, TypeError, OSError, RuntimeError):
        pass  # -- U-49: best-effort, polling is fallback


def _dispatch_via_provider_or_claude(
    round_def: Any,
    config: Any,
    model: str,
    prompt: str,
    dry_run: bool,
    run_round: Any,
) -> Any:
    """REQ-109 req 026-027: route to provider adapter or Claude dispatch.

    Non-Claude providers go through adapter.dispatch() + shared _finalize_dispatch().
    Claude goes through run_round() → dispatch_task() (proven path).
    Both paths get the full ALWAYS-ON pipeline: audit, sanitize, spool, history, metrics.
    """
    from rondo.providers import get_provider

    provider = get_provider(model)
    if provider is not None:
        from rondo.audit import AuditConfig, AuditTrail
        from rondo.dispatch import _finalize_dispatch
        from rondo.engine import DispatchUsage, RoundResult, TaskResult

        # -- REQ-109 req 026: shared finalization for ALL providers
        audit_dir = _resolve_dir(_DEFAULT_AUDIT_DIR, "audit")
        audit_trail = None
        try:
            audit_trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir))
        except (OSError, TypeError):
            pass

        # -- Build a minimal config for _finalize_dispatch
        from rondo.config import RondoConfig

        finalize_config = (
            config
            if isinstance(config, RondoConfig)
            else RondoConfig(
                audit_dir=audit_dir,
                results_dir=_resolve_dir("~/.rondo/results", "results"),
            )
        )

        task_results = []
        for task in round_def.tasks:
            task_prompt = task.instruction or prompt
            if dry_run:
                task_results.append(
                    TaskResult(task_name=task.name, status="skipped", prompt_sent=task_prompt[:500], model=model)
                )
            else:
                # -- Audit INTENT before dispatch
                audit_record = None
                if audit_trail:
                    audit_record = audit_trail.record_intent(
                        task_name=task.name,
                        round_name=round_def.name,
                        model=model,
                        prompt=task_prompt,
                    )
                tr = provider.dispatch(prompt=task_prompt, model=model, task_name=task.name)
                usage = DispatchUsage(task_name=task.name, model=model, cost_usd=tr.cost_usd or 0.0)
                # -- REQ-109 req 026: shared finalization (audit OUTCOME, sanitize, spool, history, metrics)
                tr, usage = _finalize_dispatch(
                    tr,
                    usage,
                    finalize_config,
                    audit_trail,
                    audit_record,
                    round_name=round_def.name,
                )
                task_results.append(tr)
        ok_statuses = {"done", "skipped"}
        return RoundResult(
            round_name=round_def.name,
            status="done" if all(t.status in ok_statuses for t in task_results) else "partial",
            task_results=task_results,
        )
    return run_round(round_def, config=config)


def _get_task_names(file_path: str, prompt: str) -> list[str]:
    """U-31 + U-54: pre-populate task names for background progress tracking."""
    if prompt:
        return ["inline-task"]
    try:
        from rondo.cli import load_round_file as _load

        rd = _load(file_path)
        return [t.name for t in rd.tasks]
    except (FileNotFoundError, AttributeError, TypeError, ImportError):
        return []


def _validate_run_inputs(file_path: str, project: str, prompt: str) -> tuple[str, str, str | None]:
    """Validate and resolve file_path + project. Returns (file_path, project, error_json)."""
    from pathlib import Path

    # -- H-07: prompt size limit
    if prompt and len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        return (
            file_path,
            project,
            json.dumps({"status": "error", "error": "Prompt too large", "code": "ERR_INPUT_TOO_LARGE"}),
        )
    if prompt:
        file_path = ""
    elif file_path:
        file_path = str(Path(file_path).expanduser())
        if not Path(file_path).exists():
            return file_path, project, json.dumps({"status": "error", "error": f"File not found: {file_path}"})
    else:
        return file_path, project, json.dumps({"status": "error", "error": "Provide file_path or prompt"})

    if project:
        project = str(Path(project).expanduser())
        if not Path(project).is_dir():
            return file_path, project, json.dumps({"status": "error", "error": f"Project dir not found: {project}"})

    return file_path, project, None


def rondo_run_file(
    file_path: str = "",
    dry_run: bool = True,
    model: str = "sonnet",
    project: str = "",
    max_budget: float = 0.0,
    timeout_sec: int = 300,
    background: bool = False,
    prompt: str = "",
    done_when: str = "Task completed. Return results.",
    _session: Any = None,
) -> str:
    """Run a round file or inline prompt — MCP dispatch tool.

    Two modes:
        1. File: file_path="my_round.py" — loads build_round() from file
        2. Inline: prompt="Search for X" — creates one-task round in memory (U-33)

    Default dry_run=True for safety. Set dry_run=False for real dispatch.
    Strips CLAUDECODE env var to avoid nested session errors.
    """
    import threading
    import uuid

    file_path, project, err = _validate_run_inputs(file_path, project, prompt)
    if err:
        return err

    def _dispatch() -> dict:
        """Run the dispatch (called directly or in background thread)."""
        try:
            from rondo.config import RondoConfig
            from rondo.engine import Round, Task
            from rondo.runner import run_round

            # -- U-33: inline prompt → in-memory round
            if prompt:
                round_def = Round(
                    name="inline",
                    tasks=[Task(name="inline-task", instruction=prompt, done_when=done_when)],
                )
            else:
                from rondo.cli import load_round_file

                round_def = load_round_file(file_path)
            config_kwargs: dict = {
                "default_model": model,
                "dry_run": dry_run,
                "task_timeout_sec": timeout_sec,
            }
            if project:
                config_kwargs["project"] = project
            if max_budget > 0:
                config_kwargs["max_budget_usd"] = max_budget
            config = RondoConfig(**config_kwargs)

            # -- REQ-109: route to provider adapter or Claude dispatch
            result = _dispatch_via_provider_or_claude(
                round_def,
                config,
                model,
                prompt,
                dry_run,
                run_round,
            )

            tasks_out = [
                {
                    "name": tr.task_name,
                    "status": tr.status,
                    "duration_sec": tr.duration_sec,
                    "model": tr.model,
                    "prompt_sent": tr.prompt_sent[:500] if dry_run else "",
                    "raw_output": tr.raw_output[:2000] if not dry_run else "",
                    "cost_usd": tr.cost_usd or 0.0,
                    "error_code": tr.error_code or "",
                    "error_message": tr.error_message or "",
                }
                for tr in result.task_results
            ]
            statuses = [t["status"] for t in tasks_out]
            return {
                "status": result.status,
                "round_name": result.round_name,
                "tasks": tasks_out,
                "done_count": statuses.count("done") + statuses.count("skipped"),
                "error_count": statuses.count("error") + statuses.count("blocked"),
                "pending_count": statuses.count("pending"),
                "total_cost_usd": sum(u.cost_usd for u in result.usage),
                "duration_sec": result.duration_sec,
                "dry_run": dry_run,
            }
        except (FileNotFoundError, AttributeError, TypeError, ImportError, OSError) as exc:
            return {"status": "error", "error": str(exc)}

    # -- Background dispatch: return dispatch_id immediately
    if background and not dry_run:
        dispatch_id = f"mcp-{uuid.uuid4().hex[:12]}"
        _prune_background()  # -- H-01: evict before adding

        task_names = _get_task_names(file_path, prompt)

        _background_results[dispatch_id] = {
            "status": "running",
            "dispatch_id": dispatch_id,
            "tasks": [{"name": tn, "status": "pending"} for tn in task_names],
            "total_cost_usd": 0.0,
        }

        def _bg_worker() -> None:
            result = _dispatch()
            result["dispatch_id"] = dispatch_id
            _background_results[dispatch_id] = result
            # -- RONDO-106: persist to disk for cross-session retry
            _save_background_result(dispatch_id, result)
            _notify_completion(_session, dispatch_id, result)

        thread = threading.Thread(target=_bg_worker, daemon=True)
        thread.start()
        return json.dumps(
            {
                "status": "dispatched",
                "dispatch_id": dispatch_id,
                "tasks": task_names,
                "message": "Use rondo_run_status to check progress.",
            },
            indent=2,
        )

    # -- Synchronous dispatch (dry-run or foreground)
    return json.dumps(_dispatch(), indent=2)


_STATUS_SHORT = {"running": "w", "done": "d", "error": "e", "dispatched": "w"}


def rondo_run_status(dispatch_id: str = "", brief: bool = False, heartbeat: bool = False) -> str:
    """Check status of a background MCP dispatch.

    Three tiers (U-45, U-50):
        heartbeat=True  → ~10 tokens: {"s":"w","d":2,"e":0,"p":1}
        brief=True      → ~40 tokens: {status, done_count, error_count, pending_count}
        (default)       → ~300+ tokens: full results with task output
    """
    if not dispatch_id:
        return json.dumps(
            {
                "dispatches": [
                    {"dispatch_id": did, "status": r.get("status", "unknown")} for did, r in _background_results.items()
                ]
            },
            indent=2,
        )

    result = _background_results.get(dispatch_id)
    if not result:
        return json.dumps({"status": "error", "error": f"Unknown dispatch_id: {dispatch_id}"})

    # -- U-50: heartbeat mode — ultra-compact (~10 tokens)
    if heartbeat:
        return json.dumps(
            {
                "s": _STATUS_SHORT.get(result.get("status", ""), "?"),
                "d": result.get("done_count", 0),
                "e": result.get("error_count", 0),
                "p": result.get("pending_count", 0),
            }
        )

    # -- U-45: brief mode — minimal tokens for polling (~40 tokens)
    if brief:
        return json.dumps(
            {
                "status": result.get("status", "unknown"),
                "done_count": result.get("done_count", 0),
                "error_count": result.get("error_count", 0),
                "pending_count": result.get("pending_count", 0),
            }
        )

    return json.dumps(result, indent=2)


# -- ──────────────────────────────────────────────────────────────
# --  MCP server setup (stdio transport)
# -- ──────────────────────────────────────────────────────────────


def create_mcp_server() -> Any:
    """Create the FastMCP server with all tools registered.

    Separated from run() for testability.
    """
    from mcp.server import FastMCP

    mcp = FastMCP(name="rondo", log_level="WARNING")

    # -- MCP Resources: self-documentation for AI discovery
    @mcp.resource(
        uri="rondo://help",
        name="Rondo Help",
        description="Full API documentation: Round/Task schema, examples, commands. Read this first.",
    )
    def _help_resource() -> str:
        from rondo.ai_help import get_ai_help

        return json.dumps(get_ai_help(), indent=2)

    @mcp.tool(
        name="rondo_metrics",
        description="Full dispatch metrics: cost, reliability, latency, tokens, model comparison, health status. Returns JSON.",
    )
    def _metrics() -> str:
        return rondo_metrics()

    @mcp.tool(
        name="rondo_health",
        description="Quick health check: GREEN/YELLOW/RED with key numbers. Lightweight for preflight.",
    )
    def _health() -> str:
        return rondo_health()

    @mcp.tool(
        name="rondo_audit_summary",
        description="Recent dispatch audit records. Shows last N dispatches with status, cost, duration.",
    )
    def _audit(limit: int = 10) -> str:
        return rondo_audit_summary(limit=limit)

    @mcp.tool(
        name="rondo_dispatch_info",
        description="Rondo version, commands, capabilities, design principles. Discovery for AI agents.",
    )
    def _info() -> str:
        return rondo_dispatch_info()

    @mcp.tool(
        name="rondo_run",
        description="Run AI tasks. Two modes: file_path= for round files, OR prompt= for one-off tasks. dry_run=True previews. background=True for async.",
    )
    def _run(
        file_path: str = "",
        dry_run: bool = True,
        model: str = "sonnet",
        project: str = "",
        max_budget: float = 0.0,
        timeout_sec: int = 300,
        background: bool = False,
        prompt: str = "",
        done_when: str = "Task completed. Return results.",
        ctx: Any = None,
    ) -> str:
        # -- U-47: capture session for background progress notifications
        session = None
        if ctx is not None:
            try:
                session = ctx.session
            except (AttributeError, TypeError):
                pass
        return rondo_run_file(
            file_path=file_path,
            dry_run=dry_run,
            model=model,
            project=project,
            max_budget=max_budget,
            timeout_sec=timeout_sec,
            background=background,
            prompt=prompt,
            done_when=done_when,
            _session=session,
        )

    @mcp.tool(
        name="rondo_run_status",
        description="Check background dispatch. 3 tiers: heartbeat=True (~10 tokens), brief=True (~40 tokens), default (~300+ tokens for full results).",
    )
    def _run_status(dispatch_id: str = "", brief: bool = False, heartbeat: bool = False) -> str:
        return rondo_run_status(dispatch_id=dispatch_id, brief=brief, heartbeat=heartbeat)

    @mcp.tool(
        name="rondo_history",
        description="Query dispatch history. Filter by model= or status=. Returns records + model aggregate stats.",
    )
    def _history(model: str = "", status: str = "", limit: int = 20) -> str:
        return rondo_history(model=model, status=status, limit=limit)

    @mcp.tool(
        name="rondo_cost",
        description="Monthly cost dashboard: total spend, cost per model, daily average. Default last 30 days.",
    )
    def _cost(days: int = 30) -> str:
        return rondo_cost(days=days)

    @mcp.tool(
        name="rondo_schedule_list",
        description="List installed Rondo scheduled dispatches (launchd plists).",
    )
    def _schedule_list() -> str:
        return rondo_schedule_list()

    @mcp.tool(
        name="rondo_schedule_create",
        description="Create a scheduled Rondo dispatch. interval: hourly/daily/weekly/monthly. dry_run=True to preview.",
    )
    def _schedule_create(
        file_path: str, interval: str = "weekly", model: str = "", name: str = "", dry_run: bool = False
    ) -> str:
        return rondo_schedule_create(file_path=file_path, interval=interval, model=model, name=name, dry_run=dry_run)

    @mcp.tool(
        name="rondo_explain",
        description="Second opinion: local model reviews AI output at $0 cost. Pass output + question. Default: qwen2.5:32b.",
    )
    def _explain(
        output: str, question: str = "Is this correct?", model: str = "qwen2.5:32b", dry_run: bool = False
    ) -> str:
        return rondo_explain(output=output, question=question, model=model, dry_run=dry_run)

    @mcp.tool(
        name="rondo_benchmark",
        description="Benchmark: same prompt → multiple models → ranked by speed. Pass models as JSON array. Default: llama3.1:8b + qwen2.5:32b + sonnet.",
    )
    def _benchmark(prompt: str, models: str = "[]", dry_run: bool = False) -> str:
        return rondo_benchmark(prompt=prompt, models=models, dry_run=dry_run)

    @mcp.tool(
        name="rondo_chain",
        description="Pipeline: chain steps where output of step N feeds into step N+1. Pass JSON array of {prompt, model, done_when}. dry_run=True to preview.",
    )
    def _chain(steps_json: str, dry_run: bool = False) -> str:
        return rondo_chain(steps_json=steps_json, dry_run=dry_run)

    @mcp.tool(
        name="rondo_models",
        description="List available AI models: Claude + Ollama local models, with task-type recommendations (code-review→qwen-coder, reasoning→deepseek, etc.).",
    )
    def _models() -> str:
        return rondo_models()

    @mcp.tool(
        name="rondo_templates",
        description="List pre-built round templates: code-review, test-gaps, doc-sweep, security-audit, dependency-check. Each has a ready-to-dispatch prompt.",
    )
    def _templates() -> str:
        return rondo_templates()

    @mcp.tool(
        name="rondo_summarize",
        description="Condense multiple task results into one report via AI. Pass dispatch result JSON. dry_run=True to preview prompt.",
    )
    def _summarize(dispatch_json: str, dry_run: bool = False, model: str = "haiku") -> str:
        return rondo_summarize(dispatch_json=dispatch_json, dry_run=dry_run, model=model)

    @mcp.tool(
        name="rondo_diff",
        description="Compare two dispatch results. Shows new/changed/removed tasks. Pass current + previous JSON.",
    )
    def _diff(current_json: str, previous_json: str = "") -> str:
        return rondo_diff(current_json=current_json, previous_json=previous_json)

    @mcp.tool(
        name="rondo_retry",
        description="Re-run failed tasks from a previous background dispatch. Pass the dispatch_id.",
    )
    def _retry(dispatch_id: str, model: str = "") -> str:
        return rondo_retry(dispatch_id=dispatch_id, model=model)

    @mcp.tool(
        name="rondo_spool_consume",
        description="Drain spool mailbox: read all pending overnight results and delete files. Returns consumed results as JSON.",
    )
    def _spool_consume() -> str:
        return rondo_spool_consume()

    return mcp


def run_mcp() -> None:
    """Start MCP server with stdio transport.

    Called by `rondo mcp` CLI command.
    Claude Code spawns this process, talks via stdin/stdout.
    """
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("anyio").setLevel(logging.WARNING)

    mcp = create_mcp_server()
    mcp.run(transport="stdio")


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b9
