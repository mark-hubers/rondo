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
    parser.add_argument("--version", action="version", version="rondo 0.1.0")
    parser.add_argument("--ai-help", action="store_true", default=False, help="JSON capability description for AI agents")
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
    parser.add_argument("--json-schema", default=None, help="JSON schema for structured output ('auto' for Rondo default)")
    parser.add_argument("--system-prompt", default=None, dest="system_prompt", help="System prompt for dispatch ('auto' for Rondo default)")
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

        if args.command == "run":
            return _cmd_run(args)
        if args.command == "live":
            return _cmd_live(args)
        if args.command == "overnight":
            return _cmd_overnight(args)
        if args.command == "report":
            return _cmd_report(args)
        if args.command == "preflight":
            return _cmd_preflight(args)
        if args.command == "history":
            return _cmd_history(args)

        return EXIT_SUCCESS

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
    from rondo.overnight import run_overnight  # pylint: disable=import-outside-toplevel
    from rondo.report import save_report  # pylint: disable=import-outside-toplevel

    try:
        phases = load_phases_file(args.file)
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
            print("  Models:", " | ".join(
                f"{m}: {d['count']} dispatches, ${d['total_cost']:.4f}"
                for m, d in sorted(agg.items())
            ))
        print()
        # -- REQ-104 req 007: --expensive sorts by cost (top 10)
        is_expensive = getattr(args, "expensive", False)
        if is_expensive:
            filtered = sorted(filtered, key=lambda r: r.get("cost_usd", 0), reverse=True)
        display = filtered[:10] if is_expensive else filtered[-10:]
        for r in display:
            cost = r.get("cost_usd", 0)
            print(f"  {r.get('status', '?'):8s} {r.get('task_name', '?'):30s} "
                  f"{r.get('model', '?'):8s} ${cost:.4f} {r.get('duration_sec', 0):.1f}s")

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

        print(_json.dumps({
            "status": result.status,
            "can_proceed": result.can_proceed,
            "checks": result.checks,
            "warnings": result.warnings,
            "errors": result.errors,
        }, indent=2))
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

if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.7648.92f73b
