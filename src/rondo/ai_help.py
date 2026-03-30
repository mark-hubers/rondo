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

from rondo._version import get_version as _get_rondo_version


def get_ai_help() -> dict[str, Any]:
    """Return complete AI-readable help as a dict.

    This is what an AI agent reads to understand how to use Rondo.
    """
    return {
        "name": "rondo",
        "version": _get_rondo_version(),
        "description": "AI task automation for Claude Code. Define tasks in Python, dispatch to Claude, get structured results.",
        "how_it_works": _get_how_it_works(),
        "quick_examples": _get_quick_examples(),
        "install": "uv tool install --editable ~/git/mhubers/ace2/rondo",
        "commands": _get_commands(),
        "config": _get_config_options(),
        "round_schema": _get_round_schema(),
        "task_schema": _get_task_schema(),
        "gate_schema": _get_gate_schema(),
        "result_schema": _get_result_schema(),
        "capabilities": get_capabilities(),
        "examples": _get_examples(),
        "example_round_file": _get_example_round_file(),
    }


def _get_how_it_works() -> dict[str, Any]:
    """The 3-step heart of Rondo — REQ-100 three-field contract."""
    return {
        "summary": "Tell AI what to do. Rondo dispatches it. Get the result back.",
        "three_steps": [
            {
                "step": 1,
                "name": "DEFINE",
                "what": "Write a Task with instruction (Do), context_files (Read), done_when (Done)",
                "example": 'Task(name="scan", instruction="Search for new trials", done_when="Results returned as JSON")',
            },
            {
                "step": 2,
                "name": "DISPATCH",
                "what": "Rondo sends it to Claude via subprocess (or MCP via rondo_run)",
                "example": "rondo run my_round.py  OR  rondo_run(file_path='my_round.py')",
            },
            {
                "step": 3,
                "name": "RESULT",
                "what": "Get back TaskResult with status, raw_output, cost, duration",
                "example": "result.extract_json() → dict  |  result.extract_code_blocks() → [(lang, code)]",
            },
        ],
    }


def _get_quick_examples() -> list[dict[str, str]]:
    """Simple 'do this, get that' examples — the 99% use case."""
    return [
        {
            "name": "Search for data",
            "task": 'Task(name="find-trials", instruction="Search BioMCP for Usher Syndrome trials. Return as JSON array.", done_when="All results returned as JSON.")',
            "run": "rondo_run(file_path='search_round.py', model='haiku')",
        },
        {
            "name": "Review code",
            "task": 'Task(name="review", instruction="Review src/main.py for bugs and security issues.", context_files=["src/main.py"], done_when="Findings listed.")',
            "run": "rondo_run(file_path='review_round.py')",
        },
        {
            "name": "Generate a report",
            "task": 'Task(name="report", instruction="Read the test results and write a summary report.", context_files=["reports/test-results.json"], done_when="Report written to reports/summary.md")',
            "run": "rondo_run(file_path='report_round.py', model='haiku')",
        },
        {
            "name": "Scan and update DB",
            "task": 'Task(name="db-update", instruction="Query the API for new records. Add any new ones to the SQLite database.", done_when="New records added. Count reported.")',
            "run": "rondo_run(file_path='scan_round.py', project='~/my-project')",
        },
    ]


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
        {
            "name": "live",
            "description": "Execute round in live mode (human reviews each task)",
            "usage": "rondo live <file.py> [--from N] [--task N]",
        },
        {
            "name": "overnight",
            "description": "Run overnight automation with phase scheduling",
            "usage": "rondo overnight <file.py> [--mode minimal|standard|full]",
        },
        {
            "name": "preflight",
            "description": "Check dispatch environment without running",
            "usage": "rondo preflight [--json]",
        },
        {
            "name": "history",
            "description": "Show dispatch history with cost tracking",
            "usage": "rondo history [--model M] [--status S] [--expensive] [--json]",
        },
        {
            "name": "report",
            "description": "Generate morning report from results",
            "usage": "rondo report <results_dir>",
        },
        {
            "name": "audit",
            "description": "Query dispatch audit trail (always-on, every dispatch recorded)",
            "usage": "rondo audit [dispatch_id] [--cost] [--failed] [--json]",
        },
        {
            "name": "flaky",
            "description": "Show flaky task templates with flip rates",
            "usage": "rondo flaky [--json] [--threshold 0.20]",
        },
        {
            "name": "spool",
            "description": "Manage result spool (list/clean/export pending results)",
            "usage": "rondo spool [list|clean|export|consume] [--all] [--since YYYY-MM-DD] [--json]",
        },
        {
            "name": "metrics",
            "description": "Dispatch metrics for dashboards and health (cost, reliability, latency, tokens)",
            "usage": "rondo metrics [--json]",
        },
    ]


