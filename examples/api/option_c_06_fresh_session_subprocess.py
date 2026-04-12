# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=option-c value="Escape hatch: force fresh Sonnet subprocess session"

"""Option C example 06: review with Sonnet in a fresh subprocess session.

This is the explicit escape hatch when you want isolation from session context.
"""

from __future__ import annotations

import argparse
import json
import sys

from rondo.mcp_dispatch import rondo_run_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="Run live dispatch (default uses dry-run)")
    args = parser.parse_args()

    payload = json.loads(
        rondo_run_file(
            prompt="Review this snippet and return one risk.",
            model="sonnet",
            execution="subprocess",
            dry_run=not args.live,
        )
    )
    if "tasks" not in payload:
        print(f"-ERROR- Expected subprocess results envelope, got: {payload}", file=sys.stderr)
        return 1

    print("-PASS- Fresh-session subprocess execution returned results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

