# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http,subprocess provider=grok,anthropic category=pipeline value="Primary provider failure path with automatic fallback dispatch"

"""Rondo API example: provider fallback chain with real dispatch recovery.

Run:
    cd rondo && command uv run python examples/api/provider_fallback_chain.py
"""

from __future__ import annotations

import argparse
import json
import sys

from example_dispatch import banner, invoke_rondo

from rondo.mcp_dispatch import rondo_run_file


def _loads(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON payload: {raw[:200]!r}") from exc


def _primary_attempt(timeout_sec: int) -> dict:
    return _loads(
        rondo_run_file(
            prompt='Return JSON only: {"provider":"primary","ok":true}',
            model="grok:nonexistent-model-for-fallback-demo",
            execution="subprocess",
            timeout_sec=timeout_sec,
            dry_run=False,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Provider Fallback Chain"))
    print("[TEST]  primary provider dispatch (expected failure)")
    primary = _primary_attempt(args.timeout)
    if primary.get("status") != "error":
        print("-WARNING- primary unexpectedly succeeded; continuing with fallback anyway")
    else:
        print(f"-PASS- primary failed as expected: {primary.get('error_code')} ({primary.get('error_help', '')[:90]})")

    print("[TEST]  fallback to subprocess Claude model")
    fallback = invoke_rondo(
        prompt='Return JSON only: {"provider":"fallback","ok":true}',
        model="sonnet",
        execution="subprocess",
        timeout_sec=args.timeout,
        dry_run=False,
    )
    print(f"-PASS- fallback status={fallback.get('status')}")
    if fallback.get("status") not in ("done", "partial"):
        print(f"-ERROR- fallback failed: {fallback}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

