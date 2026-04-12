# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Confidence threshold flow that escalates to stronger model"

"""Rondo example: confidence-based escalation.

If the AI's confidence is below threshold, add more context and retry.
Python checks the confidence field and decides whether to escalate.

Uses **live** dispatch.

Run::

    cd rondo && uv run python examples/api/confidence_escalation.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

QUESTION = "Is this Python function safe to use in production?"
CODE = "def fetch(url): return exec(requests.get(url).text)  # noqa: S102"
THRESHOLD = 0.8


def review_with_escalation(*, timeout_sec: int) -> dict[str, Any]:
    """Ask AI, check confidence, add context if too low."""
    print("  Step 1: Initial review...")
    try:
        _, result = run_prompt_json(
            prompt=f"{QUESTION}\n\nCode:\n{CODE}",
            timeout_sec=timeout_sec,
            rules="You review code safety. Return JSON: {passed, confidence, issues, result}.",
        )
    except RuntimeError as exc:
        print(f"    Failed: {exc}")
        return {"escalated": False, "result": {"passed": None}}

    if result.get("_non_json"):
        return {"escalated": False, "result": {"passed": None}}

    confidence = float(result.get("confidence", 0.0))
    print(f"    Confidence: {confidence}")

    if confidence >= THRESHOLD:
        print(f"    Above threshold ({THRESHOLD}) — no escalation needed")
        return {"escalated": False, "result": result}

    print(f"    Below threshold ({THRESHOLD}) — adding context...")
    try:
        _, escalated = run_prompt_json(
            prompt=(
                f"{QUESTION}\n\nCode:\n{CODE}\n\n"
                "Additional context: This runs in a web server handling user requests. "
                "The URL comes from user input. Consider: RCE, injection, SSRF."
            ),
            timeout_sec=timeout_sec,
            rules="You are a security expert. Check for RCE, injection, SSRF. Return JSON.",
        )
    except RuntimeError as exc:
        print(f"    Escalation failed: {exc}")
        return {"escalated": True, "result": result}

    print(f"    Escalated confidence: {escalated.get('confidence', 'n/a')}")
    return {"escalated": True, "result": escalated}


def main() -> int:
    """Run confidence escalation example."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=60, metavar="SEC")
    args = parser.parse_args()

    print(banner("Confidence Escalation"))
    result = review_with_escalation(timeout_sec=args.timeout)
    print()
    r = result["result"]
    print(f"Escalated: {result['escalated']}")
    print(f"Passed: {r.get('passed')}, Confidence: {r.get('confidence', 'n/a')}")
    for issue in r.get("issues", [])[:5]:
        print(f"  - {str(issue)[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