def _get_config_options() -> list[dict[str, Any]]:
    """Configuration options (rondo.toml or CLI flags)."""
    return [
        {"name": "auth", "type": "string", "default": "max", "values": ["max", "api"]},
        {"name": "default_model", "type": "string", "default": "sonnet", "values": ["sonnet", "opus", "haiku"]},
        {"name": "effort", "type": "string", "default": "high", "values": ["low", "medium", "high", "max"]},
        {"name": "workers", "type": "int", "default": 4, "description": "Parallel dispatch workers"},
        {
            "name": "permission_mode",
            "type": "string",
            "default": "auto",
            "values": ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"],
        },
        {
            "name": "bare",
            "type": "bool",
            "default": False,
            "description": "Use --bare for fast dispatch (CC >= 2.1.81)",
        },
        {"name": "json_schema", "type": "string", "default": "", "description": "'auto' for Rondo result schema"},
        {
            "name": "dispatch_system_prompt",
            "type": "string",
            "default": "",
            "description": "'auto' for Rondo dispatch prompt",
        },
        {"name": "max_budget_usd", "type": "float", "default": None, "description": "Cost cap per task in USD"},
        {"name": "task_timeout_sec", "type": "int", "default": 300},
        {"name": "dry_run", "type": "bool", "default": False},
    ]


def _get_round_schema() -> dict[str, Any]:
    """Round definition schema — U-05."""
    return {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "description": "Round name (unique identifier)"},
            "tasks": {
                "type": "array",
                "items": {"$ref": "#/task_schema"},
                "description": "List of Task objects to execute",
            },
            "pre_gates": {
                "type": "array",
                "items": {"$ref": "#/gate_schema"},
                "description": "Gates checked BEFORE any task runs (all must pass)",
            },
            "post_gates": {
                "type": "array",
                "items": {"$ref": "#/gate_schema"},
                "description": "Gates checked AFTER all tasks complete",
            },
        },
        "note": "Import: from rondo.engine import Round, Task, Gate",
    }


def _get_task_schema() -> dict[str, Any]:
    """Task definition schema — U-06 (complete fields)."""
    return {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique task name within round",
            },
            "description": {
                "type": "string",
                "default": "",
                "description": "Brief human summary of what this task does",
            },
            "instruction": {
                "type": "string",
                "default": "",
                "description": "What Claude should do (the 'Do' field of three-field contract)",
            },
            "context_files": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "Files Claude should read for context (the 'Read' field)",
            },
            "done_when": {
                "type": "string",
                "default": "",
                "description": "Completion criteria (the 'Done' field)",
            },
            "context_data": {
                "type": "object",
                "default": {},
                "description": "Structured data injected into prompt (REQ-106)",
            },
            "auto_fn": {
                "type": "callable",
                "default": None,
                "description": "Python function returning (bool, str) — alternative to three-field contract for non-AI tasks",
            },
            "model": {
                "type": "string",
                "default": None,
                "description": "Model hint — COALESCE: task.model → config.default_model → 'sonnet'",
            },
            "mode": {
                "type": "string",
                "enum": ["interactive", "auto"],
                "default": "interactive",
                "description": "Task mode — 'interactive' dispatches to Claude, 'auto' calls auto_fn",
            },
        },
        "note": "Interactive tasks need instruction + done_when. Auto tasks need auto_fn.",
    }


def _get_gate_schema() -> dict[str, Any]:
    """Gate definition schema — U-08."""
    return {
        "type": "object",
        "required": ["name", "check_fn"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Gate name for logging and reporting",
            },
            "check_fn": {
                "type": "callable",
                "description": "Function returning (bool, str) — (passed, detail). Takes NO arguments. Capture context via closure.",
            },
            "blocking": {
                "type": "boolean",
                "default": True,
                "description": "If True and gate fails, round is aborted. If False, failure is logged but round continues.",
            },
        },
        "note": "Import: from rondo.engine import Gate",
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
        {
            "description": "With structured output",
            "code": "rondo run my_round.py --json-schema auto --system-prompt auto",
        },
        {"description": "Cost-capped dispatch", "code": "rondo run my_round.py --max-budget 0.50"},
        {"description": "Check environment first", "code": "rondo preflight --json"},
        {"description": "See what would execute", "code": "rondo run my_round.py --dry-run --verbose"},
        {"description": "Scaffold a new round", "code": "rondo init"},
        {"description": "Target another project", "code": "rondo run scan.py --project ~/my-project"},
    ]


def _get_example_round_file() -> str:
    """Copy-paste ready example round file — U-07."""
    return '''"""Example Rondo round file — copy this to get started.

Usage:
    rondo run this_file.py --dry-run      # preview
    rondo run this_file.py                # execute
    rondo run this_file.py --model haiku  # use haiku
"""

from rondo.engine import Round, Task


def build_round() -> Round:
    """Define the tasks for this round."""
    return Round(
        name="my-round",
        tasks=[
            Task(
                name="review-code",
                description="Review Python code for issues",
                instruction="""Review the code in src/ for:
1. Security issues
2. Performance problems
3. Missing error handling

Report findings as a numbered list.""",
                context_files=["src/main.py", "src/utils.py"],
                done_when="All files reviewed. Findings listed.",
            ),
            Task(
                name="check-tests",
                description="Verify test coverage",
                instruction="Run pytest and report coverage gaps.",
                done_when="Test results shown. Coverage gaps identified.",
                model="haiku",  # -- cheaper model for simple task
            ),
        ],
    )
'''


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b3c6
