# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=option-c value="Run declarative find-fix-verify round file through MCP"

"""Option C example 04: run the find-fix-verify round on code."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
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

    round_file = Path(__file__).resolve().parents[1] / "rounds" / "06-find-fix-verify.yaml"
    payload = _call_rondo_run(
        {
            "file_path": str(round_file),
            "model": "sonnet",
            "execution": "subprocess",
            "dry_run": not args.live,
        }
    )
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) < 3:
        print(f"-ERROR- Expected 3 tasks from round dispatch, got: {payload}", file=sys.stderr)
        return 1

    print("-PASS- Find-fix-verify round executed and returned multi-step results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

