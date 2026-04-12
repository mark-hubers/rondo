# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=observability value="Duplicate-request cache behavior and timing comparison"

"""Rondo API example: idempotency cache in real dispatch.

What this demonstrates
----------------------
Rondo deduplicates repeated live calls by cache key:

``(prompt, model, execution)``

This script sends the same request twice and prints timing + payload comparison.
The second call should usually be faster due to cache hit.

Run::

    cd rondo && uv run python examples/api/idempotency_cache_demo.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from example_dispatch import banner

from rondo.mcp_dispatch import rondo_run_file


def _run_once(prompt: str, model: str, timeout_sec: int) -> tuple[dict[str, Any], float]:
    """Run one live dispatch and return (parsed_payload, elapsed_seconds)."""
    t0 = time.perf_counter()
    raw = rondo_run_file(
        prompt=prompt,
        model=model,
        execution="subprocess",
        dry_run=False,
        timeout_sec=timeout_sec,
    )
    elapsed = time.perf_counter() - t0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response: {raw[:200]!r}") from exc
    return payload, elapsed


def main() -> int:
    """Run same dispatch twice to show idempotency behavior."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="sonnet", help="Claude shorthand or provider-prefixed model")
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Idempotency Cache Demo"))
    prompt = "Return JSON only: {\"benefits\": [\"...\", \"...\"]} for why test automation improves delivery confidence."

    try:
        first, first_s = _run_once(prompt, args.model, args.timeout)
        second, second_s = _run_once(prompt, args.model, args.timeout)
    except RuntimeError as exc:
        print(f"-ERROR- {exc}", file=sys.stderr)
        return 1

    same_payload = first == second
    speedup = first_s - second_s
    print(f"First call:  {first_s:.3f}s")
    print(f"Second call: {second_s:.3f}s")
    print(f"Same payload: {same_payload}")
    print(f"Second faster by: {speedup:.3f}s")

    if not same_payload:
        print("-WARNING- Payloads differ; cache may be cold or disabled.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
