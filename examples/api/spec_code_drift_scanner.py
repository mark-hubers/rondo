"""Rondo Real-World: Spec-Code Drift Scanner.

REAL WORKFLOW THIS REPLACES:
  Cursor found "spec says 18 MCP tools, code registers 21."
  Mark manually cross-checks each spec requirement against code.

SCRIPTED VERSION:
  For each requirement, ask Claude "does the code satisfy this?"
  Collect PASS/FAIL/CONFLICT verdicts. Create findings for FAILs.

HOW TO RUN:
  python examples/api/spec_code_drift_scanner.py
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


## --- Sample Requirements + Code ----------------------------------

SAMPLE_REQUIREMENTS = [
    {"id": "REQ-001", "text": "normalize_response SHALL return passed, confidence, issues, and result fields"},
    {"id": "REQ-002", "text": "Provider scoring SHALL track quality, latency, and cost per call"},
    {"id": "REQ-003", "text": "MCP server SHALL register exactly 22 tools"},
]

SAMPLE_CODE = '''def normalize_response(raw):
    """Normalize any AI response to standard schema."""
    return {
        "passed": raw.get("passed", True),
        "confidence": raw.get("confidence", 0.5),
        "issues": raw.get("issues", []),
        "result": raw.get("result", ""),
        "_meta": raw.get("_meta", {}),
    }

class ProviderScore:
    def __init__(self):
        self.quality = 0
        self.latency_ms = 0
        # NOTE: cost_usd field is missing!
'''

CHECK_PROMPT = """Check if this code satisfies this requirement.
Return JSON: {{"verdict": "PASS"|"FAIL"|"CONFLICT", "evidence": "what you found", "confidence": 0.9}}

Requirement: {req}

Code:
{code}"""


## --- The Scanner -------------------------------------------------


def scan_drift(requirements: list[dict], code: str) -> dict:
    """Check each requirement against code via real AI dispatch."""
    results: list[dict] = []

    for req in requirements:
        _out(f"  Checking {req['id']}...")
        prompt = CHECK_PROMPT.format(req=req["text"], code=code)
        result = _dispatch(prompt)

        if result is None:
            _out(f"    SKIP: dispatch failed for {req['id']}")
            continue

        ## Extract verdict from AI response
        verdict = result.get("result", "")
        if isinstance(verdict, str):
            verdict_upper = verdict.upper()
            if "FAIL" in verdict_upper:
                verdict = "FAIL"
            elif "CONFLICT" in verdict_upper:
                verdict = "CONFLICT"
            else:
                verdict = "PASS" if result.get("passed", True) else "FAIL"

        results.append(
            {
                "req_id": req["id"],
                "verdict": verdict,
                "evidence": result.get("result", "")[:100],
                "confidence": result.get("confidence", 0.5),
            }
        )
        _out(f"    {verdict}: {result.get('result', '')[:60]}")

    passes = [r for r in results if r["verdict"] == "PASS"]
    fails = [r for r in results if r["verdict"] != "PASS"]

    return {
        "total": len(results),
        "pass_count": len(passes),
        "fail_count": len(fails),
        "has_drift": len(fails) > 0,
        "results": results,
    }


def main() -> None:
    """Demonstrate spec-code drift scanner."""
    _out("=== Spec-Code Drift Scanner ===")
    _out("")

    _out("(REAL dispatch -- Claude checks each requirement)")
    _out("")
    report = scan_drift(SAMPLE_REQUIREMENTS, SAMPLE_CODE)
    _out("")
    _out(f"Result: {report['pass_count']} PASS, {report['fail_count']} FAIL")
    if report["has_drift"]:
        _out("-WARNING- Spec-code drift detected")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea22.1ea522
