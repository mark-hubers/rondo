# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo CLI — command-line entry point.

Rondo-REQ-100 reqs 36-41.
Thin adapter: parses args → constructs config → calls library functions.

Import direction:
    cli.py → imports config + engine + runner + overnight + report
    (never imported by other rondo modules)
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from rondo.config import RondoConfig, load_config, validate_config  # noqa: F401 — re-export for test compat
from rondo.engine import Round
from rondo.runner import run_round

# -- Exit code contract (documented, consistent)
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130  # -- standard Unix: 128 + SIGINT(2)

# ──────────────────────────────────────────────────────────────────
#  Argument parser — Rondo-REQ-100 reqs 36-37, 41
# ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Rondo-REQ-100 req 36: CLI entry point.
    Rondo-REQ-100 req 37: subcommands (run, overnight, report).
    Rondo-REQ-100 req 41: all Rondo-STD-109 flags.
    """
    parser = argparse.ArgumentParser(
        prog="rondo",
        description="Rondo — AI task automation for Claude Code",
    )
    from rondo._version import get_version

    parser.add_argument("--version", action="version", version=f"rondo {get_version()}")
    parser.add_argument(
        "--ai-help", action="store_true", default=False, help="JSON capability description for AI agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -- run subcommand (Rondo-REQ-100 req 38)
    run_parser = subparsers.add_parser("run", help="Execute a round definition file")
    run_parser.add_argument("file", help="Path to Python file with build_round()")
    _add_common_flags(run_parser)

    # -- live subcommand (Rondo-REQ-100 reqs 47-56)
    live_parser = subparsers.add_parser("live", help="Execute round in live mode (human reviews)")
    live_parser.add_argument("file", help="Path to Python file with build_round()")
    live_parser.add_argument("--from", type=int, default=0, dest="from_task", help="Resume from task N")
    live_parser.add_argument("--task", type=int, default=-1, help="Run only task N")
    _add_common_flags(live_parser)

    # -- overnight subcommand
    overnight_parser = subparsers.add_parser("overnight", help="Run overnight automation")
    overnight_parser.add_argument("file", help="Path to Python file with build_phases()")
    overnight_parser.add_argument("--mode", default=None, help="Execution mode (minimal/standard/full)")
    _add_common_flags(overnight_parser)

    # -- report subcommand
    report_parser = subparsers.add_parser("report", help="Generate morning report")
    report_parser.add_argument("results_dir", help="Path to results directory")
    report_parser.add_argument("--config", default=None, help="Path to rondo.toml config")

    # -- preflight subcommand (Rondo-REQ-103 req 015)
    pf_parser = subparsers.add_parser("preflight", help="Check dispatch environment without running")
    pf_parser.add_argument("--json", action="store_true", help="JSON output (REQ-103 req 016)")

    # -- history subcommand (Rondo-REQ-104 req 005)
    hist_parser = subparsers.add_parser("history", help="Show dispatch history")
    hist_parser.add_argument("--model", default="", help="Filter by model")
    hist_parser.add_argument("--status", default="", help="Filter by status")
    hist_parser.add_argument("--json", action="store_true", help="JSON output")
    hist_parser.add_argument("--expensive", action="store_true", help="Sort by cost (highest first)")
    hist_parser.add_argument("--results-dir", default="reports", help="Results directory")

    # -- audit subcommand (Rondo-STD-113 reqs 011-013)
    audit_parser = subparsers.add_parser("audit", help="Query dispatch audit trail")
    audit_parser.add_argument("dispatch_id", nargs="?", default="", help="Show detail for one dispatch")
    audit_parser.add_argument("--cost", action="store_true", help="Show total cost summary")
    audit_parser.add_argument("--failed", action="store_true", help="Show only failed dispatches")
    audit_parser.add_argument("--rotate", action="store_true", help="Archive current audit to monthly file")
    audit_parser.add_argument("--reset", action="store_true", help="Clear all audit data")
    audit_parser.add_argument("--json", action="store_true", help="JSON output")
    audit_parser.add_argument("--audit-dir", default="~/.rondo/audit", help="Audit directory")

    # -- flaky subcommand (Rondo-REQ-107 reqs 007-008)
    flaky_parser = subparsers.add_parser("flaky", help="Show flaky task templates")
    flaky_parser.add_argument("--json", action="store_true", help="JSON output")
    flaky_parser.add_argument("--threshold", type=float, default=0.20, help="Flakiness threshold (default 0.20)")
    flaky_parser.add_argument("--audit-dir", default="~/.rondo/audit", help="Audit directory")

    # -- spool subcommand (Rondo-REQ-101 reqs 047-049)
    spool_parser = subparsers.add_parser("spool", help="Manage result spool (mailbox)")
    spool_parser.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "clean", "export", "consume"],
        help="Spool action (default: list)",
    )
    spool_parser.add_argument("--all", action="store_true", help="Clean all files (not just expired)")
    spool_parser.add_argument("--since", default="", help="Export since date (YYYY-MM-DD)")
    spool_parser.add_argument("--json", action="store_true", help="JSON output")
    spool_parser.add_argument("--spool-dir", default="~/.rondo/spool", help="Spool directory")

    # -- metrics subcommand (OB dashboard + health + MCP-ready)
    metrics_parser = subparsers.add_parser("metrics", help="Dispatch metrics for dashboards and health")
    metrics_parser.add_argument("--json", action="store_true", help="JSON output for OB/ACE/MCP")
    metrics_parser.add_argument("--audit-dir", default="~/.rondo/audit", help="Audit directory")

    # -- mcp subcommand (IFS-104 stdio transport)
    subparsers.add_parser("mcp", help="Start MCP stdio server (for Claude Code integration)")

    # -- init subcommand (U-10 to U-14 scaffolding)
    init_parser = subparsers.add_parser("init", help="Create a starter round file or config")
    init_parser.add_argument("--name", default="my-round", help="Round name (default: my-round)")
    init_parser.add_argument("--config", action="store_true", help="Create ~/.rondo/config.toml from template")

    ## -- schedule subcommand (REQ-101 scheduling)
    sched_parser = subparsers.add_parser("schedule", help="Create launchd plist for recurring dispatch")
    sched_parser.add_argument("file", help="Round file to schedule")
    sched_parser.add_argument("--interval", default="weekly", choices=["hourly", "daily", "weekly", "monthly"])
    sched_parser.add_argument("--name", default="", help="Schedule name (default: derived from file)")
    sched_parser.add_argument("--model", default=None, help="Model override")
    sched_parser.add_argument("--install", action="store_true", help="Install plist to ~/Library/LaunchAgents/")

    # -- providers subcommand (REQ-109 req 020)
    prov_parser = subparsers.add_parser("providers", help="Show all configured providers with health status")
    prov_parser.add_argument("--json", action="store_true", help="JSON output")

    # -- review subcommand (REQ-109 reqs 082-087)
    review_parser = subparsers.add_parser("review", help="Send file to 2+ cloud providers for independent review")
    review_parser.add_argument("file", help="File to review")
    review_parser.add_argument(
        "--providers", default="", help="Comma-separated providers (default: from config review profile)"
    )
    review_parser.add_argument("--tier", default="default", choices=["high", "default", "low"], help="Model tier")
    review_parser.add_argument("--dry-run", action="store_true", help="Show prompt without dispatching")
    review_parser.add_argument("--output", default="text", choices=["text", "json"], help="Output format")

    return parser


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags shared between run and overnight subcommands."""
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers")
    parser.add_argument("--model", default=None, help="Model override (sonnet/opus/haiku)")
    parser.add_argument("--auth", default=None, help="Auth mode (max/api)")
    parser.add_argument("--timeout", type=int, default=None, help="Task timeout in seconds")
    parser.add_argument("--config", default=None, help="Path to rondo.toml config")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Show prompts without invoking")
    parser.add_argument("--verbose", action="store_true", default=False, help="Verbose output")
    parser.add_argument("--effort", default=None, help="Effort level (high/medium/low)")
    parser.add_argument("--on-overage", default=None, help="Overage action (continue/pause/stop)")
    parser.add_argument(
        "--permission-mode",
        default=None,
        help="Claude permission mode (default/acceptEdits/plan/auto/dontAsk/bypassPermissions)",
    )
    parser.add_argument("--bare", action="store_true", default=False, help="Use --bare flag for fast dispatch")
    parser.add_argument(
        "--json-schema", default=None, help="JSON schema for structured output ('auto' for Rondo default)"
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        dest="system_prompt",
        help="System prompt for dispatch ('auto' for Rondo default)",
    )
    parser.add_argument("--max-budget", type=float, default=None, dest="max_budget", help="Max cost per task in USD")
    parser.add_argument("--project", default=None, help="Working directory for dispatched tasks (U-15)")


