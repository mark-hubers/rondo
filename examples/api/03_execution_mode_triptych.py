# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=inline,subprocess,agent provider=anthropic category=basic value="Side-by-side behavior of all three execution modes"

"""Rondo API example 03: execution modes side-by-side (inline | subprocess | agent).

What this demonstrates
----------------------
This example shows the new RONDO-265 execution contract in one script:

1) ``execution="inline"``:
   returns an ``inline_dispatch_plan`` for host execution.
2) ``execution="agent"``:
   returns an ``agent_dispatch_plan`` for host Agent-tool execution.
3) ``execution="subprocess"``:
   performs real dispatch and returns task results.

Why this matters
----------------
It teaches the core mental model:
- ``execution`` = HOW work runs
- ``model``     = WHERE model traffic routes

Provider-prefixed models (``gemini:``, ``anthropic:``, etc.) still route HTTP.

Run::

    cd rondo && uv run python examples/api/03_execution_mode_triptych.py
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from example_dispatch import banner

from rondo.mcp_dispatch import rondo_run_file


def _parse(raw: str) -> dict[str, Any]:
    """Parse Rondo response JSON with a clear runtime error."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response (first 200 chars): {raw[:200]!r}") from exc


def main() -> int:
    """Run all three execution modes and print their different outputs."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=90, metavar="SEC", help="Subprocess timeout for live call")
    args = parser.parse_args()

    prompt = "List two practical benefits of writing integration tests for a Python package."
    host_session = object()  # -- Simulates MCP caller context for plan defaults.

    print(banner("03 — Execution Modes (inline | subprocess | agent)"))

    try:
        inline = _parse(
            rondo_run_file(
                prompt=prompt,
                model="sonnet",
                execution="inline",
                _session=host_session,
                dry_run=False,
            )
        )
        agent = _parse(
            rondo_run_file(
                prompt=prompt,
                model="sonnet",
                execution="agent",
                _session=host_session,
                dry_run=False,
            )
        )
        subprocess_result = _parse(
            rondo_run_file(
                prompt=prompt,
                model="sonnet",
                execution="subprocess",
                dry_run=False,
                timeout_sec=args.timeout,
            )
        )
    except RuntimeError as exc:
        print(f"-ERROR- {exc}", file=sys.stderr)
        return 1

    print("INLINE:")
    print(f"  engine={inline.get('engine')!r} kind={inline.get('kind')!r} status={inline.get('status')!r}")

    print("AGENT:")
    print(f"  engine={agent.get('engine')!r} kind={agent.get('kind')!r} status={agent.get('status')!r}")

    tasks = subprocess_result.get("tasks") or []
    print("SUBPROCESS:")
    print(f"  status={subprocess_result.get('status')!r} tasks={len(tasks)}")
    if tasks:
        print(f"  first_task_status={tasks[0].get('status')!r}")

    good_inline = inline.get("engine") == "inline"
    good_agent = agent.get("engine") == "agent"
    good_subprocess = "tasks" in subprocess_result and "engine" not in subprocess_result
    if not (good_inline and good_agent and good_subprocess):
        print("-ERROR- One or more execution-mode contracts did not match expectations.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
