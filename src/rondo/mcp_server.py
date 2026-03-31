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

Tools exposed:
    rondo_metrics       — full dashboard data (cost, reliability, latency, health)
    rondo_health        — quick GREEN/YELLOW/RED status
    rondo_audit_summary — recent dispatch records
    rondo_dispatch_info — Rondo version, commands, capabilities

Import direction:
    mcp_server.py → imports metrics, _version (reads computed data)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- ──────────────────────────────────────────────────────────────
# --  Default paths — ALWAYS-ON data locations
# -- ──────────────────────────────────────────────────────────────


def _resolve_dir(default: str, subdir: str) -> str:
    """Resolve path: RONDO_TEST_DIR → default. Shared by MCP tools."""
    import os

    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return os.path.join(test_dir, subdir)
    return default


_DEFAULT_AUDIT_DIR = "~/.rondo/audit"
_DEFAULT_SPOOL_DIR = "~/.rondo/spool"


# -- ──────────────────────────────────────────────────────────────
# --  Tool functions (testable without MCP transport)
# -- ──────────────────────────────────────────────────────────────


def rondo_metrics() -> str:
    """Full metrics dashboard — cost, reliability, latency, tokens, health.

    IFS-104 req 003: query tool for dashboard data.
    Returns JSON string — same data as `rondo metrics --json`.
    """
    from rondo.metrics import compute_metrics

    report = compute_metrics(
        audit_dir=_resolve_dir(_DEFAULT_AUDIT_DIR, "audit"), spool_dir=_resolve_dir(_DEFAULT_SPOOL_DIR, "spool")
    )
    return json.dumps(report.to_dict(), indent=2)


def rondo_health() -> str:
    """Quick health check — GREEN/YELLOW/RED with key numbers.

    IFS-104 req 005: lightweight status for preflight decisions.
    """
    from rondo.metrics import compute_metrics

    report = compute_metrics(
        audit_dir=_resolve_dir(_DEFAULT_AUDIT_DIR, "audit"), spool_dir=_resolve_dir(_DEFAULT_SPOOL_DIR, "spool")
    )
    return json.dumps(
        {
            "health": report.health,
            "total_dispatches": report.total_dispatches,
            "success_rate": report.success_rate,
            "total_cost_usd": report.total_cost_usd,
            "spool_pending": report.spool_pending,
        }
    )


def rondo_audit_summary(limit: int = 10) -> str:
    """Recent dispatch audit records — last N outcomes.

    IFS-104 req 003: query tool for audit data.
    """
    audit_path = Path(_resolve_dir(_DEFAULT_AUDIT_DIR, "audit")).expanduser() / "rondo_audit.jsonl"
    if not audit_path.exists():
        return json.dumps({"recent": [], "total": 0})

    records = []
    for line in audit_path.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("status") != "INTENT":
                records.append(r)
        except json.JSONDecodeError:
            continue

    recent = records[-limit:] if records else []
    return json.dumps(
        {
            "recent": recent,
            "total": len(records),
        }
    )


def rondo_dispatch_info() -> str:
    """Rondo version, commands, capabilities, design principles.

    IFS-104 req 003: discovery tool for AI agents.
    Same data as `rondo --ai-help` but via MCP.
    """
    from rondo._version import get_version
    from rondo.cli import build_parser

    ## -- U-55: derive command list from CLI parser (single source of truth)
    commands: list[str] = []
    parser = build_parser()
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices:
            commands = sorted(action.choices.keys())
            break

    return json.dumps(
        {
            "name": "rondo",
            "version": get_version(),
            "description": "Define AI tasks in Python, send them to Claude, get structured results back.",
            "commands": commands,
            "interfaces": ["python_import", "cli", "mcp_stdio"],
            "design_principles": ["COALESCE", "ALWAYS-ON", "Dual-Path-With-Alerting"],
            "always_on_artifacts": [
                "audit_jsonl",
                "prompt_file",
                "result_file",
                "spool_file",
                "history_record",
                "metrics_dict",
            ],
        }
    )


## -- Background dispatch tracking (RONDO-39)
_background_results: dict[str, dict] = {}


def rondo_history(model: str = "", status: str = "", limit: int = 20) -> str:
    """Query dispatch history — REQ-104 reqs 003-005.

    Returns recent dispatch records with model aggregate stats.
    Filterable by model and status.
    """
    try:
        from rondo.history import aggregate_by_model, load_history, query_history

        records = load_history(history_dir="reports")
        if model or status:
            records = query_history(
                records,
                model=model or None,
                status=status or None,
            )
        recent = records[-limit:] if len(records) > limit else records
        agg = aggregate_by_model(records)
        return json.dumps({"records": recent, "aggregate": agg, "total": len(records)}, indent=2)
    except (ImportError, OSError, TypeError) as exc:
        return json.dumps({"records": [], "aggregate": {}, "total": 0, "error": str(exc)})


