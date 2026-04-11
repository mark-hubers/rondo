"""Rondo Real-World: Spec-Code Drift Scanner.

REAL WORKFLOW THIS REPLACES:
  Cursor found 'spec says 18 tools, code registers 21.' Manual cross-check.

SCRIPTED VERSION:
  For each requirement, ask Claude 'does the code satisfy this?'
  Collect PASS/FAIL verdicts. Report drift.

HOW TO RUN:
  python examples/api/spec_code_drift_scanner.py
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


SAMPLE_REQUIREMENTS = [
    {"id": "REQ-001", "text": "normalize_response SHALL return passed, confidence, issues, and result fields"},
    {"id": "REQ-002", "text": "Provider scoring SHALL track quality, latency, and cost per call"},
    {"id": "REQ-003", "text": "MCP server SHALL register exactly 22 tools"},
]

SAMPLE_CODE = """def normalize_response(raw):
    return {
        "passed": raw.get("passed", True),
        "confidence": raw.get("confidence", 0.5),
        "issues": raw.get("issues", []),
        "result": raw.get("result", ""),
    }

class ProviderScore:
    def __init__(self):
        self.quality = 0
        self.latency_ms = 0
        # NOTE: cost_usd field is missing!
"""

CHECK_PROMPT = """Does this code satisfy this requirement? Return JSON:
{{"verdict": "PASS" or "FAIL", "evidence": "what you found", "confidence": 0.9}}

Requirement: {req}
Code:
{code}"""


def scan_drift(requirements: list[dict], code: str) -> dict:
    """Check each requirement against code via real AI dispatch."""
    results: list[dict] = []
    for req in requirements:
        _out(f"  Checking {req['id']}...")
        result = dispatch(
            CHECK_PROMPT.format(req=req["text"], code=code),
            rules="You verify code against requirements. Return JSON only.",
        )
        if result is None:
            _out("    SKIP: dispatch failed")
            continue
        verdict = "FAIL" if not result.get("passed", True) else "PASS"
        if "FAIL" in str(result.get("result", "")).upper():
            verdict = "FAIL"
        results.append({"req_id": req["id"], "verdict": verdict, "evidence": str(result.get("result", ""))[:80]})
        _out(f"    {verdict}: {str(result.get('result', ''))[:60]}")

    return {
        "total": len(results),
        "pass_count": len([r for r in results if r["verdict"] == "PASS"]),
        "fail_count": len([r for r in results if r["verdict"] == "FAIL"]),
        "has_drift": any(r["verdict"] == "FAIL" for r in results),
        "results": results,
    }


def main() -> None:
    """Run spec-code drift scanner."""
    _out("=== Spec-Code Drift Scanner ===")
    _out("")
    report = scan_drift(SAMPLE_REQUIREMENTS, SAMPLE_CODE)
    _out("")
    _out(f"Result: {report['pass_count']} PASS, {report['fail_count']} FAIL")
    if report["has_drift"]:
        _out("-WARNING- Spec-code drift detected")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea22.1ea522
