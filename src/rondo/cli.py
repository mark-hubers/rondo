"""Rondo CLI — command-line entry point.

REQ-001 reqs 36-41.
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

from rondo.config import RondoConfig, load_config
from rondo.engine import Round
from rondo.runner import run_round


# ──────────────────────────────────────────────────────────────────
#  Argument parser — REQ-001 reqs 36-37, 41
# ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    REQ-001 req 36: CLI entry point.
    REQ-001 req 37: subcommands (run, overnight, report).
    REQ-001 req 41: all STD-002 flags.
    """
    parser = argparse.ArgumentParser(
        prog="rondo",
        description="Rondo — AI task automation for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -- run subcommand (REQ-001 req 38)
    run_parser = subparsers.add_parser("run", help="Execute a round definition file")
    run_parser.add_argument("file", help="Path to Python file with build_round()")
    _add_common_flags(run_parser)

    # -- overnight subcommand
    overnight_parser = subparsers.add_parser("overnight", help="Run overnight automation")
    overnight_parser.add_argument("file", help="Path to Python file with build_phases()")
    overnight_parser.add_argument("--mode", default=None, help="Execution mode (minimal/standard/full)")
    _add_common_flags(overnight_parser)

    # -- report subcommand
    report_parser = subparsers.add_parser("report", help="Generate morning report")
    report_parser.add_argument("results_dir", help="Path to results directory")
    report_parser.add_argument("--config", default=None, help="Path to rondo.toml config")

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


# ──────────────────────────────────────────────────────────────────
#  Dynamic loading — REQ-001 req 39
# ──────────────────────────────────────────────────────────────────

def load_round_file(filepath: str) -> Round:
    """Dynamically import a round definition file and call build_round().

    REQ-001 req 39: importlib.util.spec_from_file_location().
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Round file not found: {filepath}")

    spec = importlib.util.spec_from_file_location("round_def", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_round"):
        raise AttributeError(
            f"Round file '{filepath}' must define a build_round() function"
        )

    result = module.build_round()

    if not isinstance(result, Round):
        raise TypeError(
            f"build_round() must return a Round, got {type(result).__name__}"
        )

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
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    if getattr(args, "verbose", False):
        overrides["verbose"] = True

    config_path = getattr(args, "config", None)

    return load_config(
        config_path=config_path,
        cli_overrides=overrides if overrides else None,
    )


# ──────────────────────────────────────────────────────────────────
#  main() — REQ-001 req 36
# ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code (0=success, 1=error).

    REQ-001 req 36: CLI entry point.
    REQ-001 req 40: auto-detect sequential vs parallel (via run_round).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        raise SystemExit(2)

    if args.command == "run":
        return _cmd_run(args)
    elif args.command == "overnight":
        return _cmd_overnight(args)
    elif args.command == "report":
        return _cmd_report(args)

    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute 'rondo run <file>' subcommand."""
    round_def = load_round_file(args.file)
    config = _build_config(args)

    result = run_round(round_def, config=config)

    # -- Print summary
    if config.verbose:
        print(f"Round: {result.round_name}")
        print(f"Status: {result.status}")
        print(f"Summary: {result.summary}")
        print(f"Duration: {result.duration_sec:.1f}s")
        for tr in result.task_results:
            print(f"  {tr.task_name}: {tr.status}")
    else:
        print(f"{result.status}: {result.summary}")

    return 0 if result.status == "done" else 1


def _cmd_overnight(args: argparse.Namespace) -> int:
    """Execute 'rondo overnight <file>' subcommand."""
    from rondo.overnight import run_overnight
    from rondo.report import save_report

    # -- Load phases file (expects build_phases() → list[Round])
    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    spec = importlib.util.spec_from_file_location("phases_def", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_phases"):
        print(f"Error: {args.file} must define build_phases()", file=sys.stderr)
        return 1

    phases = module.build_phases()
    config = _build_config(args)

    result = run_overnight(
        phases=phases,
        config=config,
        mode=getattr(args, "mode", None),
    )

    # -- Save report
    try:
        report_path = save_report(result, config)
        print(f"Report saved: {report_path}")
    except Exception as exc:
        print(f"Warning: could not save report: {exc}", file=sys.stderr)

    print(f"{result.status}: {len(result.phase_results)} phases, ${result.total_cost_usd:.2f}")

    return 0 if result.status == "done" else 1


def _cmd_report(args: argparse.Namespace) -> int:
    """Execute 'rondo report <results_dir>' subcommand."""
    # -- Future: re-generate report from saved results
    print(f"Report from {args.results_dir} — not yet implemented")
    return 0


# ──────────────────────────────────────────────────────────────────
#  Entry point for `python -m rondo`
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(main())
