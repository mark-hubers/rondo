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

    report = compute_metrics(audit_dir=_DEFAULT_AUDIT_DIR, spool_dir=_DEFAULT_SPOOL_DIR)
    return json.dumps(report.to_dict(), indent=2)


def rondo_health() -> str:
    """Quick health check — GREEN/YELLOW/RED with key numbers.

    IFS-104 req 005: lightweight status for preflight decisions.
    """
    from rondo.metrics import compute_metrics

    report = compute_metrics(audit_dir=_DEFAULT_AUDIT_DIR, spool_dir=_DEFAULT_SPOOL_DIR)
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
    audit_path = Path(_DEFAULT_AUDIT_DIR).expanduser() / "rondo_audit.jsonl"
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

    return json.dumps(
        {
            "name": "rondo",
            "version": get_version(),
            "description": "Define AI tasks in Python, send them to Claude, get structured results back.",
            "commands": [
                "run",
                "live",
                "overnight",
                "preflight",
                "history",
                "report",
                "audit",
                "flaky",
                "spool",
                "metrics",
            ],
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


def rondo_spool_consume() -> str:
    """Consume all pending spool results — mailbox drain.

    Reads all spool files, returns their contents, and deletes them.
    This is how OB/ACE picks up overnight dispatch results.
    """
    try:
        from rondo.spool import SpoolConfig, SpoolManager

        spool = SpoolManager(config=SpoolConfig(spool_dir=_DEFAULT_SPOOL_DIR))
        consumed = spool.consume_all()
        return json.dumps({"consumed": consumed, "count": len(consumed)}, indent=2)
    except (ImportError, OSError, TypeError) as exc:
        return json.dumps({"consumed": [], "count": 0, "error": str(exc)})


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

            return {
                "status": result.status,
                "round_name": result.round_name,
                "tasks": [
                    {
                        "name": tr.task_name,
                        "status": tr.status,
                        "duration_sec": tr.duration_sec,
                        "model": tr.model,
                        "prompt_sent": tr.prompt_sent[:500] if dry_run else "",
                        "raw_output": tr.raw_output[:2000] if not dry_run else "",
                        "cost_usd": tr.cost_usd or 0.0,
                    }
                    for tr in result.task_results
                ],
                "total_cost_usd": sum(u.cost_usd for u in result.usage),
                "duration_sec": result.duration_sec,
                "dry_run": dry_run,
            }
        except (FileNotFoundError, AttributeError, TypeError, ImportError, OSError) as exc:
            return {"status": "error", "error": str(exc)}

    # -- Background dispatch: return dispatch_id immediately
    if background and not dry_run:
        dispatch_id = f"mcp-{uuid.uuid4().hex[:12]}"

        # -- U-31: pre-populate task names as "pending" for progress tracking
        try:
            from rondo.cli import load_round_file as _load

            rd = _load(file_path)
            task_names = [t.name for t in rd.tasks]
        except (FileNotFoundError, AttributeError, TypeError, ImportError):
            task_names = []

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


def rondo_run_status(dispatch_id: str = "") -> str:
    """Check status of a background MCP dispatch.

    Returns the result if complete, or running status if still in progress.
    With no dispatch_id, lists all background dispatches.
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
    ) -> str:
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
        )

    @mcp.tool(
        name="rondo_run_status",
        description="Check status of background MCP dispatch. No args = list all. dispatch_id = get result.",
    )
    def _run_status(dispatch_id: str = "") -> str:
        return rondo_run_status(dispatch_id=dispatch_id)

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
