# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""CLI command handlers — package split from flat cli_commands.py.

Rondo-REQ-100, Rondo-REQ-101, Rondo-REQ-109.
Each _cmd_* function uses lazy imports from rondo.cli to avoid circular dependency.
Import direction: cli.py → cli_commands (one-way).

Submodules:
    dispatch — run, live, overnight (core dispatch operations)
    observe  — report, history, audit, flaky, metrics (monitoring)
    infra    — preflight, spool, mcp, init, schedule, providers (setup/config)
    review   — review (multi-provider file review)
"""

from __future__ import annotations

## Exit codes (shared across all submodules)
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def register_commands(commands: dict) -> None:
    """Register all command handlers into the dispatch dict."""
    from rondo.cli_commands.dispatch import (  # pylint: disable=import-outside-toplevel
        _cmd_live,
        _cmd_overnight,
        _cmd_run,
    )
    from rondo.cli_commands.infra import (  # pylint: disable=import-outside-toplevel
        _cmd_init,
        _cmd_mcp,
        _cmd_preflight,
        _cmd_providers,
        _cmd_schedule,
        _cmd_spool,
    )
    from rondo.cli_commands.observe import (  # pylint: disable=import-outside-toplevel
        _cmd_audit,
        _cmd_flaky,
        _cmd_history,
        _cmd_metrics,
        _cmd_report,
    )
    from rondo.cli_commands.review import _cmd_review  # pylint: disable=import-outside-toplevel

    commands.update(
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
            "init": _cmd_init,
            "schedule": _cmd_schedule,
            "providers": _cmd_providers,
            "review": _cmd_review,
        }
    )


# -- sig: mgh-6201.cd.bd955f.a1b2.36633d
