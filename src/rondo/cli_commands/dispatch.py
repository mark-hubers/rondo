# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""CLI dispatch commands — run, live, overnight.

Rondo-REQ-100, Rondo-REQ-101, Rondo-REQ-103.
Core dispatch operations that invoke the Rondo engine.
Import direction: cli.py → cli_commands → dispatch.py (one-way).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from rondo.cli_commands import EXIT_FAILURE, EXIT_SUCCESS


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute 'rondo run <file>' subcommand."""
    from rondo.cli import (  # pylint: disable=import-outside-toplevel
        _build_config,
        _dispatch_with_provider,
    )
    from rondo.config import validate_config  # pylint: disable=import-outside-toplevel
    from rondo.engine import load_round_file  # pylint: disable=import-outside-toplevel

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

    # -- U-01/U-02: dry-run skips preflight (no dispatch = no preflight needed)
    if not config.dry_run:
        # -- REQ-103 req 001: preflight before dispatch
        from rondo.preflight import run_preflight  # pylint: disable=import-outside-toplevel

        preflight = run_preflight(config=config)
        if not preflight.can_proceed:
            print("Preflight FAILED (RED):", file=sys.stderr)
            for err in preflight.errors:
                print(f"  -ERROR- {err}", file=sys.stderr)
            return EXIT_FAILURE
        for warn in preflight.warnings:
            print(f"  -WARNING- {warn}", file=sys.stderr)

    result = _dispatch_with_provider(round_def, config)

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
    from rondo.engine import load_round_file  # pylint: disable=import-outside-toplevel
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
    from rondo.cli import _build_config  # pylint: disable=import-outside-toplevel
    from rondo.config import validate_config  # pylint: disable=import-outside-toplevel
    from rondo.engine import load_phases_file  # pylint: disable=import-outside-toplevel
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


# -- sig: mgh-6201.cd.bd955f.a2c3.f30936
