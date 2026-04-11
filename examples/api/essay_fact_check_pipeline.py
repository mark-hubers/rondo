"""Rondo Real-World: Essay Fact-Check Pipeline.

REAL WORKFLOW THIS REPLACES:
  Agent gave wrong verdicts on 62 claims. 685 fact-check messages.

SCRIPTED VERSION:
  Extract claims -> ask Claude to verify each -> collect verdicts.

HOW TO RUN:
  python examples/api/essay_fact_check_pipeline.py
"""

import json
import sys

from rondo import mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def dispatch(prompt: str, **kwargs: str | int) -> dict | None:
    """Dispatch prompt via Rondo inline subprocess (free on Max)."""
    raw = mcp_dispatch.rondo_run_file(
        prompt=prompt,
        model="",
        dry_run=False,
        timeout_sec=60,
        _session=object(),
        **kwargs,
    )
    data = json.loads(raw)
    tasks = data.get("tasks", [])
    if not tasks or tasks[0].get("status") == "error":
        return None
    output = tasks[0].get("raw_output", "")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"result": output, "passed": None, "issues": [], "confidence": 0.0}


SAMPLE_CLAIMS = [
    "Usher syndrome affects approximately 25,000 people in the US",
    "USH2A is the most common gene associated with Usher Type 2",
    "The USH2A gene is located on chromosome 1q41",
]


def fact_check_claims(claims: list[str]) -> dict:
    """Verify each claim by asking Claude."""
    results: list[dict] = []
    for i, claim in enumerate(claims):
        _out(f"  Claim {i + 1}: {claim[:50]}...")
        result = dispatch(
            f'Is this medical claim accurate? Return JSON: {{"verified": true/false, "note": "why"}}\n\nClaim: {claim}',
            rules="You verify medical claims. Return JSON only. Be precise.",
        )
        if result is None:
            _out("    SKIP")
            continue
        verified = result.get("passed", result.get("verified", False))
        note = str(result.get("result", result.get("note", "")))[:80]
        verdict = "VERIFIED" if verified else "NEEDS_REVIEW"
        results.append({"claim": claim[:50], "verdict": verdict, "note": note})
        _out(f"    {verdict}: {note[:50]}")

    return {
        "total": len(claims),
        "checked": len(results),
        "verified": len([r for r in results if r["verdict"] == "VERIFIED"]),
        "needs_review": len([r for r in results if r["verdict"] == "NEEDS_REVIEW"]),
        "safe_to_publish": all(r["verdict"] == "VERIFIED" for r in results),
        "results": results,
    }


def main() -> None:
    """Run essay fact-check pipeline."""
    _out("=== Essay Fact-Check Pipeline ===")
    _out("")
    report = fact_check_claims(SAMPLE_CLAIMS)
    _out("")
    _out(f"Result: {report['verified']} verified, {report['needs_review']} need review")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea24.1ea524
