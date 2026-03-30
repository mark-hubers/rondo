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

from rondo.config import RondoConfig, load_config, validate_config
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


def _build_config(args: argparse.Namespace) -> RondoConfig:
    """Construct RondoConfig from CLI args with COALESCE."""
    # -- Build CLI overrides dict (only non-None values)
    overrides: dict = {}
    if getattr(args, "workers", None) is not None:
        overrides["workers"] = args.workers
    if getattr(args, "model", None) is not None:
        overrides["default_model"] = args.model
    if getattr(args, "auth", None) is not None:
        overrides["auth"] = args.auth
    if getattr(args, "timeout", None) is not None:
        overrides["task_timeout_sec"] = args.timeout
    if getattr(args, "effort", None) is not None:
        overrides["effort"] = args.effort
    if getattr(args, "on_overage", None) is not None:
        overrides["on_overage"] = args.on_overage
    if getattr(args, "permission_mode", None) is not None:
        overrides["permission_mode"] = args.permission_mode
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    if getattr(args, "verbose", False):
        overrides["verbose"] = True
    if getattr(args, "bare", False):
        overrides["bare"] = True
    if getattr(args, "json_schema", None):
        overrides["json_schema"] = args.json_schema
    if getattr(args, "system_prompt", None):
        overrides["dispatch_system_prompt"] = args.system_prompt
    if getattr(args, "max_budget", None) is not None:
        overrides["max_budget_usd"] = args.max_budget

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


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute 'rondo run <file>' subcommand."""
    try:
        round_def = load_round_file(args.file)
    except (FileNotFoundError, AttributeError, TypeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    config = _build_config(args)

    # -- Validate config before running (fail fast)
    config_errors = validate_config(config)
    if config_errors:
        for err in config_errors:
            print(f"Config error: {err}", file=sys.stderr)
        return EXIT_FAILURE

    # -- REQ-103 req 001: preflight before dispatch
    from rondo.preflight import run_preflight

    preflight = run_preflight(config=config)
    if not preflight.can_proceed:
        print("Preflight FAILED (RED):", file=sys.stderr)
        for err in preflight.errors:
            print(f"  -ERROR- {err}", file=sys.stderr)
        return EXIT_FAILURE
    for warn in preflight.warnings:
        print(f"  -WARNING- {warn}", file=sys.stderr)

    result = run_round(round_def, config=config)

    # -- Print summary
    total_cost = sum(u.cost_usd for u in result.usage)
    if config.verbose:
        print(f"Round: {result.round_name}")
        print(f"Status: {result.status}")
        print(f"Summary: {result.summary}")
        print(f"Duration: {result.duration_sec:.1f}s")
        print(f"Cost: ${total_cost:.4f}")
        for tr in result.task_results:
            print(f"  {tr.task_name}: {tr.status}")
    else:
        cost_str = f" (${total_cost:.4f})" if total_cost > 0 else ""
        print(f"{result.status}: {result.summary}{cost_str}")

    return EXIT_SUCCESS if result.status == "done" else EXIT_FAILURE


def _cmd_live(args: argparse.Namespace) -> int:
    """Execute 'rondo live <file>' subcommand — live mode with human review.

    Rondo-REQ-100 reqs 47-56.
    """
    from rondo.live import run_live  # pylint: disable=import-outside-toplevel

    try:
        round_def = load_round_file(args.file)
    except (FileNotFoundError, AttributeError, TypeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    start_from = getattr(args, "from_task", 0)
    single_task = getattr(args, "task", -1)

    presentations = run_live(
        round_def,
        start_from=start_from,
        single_task=single_task,
    )

    print(f"\n{len(presentations)} task(s) presented in live mode.")
    return EXIT_SUCCESS


def _cmd_overnight(args: argparse.Namespace) -> int:
    """Execute 'rondo overnight <file>' subcommand."""
    from dataclasses import replace  # pylint: disable=import-outside-toplevel

    from rondo.overnight import run_overnight  # pylint: disable=import-outside-toplevel
    from rondo.report import save_report  # pylint: disable=import-outside-toplevel

    try:
        phases = load_phases_file(args.file)
    except (FileNotFoundError, AttributeError, TypeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    config = replace(_build_config(args), spool_enabled=True)  # -- REQ-101 req 045

    # -- Validate config before running (fail fast)
    config_errors = validate_config(config)
    if config_errors:
        for err in config_errors:
            print(f"Config error: {err}", file=sys.stderr)
        return EXIT_FAILURE

    result = run_overnight(
        phases=phases,
        config=config,
        mode=getattr(args, "mode", None),
    )

    # -- Save report
    try:
        report_path = save_report(result, config)
        print(f"Report saved: {report_path}")
    except (OSError, ValueError, TypeError) as exc:
        print(f"Warning: could not save report: {exc}", file=sys.stderr)

    print(f"{result.status}: {len(result.phase_results)} phases, ${result.total_cost_usd:.2f}")

    return EXIT_SUCCESS if result.status == "done" else EXIT_FAILURE


def _cmd_report(args: argparse.Namespace) -> int:
    """Execute 'rondo report <results_dir>' subcommand."""
    # -- Future: re-generate report from saved results
    print(f"Report from {args.results_dir} — not yet implemented", file=sys.stderr)
    return EXIT_FAILURE


def _cmd_history(args: argparse.Namespace) -> int:
    """Execute 'rondo history' — show dispatch history.

    Rondo-REQ-104 req 005.
    """
    from rondo.history import load_history, query_history  # pylint: disable=import-outside-toplevel

    history_dir = str(Path(args.results_dir) / "history")
    records = load_history(history_dir)
    filtered = query_history(records, model=args.model, status=args.status)

    if args.json:
        import json  # pylint: disable=import-outside-toplevel

        print(json.dumps(filtered, indent=2, default=str))
    elif not filtered:
        print("  No dispatch history found.")
    else:
        total_cost = sum(r.get("cost_usd", 0) for r in filtered)
        print(f"  Dispatches: {len(filtered)} | Total cost: ${total_cost:.4f}")

        # -- REQ-104 req 003: per-model summary
        from rondo.history import aggregate_by_model  # pylint: disable=import-outside-toplevel

        agg = aggregate_by_model(filtered)
        if len(agg) > 1:
            print(
                "  Models:",
                " | ".join(f"{m}: {d['count']} dispatches, ${d['total_cost']:.4f}" for m, d in sorted(agg.items())),
            )
        print()
        # -- REQ-104 req 007: --expensive sorts by cost (top 10)
        is_expensive = getattr(args, "expensive", False)
        if is_expensive:
            filtered = sorted(filtered, key=lambda r: r.get("cost_usd", 0), reverse=True)
        display = filtered[:10] if is_expensive else filtered[-10:]
        for r in display:
            cost = r.get("cost_usd", 0)
            print(
                f"  {r.get('status', '?'):8s} {r.get('task_name', '?'):30s} "
                f"{r.get('model', '?'):8s} ${cost:.4f} {r.get('duration_sec', 0):.1f}s"
            )

    return EXIT_SUCCESS


def _cmd_preflight(args: argparse.Namespace) -> int:
    """Execute 'rondo preflight' — check environment without dispatching.

    Rondo-REQ-103 reqs 015-016: standalone preflight + JSON output.
    """
    from rondo.preflight import run_preflight  # pylint: disable=import-outside-toplevel

    result = run_preflight()

    # -- REQ-103 req 016: JSON output
    if getattr(args, "json", False):
        import json as _json  # pylint: disable=import-outside-toplevel

        print(
            _json.dumps(
                {
                    "status": result.status,
                    "can_proceed": result.can_proceed,
                    "checks": result.checks,
                    "warnings": result.warnings,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
        return EXIT_SUCCESS if result.can_proceed else EXIT_FAILURE

    # -- Human-readable output
    for check in result.checks:
        print(f"  -PASS- {check}")
    for warn in result.warnings:
        print(f"  -WARNING- {warn}")
    for err in result.errors:
        print(f"  -ERROR- {err}", file=sys.stderr)

    if result.status == "GREEN":
        print(f"\n  Preflight: {result.status} — ready to dispatch")
    elif result.status == "YELLOW":
        print(f"\n  Preflight: {result.status} — proceed with caution")
    else:
        print(f"\n  Preflight: {result.status} — cannot dispatch", file=sys.stderr)

    return EXIT_SUCCESS if result.can_proceed else EXIT_FAILURE


# ──────────────────────────────────────────────────────────────────
#  Entry point for `python -m rondo`
# ──────────────────────────────────────────────────────────────────


def _load_audit_records(audit_dir: str) -> list[dict]:
    """Load all records from audit JSONL — STD-113."""
    import json as _json
    from pathlib import Path

    jsonl_file = Path(audit_dir).expanduser() / "rondo_audit.jsonl"
    if not jsonl_file.exists():
        return []
    records = []
    for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                records.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue
    return records


def _cmd_audit(args: argparse.Namespace) -> int:
    """Query dispatch audit trail — STD-113 reqs 011-013.

    Always-on: every dispatch records audit data. This command reads it.
    Callers (ACE, OB, Caliber) get dispatch_id in TaskResult automatically.
    """
    from rondo.audit import AuditConfig, AuditTrail  # pylint: disable=import-outside-toplevel

    # -- Rotate: rondo audit --rotate (RONDO-29)
    if getattr(args, "rotate", False):
        trail = AuditTrail(config=AuditConfig(audit_dir=args.audit_dir))
        count = trail.rotate()
        if count:
            print(f"Rotated {count} audit records to archive/")
        else:
            print("Nothing to rotate.")
        return EXIT_SUCCESS

    # -- Reset: rondo audit --reset (RONDO-29)
    if getattr(args, "reset", False):
        trail = AuditTrail(config=AuditConfig(audit_dir=args.audit_dir))
        count = trail.reset()
        if count:
            print(f"Cleared {count} audit files.")
        else:
            print("Nothing to clear.")
        return EXIT_SUCCESS

    records = _load_audit_records(args.audit_dir)
    if not records:
        print("No audit data yet. Run a dispatch first.")
        return EXIT_SUCCESS

    # -- Detail view: rondo audit <dispatch_id>
    if args.dispatch_id:
        return _cmd_audit_detail(args, records)
    # -- Cost summary: rondo audit --cost
    if args.cost:
        return _cmd_audit_cost(args, records)
    # -- Failed only: rondo audit --failed
    if args.failed:
        return _cmd_audit_failed(args, records)
    # -- Default: list all
    return _cmd_audit_list(args, records)


def _cmd_audit_detail(args: argparse.Namespace, records: list[dict]) -> int:
    """Show detail for one dispatch_id."""
    import json as _json
    from pathlib import Path

    matches = [r for r in records if r.get("dispatch_id") == args.dispatch_id]
    if not matches:
        print(f"No records for dispatch_id: {args.dispatch_id}")
        return EXIT_FAILURE
    if args.json:
        print(_json.dumps(matches, indent=2))
    else:
        for r in matches:
            print(
                f"  {r.get('status', '?'):8s} | {r.get('task_name', '?')} | {r.get('dispatched_at', r.get('completed_at', ''))}"
            )
            if r.get("cost_usd"):
                print(f"           cost: ${r['cost_usd']:.4f} | duration: {r.get('duration_sec', 0):.1f}s")
    audit_dir = Path(args.audit_dir).expanduser()
    for ext in [".prompt.txt", ".result.json"]:
        fpath = audit_dir / f"{args.dispatch_id}{ext}"
        if fpath.exists():
            print(f"  {'Prompt' if 'prompt' in ext else 'Result'}: {fpath}")
    return EXIT_SUCCESS


def _cmd_audit_cost(args: argparse.Namespace, records: list[dict]) -> int:
    """Show total cost summary."""
    import json as _json

    outcomes = [r for r in records if r.get("cost_usd")]
    total_cost = sum(r.get("cost_usd", 0) for r in outcomes)
    if args.json:
        print(_json.dumps({"total_cost_usd": total_cost, "dispatch_count": len(outcomes)}))
    else:
        print(f"  Total cost: ${total_cost:.4f}")
        print(f"  Dispatches: {len(outcomes)}")
        if outcomes:
            print(f"  Average:    ${total_cost / len(outcomes):.4f}/dispatch")
    return EXIT_SUCCESS


def _cmd_audit_failed(args: argparse.Namespace, records: list[dict]) -> int:
    """Show only failed dispatches."""
    import json as _json

    failed = [r for r in records if r.get("status") in ("error", "blocked", "timeout")]
    if args.json:
        print(_json.dumps(failed, indent=2))
    elif not failed:
        print("  No failed dispatches.")
    else:
        print(f"  Failed Dispatches ({len(failed)}):")
        for r in failed:
            print(f"    {r.get('dispatch_id', '?')[:12]} | {r.get('task_name', '?')} | {r.get('status', '?')}")
    return EXIT_SUCCESS


def _cmd_audit_list(args: argparse.Namespace, records: list[dict]) -> int:
    """Default: list all audit records with summary."""
    import json as _json

    if args.json:
        print(_json.dumps(records, indent=2))
        return EXIT_SUCCESS
    intents = [r for r in records if r.get("status") == "INTENT"]
    outcomes = [r for r in records if r.get("status") != "INTENT"]
    total_cost = sum(r.get("cost_usd", 0) for r in outcomes)
    print(f"  Audit Trail: {len(records)} records ({len(intents)} intents, {len(outcomes)} outcomes)")
    print(f"  Total cost:  ${total_cost:.4f}")
    print()
    recent = sorted(outcomes, key=lambda r: r.get("completed_at", ""))[-10:]
    if recent:
        print("  Recent dispatches:")
        for r in recent:
            did = r.get("dispatch_id", "?")[:12]
            print(f"    {did} | {r.get('status', '?'):8s} | ${r.get('cost_usd', 0):.4f} | {r.get('task_name', '?')}")
    return EXIT_SUCCESS


def _cmd_flaky(args: argparse.Namespace) -> int:
    """Show flaky task templates — REQ-107 reqs 007-008.

    Reads audit trail, feeds into FlakyEngine, reports flip rates.
    """
    import json as _json
    from pathlib import Path

    from rondo.flaky import DispatchOutcome, FlakyEngine

    audit_dir = Path(args.audit_dir).expanduser()
    jsonl_file = audit_dir / "rondo_audit.jsonl"

    if not jsonl_file.exists():
        print("No audit data yet. Run dispatches first to build history.")
        return EXIT_SUCCESS

    # -- Load outcomes from audit trail
    engine = FlakyEngine()
    for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        # -- Only outcomes (not INTENTs)
        if r.get("status") == "INTENT":
            continue
        if not r.get("task_name"):
            continue
        engine.add_outcome(
            DispatchOutcome(
                task_name=r.get("task_name", ""),
                prompt_hash=r.get("prompt_hash", "unknown"),
                model=r.get("model", "unknown"),
                status=r.get("status", "unknown"),
                confidence=0.0,
                run_at=r.get("completed_at", r.get("dispatched_at", "")),
            )
        )

    flaky_tasks = engine.get_flaky_tasks(threshold=args.threshold)

    if args.json:
        print(_json.dumps([f.to_dict() for f in flaky_tasks], indent=2))
        return EXIT_SUCCESS

    if not flaky_tasks:
        print(f"  No flaky tasks (threshold: {args.threshold:.0%})")
        stats = engine.get_model_stats()
        if stats:
            print("\n  Model reliability:")
            for model, data in sorted(stats.items()):
                print(f"    {model}: {data['total_runs']} runs, {data['flakiness']:.0%} flip rate")
        return EXIT_SUCCESS

    print(f"  Flaky Tasks ({len(flaky_tasks)}, threshold: {args.threshold:.0%}):")
    for f in flaky_tasks:
        print(f"    {f.task_name}: {f.flakiness_score:.0%} flaky ({f.flip_count} flips / {f.total_runs} runs)")
    return EXIT_SUCCESS


def _cmd_spool(args: argparse.Namespace) -> int:
    """Manage result spool — REQ-101 reqs 047-049."""
    import json as _json

    from rondo.spool import SpoolConfig, SpoolManager

    spool = SpoolManager(config=SpoolConfig(spool_dir=args.spool_dir))

    if args.action == "list":
        entries = spool.list_pending()
        if args.json:
            print(_json.dumps(entries, indent=2))
        elif not entries:
            print("  Spool empty.")
        else:
            print(f"  Pending Results ({len(entries)}):")
            for e in entries:
                age_h = e["age_sec"] / 3600
                print(f"    {e['filename']:50s} {e['size_bytes']:6d}B  {age_h:.1f}h old")
        return EXIT_SUCCESS

    if args.action == "clean":
        if getattr(args, "all", False):
            removed = spool.clean_all()
        else:
            removed = spool.clean_expired()
        print(f"  Cleaned {removed} file(s).")
        return EXIT_SUCCESS

    if args.action == "export":
        since = args.since or "2000-01-01"
        exported = spool.export_since(since)
        print(_json.dumps(exported, indent=2))
        return EXIT_SUCCESS

    if args.action == "consume":
        consumed = spool.consume_all()
        if args.json:
            print(_json.dumps(consumed, indent=2))
        elif not consumed:
            print("  No results to consume.")
        else:
            print(f"  Consumed {len(consumed)} result(s):")
            for c in consumed:
                status = c.get("status", "?")
                name = c.get("task_name", c.get("_spool_file", "?"))
                print(f"    {status:8s} | {name}")
        return EXIT_SUCCESS

    return EXIT_SUCCESS


def _cmd_metrics(args: argparse.Namespace) -> int:
    """Dispatch metrics for OB dashboards — one call, everything.

    ALWAYS-ON: reads existing audit data, no new capture needed.
    Designed for OB dashboard, ACE health, and future MCP (IFS-104).
    """
    import json as _json

    from rondo.metrics import compute_metrics

    report = compute_metrics(audit_dir=args.audit_dir)

    if args.json:
        print(_json.dumps(report.to_dict(), indent=2))
        return EXIT_SUCCESS

    print("  Rondo Metrics")
    print(f"  {'─' * 45}")
    print(f"  Health:       {report.health}")
    print(f"  Dispatches:   {report.total_dispatches}")
    print(f"  Success rate: {report.success_rate:.0%}")
    print(f"  Total cost:   ${report.total_cost_usd:.4f}")
    print(f"  Avg cost:     ${report.avg_cost_usd:.4f}")
    print(f"  Avg duration: {report.avg_duration_sec:.1f}s")
    print(f"  Max duration: {report.max_duration_sec:.1f}s")
    print(f"  Tokens:       {report.total_input_tokens:,} in / {report.total_output_tokens:,} out")
    print(f"  Spool:        {report.spool_pending} pending")
    if report.dispatches_by_model:
        print("\n  Models:")
        for model, count in sorted(report.dispatches_by_model.items()):
            cost = report.cost_by_model.get(model, 0)
            print(f"    {model:12s}  {count:3d} dispatches  ${cost:.4f}")
    if report.error_breakdown:
        print("\n  Errors:")
        for code, count in sorted(report.error_breakdown.items(), key=lambda x: -x[1]):
            print(f"    {code:20s}  {count}")
    return EXIT_SUCCESS


def _cmd_mcp(args: argparse.Namespace) -> int:
    """Start MCP stdio server — IFS-104.

    Claude Code spawns this, talks via stdin/stdout.
    No daemon, no port, just stdio.
    """
    from rondo.mcp_server import run_mcp

    run_mcp()
    return EXIT_SUCCESS


# -- Populate command dispatch table
_COMMANDS.update(
    {
        "run": _cmd_run,
        "live": _cmd_live,
        "overnight": _cmd_overnight,
        "report": _cmd_report,
        "preflight": _cmd_preflight,
        "history": _cmd_history,
        "audit": _cmd_audit,
        "flaky": _cmd_flaky,
        "spool": _cmd_spool,
        "metrics": _cmd_metrics,
        "mcp": _cmd_mcp,
    }
)


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.7648.92f73b
