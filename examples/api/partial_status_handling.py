# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=observability value="Show how to handle partial/non-JSON output while preserving raw_output"

"""Rondo API example: handling partial-style outcomes and raw output fallback.

Run:
    cd rondo && command uv run python examples/api/partial_status_handling.py
"""

from __future__ import annotations

import argparse
import sys

from example_dispatch import banner, first_task_parsed_json, invoke_rondo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Partial Status Handling"))
    envelope = invoke_rondo(
        prompt=(
            "Give a concise explanation of CI value in plain text only. "
            "Do not return JSON. Keep it under 6 lines."
        ),
        model="sonnet",
        execution="subprocess",
        timeout_sec=args.timeout,
        dry_run=False,
    )

    tasks = envelope.get("tasks") or []
    if not tasks:
        print("-ERROR- no tasks in envelope", file=sys.stderr)
        return 1

    first = tasks[0]
    parsed = first_task_parsed_json(envelope)
    print(f"Top-level status: {envelope.get('status')} | task status: {first.get('status')}")

    if parsed.get("_non_json"):
        snippet = parsed.get("snippet", "")
        if not snippet:
            print("-ERROR- expected raw_output snippet for non-JSON case", file=sys.stderr)
            return 1
        print(f"-PASS- non-JSON recovered via raw_output snippet ({len(snippet)} chars)")
        return 0

    print("-PASS- model returned valid JSON; fallback path not required on this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

