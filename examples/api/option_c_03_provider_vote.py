# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini,openai,grok category=option-c value="Three-provider vote on a design decision via MCP multi_review"

"""Option C example 03: get 3 providers to vote on a design decision."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from rondo.mcp_server import create_mcp_server


def _call_multi_review(arguments: dict[str, Any]) -> dict[str, Any]:
    async def _inner() -> dict[str, Any]:
        server = create_mcp_server()
        payload = await server.call_tool("rondo_multi_review", arguments)
        result_text = payload[1].get("result", "") if isinstance(payload, tuple) else ""
        return json.loads(result_text) if str(result_text).strip() else {}

    return asyncio.run(_inner())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="Run live dispatch (default uses dry-run)")
    args = parser.parse_args()

    payload = _call_multi_review(
        {
            "prompt": "Vote yes/no: should we add Redis caching to this workflow? Give one reason.",
            "providers": json.dumps(["gemini:flash", "openai:gpt-4.1-mini", "grok:grok-3-mini"]),
            "dry_run": not args.live,
        }
    )
    per_provider = payload.get("per_provider", [])
    if not isinstance(per_provider, list) or len(per_provider) != 3:
        print(f"-ERROR- Expected 3 provider results, got: {payload}", file=sys.stderr)
        return 1

    print("-PASS- Multi-provider vote returned per-provider results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

