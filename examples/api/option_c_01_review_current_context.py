# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=inline provider=anthropic category=option-c value="Option C in-session file review using inline plan auto-execution contract"

"""Option C example 01: review the file I just read.

What Mark types in Claude Code:
    "Use rondo to review the file I just read."

Why this proves Option C:
    MCP `rondo_run` returns an inline plan for host execution.
    The host skill then executes that prompt in current session context
    and returns a canonical results envelope.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from rondo.mcp_server import create_mcp_server


def _call_rondo_run(arguments: dict[str, Any]) -> dict[str, Any]:
    async def _inner() -> dict[str, Any]:
        server = create_mcp_server()
        payload = await server.call_tool("rondo_run", arguments)
        result_text = payload[1].get("result", "") if isinstance(payload, tuple) else ""
        return json.loads(result_text) if str(result_text).strip() else {}

    return asyncio.run(_inner())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="Run live dispatch (default uses dry-run)")
    args = parser.parse_args()

    prompt = (
        "Review the file I just read in this session. Return JSON with keys: "
        "passed, confidence, result, issues."
    )
    payload = _call_rondo_run(
        {
            "prompt": prompt,
            "model": "sonnet",
            "execution": "inline",
            "dry_run": not args.live,
        }
    )

    # -- For Option C host flow this is expected to be an inline plan.
    if payload.get("kind") != "inline_dispatch_plan":
        print(f"-ERROR- Expected inline dispatch plan, got: {payload}", file=sys.stderr)
        return 1

    print("-PASS- Received inline plan. Host skill should auto-execute this in current session context.")
    print(f"plan_prompt_preview={str(payload.get('prompt', ''))[:140]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

