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
        "description": "AI dispatch layer — route tasks to any AI provider (Claude, Gemini, OpenAI, Grok, Mistral, Anthropic API, Ollama) and get structured results back. Supports single-provider dispatch, multi-provider parallel review (rondo_cloud), and automatic health-based fallback.",
        "deployment": "Per-user, local infrastructure. Each user runs their own instance via Claude Code MCP stdio. No shared/multi-tenant mode.",
        "important": {
            "model_parameter": "Do NOT specify model= unless you need a DIFFERENT model than your current session. Omitting model= uses your current session model with zero overhead. Specifying a different model spawns a new process (slower).",
            "dry_run": "Always use dry_run=True first to preview what will be dispatched.",
            "local_models": "For cheap/fast tasks (review, classify, scan), use local Ollama models (e.g. model='llama3.1:8b') — $0 cost, ~2 seconds.",
            "cloud_providers": "Use provider:model syntax for cloud providers: 'gemini:flash', 'openai:gpt-4.1', 'grok:grok-3', 'mistral:large', 'anthropic:claude-sonnet-4-6'. Configure API keys in ~/.rondo/config.toml or env vars.",
            "multi_provider": "rondo_cloud() dispatches the same prompt to multiple providers sequentially and returns all results. Use for consensus reviews or cross-validation.",
            "health_fallback": "Providers with health checks auto-fallback when down. Configure fallback= in [providers.<name>] section of config.toml. Check status with: rondo providers",
        },
        "providers": _get_providers(),
        "mcp_tools": _get_mcp_tools(),
        "commands": _get_commands(),
        "how_it_works": _get_how_it_works(),
        "quick_examples": _get_quick_examples(),
        "polling_tiers": _get_polling_tiers(),
        "config": _get_config_options(),
        "round_schema": _get_round_schema(),
        "task_schema": _get_task_schema(),
        "gate_schema": _get_gate_schema(),
        "result_schema": _get_result_schema(),
        "capabilities": get_capabilities(),
        "examples": _get_examples(),
        "install": "uv tool install --editable ~/git/mhubers/ace2/rondo",
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