# ──────────────────────────────────────────────────────────────────
#  Dynamic loading — Rondo-REQ-100 req 39
# ──────────────────────────────────────────────────────────────────


def load_round_file(filepath: str) -> Round:
    """Dynamically import a round definition file and call build_round().

    Rondo-REQ-100 req 39: importlib.util.spec_from_file_location().
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Round file not found: {filepath}")

    spec = importlib.util.spec_from_file_location("round_def", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from: {filepath}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_round"):
        raise AttributeError(f"Round file '{filepath}' must define a build_round() function")

    result = module.build_round()

    if not isinstance(result, Round):
        raise TypeError(f"build_round() must return a Round, got {type(result).__name__}")

    return result


def load_phases_file(filepath: str) -> list[Round]:
    """Dynamically import a phases file and call build_phases().

    Same pattern as load_round_file() but expects build_phases() → list[Round].
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Phases file not found: {filepath}")

    spec = importlib.util.spec_from_file_location("phases_def", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from: {filepath}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_phases"):
        raise AttributeError(f"Phases file '{filepath}' must define a build_phases() function")

    result = module.build_phases()

    if not isinstance(result, list):
        raise TypeError(f"build_phases() must return a list[Round], got {type(result).__name__}")

    return result


# ──────────────────────────────────────────────────────────────────
#  Config construction — COALESCE: CLI → TOML → defaults
# ──────────────────────────────────────────────────────────────────


## -- CLI arg name → RondoConfig field name (for non-None override)
_ARG_TO_CONFIG = {
    "workers": "workers",
    "model": "default_model",
    "auth": "auth",
    "timeout": "task_timeout_sec",
    "effort": "effort",
    "on_overage": "on_overage",
    "permission_mode": "permission_mode",
    "json_schema": "json_schema",
    "max_budget": "max_budget_usd",
    "project": "project",
}

## -- CLI boolean flags (store_true) → RondoConfig field name
_BOOL_FLAGS = {
    "dry_run": "dry_run",
    "verbose": "verbose",
    "bare": "bare",
}


def _build_config(args: argparse.Namespace) -> RondoConfig:
    """Construct RondoConfig from CLI args with COALESCE."""
    overrides: dict = {}
    for arg_name, config_name in _ARG_TO_CONFIG.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            overrides[config_name] = val
    for arg_name, config_name in _BOOL_FLAGS.items():
        if getattr(args, arg_name, False):
            overrides[config_name] = True
    if getattr(args, "system_prompt", None):
        overrides["dispatch_system_prompt"] = args.system_prompt

    config_path = getattr(args, "config", None)

    return load_config(
        config_path=config_path,
        cli_overrides=overrides if overrides else None,
    )


# ──────────────────────────────────────────────────────────────────
#  main() — Rondo-REQ-100 req 36
# ──────────────────────────────────────────────────────────────────


# -- Command dispatch table (extracted for complexity — max 15 per function)
_COMMANDS: dict[str, Any] = {}  # -- populated after function defs


def _dispatch_command(args: argparse.Namespace) -> int:
    """Route to the appropriate command handler."""
    handler = _COMMANDS.get(args.command)
    if handler:
        return handler(args)
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    """CLI entry point, returns exit code per contract.

    EXIT_SUCCESS (0):     All tasks completed successfully.
    EXIT_FAILURE (1):     Task failure, config error, or unexpected error.
    EXIT_USAGE (2):       Bad arguments or missing subcommand.
    EXIT_INTERRUPTED (130): User pressed Ctrl+C.

    Rondo-REQ-100 req 36: CLI entry point.
    Rondo-REQ-100 req 40: auto-detect sequential vs parallel (via run_round).
    """
    try:
        parser = build_parser()
        args = parser.parse_args(argv)

        # -- REQ-109: load provider + routing config for tier resolution
        from rondo.providers import load_providers_config, load_task_models  # pylint: disable=import-outside-toplevel

        load_providers_config()
        load_task_models()

        # -- CORE-STD-023: --ai-help outputs JSON capability description
        if getattr(args, "ai_help", False):
            import json as _json  # pylint: disable=import-outside-toplevel

            from rondo.ai_help import get_ai_help  # pylint: disable=import-outside-toplevel

            print(_json.dumps(get_ai_help(), indent=2))
            return EXIT_SUCCESS

        if not args.command:
            parser.print_help()
            return EXIT_USAGE

        return _dispatch_command(args)

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED

    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_FAILURE

    except Exception as exc:  # pylint: disable=broad-except
        # -- Top-level safety net: no raw tracebacks for users
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_FAILURE


def _dispatch_with_provider(round_def: Round, config: RondoConfig) -> Any:
    """REQ-109 req 026-027: route to provider adapter or Claude run_round.

    Non-Claude providers go through adapter.dispatch() + shared _finalize_dispatch().
    Claude goes through run_round() → dispatch_task() (proven path).
    Both paths get the full ALWAYS-ON pipeline: audit, sanitize, spool, history, metrics.
    """
    from rondo.providers import get_provider_with_fallback, parse_model  # pylint: disable=import-outside-toplevel

    provider, resolved_model = get_provider_with_fallback(config.default_model)

    # -- REQ-109 req 016: all providers down + no fallback → error, NOT Claude
    provider_name, _ = parse_model(config.default_model)
    if provider is None and provider_name and not resolved_model:
        from rondo.engine import RoundResult, TaskResult  # pylint: disable=import-outside-toplevel

        print(f"  -ERROR- Provider '{provider_name}' is down and no healthy fallback configured", file=sys.stderr)
        return RoundResult(
            round_name=round_def.name,
            status="error",
            task_results=[
                TaskResult(
                    task_name="dispatch",
                    status="error",
                    error_code="ERR_PROVIDER_DOWN",
                    error_message=f"Provider '{provider_name}' is down and no healthy fallback configured",
                    model=config.default_model,
                )
            ],
        )

    if provider is not None:
        from rondo.audit import AuditConfig, AuditTrail  # pylint: disable=import-outside-toplevel
        from rondo.dispatch import _finalize_dispatch  # pylint: disable=import-outside-toplevel
        from rondo.engine import DispatchUsage, RoundResult, TaskResult  # pylint: disable=import-outside-toplevel

        # -- REQ-109 req 026: shared finalization for ALL providers
        audit_trail = None
        if config.audit_dir:
            try:
                audit_trail = AuditTrail(config=AuditConfig(audit_dir=config.audit_dir))
            except (OSError, TypeError):
                pass

        task_results = []
        for task in round_def.tasks:
            if config.dry_run:
                task_results.append(
                    TaskResult(
                        task_name=task.name,
                        status="skipped",
                        prompt_sent=(task.instruction or "")[:500],
                        model=config.default_model,
                    )
                )
            else:
                # -- Audit INTENT before dispatch
                audit_record = None
                if audit_trail:
                    audit_record = audit_trail.record_intent(
                        task_name=task.name,
                        round_name=round_def.name,
                        model=config.default_model,
                        prompt=task.instruction or "",
                    )
                tr = provider.dispatch(prompt=task.instruction, model=config.default_model, task_name=task.name)
                usage = DispatchUsage(task_name=task.name, model=config.default_model, cost_usd=tr.cost_usd or 0.0)
                # -- REQ-109 req 026: shared finalization (audit OUTCOME, sanitize, spool, history, metrics)
                tr, usage = _finalize_dispatch(tr, usage, config, audit_trail, audit_record, round_name=round_def.name)
                task_results.append(tr)
        ok = {"done", "skipped"}
        return RoundResult(
            round_name=round_def.name,
            status="done" if all(t.status in ok for t in task_results) else "partial",
            task_results=task_results,
        )
    return run_round(round_def, config=config)


# -- Import command handlers (split for module size)
from rondo.cli_commands import register_commands  # noqa: E402

register_commands(_COMMANDS)


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.7648.92f73b
