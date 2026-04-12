# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=essay value="Multi-step essay claim extraction and fact-check loop"

"""Rondo example: per-claim structured verification (sample medical-style claims).

What this demonstrates
----------------------
* **Looping** over a list with one ``rondo_run_file`` invocation per item.
* Asking for **JSON** with explicit keys and handling ``_non_json`` from :mod:`example_dispatch`.
* Aggregating a simple **publish gate** from parsed fields (``verified`` / ``passed``).

Important:
---------
Sample strings are **illustrative only** — not medical advice. Production pipelines should
attach citations, retrieval, and human review.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/essay_fact_check_pipeline.py
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

SAMPLE_CLAIMS: list[str] = [
    "Usher syndrome affects approximately 25,000 people in the US",
    "USH2A is the most common gene associated with Usher Type 2",
    "The USH2A gene is located on chromosome 1q41",
]


def fact_check_claims(claims: list[str], *, timeout_sec: int) -> dict[str, Any]:
    """Return aggregate stats plus per-claim rows."""
    rows: list[dict[str, Any]] = []
    for i, claim in enumerate(claims):
        print(f"  Claim {i + 1}: {claim[:56]}…")
        prompt = (
            f"Is this medical claim accurate for lay summary writing? "
            f'Return JSON only: {{"verified": true/false, "note": "short caveat"}}\n\nClaim: {claim}'
        )
        try:
            env, parsed = run_prompt_json(
                prompt=prompt,
                model="",
                dry_run=False,
                timeout_sec=timeout_sec,
                rules="You verify factual claims conservatively. JSON only.",
            )
        except RuntimeError as exc:
            print(f"    -ERROR- {exc}", file=sys.stderr)
            rows.append({"claim": claim[:56], "verdict": "ERROR", "note": str(exc)[:80]})
            continue

        if parsed.get("_non_json"):
            rows.append({"claim": claim[:56], "verdict": "NON_JSON", "note": str(parsed.get("snippet", ""))[:80]})
            print("    -WARNING- Model did not return JSON.")
            continue

        verified = bool(parsed.get("verified", parsed.get("passed")))
        note = str(parsed.get("note", parsed.get("result", "")))[:120]
        verdict = "VERIFIED" if verified else "NEEDS_REVIEW"
        rows.append({"claim": claim[:56], "verdict": verdict, "note": note, "round_status": env.get("status")})
        print(f"    {verdict}: {note[:56]}…")

    ok = [r for r in rows if r["verdict"] == "VERIFIED"]
    bad = [r for r in rows if r["verdict"] != "VERIFIED"]
    return {
        "total": len(claims),
        "checked": len(rows),
        "verified": len(ok),
        "needs_review": len(bad),
        "safe_to_publish": len(bad) == 0 and len(rows) == len(claims),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Essay-style fact check (sample claims)"))
    report = fact_check_claims(SAMPLE_CLAIMS, timeout_sec=args.timeout)
    print()
    print(f"Verified={report['verified']} needs_review={report['needs_review']} safe={report['safe_to_publish']}")
    return 0 if report["safe_to_publish"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
