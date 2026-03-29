# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo AI help — machine-readable capability description for AI agents.

CORE-STD-023: tools output JSON for AI agents describing what they can do,
what parameters they accept, and how to use them.

Usage:
    rondo --ai-help          # JSON to stdout
    from rondo.ai_help import get_ai_help
"""

from __future__ import annotations

from typing import Any


def get_ai_help() -> dict[str, Any]:
    """Return complete AI-readable help as a dict.

    This is what an AI agent reads to understand how to use Rondo.
    """
    return {
        "name": "rondo",
        "version": "0.2.0",
        "description": "AI task automation for Claude Code. Define tasks in Python, dispatch to Claude, get structured results.",
        "install": "uv tool install --editable ~/git/mhubers/ace2/rondo",
        "commands": _get_commands(),
        "config": _get_config_options(),
        "task_schema": _get_task_schema(),
        "result_schema": _get_result_schema(),
        "capabilities": get_capabilities(),
        "examples": _get_examples(),
    }


def get_capabilities() -> dict[str, Any]:
    """Return capability map for AI agents."""
    return {
        "dispatch": {
            "description": "Send tasks to Claude Code via claude -p",
            "models": ["sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"],
            "auth_modes": ["max", "api"],
            "tool_modes": ["none", "sandbox", "default"],
            "features": [
                "structured_output (--json-schema auto)",
                "system_prompt (--system-prompt auto)",
                "cost_cap (--max-budget-usd N)",
                "bare_mode (--bare, CC >= 2.1.81)",
                "circuit_breaker (3 consecutive errors halts)",
                "budget_exceeded_detection",
            ],
        },
        "preflight": {
            "description": "Verify dispatch environment before running",
            "checks": [
                "claude_binary_on_path",
                "cc_version_detection",
                "api_key_or_max_plan",
                "nested_session_guard",
                "disk_space_500mb",
                "git_available",
            ],
            "outputs": ["GREEN", "YELLOW", "RED"],
            "flags": ["--json"],
        },
        "history": {
            "description": "Dispatch telemetry — cost, duration, model, status",
            "storage": "JSONL (one file per day)",
            "queries": ["by_model", "by_status", "by_round", "by_task", "aggregate_by_model"],
            "flags": ["--json", "--model", "--status", "--expensive"],
        },
        "notifications": {
            "description": "Notify on round completion or dispatch failure",
            "channels": ["terminal", "file", "macos"],
            "triggers": ["round_complete", "dispatch_failure"],
        },
        "live_mode": {
            "description": "Present tasks one at a time for human review",
            "flags": ["--from N", "--task N"],
        },
        "overnight": {
            "description": "Batch automation with phase scheduling",
            "features": ["preflight_gate", "usage_gating", "phase_modes"],
        },
    }


def _get_commands() -> list[dict[str, str]]:
    """All CLI commands with descriptions."""
    return [
        {"name": "run", "description": "Execute a round definition file", "usage": "rondo run <file.py> [flags]"},
        {"name": "live", "description": "Execute round in live mode (human reviews each task)", "usage": "rondo live <file.py> [--from N] [--task N]"},
        {"name": "overnight", "description": "Run overnight automation with phase scheduling", "usage": "rondo overnight <file.py> [--mode minimal|standard|full]"},
        {"name": "preflight", "description": "Check dispatch environment without running", "usage": "rondo preflight [--json]"},
        {"name": "history", "description": "Show dispatch history with cost tracking", "usage": "rondo history [--model M] [--status S] [--expensive] [--json]"},
        {"name": "report", "description": "Generate morning report from results", "usage": "rondo report <results_dir>"},
        {"name": "audit", "description": "Query dispatch audit trail (always-on, every dispatch recorded)", "usage": "rondo audit [dispatch_id] [--cost] [--failed] [--json]"},
        {"name": "flaky", "description": "Show flaky task templates with flip rates", "usage": "rondo flaky [--json] [--threshold 0.20]"},
        {"name": "spool", "description": "Manage result spool (list/clean/export pending results)", "usage": "rondo spool [list|clean|export] [--all] [--since YYYY-MM-DD] [--json]"},
    ]


def _get_config_options() -> list[dict[str, Any]]:
    """Configuration options (rondo.toml or CLI flags)."""
    return [
        {"name": "auth", "type": "string", "default": "max", "values": ["max", "api"]},
        {"name": "default_model", "type": "string", "default": "sonnet", "values": ["sonnet", "opus", "haiku"]},
        {"name": "effort", "type": "string", "default": "high", "values": ["low", "medium", "high", "max"]},
        {"name": "workers", "type": "int", "default": 4, "description": "Parallel dispatch workers"},
        {"name": "permission_mode", "type": "string", "default": "auto", "values": ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"]},
        {"name": "bare", "type": "bool", "default": False, "description": "Use --bare for fast dispatch (CC >= 2.1.81)"},
        {"name": "json_schema", "type": "string", "default": "", "description": "'auto' for Rondo result schema"},
        {"name": "dispatch_system_prompt", "type": "string", "default": "", "description": "'auto' for Rondo dispatch prompt"},
        {"name": "max_budget_usd", "type": "float", "default": None, "description": "Cost cap per task in USD"},
        {"name": "task_timeout_sec", "type": "int", "default": 300},
        {"name": "dry_run", "type": "bool", "default": False},
    ]


def _get_task_schema() -> dict[str, Any]:
    """Task definition schema for round files."""
    return {
        "type": "object",
        "required": ["name", "instruction", "done_when"],
        "properties": {
            "name": {"type": "string", "description": "Unique task name within round"},
            "instruction": {"type": "string", "description": "What Claude should do (the 'Do' field)"},
            "done_when": {"type": "string", "description": "Completion criteria (the 'Done' field)"},
            "context_files": {"type": "array", "items": {"type": "string"}, "description": "Files for context (the 'Read' field)"},
            "context_data": {"type": "object", "description": "Structured data injected into prompt"},
            "model": {"type": "string", "description": "Model hint (COALESCE: task → config → default)"},
            "tool_mode": {"type": "string", "enum": ["none", "sandbox", "default"]},
            "human_input": {"type": "string", "description": "Prompt for human before dispatch"},
        },
    }


def _get_result_schema() -> dict[str, Any]:
    """Expected result schema from dispatched tasks."""
    return {
        "type": "object",
        "required": ["status", "result"],
        "properties": {
            "status": {"type": "string", "enum": ["done", "error", "blocked", "partial"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "result": {"type": "string", "description": "What was accomplished"},
            "question": {"type": "string", "description": "If blocked, what's needed"},
        },
    }


def _get_examples() -> list[dict[str, str]]:
    """Usage examples for AI agents."""
    return [
        {"description": "Simple dispatch", "code": "rondo run my_round.py"},
        {"description": "With structured output", "code": "rondo run my_round.py --json-schema auto --system-prompt auto"},
        {"description": "Cost-capped dispatch", "code": "rondo run my_round.py --max-budget 0.50"},
        {"description": "Check environment first", "code": "rondo preflight --json"},
        {"description": "See what would execute", "code": "rondo run my_round.py --dry-run --verbose"},
    ]


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b3c6
