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
    return json.dumps({
        "health": report.health,
        "total_dispatches": report.total_dispatches,
        "success_rate": report.success_rate,
        "total_cost_usd": report.total_cost_usd,
        "spool_pending": report.spool_pending,
    })


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
    return json.dumps({
        "recent": recent,
        "total": len(records),
    })


def rondo_dispatch_info() -> str:
    """Rondo version, commands, capabilities, design principles.

    IFS-104 req 003: discovery tool for AI agents.
    Same data as `rondo --ai-help` but via MCP.
    """
    from rondo._version import get_version

    return json.dumps({
        "name": "rondo",
        "version": get_version(),
        "description": "Define AI tasks in Python, send them to Claude, get structured results back.",
        "commands": [
            "run", "live", "overnight", "preflight", "history",
            "report", "audit", "flaky", "spool", "metrics",
        ],
        "interfaces": ["python_import", "cli", "mcp_stdio"],
        "design_principles": ["COALESCE", "ALWAYS-ON", "Dual-Path-With-Alerting"],
        "always_on_artifacts": [
            "audit_jsonl", "prompt_file", "result_file",
            "spool_file", "history_record", "metrics_dict",
        ],
    })


# -- ──────────────────────────────────────────────────────────────
# --  MCP server setup (stdio transport)
# -- ──────────────────────────────────────────────────────────────


def create_mcp_server() -> Any:
    """Create the FastMCP server with all tools registered.

    Separated from run() for testability.
    """
    from mcp.server import FastMCP

    mcp = FastMCP(name="rondo", log_level="WARNING")

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
