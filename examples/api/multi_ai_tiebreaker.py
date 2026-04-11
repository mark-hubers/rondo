# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo example: multi-AI tiebreaker.

Send the same question to 2 models. If they disagree, ask a 3rd.
Majority vote decides. Catches hallucinations — if 2 of 3 agree,
the answer is likely correct.

Uses **live** dispatch. Cloud providers need API keys.

Run::

    cd rondo && uv run python examples/api/multi_ai_tiebreaker.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

REVIEW_PROMPT = (
    "Is this code safe? Return JSON: "
    '{"passed": true/false, "issues": ["..."], "result": "summary"}\n\n'
    "Code:\ndef admin_page(request): return db.execute(f\"SELECT * FROM admin WHERE token={request.args['t']}\")"
)


def tiebreaker_review(*, timeout_sec: int) -> dict[str, Any]:
    """Two reviewers + optional tiebreaker if they disagree."""
    reviews: list[dict[str, Any]] = []
    models = ["", "anthropic:claude-haiku-4-5"]  ## Default + cheap second opinion

    for i, model in enumerate(models):
        label = "Primary" if i == 0 else "Secondary"
        print(f"  {label} ({model or 'default'})...")
        try:
            _, result = run_prompt_json(
                prompt=REVIEW_PROMPT,
                model=model,
                timeout_sec=timeout_sec,
                rules="You review code security. Return JSON only.",
            )
        except RuntimeError as exc:
            print(f"    Failed: {exc}")
            continue
        if result.get("_non_json"):
            print("    Non-JSON — skipping")
            continue
        reviews.append(
            {"model": model or "default", "passed": result.get("passed"), "issues": result.get("issues", [])}
        )
        print(f"    passed={result.get('passed')}, issues={len(result.get('issues', []))}")

    if len(reviews) < 2:
        print("  Not enough reviews for comparison")
        return {"verdict": "inconclusive", "reviews": reviews}

    ## Check agreement
    if reviews[0]["passed"] == reviews[1]["passed"]:
        print(f"  AGREE: both say passed={reviews[0]['passed']}")
        return {"verdict": "agreed", "passed": reviews[0]["passed"], "reviews": reviews}

    ## Disagreement — no tiebreaker without cloud keys, just report it
    print("  DISAGREE — reporting both views")
    return {"verdict": "disagreed", "reviews": reviews}


def main() -> int:
    """Run multi-AI tiebreaker."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=60, metavar="SEC")
    args = parser.parse_args()

    print(banner("Multi-AI Tiebreaker"))
    result = tiebreaker_review(timeout_sec=args.timeout)
    print()
    print(f"Verdict: {result['verdict']}")
    for r in result.get("reviews", []):
        print(f"  {r['model']}: passed={r['passed']}, issues={len(r.get('issues', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
