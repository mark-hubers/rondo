# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch — AI composition functions (multi-review, chain, benchmark, cloud).

Rondo-IFS-104, Rondo-REQ-109.
Split from mcp_server.py (Session 97): this file has dispatch logic,
mcp_server.py has tool registration + MCP stdio transport.

Functions here are called by MCP tools AND by CLI (rondo review).
Thread-safe: _background_results protected by _background_lock.

Import direction:
    mcp_dispatch.py → imports runner, dispatch, engine, config (does work)
    mcp_server.py   → imports mcp_dispatch (re-exports for backward compat)
    mcp_tools.py    → imports mcp_dispatch.rondo_multi_review (lazy, for rondo_cloud)
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

# -- Import tool functions from mcp_tools (Finding #195 split)
from rondo.mcp_tools import (  # noqa: F401
    _DEFAULT_AUDIT_DIR,
    _resolve_dir,
    rondo_audit_summary,
    rondo_cloud,
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
_background_lock = threading.Lock()  # -- Thread-safe access to _background_results
_MAX_BACKGROUND_ENTRIES = 100  # -- H-01


def _prune_background() -> None:
    """H-01/H-02: evict oldest completed entries when over max. Thread-safe."""
    with _background_lock:
        if len(_background_results) <= _MAX_BACKGROUND_ENTRIES:
            return
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


# -- Re-export composition tools for backward compatibility
from rondo.mcp_compose import (  # noqa: E402, F401
    rondo_benchmark,
    rondo_chain,
    rondo_explain,
    rondo_multi_review,
    rondo_review_file,
    rondo_summarize,
)


def rondo_retry(dispatch_id: str, model: str = "") -> str:
    """Re-run failed tasks from a previous dispatch — U-56 to U-58.

    RONDO-106: checks in-memory first, then disk (~/.rondo/retry/).
    Works across sessions — failed dispatch results persist on disk.
    """
    with _background_lock:
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
    from rondo.providers import get_provider_with_fallback, parse_model

    provider, resolved_model = get_provider_with_fallback(model)

    # -- REQ-109 req 016: all providers down + no fallback → error, NOT Claude
    provider_name, _ = parse_model(model)
    if provider is None and provider_name and not resolved_model:
        from rondo.engine import RoundResult, TaskResult

        return RoundResult(
            round_name=round_def.name if hasattr(round_def, "name") else "dispatch",
            status="error",
            task_results=[
                TaskResult(
                    task_name="dispatch",
                    status="error",
                    error_code="ERR_PROVIDER_DOWN",
                    error_message=f"Provider '{provider_name}' is down and no healthy fallback configured",
                    model=model,
                )
            ],
        )

    if provider is not None:
        from rondo.audit import AuditConfig, AuditTrail
        from rondo.dispatch import _finalize_dispatch
        from rondo.engine import DispatchUsage, RoundResult, TaskResult

        # -- Strip provider prefix for adapter dispatch (local:llama → llama)
        _, adapter_model = parse_model(resolved_model)
        model = adapter_model or resolved_model

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


def _build_round_and_config(
    prompt: str,
    done_when: str,
    file_path: str,
    model: str,
    dry_run: bool,
    timeout_sec: int,
    project: str,
    max_budget: float,
) -> tuple:
    """Build Round + RondoConfig for dispatch — extracted for complexity."""
    from rondo.config import RondoConfig
    from rondo.engine import Round, Task

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

    return round_def, RondoConfig(**config_kwargs)


def _check_inline_dispatch(model: str, prompt: str, done_when: str, project: str) -> str | None:
    """RONDO-111: return inline dispatch plan if model is empty + prompt provided.

    MCP tools return data only (Cursor confirmed). When no model specified,
    return a plan for the host to execute inline — no subprocess needed.
    Returns None if normal dispatch should proceed.
    """
    if not model and prompt:
        return json.dumps(
            {
                "kind": "inline_dispatch_plan",
                "prompt": prompt,
                "done_when": done_when,
                "model": "current",
                "project": project,
                "note": "No model specified — execute this inline in your current session.",
            }
        )
    return None


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
    file_path, project, err = _validate_run_inputs(file_path, project, prompt)
    if err:
        return err

    # -- RONDO-111/112: inline dispatch + model resolution
    plan = _check_inline_dispatch(model, prompt, done_when, project)
    if plan:
        return plan
    # -- Strip provider prefix (local:llama → llama) and :new suffix
    from rondo.providers import parse_model

    _provider, _model_name = parse_model(model.removesuffix(":new") if model.endswith(":new") else model)
    _clean_model = _model_name or model

    dispatch_fn = lambda: _execute_dispatch(  # noqa: E731
        prompt, done_when, file_path, _clean_model or model, model, dry_run, timeout_sec, project, max_budget
    )

    # -- Background dispatch: return dispatch_id immediately
    if background and not dry_run:
        return _start_background_dispatch(file_path, prompt, dispatch_fn, _session)

    # -- Synchronous dispatch (dry-run or foreground)
    return json.dumps(dispatch_fn(), indent=2)


def _execute_dispatch(
    prompt: str,
    done_when: str,
    file_path: str,
    clean_model: str,
    model: str,
    dry_run: bool,
    timeout_sec: int,
    project: str,
    max_budget: float,
) -> dict:
    """Run the actual dispatch — called synchronously or from background thread."""
    try:
        from rondo.runner import run_round  # pylint: disable=import-outside-toplevel

        round_def, config = _build_round_and_config(
            prompt,
            done_when,
            file_path,
            clean_model,
            dry_run,
            timeout_sec,
            project,
            max_budget,
        )

        result = _dispatch_via_provider_or_claude(round_def, config, model, prompt, dry_run, run_round)

        tasks_out = [
            {
                "name": tr.task_name,
                "status": tr.status,
                "duration_sec": tr.duration_sec,
                "model": tr.model,
                "prompt_sent": tr.prompt_sent[:500] if dry_run else "",
                "prompt_length": len(tr.prompt_sent) if dry_run and tr.prompt_sent else 0,
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


def _start_background_dispatch(file_path: str, prompt: str, dispatch_fn: Any, session: Any) -> str:
    """Launch dispatch in background thread, return dispatch_id JSON immediately."""
    import threading
    import uuid

    dispatch_id = f"mcp-{uuid.uuid4().hex[:12]}"
    _prune_background()

    task_names = _get_task_names(file_path, prompt)
    with _background_lock:
        _background_results[dispatch_id] = {
            "status": "running",
            "dispatch_id": dispatch_id,
            "tasks": [{"name": tn, "status": "pending"} for tn in task_names],
            "total_cost_usd": 0.0,
        }

    def _bg_worker() -> None:
        result = dispatch_fn()
        result["dispatch_id"] = dispatch_id
        with _background_lock:
            _background_results[dispatch_id] = result
        _save_background_result(dispatch_id, result)
        _notify_completion(session, dispatch_id, result)

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


_STATUS_SHORT = {"running": "w", "done": "d", "error": "e", "dispatched": "w"}


def rondo_run_status(dispatch_id: str = "", brief: bool = False, heartbeat: bool = False) -> str:
    """Check status of a background MCP dispatch.

    Three tiers (U-45, U-50):
        heartbeat=True  → ~10 tokens: {"s":"w","d":2,"e":0,"p":1}
        brief=True      → ~40 tokens: {status, done_count, error_count, pending_count}
        (default)       → ~300+ tokens: full results with task output
    """
    if not dispatch_id:
        with _background_lock:
            dispatches = [
                {"dispatch_id": did, "status": r.get("status", "unknown")} for did, r in _background_results.items()
            ]
        return json.dumps({"dispatches": dispatches}, indent=2)

    with _background_lock:
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


# -- sig: mgh-6201.cd.bd955f.7648.d15fa7
