# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# pylint: disable=too-many-lines
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

import asyncio
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

# -- RONDO-213 cycle break: moved DEFAULT_AUDIT_DIR + _resolve_dir from
# -- mcp_tools.py to config.py (leaf module). This eliminates the top-level
# -- mcp_dispatch → mcp_tools edge that created the MCP triangle cycle
# -- (mcp_dispatch → mcp_tools → mcp_compose → mcp_dispatch).
# -- RONDO-222: all lazy imports moved to top — dependency analysis confirmed
# -- no cycles (all targets are leaf/core modules that don't import mcp_dispatch).
from rondo.audit import AuditConfig, AuditTrail
from rondo.config import (
    DEFAULT_AUDIT_DIR,
    RondoConfig,
    resolve_rondo_dir,
)
from rondo.dispatch import finalize_dispatch
from rondo.engine import (
    DispatchUsage,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.envelope import (
    ENVELOPE_SCHEMA_VERSION,
    build_error_envelope,
    normalize_envelope,
)
from rondo.idempotency import cache_result, compute_idempotency_key, get_cached_result
from rondo.notify import NotifyConfig, notify_round_complete
from rondo.providers import (
    get_provider_with_fallback,
    parse_model,
)
from rondo.sanitize import sanitize_task_result
from rondo.structured_log import bind_request_id, log_event  # noqa: E402

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
    return resolve_rondo_dir("~/.rondo/retry", "retry")


def _save_background_result(dispatch_id: str, result: dict) -> None:
    """RONDO-106: persist background result to disk for cross-session retry.

    Only saves if the result has failed tasks — successful dispatches
    don't need retry. Files in ~/.rondo/retry/{dispatch_id}.json.
    """
    tasks = result.get("tasks", [])
    has_failures = any(t.get("status") in ("error", "blocked", "partial") for t in tasks)
    if not has_failures:
        return

    retry_dir = Path(_get_retry_dir()).expanduser()
    try:
        retry_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    retry_dir = Path(_get_retry_dir()).expanduser()
    retry_path = retry_dir / f"{dispatch_id}.json"
    if retry_path.is_file():
        try:
            return json.loads(retry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# -- RONDO-209 cycle break: removed re-export of mcp_compose functions.
# -- Verified zero callers were using "from rondo.mcp_dispatch import rondo_benchmark"
# -- (etc.) so the re-export was dead weight that created a cyclic import.
# -- Callers should import directly from rondo.mcp_compose for these tools.


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
        return json.dumps(
            build_error_envelope(
                error_code="ERR_UNKNOWN_DISPATCH_ID",
                error_message=f"Unknown dispatch_id: {dispatch_id}",
            )
        )

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
        loop = asyncio.new_event_loop()
        loop.run_until_complete(session.send_log_message(level="info", data=msg))
        loop.close()
    except (AttributeError, TypeError, OSError, RuntimeError):
        pass  # -- U-49: best-effort, polling is fallback


def _provider_down_round(round_def: Any, provider_name: str, model: str, dry_run: bool, _run_pipeline: Any) -> Any:
    """Provider down: dry-run previews free, live errors — RONDO-341 extract.

    Dry run is the FREE preview (GOLDEN-FIVE #3): no keys, no network, no
    healthy provider may be required to preview. Found on Linux: keyless
    dry_run returned ERR_PROVIDER_DOWN before previewing anything.
    Extracted from _dispatch_via_provider_or_claude (complexity lock <=15).
    """
    round_name = round_def.name if hasattr(round_def, "name") else "dispatch"
    if dry_run:
        note = (
            f"DRY RUN: provider '{provider_name}' unavailable (no key or unhealthy) — preview only, nothing dispatched"
        )
        skipped_tr = TaskResult(task_name="dispatch", status="skipped", raw_output=note, model=model)
        return RoundResult(round_name=round_name, status="done", task_results=[_run_pipeline(skipped_tr, "dispatch")])
    error_tr = TaskResult(
        task_name="dispatch",
        status="error",
        error_code="ERR_PROVIDER_DOWN",
        error_message=f"Provider '{provider_name}' is down and no healthy fallback configured",
        model=model,
    )
    # -- RONDO-139: even provider-down errors get the pipeline
    return RoundResult(round_name=round_name, status="error", task_results=[_run_pipeline(error_tr, "dispatch")])


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

    RONDO-139 (Finding #203): EVERY result — success, error, dry-run, provider-down,
    exception — MUST go through _finalize_dispatch. No early returns. The pipeline
    is ALWAYS-ON for all paths.
    """
    # -- Build finalize_config + audit_trail upfront — used by ALL paths
    audit_dir = resolve_rondo_dir(DEFAULT_AUDIT_DIR, "audit")
    audit_trail = None
    try:
        audit_trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir))
    except (OSError, TypeError):
        pass

    finalize_config = (
        config
        if isinstance(config, RondoConfig)
        else RondoConfig(
            audit_dir=audit_dir,
            results_dir=resolve_rondo_dir("~/.rondo/results", "results"),
        )
    )

    def _run_pipeline(tr: TaskResult, task_name: str, audit_record: Any = None) -> TaskResult:
        """ALWAYS-ON pipeline wrapper — RONDO-139.

        Every TaskResult passes through finalize_dispatch (audit OUTCOME,
        sanitize, spool, history, metrics) regardless of status.

        RONDO-202 (Finding #223): on finalize failure, we STILL sanitize
        the returned tr before handing it back to the caller. Defensive
        return must not leak unsanitized secrets.
        """
        try:
            usage = DispatchUsage(task_name=task_name, model=tr.model or model, cost_usd=tr.cost_usd or 0.0)
            finalized_tr, _usage = finalize_dispatch(
                tr,
                usage,
                finalize_config,
                audit_trail,
                audit_record,
                round_name=round_def.name if hasattr(round_def, "name") else "dispatch",
            )
            return finalized_tr
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Pipeline finalization failed for %s: %s", task_name, exc)
            # -- RONDO-202 Finding #223: sanitize BEFORE returning even on finalize failure
            try:
                sanitized_tr, _report = sanitize_task_result(tr, config=None)
                return sanitized_tr
            except (TypeError, AttributeError):
                # -- Defensive: if even sanitize fails, scrub raw_output manually
                tr.raw_output = "[REDACTED:sanitize_failed]"
                return tr

    provider, resolved_model = get_provider_with_fallback(model)
    provider_name, _ = parse_model(model)

    # -- REQ-109 req 016: provider down → error result MUST also flow through pipeline
    if provider is None and provider_name and not resolved_model:
        return _provider_down_round(round_def, provider_name, model, dry_run, _run_pipeline)

    if provider is not None:
        # -- Strip provider prefix for adapter dispatch (local:llama → llama)
        _, adapter_model = parse_model(resolved_model)
        model = adapter_model or resolved_model

        task_results = _run_provider_round(
            round_def=round_def,
            provider=provider,
            model=model,
            prompt=prompt,
            dry_run=dry_run,
            budget_cap=finalize_config.max_budget_usd,
            audit_trail=audit_trail,
            run_pipeline=_run_pipeline,
        )
        ok_statuses = {"done", "skipped"}
        return RoundResult(
            round_name=round_def.name,
            status="done" if all(t.status in ok_statuses for t in task_results) else "partial",
            task_results=task_results,
        )
    return run_round(round_def, config=config)


def _dispatch_one_task(
    task: Any,
    provider: Any,
    model: str,
    prompt: str,
    audit_trail: Any,
    round_name: str,
    run_pipeline: Any,
) -> Any:
    """Process a single task in a provider round — RONDO-139 always-on path.

    Records audit INTENT, dispatches, catches exceptions, runs pipeline.
    Extracted from _dispatch_via_provider_or_claude to reduce complexity.
    """
    task_prompt = task.instruction or prompt

    # -- REQ-111: inject smart return template for structured JSON output
    try:
        from rondo.smart_return import build_return_prompt  # pylint: disable=import-outside-toplevel

        return_prompt = build_return_prompt(provider=model)
        task_prompt = f"{task_prompt}\n{return_prompt}"
    except (ImportError, TypeError):
        pass  # -- smart_return not available — dispatch without template

    # -- Audit INTENT before dispatch
    audit_record = None
    if audit_trail:
        try:
            audit_record = audit_trail.record_intent(
                task_name=task.name,
                round_name=round_name,
                model=model,
                prompt=task_prompt,
                task_type=getattr(task, "task_type", "") or "",
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Audit INTENT failed for %s: %s", task.name, exc)

    # -- RONDO-139: wrap dispatch in try/except so exceptions also flow through pipeline
    try:
        tr = provider.dispatch(prompt=task_prompt, model=model, task_name=task.name)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        tr = TaskResult(
            task_name=task.name,
            status="error",
            error_code="ERR_PROVIDER",
            error_message=f"Adapter exception: {type(exc).__name__}: {str(exc)[:200]}",
            model=model,
        )
    return run_pipeline(tr, task.name, audit_record)


def _run_provider_round(
    round_def: Any,
    provider: Any,
    model: str,
    prompt: str,
    dry_run: bool,
    budget_cap: float | None,
    audit_trail: Any,
    run_pipeline: Any,
) -> list:
    """Process all tasks in a provider round with budget cap enforcement.

    RONDO-139: every result flows through pipeline.
    RONDO-141: pre-dispatch budget cap check accumulates running cost.
    RONDO-202 (Finding #226): predictive cap (running + estimated >= cap)
    and thread-safe running_cost updates via local lock.
    """
    # -- RONDO-202: thread-safe running cost and predictive estimate
    # -- Estimate: average cost of completed tasks, fallback to $0.01 per task
    running_cost: float = 0.0
    cost_lock = threading.Lock()
    estimated_next_cost: float = 0.01  # -- conservative first-dispatch estimate
    task_results = []

    def _check_budget(current_running: float, current_estimate: float) -> bool:
        """Return True if next dispatch would exceed budget_cap."""
        if budget_cap is None:
            return False
        # -- Predictive: running + estimated >= cap (not reactive)
        return (current_running + current_estimate) >= budget_cap

    for task in round_def.tasks:
        task_prompt = task.instruction or prompt

        if dry_run:
            tr = TaskResult(task_name=task.name, status="skipped", prompt_sent=task_prompt[:500], model=model)
            task_results.append(run_pipeline(tr, task.name))
            continue

        # -- RONDO-202: predictive, thread-safe budget check
        with cost_lock:
            if _check_budget(running_cost, estimated_next_cost):
                tr = TaskResult(
                    task_name=task.name,
                    status="error",
                    error_code="ERR_BUDGET_EXCEEDED",
                    error_message=(
                        f"Round budget cap ${budget_cap:.4f} reached "
                        f"(spent ${running_cost:.4f}, est next ${estimated_next_cost:.4f})"
                    ),
                    model=model,
                )
                task_results.append(run_pipeline(tr, task.name))
                continue

        tr = _dispatch_one_task(
            task=task,
            provider=provider,
            model=model,
            prompt=prompt,
            audit_trail=audit_trail,
            round_name=round_def.name,
            run_pipeline=run_pipeline,
        )
        task_results.append(tr)

        # -- RONDO-202: update running cost + estimate under lock
        with cost_lock:
            actual_cost = tr.cost_usd or 0.0
            running_cost += actual_cost
            # -- Update estimate: rolling average of observed costs, floor $0.001
            if actual_cost > 0:
                estimated_next_cost = max(actual_cost, 0.001)

    return task_results


def _get_task_names(file_path: str, prompt: str) -> list[str]:
    """U-31 + U-54: pre-populate task names for background progress tracking."""
    if prompt:
        return ["inline-task"]
    try:
        from rondo.round_loader import load_round  # pylint: disable=import-outside-toplevel

        rd = load_round(file_path)
        return [t.name for t in rd.tasks]
    except (FileNotFoundError, AttributeError, TypeError, ImportError, ValueError, OSError, json.JSONDecodeError):
        return []


def _validate_run_inputs(file_path: str, project: str, prompt: str) -> tuple[str, str, str | None]:
    """Validate and resolve file_path + project. Returns (file_path, project, error_json)."""
    # -- H-07: prompt size limit
    if prompt and len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        return (
            file_path,
            project,
            json.dumps(
                build_error_envelope(
                    error_code="ERR_INPUT_TOO_LARGE",
                    error_message="Prompt too large",
                )
            ),
        )
    if prompt:
        file_path = ""
    elif file_path:
        file_path = str(Path(file_path).expanduser())
        if not Path(file_path).exists():
            return (
                file_path,
                project,
                json.dumps(
                    build_error_envelope(
                        error_code="ERR_FILE_NOT_FOUND",
                        error_message=f"File not found: {file_path}",
                    )
                ),
            )
    else:
        return (
            file_path,
            project,
            json.dumps(
                build_error_envelope(
                    error_code="ERR_INVALID_INPUT",
                    error_message="Provide file_path or prompt",
                )
            ),
        )

    if project:
        project = str(Path(project).expanduser())
        if not Path(project).is_dir():
            return (
                file_path,
                project,
                json.dumps(
                    build_error_envelope(
                        error_code="ERR_PROJECT_NOT_FOUND",
                        error_message=f"Project dir not found: {project}",
                    )
                ),
            )

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
    bare: bool = True,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    add_dir: str = "",
    json_schema: str = "",
) -> tuple:
    """Build Round + RondoConfig for dispatch — extracted for complexity."""
    effective_project = _resolve_dispatch_project(file_path=file_path, project=project, add_dir=add_dir)
    effective_turns = _resolve_claude_p_max_turns(max_turns=max_turns, file_path=file_path, prompt=prompt)
    effective_add_dir = add_dir or effective_project

    if prompt:
        round_def = Round(
            name="inline",
            tasks=[Task(name="inline-task", instruction=prompt, done_when=done_when)],
        )
    else:
        from rondo.round_loader import load_round  # pylint: disable=import-outside-toplevel

        round_def = load_round(file_path)

    # -- RONDO-257: read claude_p_* and claude_agent_* from ~/.rondo/config.toml
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    global_toml = get_rondo_config()
    config_kwargs: dict = {
        "default_model": model,
        "default_execution": global_toml.get("default_execution", ""),
        "dry_run": dry_run,
        "task_timeout_sec": timeout_sec,
        "bare": bare,
        "dispatch_system_prompt": global_toml.get("dispatch_system_prompt", ""),
        # -- RONDO-258: COALESCE per-call → config.toml → code default
        "claude_p_rules": rules or global_toml.get("claude_p_rules", ""),
        "claude_p_allowed_tools": allowed_tools or global_toml.get("claude_p_allowed_tools", "Read,Grep,Glob"),
        "claude_p_max_turns": effective_turns,
        "claude_p_add_dir": effective_add_dir or global_toml.get("claude_p_add_dir", ""),
        "claude_p_json_schema": json_schema or global_toml.get("claude_p_json_schema", ""),
        "claude_agent_rules": global_toml.get("claude_agent_rules", ""),
        "claude_agent_max_turns": global_toml.get("claude_agent_max_turns", 10),
        "claude_agent_allowed_tools": global_toml.get("claude_agent_allowed_tools", "Read,Grep,Glob"),
    }
    if effective_project:
        config_kwargs["project"] = effective_project
    if max_budget > 0:
        config_kwargs["max_budget_usd"] = max_budget

    return round_def, RondoConfig(**config_kwargs)


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-279: Routing logic extracted to dispatch_routing.py
# --  (~380 lines moved). Re-exported here for backward compat —
# --  all existing `from rondo.mcp_dispatch import X` still work.
# -- ──────────────────────────────────────────────────────────────
from rondo.dispatch_routing import (  # noqa: F401,E402
    _EXECUTION_MODES,
    DEFAULT_CONTEXT_LIMIT,
    PLAN_SCHEMA_VERSION,
    _build_agent_plan,
    _build_agent_plan_or_error,
    _build_inline_plan,
    _build_subprocess_plan,
    _is_in_session,
    _normalize_execution_mode,
    _normalize_subprocess_model,
    _resolve_effective_execution,
    _resolve_no_provider_model,
    _route_by_execution_mode,
    _should_bypass_execution_override,
    check_context_limit,
    estimate_token_count,
    resolve_dispatch_engine,
)


def rondo_run_file(
    file_path: str = "",
    dry_run: bool = True,
    model: str = "",
    project: str = "",
    max_budget: float = 0.0,
    timeout_sec: int = 300,
    background: bool = False,
    prompt: str = "",
    done_when: str = "Task completed. Return results.",
    _session: Any = None,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    add_dir: str = "",
    json_schema: str = "",
    execution: str = "",
    plan_only: bool = False,
) -> str:
    """Run a round file or inline prompt — MCP dispatch tool.

    Two modes:
        1. File: file_path="my_round.py" — loads build_round() from file
        2. Inline: prompt="Search for X" — creates one-task round in memory (U-33)

    Default dry_run=True for safety. Set dry_run=False for real dispatch.

    Per-call overrides (RONDO-258, REQ-111 reqs 478-479):
        rules: --system-prompt override (replaces config.toml claude_p_rules)
        allowed_tools: --allowedTools override (e.g. "Read,Edit,Bash")
        max_turns: --max-turns override (0 = use config default)
        add_dir: --add-dir override (additional directory access)
        json_schema: --json-schema override (platform-enforced structured output)
        execution: dispatch mode override: inline | subprocess | agent
        plan_only: return plan payload without execution (debug/compat override)
    """
    # -- RONDO-202 (Finding #227): wire structured_log request_id for tracing

    with bind_request_id():
        log_event(
            "INFO",
            "rondo_run_file invoked",
            component="mcp_dispatch",
            model=model,
            dry_run=dry_run,
            background=background,
            has_prompt=bool(prompt),
            has_file=bool(file_path),
        )
        return _rondo_run_file_inner(
            file_path=file_path,
            dry_run=dry_run,
            model=model,
            project=project,
            max_budget=max_budget,
            timeout_sec=timeout_sec,
            background=background,
            prompt=prompt,
            done_when=done_when,
            _session=_session,
            rules=rules,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            add_dir=add_dir,
            json_schema=json_schema,
            execution=execution,
            plan_only=plan_only,
        )


def _idempotency_lookup(
    prompt: str, model: str, execution: str, dry_run: bool, background: bool
) -> tuple[str, str | None]:
    """RONDO-202 (Finding #227): look up cached result for (prompt, model).

    Returns (key, cached_result) — key is empty if not eligible.
    """
    if not prompt or dry_run or background:
        return "", None

    key = compute_idempotency_key(prompt, model, execution)
    cached = get_cached_result(key)
    if cached is None:
        return key, None

    log_event(
        "INFO",
        "idempotency cache hit — returning cached result",
        component="mcp_dispatch",
        key=key[:16],
    )
    return key, cached if isinstance(cached, str) else json.dumps(cached, indent=2)


def _idempotency_store(key: str, result_str: str) -> None:
    """RONDO-202: cache successful results for future deduplication."""
    if not key:
        return

    cache_result(key, result_str)
    log_event("INFO", "result cached for idempotency", component="mcp_dispatch", key=key[:16])


def _resolve_option_c_execution_override(execution: str, plan_only: bool, session: Any) -> tuple[str, list[str]]:
    """Apply Option C fallback overrides before execution-mode routing."""
    if session is None or plan_only or (execution or "").strip().lower() != "inline":
        return execution, []
    if os.environ.get("RONDO_OPTION_C_FORCE_INLINE_FAIL") != "1":
        return execution, []
    return "subprocess", ["inline_auto_execute_failed; used subprocess fallback"]


def _resolve_dispatch_project(file_path: str, project: str, add_dir: str) -> str:
    """Resolve subprocess cwd for stable file-relative execution."""
    requested_project = (project or "").strip()
    if requested_project:
        return requested_project

    if file_path:
        return str(Path(file_path).expanduser().resolve().parent)

    add_dir_value = (add_dir or "").strip()
    if not add_dir_value:
        return ""
    return add_dir_value.split(",")[0].strip()


def _resolve_claude_p_max_turns(max_turns: int, file_path: str, prompt: str) -> int:
    """Use higher default max-turns for round-file dispatches."""
    if max_turns > 0:
        return max_turns

    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    cfg_turns = int(get_rondo_config().get("claude_p_max_turns", 5))
    is_round_dispatch = bool(file_path and not prompt)
    if is_round_dispatch:
        return max(cfg_turns, 12)
    return cfg_turns


def _resolve_dispatch_model_override(file_path: str, prompt: str, model: str, clean_model: str) -> str:
    """Let round task models win when caller leaves model at default sonnet."""
    if prompt or not file_path:
        return clean_model or model
    if (model or "").strip() != "sonnet":
        return clean_model or model

    try:
        from rondo.round_loader import load_round  # pylint: disable=import-outside-toplevel

        rd = load_round(file_path)
    except (FileNotFoundError, ValueError, TypeError, ImportError, OSError, json.JSONDecodeError):
        return clean_model or model

    has_task_model = any(bool((getattr(task, "model", "") or "").strip()) for task in rd.tasks)
    if has_task_model:
        return ""
    return clean_model or model


def _attach_route_warnings(result_obj: dict, route_warnings: list[str]) -> dict:
    """Attach fallback warnings to normalized result envelope."""
    if not route_warnings:
        return result_obj
    existing = result_obj.get("warnings")
    warnings_out = list(existing) if isinstance(existing, list) else []
    warnings_out.extend(route_warnings)
    result_obj["warnings"] = warnings_out
    return result_obj


def _rondo_run_file_inner(
    file_path: str,
    dry_run: bool,
    model: str,
    project: str,
    max_budget: float,
    timeout_sec: int,
    background: bool,
    prompt: str,
    done_when: str,
    _session: Any,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    add_dir: str = "",
    json_schema: str = "",
    execution: str = "",
    plan_only: bool = False,
) -> str:
    """Inner dispatch body — extracted for complexity budget. RONDO-202."""
    file_path, project, err = _validate_run_inputs(file_path, project, prompt)
    if err:
        log_event("WARNING", "input validation failed", component="mcp_dispatch", error=err[:200])
        return err

    # -- RONDO-202 (Finding #227): idempotency cache — short-circuit duplicates
    idempotency_key, cached = _idempotency_lookup(prompt, model, execution, dry_run, background)
    if cached is not None:
        return cached

    # -- Base engine routing (provider prefixes/background/:new/context checks)
    engine = resolve_dispatch_engine(
        model=model,
        background=background,
        prompt=prompt,
        done_when=done_when,
        project=project,
    )
    log_event(
        "INFO",
        "engine resolved",
        component="mcp_dispatch",
        engine=engine.get("engine"),
        reason=engine.get("reason", "")[:120],
    )

    if engine["engine"] == "error":
        reason = str(engine.get("reason", ""))
        error_code = "ERR_INPUT_TOO_LARGE" if "exceeds context limit" in reason.lower() else "ERR_INVALID_INPUT"
        return json.dumps(
            build_error_envelope(
                error_code=error_code,
                error_message=reason,
                context={"model": model},
            ),
            indent=2,
        )

    execution, route_warnings = _resolve_option_c_execution_override(execution, plan_only, _session)

    engine, model, route_error = _route_by_execution_mode(
        engine=engine,
        model=model,
        execution=execution,
        plan_only=plan_only,
        session=_session,
        background=background,
        prompt=prompt,
        done_when=done_when,
        project=project,
    )
    if route_error:
        return route_error

    if engine["engine"] in ("inline", "agent"):
        return json.dumps(engine, indent=2)

    # -- HTTP adapter or subprocess: proceed with dispatch

    _provider, _model_name = parse_model(model.removesuffix(":new") if model.endswith(":new") else model)
    _clean_model = _model_name or model
    _use_bare = engine.get("_bare", True)  # -- RONDO-254: inline routes set _bare=False

    def dispatch_fn() -> dict:
        """Closure wrapping _execute_dispatch with resolved model args."""
        return _execute_dispatch(
            prompt,
            done_when,
            file_path,
            _resolve_dispatch_model_override(file_path, prompt, model, _clean_model),
            model,
            dry_run,
            timeout_sec,
            project,
            max_budget,
            bare=_use_bare,
            rules=rules,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            add_dir=add_dir,
            json_schema=json_schema,
        )

    if background and not dry_run:
        return _start_background_dispatch(file_path, prompt, dispatch_fn, _session)

    return _dispatch_and_cache(idempotency_key, dispatch_fn, route_warnings)


def _dispatch_and_cache(key: str, dispatch_fn: Any, route_warnings: Any) -> str:
    """Run a dispatch under single-flight + cache the result — RONDO-360/390.

    Two identical concurrent dispatches used to both miss the cache and both
    PAY (the lookup→dispatch→store sequence was unlocked). RONDO-360: same-key
    THREADS serialize on key_lock. RONDO-390 (Mark's ruling, checklist 22):
    same-key PROCESSES serialize on cross_process_key_lock (per-key flock) —
    the in-process lock goes first so only one thread per process contends on
    the file lock. The re-check under both locks covers both layers: a peer
    process's store lands in the shared JSONL before it releases its flock.
    Empty key (ineligible) = no locking.
    """

    def _run() -> str:
        result_obj = _attach_route_warnings(normalize_envelope(dispatch_fn()), route_warnings)
        result_str = json.dumps(result_obj, indent=2)
        _idempotency_store(key, result_str)
        return result_str

    if not key:
        return _run()

    from rondo.idempotency import cross_process_key_lock, key_lock  # pylint: disable=import-outside-toplevel

    with key_lock(key), cross_process_key_lock(key):
        # -- re-check under the locks: a peer (thread OR process) may have
        # -- finished while we resolved routing — reuse instead of paying again.
        recheck = get_cached_result(key)
        if recheck is not None:
            return recheck if isinstance(recheck, str) else json.dumps(recheck, indent=2)
        return _run()


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
    bare: bool = True,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    add_dir: str = "",
    json_schema: str = "",
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
            bare=bare,
            rules=rules,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            add_dir=add_dir,
            json_schema=json_schema,
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
                # -- RONDO-211 #258: was [:2000] which silently truncated AI review
                # -- output mid-sentence. RONDO-209 #247 bumped provider max_tokens
                # -- to 8K but missed this Rondo-side cap, causing partial closure.
                # -- MCP responses can handle multi-MB JSON; no need for an arbitrary
                # -- 2000-char cap. If a future client needs a cap, add a parameter.
                "raw_output": tr.raw_output if not dry_run else "",
                "cost_usd": tr.cost_usd or 0.0,
                "error_code": tr.error_code or "",
                "error_message": tr.error_message or "",
            }
            for tr in result.task_results
        ]
        statuses = [t["status"] for t in tasks_out]
        payload = {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "status": result.status,
            "round_name": result.round_name,
            "tasks": tasks_out,
            "done_count": statuses.count("done") + statuses.count("skipped"),
            "error_count": statuses.count("error") + statuses.count("blocked"),
            "partial_count": statuses.count("partial"),
            "pending_count": statuses.count("pending"),
            "total_cost_usd": sum(u.cost_usd for u in result.usage),
            "duration_sec": result.duration_sec,
            "dry_run": dry_run,
        }
        return normalize_envelope(payload)
    except TimeoutError as exc:
        return build_error_envelope(
            error_code="ERR_TIMEOUT",
            error_message=str(exc) or "Dispatch timed out before completing results.",
        )
    except (FileNotFoundError, AttributeError, TypeError, ImportError, OSError) as exc:
        exc_text = str(exc).strip()
        msg = f"{type(exc).__name__}: {exc_text}" if exc_text else f"{type(exc).__name__} during dispatch"
        code = "ERR_TIMEOUT" if "timeout" in exc_text.lower() else "ERR_DISPATCH_EXCEPTION"
        return build_error_envelope(
            error_code=code,
            error_message=msg,
        )


def _start_background_dispatch(file_path: str, prompt: str, dispatch_fn: Any, session: Any) -> str:
    """Launch dispatch in background thread, return dispatch_id JSON immediately."""
    dispatch_id = f"mcp-{uuid.uuid4().hex[:12]}"
    _prune_background()

    task_names = _get_task_names(file_path, prompt)
    with _background_lock:
        _background_results[dispatch_id] = {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "status": "running",
            "dispatch_id": dispatch_id,
            "tasks": [{"name": tn, "status": "pending"} for tn in task_names],
            "done_count": 0,
            "error_count": 0,
            "partial_count": 0,
            "pending_count": len(task_names),
            "total_cost_usd": 0.0,
            "duration_sec": 0.0,
            "dry_run": False,
        }

    def _bg_worker() -> None:
        result = normalize_envelope(dispatch_fn())
        result["dispatch_id"] = dispatch_id
        with _background_lock:
            _background_results[dispatch_id] = result
        _save_background_result(dispatch_id, result)
        _notify_completion(session, dispatch_id, result)

    thread = threading.Thread(target=_bg_worker, daemon=True)
    thread.start()
    return json.dumps(
        normalize_envelope(
            {
                "schema_version": ENVELOPE_SCHEMA_VERSION,
                "status": "dispatched",
                "dispatch_id": dispatch_id,
                "tasks": task_names,
                "message": "Use rondo_run_status to check progress.",
            }
        ),
        indent=2,
    )


_STATUS_SHORT = {"running": "w", "done": "d", "partial": "p", "error": "e", "dispatched": "w"}


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
        return json.dumps(
            build_error_envelope(
                error_code="ERR_UNKNOWN_DISPATCH_ID",
                error_message=f"Unknown dispatch_id: {dispatch_id}",
            ),
            indent=2,
        )

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

    # -- U-32 (REQ-100 addendum): rondo_run_status MUST include completed task
    # -- results inline with raw_output truncated to 2000 chars so callers
    # -- don't need to read separate files. RONDO-212 moved the truncation
    # -- from _execute_dispatch (producer) to here (consumer boundary) because
    # -- rondo_multi_review needs the full output (see RONDO-211 finding #258).
    # -- Shallow copy to avoid mutating _background_results storage.
    if "tasks" in result and isinstance(result["tasks"], list):
        truncated = normalize_envelope(dict(result))
        truncated["tasks"] = [{**t, "raw_output": (t.get("raw_output") or "")[:2000]} for t in result["tasks"]]
        return json.dumps(truncated, indent=2)

    return json.dumps(normalize_envelope(result), indent=2)


# -- ──────────────────────────────────────────────────────────────
# --  MCP server setup (stdio transport)
# -- ──────────────────────────────────────────────────────────────


# -- sig: mgh-6201.cd.bd955f.41eb.bc8ae6
