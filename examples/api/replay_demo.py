# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=observability value="Replay baseline-vs-current outputs and summarize drift."

"""Replay demo: compare baseline and current outputs for quick drift checks."""

from __future__ import annotations

import json

from example_dispatch import banner, invoke_rondo

from rondo.mcp_tools import rondo_diff


def main() -> int:
    print(banner("Replay demo — baseline vs current drift"))
    baseline = invoke_rondo(
        prompt='Return JSON only: {"summary":"baseline","risk":"low"}',
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=90,
    )
    current = invoke_rondo(
        prompt='Return JSON only: {"summary":"current","risk":"medium"}',
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=90,
    )
    diff = json.loads(rondo_diff(current_json=json.dumps(current), previous_json=json.dumps(baseline)))
    print(f"-PASS- status={diff.get('status')} changes={diff.get('changes')}")
    return 0 if diff.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
