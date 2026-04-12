# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=observability value="Retry strategy and recovery handling for failed runs"

"""Rondo example: retry on failure with provider escalation.

When the first AI call fails or returns low confidence, try a
different model. Python controls the retry logic.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/retry_on_failure.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

REVIEW_PROMPT = (
    "Review this code for bugs. Return JSON:\n"
    '{"passed": true/false, "confidence": 0.0-1.0, "issues": ["..."], "result": "summary"}\n\n'
    "Code:\ndef divide(a, b): return a / b"
)


def review_with_retry(*, timeout_sec: int) -> dict[str, Any]:
    """Try primary model; if low confidence or failure, escalate."""
    print("  Step 1: Primary model...")
    try:
        _, result = run_prompt_json(
            prompt=REVIEW_PROMPT,
            model="",
            timeout_sec=timeout_sec,
            rules="You review code for bugs. Return JSON only.",
        )
    except RuntimeError as exc:
        print(f"    Primary failed: {exc}")
        result = {"passed": None, "confidence": 0.0}

    if result.get("_non_json"):
        print("    Primary returned non-JSON")
        result = {"passed": None, "confidence": 0.0}

    confidence = float(result.get("confidence", 0.0))
    if result.get("passed") is not None and confidence >= 0.8:
        print(f"    Primary succeeded: confidence={confidence}")
        return {"source": "primary", "result": result}

    ## Escalate
    print(f"    Low confidence ({confidence}) — escalating...")
    try:
        _, escalated = run_prompt_json(
            prompt=REVIEW_PROMPT,
            model="",
            timeout_sec=timeout_sec,
            rules="You are a senior code reviewer. Be thorough. Return JSON only.",
        )
    except RuntimeError as exc:
        print(f"    Escalation failed: {exc}")
        return {"source": "failed", "result": result}

    if escalated.get("_non_json"):
        return {"source": "escalation_non_json", "result": result}

    print(f"    Escalation: confidence={escalated.get('confidence', 'n/a')}")
    return {"source": "escalated", "result": escalated}


def main() -> int:
    """Run retry-on-failure pattern."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=60, metavar="SEC")
    args = parser.parse_args()

    print(banner("Retry on Failure"))
    result = review_with_retry(timeout_sec=args.timeout)
    print()
    print(f"Source: {result['source']}")
    issues = result["result"].get("issues", [])
    print(f"Issues: {len(issues)}")
    for issue in issues[:5]:
        print(f"  - {str(issue)[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
