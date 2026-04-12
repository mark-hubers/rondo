# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=observability value="Validate canonical envelope keys and error contract from live MCP/API dispatches"

"""Rondo API example: validate canonical envelope contract in real usage.

Run:
    cd rondo && command uv run python examples/api/envelope_validation.py
"""

from __future__ import annotations

import argparse
import json
import sys

from example_dispatch import banner, invoke_rondo

from rondo.mcp_dispatch import rondo_run_status

REQUIRED_TOP_KEYS = {
    "schema_version",
    "status",
    "tasks",
    "done_count",
    "error_count",
    "partial_count",
    "pending_count",
    "total_cost_usd",
    "duration_sec",
    "dry_run",
}


def _loads(raw: str) -> dict:
    # -- Centralize JSON parsing so all failures report useful context.
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON payload: {raw[:200]!r}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Envelope Validation"))
    # -- Run a real dispatch first so validation is against live envelopes.
    env = invoke_rondo(
        prompt='Return JSON only: {"contract":"ok","version":2}',
        model="sonnet",
        execution="subprocess",
        timeout_sec=args.timeout,
        dry_run=False,
    )
    missing = sorted(REQUIRED_TOP_KEYS - set(env.keys()))
    # -- Contract check: these keys are required for downstream automation branching.
    if missing:
        print(f"-ERROR- missing canonical keys: {missing}", file=sys.stderr)
        return 1
    print("-PASS- canonical envelope keys present")

    # -- Probe unknown dispatch-id path to validate stable error semantics + guidance.
    unknown = _loads(rondo_run_status(dispatch_id="mcp-does-not-exist"))
    if unknown.get("error_code") != "ERR_UNKNOWN_DISPATCH_ID":
        print(f"-ERROR- expected ERR_UNKNOWN_DISPATCH_ID, got: {unknown}", file=sys.stderr)
        return 1
    if not unknown.get("error_help"):
        print("-ERROR- expected user-facing error_help for unknown dispatch id", file=sys.stderr)
        return 1
    print(f"-PASS- unknown dispatch envelope includes error_help: {unknown.get('error_help')[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

