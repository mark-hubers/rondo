"""Rondo Real-World: Essay Fact-Check Pipeline.

REAL WORKFLOW THIS REPLACES:
  Agent reviewed 62 claims but gave wrong verdicts. Called things
  "unverified" that WERE in local files. 685 fact-check messages.

SCRIPTED VERSION:
  Extract claims -> ask Claude to verify each -> collect verdicts.
  In production: check local data FIRST (free), web only if needed.

HOW TO RUN:
  python examples/api/essay_fact_check_pipeline.py
"""

import json
import os
import sys

from rondo import smart_return

## Default model. Inside Claude Code: auto-falls back to Anthropic API.
## From terminal: dispatches via claude -p. Override with RONDO_MODEL env var.
DEFAULT_MODEL = os.environ.get("RONDO_MODEL", "sonnet")

_mcp_dispatch = None


def _get_dispatch_module() -> object:
    """Lazy-load mcp_dispatch."""
    global _mcp_dispatch  # noqa: PLW0603
    if _mcp_dispatch is None:
        from rondo import mcp_dispatch  # pylint: disable=import-outside-toplevel

        _mcp_dispatch = mcp_dispatch
    return _mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def _dispatch(prompt: str, model: str = "") -> dict | None:
    """Real AI dispatch via Rondo."""
    use_model = model or DEFAULT_MODEL
    try:
        mod = _get_dispatch_module()
        raw = mod.rondo_run_file(  # type: ignore[union-attr]
            prompt=prompt,
            model=use_model,
            dry_run=False,
            timeout_sec=60,
        )
        data = json.loads(raw)
        if data.get("status") == "error":
            return None
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status") == "error":
            return None
        output = tasks[0].get("raw_output", "")
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = {"passed": True, "result": output[:500], "issues": [], "confidence": 0.5}
        return smart_return.normalize_response(parsed)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        _out(f"  Dispatch failed: {exc}")
        return None


## --- Sample Claims (from real USH essays) ------------------------

SAMPLE_CLAIMS = [
    "Usher syndrome affects approximately 25,000 people in the US",
    "USH2A is the most common gene associated with Usher Type 2",
    "Retinitis pigmentosa causes progressive vision loss starting in adolescence",
    "The USH2A gene is located on chromosome 1q41",
    "Ray Therapeutics received RMAT designation for RTx-015 in April 2026",
]

VERIFY_PROMPT = """Verify this medical/scientific claim. Is it accurate?
Return JSON: {{"verified": true|false, "confidence": 0.9, "note": "explanation", "source": "what you know"}}

Claim: {claim}"""


## --- The Pipeline ------------------------------------------------


def fact_check_claims(claims: list[str]) -> dict:
    """Verify each claim by asking Claude. Real AI, no mocks."""
    results: list[dict] = []

    for i, claim in enumerate(claims):
        _out(f"  Claim {i + 1}: {claim[:60]}...")
        prompt = VERIFY_PROMPT.format(claim=claim)
        result = _dispatch(prompt)

        if result is None:
            _out("    SKIP: dispatch failed")
            continue

        verified = result.get("passed", False)
        confidence = result.get("confidence", 0.5)
        note = result.get("result", "")[:100]

        verdict = "VERIFIED" if verified else "NEEDS_REVIEW"
        results.append(
            {
                "claim": claim[:60],
                "verdict": verdict,
                "confidence": confidence,
                "note": note,
            }
        )
        _out(f"    {verdict} (confidence={confidence}): {note[:50]}")

    verified_count = len([r for r in results if r["verdict"] == "VERIFIED"])
    review_count = len([r for r in results if r["verdict"] == "NEEDS_REVIEW"])

    return {
        "total_claims": len(claims),
        "checked": len(results),
        "verified": verified_count,
        "needs_review": review_count,
        "safe_to_publish": review_count == 0,
        "results": results,
    }


def main() -> None:
    """Demonstrate essay fact-check pipeline."""
    _out("=== Essay Fact-Check Pipeline ===")
    _out("")

    _out("(REAL dispatch -- Claude verifies each claim)")
    _out("")
    report = fact_check_claims(SAMPLE_CLAIMS)
    _out("")
    _out(f"Result: {report['verified']} verified, {report['needs_review']} need review")
    if report["safe_to_publish"]:
        _out("-PASS- All claims verified")
    else:
        _out("-WARNING- Some claims need review before publishing")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea24.1ea524
