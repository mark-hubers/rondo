# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo API example: real background dispatch with heartbeat/brief/full polling.

What this demonstrates
----------------------
1) Start background work with ``background=True``.
2) Poll cheaply with ``heartbeat=True``.
3) Poll summary with ``brief=True``.
4) Fetch final full task results when work completes.

This is real usage for long-running script automation.

Run::

    cd rondo && uv run python examples/api/background_polling_workflow.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from example_dispatch import banner

from rondo.mcp_dispatch import rondo_run_file, rondo_run_status


def _loads(raw: str) -> dict[str, Any]:
    """Parse JSON response from MCP dispatch helpers."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON status payload: {raw[:200]!r}") from exc


def main() -> int:
    """Run one task in the background and poll until completion."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=180, metavar="SEC", help="Task timeout")
    parser.add_argument("--max-wait", type=int, default=30, metavar="SEC", help="Maximum wait for completion")
    parser.add_argument("--poll-every", type=float, default=1.0, metavar="SEC", help="Polling interval")
    args = parser.parse_args()

    print(banner("Background Dispatch + Polling"))
    prompt = "Give a concise JSON object with keys summary and confidence about why CI smoke tests matter."

    try:
        started = _loads(
            rondo_run_file(
                prompt=prompt,
                model="sonnet",
                execution="subprocess",
                dry_run=False,
                background=True,
                timeout_sec=args.timeout,
            )
        )
    except RuntimeError as exc:
        print(f"-ERROR- {exc}", file=sys.stderr)
        return 1

    dispatch_id = started.get("dispatch_id", "")
    if not dispatch_id:
        print(f"-ERROR- No dispatch_id in response: {started}", file=sys.stderr)
        return 1

    print(f"Dispatch started: {dispatch_id}")
    deadline = time.time() + args.max_wait
    while time.time() < deadline:
        hb = _loads(rondo_run_status(dispatch_id=dispatch_id, heartbeat=True))
        br = _loads(rondo_run_status(dispatch_id=dispatch_id, brief=True))
        print(f"  heartbeat={hb} brief={br}")

        if br.get("status") in ("done", "error"):
            final = _loads(rondo_run_status(dispatch_id=dispatch_id))
            print(f"Final status: {final.get('status')}  done={final.get('done_count')}  error={final.get('error_count')}")
            tasks = final.get("tasks") or []
            if tasks:
                print(f"First task status: {tasks[0].get('status')}")
            return 0 if final.get("status") == "done" else 1

        time.sleep(args.poll_every)

    print("-WARNING- Timed out waiting for completion; dispatch may still be running.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
