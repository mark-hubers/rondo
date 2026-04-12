# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Force an error, then recover with a real dispatch and actionable envelope checks"

"""Rondo API example: error recovery pattern with forced failure then live recovery.

Run:
    cd rondo && command uv run python examples/api/error_recovery_patterns.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from example_dispatch import banner, invoke_rondo

from rondo.mcp_dispatch import rondo_run_file


def _load_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON payload: {raw[:200]!r}") from exc


def _force_not_found_error() -> dict:
    """Trigger deterministic ERR_FILE_NOT_FOUND to demonstrate error path."""
    missing = str(Path("examples/api/__missing_round_for_demo__.py"))
    return _load_json(
        rondo_run_file(
            file_path=missing,
            model="sonnet",
            execution="subprocess",
            dry_run=False,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Error Recovery Patterns"))
    print("[TEST]  forcing deterministic file-not-found envelope")
    err_env = _force_not_found_error()
    if err_env.get("error_code") != "ERR_FILE_NOT_FOUND":
        print(f"-ERROR- expected ERR_FILE_NOT_FOUND, got: {err_env.get('error_code')}", file=sys.stderr)
        return 1
    print(f"-PASS- forced error: {err_env.get('error_code')} | help: {err_env.get('error_help', '')[:90]}")

    print("[TEST]  running live recovery dispatch")
    started = time.monotonic()
    recovered = invoke_rondo(
        prompt='Return JSON only: {"status":"recovered","checks":["inputs","routing","retry"]}',
        model="sonnet",
        execution="subprocess",
        timeout_sec=args.timeout,
        dry_run=False,
    )
    elapsed = time.monotonic() - started
    print(f"-PASS- recovery status={recovered.get('status')} in {elapsed:.1f}s")
    return 0 if recovered.get("status") in ("done", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())

