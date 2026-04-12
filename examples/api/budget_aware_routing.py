# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=config value="Cost-aware dispatch selection from script logic"

"""Rondo example: budget-aware routing.

Start with the cheapest option and escalate only when needed.
Track cost from the dispatch envelope and stop if budget exceeded.

Uses **live** dispatch. First call uses default (free on Max plan).

Run::

    cd rondo && uv run python examples/api/budget_aware_routing.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

QUESTION = "Explain what SQL injection is in one sentence."
BUDGET_USD = 0.10


def budget_routing(*, timeout_sec: int) -> dict[str, Any]:
    """Start cheap, escalate only if needed, respect budget."""
    spent = 0.0
    history: list[dict[str, Any]] = []

    ## Step 1: Try default (free on Max plan)
    print("  Step 1: Default model (free on Max)...")
    try:
        env, result = run_prompt_json(
            prompt=QUESTION,
            timeout_sec=timeout_sec,
            rules="Be concise. Return JSON: {result: 'your answer', confidence: 0.9}",
        )
    except RuntimeError as exc:
        return {"error": str(exc), "spent": spent, "history": history}

    cost = float(env.get("total_cost_usd", 0.0))
    spent += cost
    history.append({"step": "default", "cost": cost, "confidence": result.get("confidence", 0.0)})
    print(f"    Cost: ${cost:.4f}, total: ${spent:.4f}")

    confidence = float(result.get("confidence", 0.0))
    if confidence >= 0.8:
        print(f"    Confidence {confidence} — no escalation needed")
        return {"final": result, "spent": spent, "history": history}

    ## Step 2: Check budget before escalating
    if spent >= BUDGET_USD:
        print(f"    Budget (${BUDGET_USD}) exceeded — using default result")
        return {"final": result, "spent": spent, "history": history, "budget_exceeded": True}

    ## Step 3: Escalate to cloud (would cost money)
    print(f"    Low confidence — would escalate (within ${BUDGET_USD} budget)")
    return {"final": result, "spent": spent, "history": history}


def main() -> int:
    """Run budget-aware routing."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=60, metavar="SEC")
    args = parser.parse_args()

    print(banner("Budget-Aware Routing"))
    result = budget_routing(timeout_sec=args.timeout)
    print()
    if result.get("error"):
        print(f"-ERROR- {result['error']}")
        return 1
    print(f"Total spent: ${result['spent']:.4f} / ${BUDGET_USD}")
    print(f"Steps: {len(result['history'])}")
    for step in result["history"]:
        print(f"  {step['step']}: ${step['cost']:.4f}, confidence={step['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