def rondo_templates() -> str:
    """List pre-built round templates — reusable patterns for common tasks.

    Templates are inline instructions that can be dispatched via rondo_run(prompt=).
    """
    templates = [
        {
            "name": "code-review",
            "description": "Review code for bugs, security, and quality issues",
            "prompt": "Review all Python files in the current directory. Report: bugs, security issues, missing error handling, code quality concerns. Format as numbered findings.",
            "done_when": "All findings listed with file, line, and severity.",
            "model": "sonnet",
        },
        {
            "name": "test-gaps",
            "description": "Find untested code — functions without matching test_* functions",
            "prompt": "Scan src/ and tests/ directories. List every function in src/ that has no corresponding test. Report as: file:function → missing test.",
            "done_when": "All untested functions listed.",
            "model": "haiku",
        },
        {
            "name": "doc-sweep",
            "description": "Check documentation freshness — find stale or missing docs",
            "prompt": "Check all .md files in the project. For each: is it current? Does it match the code? List stale docs with what needs updating.",
            "done_when": "All docs reviewed. Stale items listed.",
            "model": "haiku",
        },
        {
            "name": "security-audit",
            "description": "Scan for security vulnerabilities in code",
            "prompt": "Scan all source files for: hardcoded secrets, SQL injection, command injection, path traversal, insecure defaults. Report each as CRITICAL/HIGH/MEDIUM with file and line.",
            "done_when": "Security audit complete. All findings listed by severity.",
            "model": "sonnet",
        },
        {
            "name": "dependency-check",
            "description": "Check for outdated or vulnerable dependencies",
            "prompt": "Read pyproject.toml (or package.json or go.mod). For each dependency: check if there's a newer version. Flag any with known CVEs.",
            "done_when": "All dependencies checked. Outdated and vulnerable items listed.",
            "model": "haiku",
        },
    ]
    return json.dumps({"templates": templates, "count": len(templates)}, indent=2)


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
        output = task.get("raw_output", "")[:3000]
        status = task.get("status", "unknown")
        parts.append(f"## Task: {name} ({status})\n{output}\n")

    prompt = "\n".join(parts)

    if dry_run:
        return json.dumps({"status": "done", "summary_prompt": prompt[:500], "task_count": len(tasks)})

    # -- Dispatch summarization via rondo_run_file
    result = rondo_run_file(prompt=prompt, done_when="Summary report written.", dry_run=False, model=model)
    return result


def rondo_diff(current_json: str, previous_json: str = "") -> str:
    """Compare two dispatch results — U-59 to U-61.

    Shows what's new, changed, or removed between runs.
    Useful for recurring scans (USH weekly) to spot deltas.
    """
    try:
        current = json.loads(current_json) if current_json else {}
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid current_json"})

    if not previous_json:
        task_count = len(current.get("tasks", []))
        return json.dumps(
            {"status": "done", "diff": "No previous — all results are new", "changes": task_count, "new": task_count}
        )

    try:
        previous = json.loads(previous_json) if previous_json else {}
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid previous_json"})

    # -- Compare task outputs
    curr_tasks = {t.get("name", ""): t.get("raw_output", "") for t in current.get("tasks", [])}
    prev_tasks = {t.get("name", ""): t.get("raw_output", "") for t in previous.get("tasks", [])}

    new_tasks = set(curr_tasks) - set(prev_tasks)
    removed_tasks = set(prev_tasks) - set(curr_tasks)
    changed_tasks = {n for n in curr_tasks if n in prev_tasks and curr_tasks[n] != prev_tasks[n]}

    changes = len(new_tasks) + len(removed_tasks) + len(changed_tasks)

    return json.dumps(
        {
            "status": "done",
            "changes": changes,
            "new": sorted(new_tasks),
            "removed": sorted(removed_tasks),
            "changed": sorted(changed_tasks),
            "unchanged": len(curr_tasks) - len(changed_tasks) - len(new_tasks),
        },
        indent=2,
    )


def rondo_retry(dispatch_id: str, model: str = "") -> str:
    """Re-run failed tasks from a previous dispatch — U-56 to U-58.

    Looks up the dispatch result, finds failed/error tasks, re-dispatches them.
    """
    result = _background_results.get(dispatch_id)
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


def rondo_spool_consume() -> str:
    """Consume all pending spool results — mailbox drain.

    Reads all spool files, returns their contents, and deletes them.
    This is how OB/ACE picks up overnight dispatch results.
    """
    try:
        from rondo.spool import SpoolConfig, SpoolManager

        spool = SpoolManager(config=SpoolConfig(spool_dir=_resolve_dir(_DEFAULT_SPOOL_DIR, "spool")))
        consumed = spool.consume_all()
        return json.dumps({"consumed": consumed, "count": len(consumed)}, indent=2)
    except (ImportError, OSError, TypeError) as exc:
        return json.dumps({"consumed": [], "count": 0, "error": str(exc)})


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
    import os
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

            # -- Strip CLAUDECODE to prevent nested session errors
            old_cc = os.environ.pop("CLAUDECODE", None)
            try:
                result = run_round(round_def, config=config)
            finally:
                if old_cc is not None:
                    os.environ["CLAUDECODE"] = old_cc

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
