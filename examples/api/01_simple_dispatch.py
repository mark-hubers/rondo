# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo API example 01: real dispatch + smart_return normalization.

What this demonstrates
----------------------
* **Live** ``rondo_run_file`` dispatch (``dry_run=False``) with the ``_session`` convention
  used across ``examples/api`` (see :mod:`example_dispatch`).
* **smart_return**: validate model JSON from ``raw_output``, normalize scores for downstream logic.

This script performs a **real** model call (subprocess or provider per your config). Ensure
``claude`` / API keys are available before running.

Run::

    cd rondo && uv run python examples/api/01_simple_dispatch.py
"""

from __future__ import annotations

import argparse
import sys

from example_dispatch import banner, invoke_rondo

from rondo.smart_return import normalize_response, validate_return_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC", help="Per-task timeout (seconds)")
    args = parser.parse_args()

    print(banner("01 — Simple dispatch + smart_return (live)"))
    prompt = "What are three concrete benefits of automated tests for a Python library?"
    try:
        result = invoke_rondo(
            prompt=prompt,
            model="",
            dry_run=False,
            timeout_sec=args.timeout,
        )
    except RuntimeError as exc:
        print(f"-ERROR- {exc}", file=sys.stderr)
        return 1

    print(f"Round status: {result.get('status')!r}")
    tasks = result.get("tasks") or []
    if not tasks:
        print("-ERROR- No tasks in response", file=sys.stderr)
        return 1

    t0 = tasks[0]
    print(f"Task status: {t0.get('status')!r}")
    print(f"Task keys: {', '.join(sorted(t0.keys()))}")

    output = (t0.get("raw_output") or "").strip()
    if not output:
        print("-ERROR- Empty raw_output — cannot run smart_return.", file=sys.stderr)
        return 1

    validated = validate_return_json(output)
    normalized = normalize_response(validated)
    print(f"Passed: {normalized['passed']}")
    print(f"Quality: {normalized['_meta']['quality']}/10")
    print(f"Answer (trimmed): {str(normalized['result'])[:240]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
