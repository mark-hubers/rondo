# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo MCP tool implementations — read-only and management tools.

IFS-104: Extracted from mcp_server.py (Finding #195 — god object split).
These tools query data (metrics, health, audit, history, cost) or manage
schedules/spool. They do NOT dispatch to AI providers.

Dispatch + composition tools (run, explain, benchmark, chain, summarize,
retry) stay in mcp_server.py because they depend on rondo_run_file.

Import direction:
    mcp_tools.py → imports metrics, history, spool, providers, schedule
    mcp_server.py → imports mcp_tools (tool functions + _resolve_dir)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- ──────────────────────────────────────────────────────────────
# --  Shared constants and helpers
# -- ──────────────────────────────────────────────────────────────

_DEFAULT_AUDIT_DIR = "~/.rondo/audit"
_DEFAULT_SPOOL_DIR = "~/.rondo/spool"

# -- Finding #183: cache metrics to avoid reading JSONL 3-4x on morning check-in
_metrics_cache: dict[str, Any] = {}
_METRICS_CACHE_TTL = 30  # -- seconds


def _resolve_dir(default: str, subdir: str) -> str:
    """Resolve path: RONDO_TEST_DIR → default. Shared by MCP tools."""
    import os

    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return os.path.join(test_dir, subdir)
    return default


# -- ──────────────────────────────────────────────────────────────
# --  Observability tools (read-only)
# -- ──────────────────────────────────────────────────────────────


def _get_cached_metrics() -> Any:
    """Return cached MetricsReport if fresh, else compute and cache."""
    import time

    from rondo.metrics import compute_metrics

    now = time.monotonic()
    if _metrics_cache.get("report") and (now - _metrics_cache.get("ts", 0)) < _METRICS_CACHE_TTL:
        return _metrics_cache["report"]

    report = compute_metrics(
        audit_dir=_resolve_dir(_DEFAULT_AUDIT_DIR, "audit"),
        spool_dir=_resolve_dir(_DEFAULT_SPOOL_DIR, "spool"),
    )
    _metrics_cache["report"] = report
    _metrics_cache["ts"] = now
    return report


def rondo_metrics() -> str:
    """Full metrics dashboard — cost, reliability, latency, tokens, health.

    IFS-104 req 003: query tool for dashboard data.
    Returns JSON string — same data as `rondo metrics --json`.
    """
    report = _get_cached_metrics()
    return json.dumps(report.to_dict(), indent=2)


def rondo_health() -> str:
    """Quick health check — GREEN/YELLOW/RED with key numbers.

    IFS-104 req 005: lightweight status for preflight decisions.
    """
    report = _get_cached_metrics()
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

    # -- U-55: derive command list from CLI parser (single source of truth)
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
            "description": "AI dispatch layer — route tasks to any AI provider, get structured results back.",
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


def rondo_history(model: str = "", status: str = "", limit: int = 20) -> str:
    """Query dispatch history — REQ-104 reqs 003-005.

    Returns recent dispatch records with model aggregate stats.
    Filterable by model and status.
    """
    try:
        from rondo.history import aggregate_by_model, load_history, query_history

        records = load_history(history_dir=_resolve_dir("~/.rondo/history", "history"))
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


def rondo_cost(days: int = 30) -> str:
    """Monthly cost dashboard — spend tracking per model.

    Reads audit trail for the last N days and aggregates cost.
    """
    from datetime import UTC, datetime, timedelta

    audit_dir = _resolve_dir(_DEFAULT_AUDIT_DIR, "audit")
    audit_path = Path(audit_dir).expanduser() / "rondo_audit.jsonl"
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    by_model: dict[str, float] = {}
    total = 0.0
    dispatch_count = 0

    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                cost = record.get("cost_usd", 0) or 0
                if cost > 0 and record.get("completed_at", "") >= cutoff:
                    model_name = record.get("model", "unknown")
                    by_model[model_name] = by_model.get(model_name, 0) + cost
                    total += cost
                    dispatch_count += 1
            except (json.JSONDecodeError, TypeError):
                continue

    return json.dumps(
        {
            "total_cost_usd": round(total, 4),
            "by_model": {k: round(v, 4) for k, v in sorted(by_model.items())},
            "dispatch_count": dispatch_count,
            "period": f"last {days} days",
            "daily_avg": round(total / max(days, 1), 4),
        },
        indent=2,
    )


# -- ──────────────────────────────────────────────────────────────
# --  Management tools
# -- ──────────────────────────────────────────────────────────────


def rondo_models() -> str:
    """List available models with providers, benchmarks, and task recommendations."""
    from rondo.providers import get_ollama_adapter, load_task_models

    merged_models = load_task_models()
    providers = [
        {
            "name": "claude",
            "models": ["sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"],
            "cost": "Max plan or API key",
        },
        {
            "name": "ollama",
            "models": get_ollama_adapter().models() or ["(none — run: ollama pull llama3.1:8b)"],
            "cost": "$0 (local)",
        },
    ]
    recommendations = [
        {"task": k, "model": v, "provider": "ollama" if ":" in v or v.startswith("llama") else "claude"}
        for k, v in merged_models.items()
    ]
    return json.dumps({"providers": providers, "recommendations": recommendations}, indent=2)


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


def rondo_schedule_list() -> str:
    """List installed Rondo schedules (launchd plists)."""
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    schedules = []
    if launch_dir.exists():
        for p in sorted(launch_dir.glob("com.rondo.*.plist")):
            name = p.stem.replace("com.rondo.", "")
            schedules.append({"name": name, "path": str(p)})
    return json.dumps({"schedules": schedules, "count": len(schedules)}, indent=2)


def rondo_schedule_create(
    file_path: str,
    interval: str = "weekly",
    model: str = "",
    name: str = "",
    dry_run: bool = False,
) -> str:
    """Create a scheduled Rondo dispatch (generates launchd plist)."""
    from rondo.schedule import generate_plist

    resolved = str(Path(file_path).expanduser().resolve()) if file_path else ""
    sched_name = name or (Path(file_path).stem if file_path else "unnamed")
    cmd_args = ["run", resolved]
    if model:
        cmd_args.extend(["--model", model])

    plist = generate_plist(
        name=sched_name,
        command="/Users/markhubers/.local/bin/rondo",
        args=cmd_args,
        interval=interval,
        work_dir=str(Path(resolved).parent) if resolved else "",
    )

    if dry_run:
        return json.dumps({"status": "preview", "plist": plist[:500], "name": sched_name, "interval": interval})

    out_dir = Path.home() / "Library" / "LaunchAgents"

    # -- H-13: max 20 active schedules
    existing = list(out_dir.glob("com.rondo.*.plist")) if out_dir.exists() else []
    if len(existing) >= 20:
        return json.dumps({"status": "error", "error": "Too many schedules (max 20)", "code": "ERR_LIMIT_EXCEEDED"})

    out_path = out_dir / f"com.rondo.{sched_name}.plist"
    out_path.write_text(plist, encoding="utf-8")
    return json.dumps({"status": "installed", "path": str(out_path), "name": sched_name, "interval": interval})


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


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 reqs 046-063: Cloud dispatch orchestration
# -- ──────────────────────────────────────────────────────────────


def rondo_cloud(
    prompt: str,
    profile: str = "",
    tier: str = "default",
    count: int = 0,
    dry_run: bool = False,
) -> str:
    """Cloud dispatch: pick providers from profile, resolve tiers, enforce cost caps.

    REQ-109 reqs 046-063. This is the --cloud flag as a function.
    Delegates actual dispatch to rondo_multi_review.

    Args:
        prompt: Task prompt.
        profile: Cloud profile name (review, coding, research). Empty = all enabled.
        tier: Model tier (high, default, low). Resolves via config.
        count: Number of providers (0 = use config default_count).
        dry_run: Preview without dispatching.
    """
    import tomllib
    from pathlib import Path

    ## Load cloud config
    config_path = Path.home() / ".rondo" / "config.toml"
    cloud_cfg: dict = {}
    providers_cfg: dict = {}
    if config_path.is_file():
        with open(config_path, "rb") as f:
            toml_data = tomllib.load(f)
        cloud_cfg = toml_data.get("cloud", {})
        providers_cfg = toml_data.get("providers", {})

    default_count = cloud_cfg.get("default_count", 2)
    max_count = cloud_cfg.get("max_count", 4)
    max_cost = cloud_cfg.get("max_cost_per_dispatch", 0.50)
    config_tier = cloud_cfg.get("default_tier", "default")

    ## Resolve count
    use_count = count if count > 0 else default_count
    if use_count > max_count:
        return json.dumps(
            {
                "status": "error",
                "error": f"count {use_count} exceeds max_count {max_count}",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    ## Resolve tier
    use_tier = tier if tier != "default" else config_tier
    tier_key = {"high": "best_model", "low": "cheap_model"}.get(use_tier, "default_model")

    ## Select providers from profile
    if profile:
        profiles = cloud_cfg.get("profiles", {})
        profile_cfg = profiles.get(profile, {})
        if not profile_cfg:
            available = list(profiles.keys())
            return json.dumps(
                {
                    "status": "error",
                    "error": f"Unknown profile '{profile}'. Available: {available}",
                    "code": "ERR_INVALID_PROFILE",
                }
            )
        provider_names = profile_cfg.get("providers", [])
    else:
        ## All enabled providers
        provider_names = [
            name for name, cfg in providers_cfg.items() if cfg.get("enabled", True)
        ]

    ## Trim to count
    selected = provider_names[:use_count]

    ## Resolve tier → actual model per provider
    provider_models = []
    for name in selected:
        pcfg = providers_cfg.get(name, {})
        model = pcfg.get(tier_key, pcfg.get("default_model", ""))
        if model:
            provider_models.append(f"{name}:{model}")
        else:
            provider_models.append(name)

    ## Cost estimate (rough: count x tier factor)
    tier_cost_factor = {"high": 0.15, "default": 0.05, "low": 0.01}.get(use_tier, 0.05)
    estimated_cost = len(provider_models) * tier_cost_factor
    if estimated_cost > max_cost and not dry_run:
        return json.dumps(
            {
                "status": "error",
                "error": f"Estimated cost ${estimated_cost:.2f} exceeds cap ${max_cost:.2f}",
                "code": "ERR_COST_CAP",
                "estimated_cost_usd": estimated_cost,
                "max_cost_per_dispatch": max_cost,
            }
        )

    ## Lazy import to avoid circular dependency (mcp_server imports mcp_tools)
    from rondo.mcp_server import rondo_multi_review

    result_raw = rondo_multi_review(
        prompt=prompt,
        providers=json.dumps(provider_models),
        dry_run=dry_run,
    )
    result = json.loads(result_raw)

    ## Enrich result with cloud metadata
    result["cloud"] = {
        "profile": profile or "(all enabled)",
        "tier": use_tier,
        "count_requested": use_count,
        "count_dispatched": len(provider_models),
        "estimated_cost_usd": estimated_cost,
        "max_cost_per_dispatch": max_cost,
    }

    return json.dumps(result, indent=2)


# -- sig: mgh-6201.cd.bd955f.a104.d19501
