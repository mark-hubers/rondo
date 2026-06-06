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
import sys
from typing import Any

from rondo._version import get_version
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


def build_parser() -> argparse.ArgumentParser:  # pylint: disable=too-many-statements
    """Build the CLI argument parser.

    Rondo-REQ-100 req 36: CLI entry point.
    Rondo-REQ-100 req 37: subcommands (run, overnight, report).
    Rondo-REQ-100 req 41: all Rondo-STD-109 flags.
    """
    parser = argparse.ArgumentParser(
        prog="rondo",
        description="Rondo — AI task automation for Claude Code",
        epilog=(
            "Execution mode quick guide:\n"
            "  inline      -> host plan JSON (host executes)\n"
            "  subprocess  -> completed task results\n"
            "  agent       -> host agent plan JSON\n"
            "  provider:model -> HTTP adapter results (execution bypass)\n"
            "\n"
            "Exit codes (stable contract — RONDO-335):\n"
            "  0    success\n"
            "  1    task/dispatch failure or unexpected error\n"
            "  2    bad arguments or unknown subcommand\n"
            "  130  interrupted (Ctrl+C)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"rondo {get_version()}")
    parser.add_argument(
        "--ai-help", action="store_true", default=False, help="JSON capability description for AI agents"
    )
    # -- REQ-111 flags (work with both subcommands and inline prompt)
    parser.add_argument("--field", default=None, help="Named field for main answer in JSON output (REQ-111 req 422)")
    parser.add_argument(
        "--return-schema", default=None, dest="return_schema", help="Custom JSON return schema (REQ-111 req 423)"
    )
    parser.add_argument("--text", action="store_true", default=False, help="Plain text output (no JSON)")
    parser.add_argument("--model", default=None, help="Model override for inline prompt dispatch")
    parser.add_argument(
        "--dry-run", action="store_true", default=False, help="Inline prompt preview without live dispatch"
    )
    # -- RONDO-335: global debug escape hatch — the safety net hides
    # -- tracebacks from users; --verbose opens the hood anywhere
    parser.add_argument("--verbose", "-v", action="store_true", default=False, help="Show full tracebacks on errors")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -- run subcommand (Rondo-REQ-100 req 38)
    run_parser = subparsers.add_parser("run", help="Execute a round definition file (.py, .yaml, .json)")
    run_parser.add_argument("file", help="Path to round file (.py, .yaml, .yml, .json)")
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

    # -- replay subcommand
    replay_parser = subparsers.add_parser("replay", help="Replay one saved task dispatch by run id")
    replay_parser.add_argument("run_id", help="Run identifier (task-<id>.json or <id>)")
    replay_parser.add_argument(
        "--results-dir",
        default="reports/rondo-results",
        help="Directory containing task-*.json records",
    )
    replay_parser.add_argument("--json", action="store_true", help="JSON output")

    # -- compare subcommand
    compare_parser = subparsers.add_parser("compare", help="Compare two saved task runs by id")
    compare_parser.add_argument("id_a", help="First run identifier")
    compare_parser.add_argument("id_b", help="Second run identifier")
    compare_parser.add_argument(
        "--results-dir",
        default="reports/rondo-results",
        help="Directory containing task-*.json records",
    )
    compare_parser.add_argument("--json", action="store_true", help="JSON output")

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

    # -- schedule subcommand (REQ-101 scheduling; RONDO-314 adds --cmd)
    sched_parser = subparsers.add_parser("schedule", help="Create launchd plist for recurring dispatch")
    sched_parser.add_argument("file", nargs="?", default="", help="Round file to schedule")
    sched_parser.add_argument(
        "--cmd", default="", help="Schedule a rondo subcommand instead of a round file (e.g. nightly)"
    )
    sched_parser.add_argument("--interval", default="weekly", choices=["hourly", "daily", "weekly", "monthly"])
    sched_parser.add_argument("--name", default="", help="Schedule name (default: derived from file/cmd)")
    sched_parser.add_argument("--model", default=None, help="Model override")
    sched_parser.add_argument("--install", action="store_true", help="Install plist to ~/Library/LaunchAgents/")

    # -- doctor subcommand (RONDO-320: install diagnosis — REQ-103 030-036)
    doctor_parser = subparsers.add_parser(
        "doctor", help="Diagnose this Rondo install: config, keys (redacted), registry, dirs — zero dispatches"
    )
    doctor_parser.add_argument("--json", action="store_true", help="JSON output")
    doctor_parser.add_argument(
        "--bundle", action="store_true", help="Write a redacted support bundle file for issue reports"
    )

    # -- models subcommand (RONDO-316: auto-tiers + canary — REQ-111 604-610)
    models_parser = subparsers.add_parser(
        "models", help="Model registry tools: --verify canary, --tiers derived auto-tiers"
    )
    models_parser.add_argument(
        "--verify", action="store_true", help="Canary-dispatch every configured tier model (req 604, costs ~cents)"
    )
    models_parser.add_argument(
        "--tiers", action="store_true", help="Show derived auto_low/mid/high per provider (reqs 607-608, free)"
    )
    models_parser.add_argument(
        "--docs-drift",
        action="store_true",
        dest="docs_drift",
        help="Scan examples/ + docs/ for model IDs no longer served (req 611, free)",
    )
    models_parser.add_argument("--json", action="store_true", help="JSON output")

    # -- nightly subcommand (RONDO-314: the watchdog — finding #285)
    nightly_parser = subparsers.add_parser(
        "nightly", help="Watchdog sweep: registry drift + retryq sweep + 7d reliability; alerts on failure"
    )
    nightly_parser.add_argument("--json", action="store_true", help="JSON output")
    nightly_parser.add_argument("--no-notify", action="store_true", help="Report only, never notify")
    nightly_parser.add_argument(
        "--no-refresh", action="store_true", help="Skip the live registry refresh (offline mode)"
    )

    # -- learn subcommand (REQ-111 req 442)
    learn_parser = subparsers.add_parser("learn", help="Compute provider scores from dispatch history")
    learn_parser.add_argument("--json", action="store_true", help="JSON output")
    learn_parser.add_argument("--audit-dir", default="", help="Audit directory (default: ~/.rondo/audit)")

    # -- providers subcommand (REQ-109 req 020)
    prov_parser = subparsers.add_parser("providers", help="Show all configured providers with health status")
    prov_parser.add_argument("--json", action="store_true", help="JSON output")
    prov_parser.add_argument("--scores", action="store_true", help="Show learned provider scores")
    prov_parser.add_argument(
        "--refresh", action="store_true", help="Refresh model registry cache from provider endpoints (REQ-111 req 600)"
    )
    prov_parser.add_argument(
        "--drift", action="store_true", help="Show config-vs-served drift report (REQ-111 req 602)"
    )

    # -- matrix subcommand (REQ-113 req 060, RONDO-308)
    matrix_parser = subparsers.add_parser("matrix", help="Experiment matrix: model x effort x context grid (REQ-113)")
    matrix_parser.add_argument("action", choices=["run", "status", "report", "reveal"], help="Matrix action")
    matrix_parser.add_argument("target", help="run: matrix YAML path; others: matrix name")
    matrix_parser.add_argument("--dry-run", action="store_true", help="Show grid + estimate without dispatching")

    # -- retryq subcommand (STD-108 req 018, Finding #296)
    retryq_parser = subparsers.add_parser(
        "retryq", help="Retry queue lifecycle: list, sweep, drain, purge-dead (STD-108)"
    )
    retryq_parser.add_argument("action", choices=["list", "sweep", "drain", "purge-dead"], help="Queue action")

    # -- version subcommand (RONDO-290 Finding #266)
    ver_parser = subparsers.add_parser("version", help="Show version or bump build counter")
    ver_parser.add_argument(
        "--bump",
        action="store_true",
        help="Increment build counter and print new version (call from ace-sprint done or CI)",
    )

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
    parser.add_argument(
        "--allow-python-rounds",
        action="store_true",
        dest="allow_python_rounds",
        help="Permit loading .py round files (they EXECUTE — RONDO-330 trust gate)",
    )
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


# -- RONDO-213: load_round_file + load_phases_file moved to rondo.engine
# -- (leaf module) to break cycles. 3 modules imported them from cli.py,
# -- creating cli → cli_commands → dispatch → cli and cli → mcp_dispatch → cli.
# -- engine.py is the natural home (Round is defined there).

# ──────────────────────────────────────────────────────────────────
#  Config construction — COALESCE: CLI → TOML → defaults
# ──────────────────────────────────────────────────────────────────

# -- CLI arg name → RondoConfig field name (for non-None override)
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

# -- CLI boolean flags (store_true) → RondoConfig field name
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


def _handle_inline_prompt(args: argparse.Namespace) -> int:
    """REQ-111 req 400: dispatch an inline prompt via simple CLI.

    rondo "review this code" → dispatch to default provider → JSON out.
    """
    import json as _json  # pylint: disable=import-outside-toplevel
    import sys as _sys  # pylint: disable=import-outside-toplevel

    from rondo.engine import Round, Task  # pylint: disable=import-outside-toplevel
    from rondo.smart_return import normalize_response, validate_return_json  # pylint: disable=import-outside-toplevel

    prompt = args.prompt

    # -- REQ-111 req 403: stdin pipe support
    if not _sys.stdin.isatty():
        stdin_data = _sys.stdin.read(1_000_000)  # -- 1MB cap
        if stdin_data:
            prompt = f"{prompt}\n\n---\nContext:\n{stdin_data}"

    # -- Build inline round
    task = Task(name="inline", instruction=prompt, done_when="Complete the task")
    round_def = Round(name="inline", tasks=[task])
    config = _build_config(args)

    # -- Dispatch
    result = _dispatch_with_provider(round_def, config)

    # -- Format output
    if getattr(args, "text", False) or not result.task_results:
        for tr in result.task_results:
            print(tr.raw_output or tr.error_message or "No output")
        return EXIT_SUCCESS if result.status == "done" else EXIT_FAILURE

    # -- JSON output with smart return validation + normalization (REQ-111 reqs 440-475)
    tr = result.task_results[0]
    # -- RONDO-328 (ERROR-ENVELOPE-CONTRACT): a failed dispatch must SAY SO
    # -- in JSON mode. Live repro: a 404 printed an EMPTY smart-return
    # -- envelope — the stranger saw nothing wrong except exit 1.
    if tr.status not in ("done", "skipped"):
        envelope = {
            "status": "error",
            "error_code": tr.error_code or "ERR_PROVIDER",
            "error_message": tr.error_message or tr.raw_output or "dispatch failed (no message)",
            "error_help": "run `rondo doctor` to diagnose; `--text` shows the raw provider response",
            "model": tr.model,
            "task": tr.task_name,
        }
        print(_json.dumps(envelope, indent=2, default=str))
        return EXIT_FAILURE
    validated = validate_return_json(tr.raw_output or "")
    normalized = normalize_response(validated)
    print(_json.dumps(normalized, indent=2, default=str))
    return EXIT_SUCCESS if normalized.get("_json_valid") else EXIT_FAILURE


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
        # -- REQ-111 req 400: detect inline prompt before argparse
        # -- If first arg is not a known subcommand or flag, treat as prompt
        _known_commands = {
            "run",
            "live",
            "overnight",
            "report",
            "replay",
            "compare",
            "preflight",
            "history",
            "audit",
            "flaky",
            "spool",
            "metrics",
            "mcp",
            "init",
            "schedule",
            "nightly",
            "models",
            "doctor",
            "providers",
            "review",
            "learn",
        }
        effective_argv = argv if argv is not None else sys.argv[1:]
        if (
            effective_argv
            and effective_argv[0] not in _known_commands
            and not effective_argv[0].startswith("-")
            and " " in effective_argv[0]  # -- multi-word = prompt; single word = possible typo
        ):
            # -- Inline prompt mode: rondo "review this code"
            prompt_text = effective_argv[0]
            remaining = effective_argv[1:]
            parser = build_parser()
            args = parser.parse_args(remaining)  # -- parse flags only
            args.prompt = prompt_text
            args.command = None
            return _handle_inline_prompt(args)

        # -- RONDO-335: --verbose/-v work in ANY position (users type flags
        # -- after the subcommand; argparse globals only parse before it).
        # -- Pre-stripped here; the safety net reads the original argv.
        parse_argv = [a for a in (argv if argv is not None else sys.argv[1:]) if a not in ("--verbose", "-v")]
        parser = build_parser()
        args = parser.parse_args(parse_argv)
        args.verbose = len(parse_argv) != len(argv if argv is not None else sys.argv[1:])

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
        return _print_unexpected_error(exc, argv)


def _print_unexpected_error(exc: Exception, argv: list[str] | None) -> int:
    """RONDO-335 (SOP-106 dim 4): the safety net GUIDES, never dumps.

    Live driver: "Unexpected error: 'dict' object has no attribute
    'providers'" — message-only, no next step, no debug path. Now every
    unexpected failure names a way forward; --verbose opens the hood.
    """
    effective = argv if argv is not None else sys.argv[1:]
    if "--verbose" in effective or "-v" in effective:
        import traceback  # pylint: disable=import-outside-toplevel

        traceback.print_exc(file=sys.stderr)
    print(
        f"Unexpected error: {exc}\n"
        f"  → Try: rondo doctor   (install diagnosis, free)\n"
        f"  → Re-run with --verbose for the full traceback",
        file=sys.stderr,
    )
    return EXIT_FAILURE


def _inject_return_template(prompt: str, model: str) -> str:
    """REQ-111: append smart return template to prompt for structured JSON output."""
    try:
        from rondo.smart_return import build_return_prompt  # pylint: disable=import-outside-toplevel

        return f"{prompt}\n{build_return_prompt(provider=model)}"
    except (ImportError, TypeError):
        return prompt


def _provider_task_result(
    task: Any, round_def: Round, provider: Any, config: RondoConfig, audit_trail: Any, resolved_model: str = ""
) -> Any:
    """One adapter-path task: intent → dispatch → shared finalize — REQ-109 req 026.

    Extracted from _dispatch_with_provider (RONDO-322 complexity lock).
    RONDO-328: dispatch the RESOLVED bare model — adapters were getting the
    full 'provider:model' string and forwarding it verbatim to provider
    APIs (live 404: 'models/gemini:gemini-flash-latest is not found').
    """
    from rondo.dispatch import _finalize_dispatch  # pylint: disable=import-outside-toplevel
    from rondo.engine import DispatchUsage, TaskResult  # pylint: disable=import-outside-toplevel
    from rondo.providers import parse_model  # pylint: disable=import-outside-toplevel

    routed = resolved_model or config.default_model
    # -- adapters take the BARE model; the routing string keeps its prefix
    # -- (live 404: 'models/gemini:gemini-flash-latest is not found')
    _, bare_model = parse_model(routed)
    dispatch_model = bare_model or routed
    if config.dry_run:
        return TaskResult(
            task_name=task.name,
            status="skipped",
            prompt_sent=(task.instruction or "")[:500],
            model=dispatch_model,
        )
    # -- Audit INTENT before dispatch
    audit_record = None
    if audit_trail:
        audit_record = audit_trail.record_intent(
            task_name=task.name,
            round_name=round_def.name,
            model=dispatch_model,
            prompt=task.instruction or "",
            task_type=getattr(task, "task_type", "") or "",
        )
    dispatch_prompt = _inject_return_template(task.instruction or "", config.default_model)
    tr = provider.dispatch(prompt=dispatch_prompt, model=dispatch_model, task_name=task.name)
    usage = DispatchUsage(task_name=task.name, model=dispatch_model, cost_usd=tr.cost_usd or 0.0)
    # -- REQ-109 req 026: shared finalization (audit OUTCOME, sanitize, spool, history, metrics)
    tr, _usage = _finalize_dispatch(tr, usage, config, audit_trail, audit_record, round_name=round_def.name)
    return tr


def _provider_down_result(round_name: str, provider_name: str, model: str) -> Any:
    """REQ-109 req 016 error result.

    Extracted from _dispatch_with_provider (RONDO-322 complexity lock).
    """
    from rondo.engine import RoundResult, TaskResult  # pylint: disable=import-outside-toplevel

    message = f"Provider '{provider_name}' is down and no healthy fallback configured"
    print(f"  -ERROR- {message}", file=sys.stderr)
    return RoundResult(
        round_name=round_name,
        status="error",
        task_results=[
            TaskResult(
                task_name="dispatch",
                status="error",
                error_code="ERR_PROVIDER_DOWN",
                error_message=message,
                model=model,
            )
        ],
    )


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
        return _provider_down_result(round_def.name, provider_name, config.default_model)

    if provider is not None:
        from rondo.audit import AuditConfig, AuditTrail  # pylint: disable=import-outside-toplevel
        from rondo.engine import RoundResult  # pylint: disable=import-outside-toplevel

        # -- REQ-109 req 026: shared finalization for ALL providers
        audit_trail = None
        if config.audit_dir:
            try:
                audit_trail = AuditTrail(config=AuditConfig(audit_dir=config.audit_dir))
            except (OSError, TypeError):
                pass

        task_results = [
            _provider_task_result(task, round_def, provider, config, audit_trail, resolved_model)
            for task in round_def.tasks
        ]
        ok = {"done", "skipped"}
        return RoundResult(
            round_name=round_def.name,
            status="done" if all(t.status in ok for t in task_results) else "partial",
            task_results=task_results,
        )
    return run_round(round_def, config=config)


# -- Import command handlers (split for module size)
from rondo.cli_commands import register_commands  # noqa: E402  # pylint: disable=wrong-import-position

register_commands(_COMMANDS)

if __name__ == "__main__":
    sys.exit(main())

# -- sig: mgh-6201.cd.bd955f.7648.92f73b
