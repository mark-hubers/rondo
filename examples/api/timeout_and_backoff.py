# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Timeout-oriented retry loop with exponential backoff and live success path"

"""Rondo API example: timeout-aware retries with exponential backoff.

Run:
    cd rondo && command uv run python examples/api/timeout_and_backoff.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from example_dispatch import banner

from rondo.mcp_dispatch import rondo_run_file


def _run_with_timeout(prompt: str, timeout_sec: int) -> dict:
    raw = rondo_run_file(
        prompt=prompt,
        model="sonnet",
        execution="subprocess",
        timeout_sec=timeout_sec,
        dry_run=False,
    )
    return json.loads(raw)


def _deterministic_error_probe() -> dict:
    """Use bad project path as deterministic pre-check error before retry loop."""
    raw = rondo_run_file(
        prompt="Return JSON only: {\"probe\":\"project-path\"}",
        model="sonnet",
        execution="subprocess",
        project="/tmp/__rondo_missing_project_for_backoff_demo__",
        dry_run=False,
    )
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=20, metavar="SEC", help="Per-attempt timeout")
    parser.add_argument("--attempts", type=int, default=3, metavar="N")
    args = parser.parse_args()

    print(banner("Timeout and Backoff"))
    probe = _deterministic_error_probe()
    if probe.get("status") == "error":
        print(f"-PASS- deterministic error path: {probe.get('error_code')} ({probe.get('error_help', '')[:80]})")

    prompt = "Return JSON only: {\"status\":\"ok\",\"topic\":\"timeout-backoff\",\"steps\":[1,2,3]}"
    delay = 1.0
    for attempt in range(1, args.attempts + 1):
        print(f"[TEST]  attempt {attempt}/{args.attempts} timeout={args.timeout}s")
        started = time.monotonic()
        env = _run_with_timeout(prompt=prompt, timeout_sec=args.timeout)
        elapsed = time.monotonic() - started
        status = env.get("status", "")
        print(f"  status={status} elapsed={elapsed:.1f}s")
        if status in ("done", "partial"):
            print("-PASS- dispatch completed before backoff exhaustion")
            return 0
        if env.get("error_code") == "ERR_TIMEOUT":
            print(f"  -WARNING- timeout; sleeping {delay:.1f}s before retry")
            time.sleep(delay)
            delay *= 2
            continue
        print(f"-ERROR- non-timeout failure: {env.get('error_code')} {env.get('error_message')}", file=sys.stderr)
        return 1

    print("-FAIL- retry budget exhausted without success", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

