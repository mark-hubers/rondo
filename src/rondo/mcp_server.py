# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""MCP server — tool registration + stdio transport.

Rondo-IFS-104, Rondo-REQ-109.
Dispatch functions live in mcp_dispatch.py. This file registers them as MCP tools.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from mcp.server import FastMCP

from rondo.ai_help import get_ai_help

# -- RONDO-209 cycle break: import composition tools directly from mcp_compose
# -- (was previously re-exported through mcp_dispatch which created a cycle).
from rondo.mcp_compose import (  # noqa: F401
    rondo_benchmark,
    rondo_chain,
    rondo_explain,
    rondo_multi_review,
    rondo_review_codebase,
    rondo_review_file,
    rondo_summarize,
)
from rondo.mcp_dispatch import (  # noqa: F401
    _MAX_BACKGROUND_ENTRIES,
    _MAX_BENCHMARK_MODELS,
    _MAX_CHAIN_STEPS,
    _MAX_PROMPT_BYTES,
    _MAX_SUMMARIZE_BYTES,
    _background_results,
    _load_background_result,
    _prune_background,
    _save_background_result,
    rondo_retry,
    rondo_run_file,
    rondo_run_status,
)
from rondo.mcp_tools import (
    rondo_audit_summary,
    rondo_cloud,
    rondo_cost,
    rondo_diff,
    rondo_dispatch_info,
    rondo_doctor,
    rondo_fleet,
    rondo_health,
    rondo_history,
    rondo_metrics,
    rondo_models,
    rondo_schedule_create,
    rondo_schedule_list,
    rondo_spool_consume,
    rondo_templates,
)

# -- Re-export dispatch functions for backward compatibility
from rondo.providers import load_providers_config, load_task_models


def create_mcp_server() -> Any:
    """Create the FastMCP server with all tools registered.

    Separated from run() for testability.
    """
    # -- REQ-109: load provider + routing config for tier resolution

    load_providers_config()
    load_task_models()

    mcp = FastMCP(name="rondo", log_level="WARNING")

    # -- MCP Resources: self-documentation for AI discovery
    @mcp.resource(
        uri="rondo://help",
        name="Rondo Help",
        description="Full API documentation: Round/Task schema, examples, commands. Read this first.",
    )
    def _help_resource() -> str:

        return json.dumps(get_ai_help(), indent=2)

    @mcp.tool(
        name="rondo_metrics",
        description="Full dispatch metrics: cost, reliability, latency, tokens, model comparison, health status. Returns JSON.",
    )
    def _metrics() -> str:
        return rondo_metrics()

    @mcp.tool(
        name="rondo_doctor",
        description="Install diagnosis: config, provider keys (redacted), registry drift, data dirs, versions. Zero dispatches, zero cost. Returns JSON with healthy flag + per-check fix hints.",
    )
    def _doctor() -> str:
        return rondo_doctor()

    @mcp.tool(
        name="rondo_fleet",
        description="Fleet watchdog sweep: model drift + retry-queue sweep + 7d reliability vs 95% target. refresh=true re-pulls provider catalogs (free). Never fires notifications. Returns JSON.",
    )
    def _fleet(refresh: bool = False) -> str:
        return rondo_fleet(refresh=refresh)

    @mcp.tool(
        name="rondo_health",
        description="Quick health check: GREEN/YELLOW/RED with key numbers (UNKNOWN when zero providers configured). Lightweight for preflight.",
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
        description="Run AI tasks. prompt= for one-off tasks, file_path= for round files. execution=inline|subprocess|agent controls dispatch mode. plan_only=true returns plan payload for debug/compat. Override config with rules=, allowed_tools=, max_turns=, add_dir=, json_schema=.",
    )
    def _run(
        file_path: str = "",
        dry_run: bool = False,
        model: str = "",
        project: str = "",
        max_budget: float = 0.0,
        timeout_sec: int = 300,
        background: bool = False,
        prompt: str = "",
        done_when: str = "Task completed. Return results.",
        rules: str = "",
        allowed_tools: str = "",
        max_turns: int = 0,
        add_dir: str = "",
        json_schema: str = "",
        execution: str = "",
        plan_only: bool = False,
        verify: str = "",
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
            rules=rules,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            add_dir=add_dir,
            json_schema=json_schema,
            execution=execution,
            plan_only=plan_only,
            verify=verify,
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
        name="rondo_review_file",
        description="Review a file with multiple cloud providers. Pass file path — no need to read+paste. Default: review profile providers at default tier. REQ-109 req 087.",
    )
    def _review_file(path: str, providers: str = "[]", tier: str = "default", dry_run: bool = False) -> str:
        return rondo_review_file(path=path, providers=providers, tier=tier, dry_run=dry_run)

    @mcp.tool(
        name="rondo_multi_review",
        description="Multi-provider review: same prompt to N providers, returns per-provider findings + merged. Pass providers as JSON array. Default: local+gemini+grok.",
    )
    def _multi_review(prompt: str, providers: str = "[]", dry_run: bool = False) -> str:
        return rondo_multi_review(prompt=prompt, providers=providers, dry_run=dry_run)

    @mcp.tool(
        name="rondo_review_codebase",
        description="Deep codebase review: reads multiple source files, batches them (4 per call), sends actual code to AI providers with architecture context. Calibrated per-provider prompts. Default: review_deep profile at high tier. RONDO-215.",
    )
    def _review_codebase(
        paths: str = "[]", focus: str = "", providers: str = "[]", batch_size: int = 4, dry_run: bool = False
    ) -> str:
        return rondo_review_codebase(
            paths=paths, focus=focus, providers=providers, batch_size=batch_size, dry_run=dry_run
        )

    @mcp.tool(
        name="rondo_cloud",
        description="Cloud AI dispatch: pick providers by profile (review/coding/research), tier (high/default/low), count (1-4). Cost-capped. dry_run=True to preview.",
    )
    def _cloud(prompt: str, profile: str = "", tier: str = "default", count: int = 0, dry_run: bool = False) -> str:
        return rondo_cloud(prompt=prompt, profile=profile, tier=tier, count=count, dry_run=dry_run)

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
        name="rondo_verify",
        description="REQ-115: verify a dispatched plan's declared postconditions (files/cmd) — rondo checks the work ITSELF and records verified/failed_verification in the audit trail. Pass the dispatch_id.",
    )
    def _verify(dispatch_id: str) -> str:
        from rondo.verify import rondo_verify as _rv  # pylint: disable=import-outside-toplevel

        return json.dumps(_rv(dispatch_id), indent=2)

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

    RONDO-108: Guard against accidental daemon use. This server is
    designed for stdio (single-user, single-process). Running it as
    a long-lived daemon would expose unauthenticated tools to anyone
    who can connect. The guard checks stdin is a pipe (not a terminal).
    """
    # -- RONDO-108: refuse to start if stdin is a terminal (not piped)
    # -- MCP stdio servers are spawned by Claude Code with piped stdin.
    # -- If someone runs `rondo mcp` interactively, warn and require --force.
    if os.isatty(sys.stdin.fileno()) and "--force" not in sys.argv:
        sys.stderr.write(
            "Rondo MCP server is designed for stdio transport (piped by Claude Code).\n"
            "Running interactively is not supported — no authN/authZ for direct access.\n"
            "If you know what you're doing: rondo mcp --force\n"
        )
        sys.exit(1)

    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("anyio").setLevel(logging.WARNING)

    mcp = create_mcp_server()
    mcp.run(transport="stdio")


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b9