def _get_polling_tiers() -> dict[str, Any]:
    """U-51: document the 3 polling tiers for background dispatch."""
    return {
        "description": "Three tiers for checking background dispatch status. Use the cheapest that gives you what you need.",
        "tiers": [
            {
                "name": "heartbeat",
                "flag": "heartbeat=True",
                "tokens": "~10",
                "response": '{"s":"w","d":2,"e":0,"p":1}',
                "use_when": "Tight polling loop — just checking 'still running?'",
                "status_codes": {"w": "working", "d": "done", "e": "error"},
            },
            {
                "name": "brief",
                "flag": "brief=True",
                "tokens": "~40",
                "response": '{"status":"running","done_count":2,"error_count":0,"pending_count":1}',
                "use_when": "Normal polling — want readable status + counts",
            },
            {
                "name": "full",
                "flag": "(default)",
                "tokens": "~300+",
                "response": "Full JSON with task results, raw_output, cost, duration",
                "use_when": "Task is done — get the actual results",
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
        {
            "name": "Background dispatch with cheap polling",
            "task": 'rondo_run(file_path="scan.py", dry_run=False, background=True)',
            "run": "rondo_run_status(dispatch_id='mcp-xxx', brief=True)  # ~50 tokens per poll",
            "note": "brief=True returns {status, done_count, error_count} only. Use brief=False when done to get full results.",
        },
        {
            "name": "One-off inline task (no round file)",
            "task": 'rondo_run(prompt="Search for new trials", dry_run=False, model="haiku")',
            "run": "Returns result directly — no polling needed for sync dispatch.",
        },
        {
            "name": "Dispatch to Gemini instead of Claude",
            "task": 'Task(name="gemini-review", instruction="Review this code.", context_files=["src/main.py"], done_when="Findings listed.")',
            "run": "rondo_run(file_path='review.py', model='gemini:flash')",
            "note": "Requires GEMINI_API_KEY or [providers.gemini] in ~/.rondo/config.toml",
        },
        {
            "name": "Multi-provider parallel review (get consensus)",
            "task": "rondo_multi_review(prompt='Review this PR for security issues.', providers=['gemini', 'openai'], dry_run=False)",
            "run": "Returns list of per-provider results. Each has provider, status, raw_output.",
            "note": "Use for cross-validation — catches issues one model might miss.",
        },
        {
            "name": "Check provider health before dispatching",
            "task": "rondo providers --json",
            "run": "Shows all configured providers: UP/DOWN status + latency. Healthy fallback auto-selected if primary is DOWN.",
        },
    ]


def _get_mcp_tools() -> list[dict[str, str]]:
    """List all 20 MCP tools with category and description."""
    return [
        {"name": "rondo_health", "category": "monitor", "description": "GREEN/YELLOW/RED status"},
        {"name": "rondo_metrics", "category": "monitor", "description": "Cost, reliability, latency"},
        {"name": "rondo_audit_summary", "category": "monitor", "description": "Recent dispatch records"},
        {"name": "rondo_cost", "category": "monitor", "description": "Monthly spend by model"},
        {"name": "rondo_dispatch_info", "category": "discovery", "description": "Version + capabilities"},
        {"name": "rondo_models", "category": "discovery", "description": "Available models + task recommendations"},
        {"name": "rondo_templates", "category": "discovery", "description": "Pre-built round patterns"},
        {
            "name": "rondo_run",
            "category": "dispatch",
            "description": "Dispatch file or inline prompt (dry-run/real/background)",
        },
        {"name": "rondo_run_status", "category": "dispatch", "description": "Progress: heartbeat/brief/full tiers"},
        {"name": "rondo_spool_consume", "category": "dispatch", "description": "Drain overnight result mailbox"},
        {"name": "rondo_retry", "category": "recovery", "description": "Re-run failed tasks"},
        {"name": "rondo_history", "category": "analysis", "description": "Query by model/status"},
        {"name": "rondo_diff", "category": "analysis", "description": "Compare results — what's new"},
        {"name": "rondo_summarize", "category": "analysis", "description": "Condense outputs via AI"},
        {"name": "rondo_explain", "category": "qa", "description": "Local model reviews AI output ($0)"},
        {"name": "rondo_chain", "category": "advanced", "description": "Pipeline: step N output → step N+1 input"},
        {"name": "rondo_benchmark", "category": "advanced", "description": "Same prompt → N models → ranked"},
        {
            "name": "rondo_cloud",
            "category": "cloud",
            "description": "Dispatch to cloud providers (Gemini/OpenAI/Grok/Mistral/Anthropic) with profile + tier + cost cap",
        },
        {
            "name": "rondo_multi_review",
            "category": "cloud",
            "description": "Send same prompt to N providers sequentially — returns per-provider results + merged findings",
        },
        {"name": "rondo_schedule_list", "category": "scheduling", "description": "List installed schedules"},
        {"name": "rondo_schedule_create", "category": "scheduling", "description": "Create recurring dispatch"},
    ]


def _get_providers() -> list[dict[str, Any]]:
    """REQ-109: list available AI providers with models and routing."""
    return [
        {
            "name": "claude",
            "description": "Claude Code via subprocess (default)",
            "models": ["sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"],
            "auth": "Max plan (free) or API key",
            "routing": "Default for all Claude model names (no prefix needed)",
            "example": "model='sonnet'",
        },
        {
            "name": "gemini",
            "description": "Google Gemini via REST API (REQ-109)",
            "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
            "tiers": {"high": "gemini-2.5-pro", "default": "gemini-2.5-flash", "low": "gemini-2.0-flash"},
            "auth": "GEMINI_API_KEY env var or ~/.rondo/config.toml",
            "routing": "Use 'gemini:' prefix",
            "examples": ["model='gemini:flash'", "model='gemini:high'", "model='gemini:gemini-2.5-pro'"],
        },
        {
            "name": "openai",
            "description": "OpenAI via Chat Completions API",
            "models": ["gpt-4.1", "gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
            "tiers": {"high": "gpt-4.1", "default": "gpt-4o", "low": "gpt-4o-mini"},
            "auth": "OPENAI_API_KEY env var or ~/.rondo/config.toml",
            "routing": "Use 'openai:' prefix",
            "examples": ["model='openai:gpt-4.1'", "model='openai:high'"],
        },
        {
            "name": "grok",
            "description": "xAI Grok via Chat Completions-compatible API",
            "models": ["grok-3", "grok-3-mini"],
            "tiers": {"high": "grok-3", "default": "grok-3", "low": "grok-3-mini"},
            "auth": "XAI_API_KEY env var or ~/.rondo/config.toml",
            "routing": "Use 'grok:' prefix",
            "examples": ["model='grok:grok-3'", "model='grok:high'"],
        },
        {
            "name": "mistral",
            "description": "Mistral AI via Chat Completions-compatible API",
            "models": ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
            "tiers": {"high": "mistral-large-latest", "default": "mistral-small-latest", "low": "mistral-small-latest"},
            "auth": "MISTRAL_API_KEY env var or ~/.rondo/config.toml",
            "routing": "Use 'mistral:' prefix",
            "examples": ["model='mistral:large'", "model='mistral:high'"],
        },
        {
            "name": "anthropic",
            "description": "Anthropic API directly (not Claude Code subprocess) — for API key billing, cost caps",
            "models": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
            "tiers": {"high": "claude-opus-4-6", "default": "claude-sonnet-4-6", "low": "claude-haiku-4-5-20251001"},
            "auth": "ANTHROPIC_API_KEY env var or ~/.rondo/config.toml",
            "routing": "Use 'anthropic:' prefix (distinct from default 'claude' subprocess path)",
            "examples": ["model='anthropic:claude-sonnet-4-6'", "model='anthropic:high'"],
        },
        {
            "name": "ollama",
            "description": "Local LLM via Ollama (no API key, zero cost)",
            "models": ["llama3.1:8b", "llama3.1:70b", "qwen2.5:32b", "mistral", "phi", "gemma", "deepseek"],
            "auth": "None — runs locally",
            "routing": "Use 'local:' prefix OR auto-detected from model name (llama, qwen, etc.)",
            "endpoint": "http://localhost:11434",
            "examples": ["model='local:llama3.1:8b'", "model='llama3.1:8b'"],
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
        "cloud_dispatch": {
            "description": "Dispatch to cloud AI providers with health check + automatic fallback (REQ-109)",
            "providers": ["gemini", "openai", "grok", "mistral", "anthropic"],
            "routing": "Use provider:model syntax — 'gemini:flash', 'openai:gpt-4.1', 'grok:grok-3'",
            "tiers": "provider:high → best_model, provider:default → default_model, provider:low → cheap_model (from config)",
            "fallback": "If primary provider is down, auto-routes to fallback= from config.toml",
            "multi_provider": "rondo_cloud() dispatches in parallel to N providers, returns per-provider results",
            "check": "rondo providers — show all configured providers with health status + latency",
        },
        "provider_health": {
            "description": "Per-provider health checks with 5-min TTL cache (REQ-109 reqs 017-019)",
            "checks": ["api_key_present", "api_reachable", "latency_measured"],
            "cache_ttl_seconds": 300,
            "on_provider_down": "logs WARNING, routes to fallback provider, never falls back to Claude interactive",
            "cli": "rondo providers [--json]",
            "mcp": "rondo_health (includes provider status when providers configured)",
        },
    }


def _get_commands() -> list[dict[str, str]]:
    """All CLI commands — derived from build_parser() (U-55 SSOT)."""
    from rondo.cli import build_parser

    commands: list[dict[str, str]] = []
    parser = build_parser()
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices:
            for name, sub in action.choices.items():
                commands.append({"name": name, "description": sub.description or sub.format_usage().strip()})
            break
    return commands


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
        {
            "name": "max_budget_usd",
            "type": "float",
            "default": None,
            "description": "Cost cap per task in USD (only works with auth:'api', not auth:'max' — Max plan has no per-token billing)",
        },
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
