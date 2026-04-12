# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini,grok,openai category=observability value="Benchmark multiple provider models and rank by speed/cost."

"""Benchmark harness: run one prompt across multiple models and rank results."""

from __future__ import annotations

import json

from example_dispatch import banner

from rondo.mcp_compose import rondo_benchmark


def main() -> int:
    print(banner("Benchmark harness"))
    result = json.loads(
        rondo_benchmark(
            prompt="List three realistic failure modes for a Python deployment pipeline.",
            models=json.dumps(["gemini:gemini-2.5-flash", "grok:grok-3", "openai:gpt-4o-mini"]),
            dry_run=False,
        )
    )
    ranked = result.get("ranked", [])
    fastest = result.get("fastest", "")
    print(f"-PASS- status={result.get('status')} fastest={fastest} ranked={len(ranked)}")
    return 0 if result.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
