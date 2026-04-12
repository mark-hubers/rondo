# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini category=option-c value="Ask Gemini via MCP and return structured opinion"

"""Option C example 02: ask Gemini what it thinks.

What Mark types:
    "Ask Gemini what it thinks of this approach."
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

    payload = _call_rondo_run(
        {
            "prompt": "Give one risk and one upside of this implementation approach.",
            "model": "gemini:high",
            "dry_run": not args.live,
        }
    )
    if "tasks" not in payload:
        print(f"-ERROR- Expected results envelope with tasks, got: {payload}", file=sys.stderr)
        return 1

    print("-PASS- Gemini HTTP dispatch returned structured results envelope.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

