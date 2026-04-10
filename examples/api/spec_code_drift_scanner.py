"""Rondo Real-World: Spec-Code Drift Scanner.

REAL WORKFLOW THIS REPLACES:
  Cursor found "spec says 18 MCP tools, code registers 21" — a real
  discrepancy that Claude missed. Mark manually cross-checks each
  spec requirement against the code. 5+ real mismatches caught in
  90 days, always by a second AI, never by the one that wrote the code.

SCRIPTED VERSION:
  Extract requirements from spec file → for each requirement, ask AI
  "does the code satisfy this?" → collect PASS/FAIL verdicts →
  create findings for FAILs → return structured drift report.

THE DECISION LOGIC:
  - Requirement verified in code → PASS, move on
  - Requirement missing from code → FAIL, create finding
  - Requirement contradicts code → CONFLICT, high-priority finding
  - Requirement ambiguous → UNCLEAR, flag for human review
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Mock Spec Parser ────────────────────────────────────────────
## In production: read the actual spec file and extract requirements
## using an AI call (rondo_run with "extract all SHALL/MUST reqs")


def _mock_extract_requirements(spec_path: str) -> list[dict]:
    """Simulate extracting requirements from a spec file.

    In production:
      content = Path(spec_path).read_text()
      result = rondo_run(prompt=f"Extract all requirements: {content}")
      return result["requirements"]
    """
    _ = spec_path
    return [
        {
            "id": "REQ-111-001",
            "text": "Smart return SHALL include passed, confidence, issues, and result fields",
            "section": "3.1 Return Schema",
        },
        {
            "id": "REQ-111-002",
            "text": "Provider scoring SHALL track quality, latency, and cost per call",
            "section": "4.2 Scoring",
        },
        {
            "id": "REQ-111-003",
            "text": "Hooks SHALL fire in order: pre-dispatch, post-dispatch, on-error",
            "section": "5.1 Hook Lifecycle",
        },
        {
            "id": "REQ-111-004",
            "text": "MCP server SHALL register exactly 22 tools",
            "section": "6.0 MCP Integration",
        },
        {
            "id": "REQ-111-005",
            "text": "Budget caps SHALL prevent dispatch when remaining budget < estimated cost",
            "section": "4.5 Budget Management",
        },
    ]


## ─── Mock Code Checker ──────────────────────────────────────────
## In production: send requirement + relevant code to AI for verification


def _mock_check_requirement(req: dict, code_path: str) -> dict:
    """Simulate AI checking if code satisfies a requirement.

    In production:
      code = Path(code_path).read_text()
      result = rondo_run(
          prompt=f"Does this code satisfy: {req['text']}  Code: {code}",
          model="gemini:flash"
      )
    """
    _ = code_path
    ## Simulate realistic results — some pass, some fail, some conflict
    verdicts = {
        "REQ-111-001": {
            "verdict": "PASS",
            "evidence": "normalize_response() returns all 4 fields",
            "confidence": 0.95,
        },
        "REQ-111-002": {
            "verdict": "PASS",
            "evidence": "ProviderScore tracks quality, latency_ms, cost_usd",
            "confidence": 0.92,
        },
        "REQ-111-003": {
            "verdict": "FAIL",
            "evidence": "post-dispatch hooks fire BEFORE finalize, not after",
            "confidence": 0.88,
        },
        "REQ-111-004": {
            "verdict": "CONFLICT",
            "evidence": "Spec says 22 tools but code registers 25 — 3 undocumented",
            "confidence": 0.96,
        },
        "REQ-111-005": {
            "verdict": "FAIL",
            "evidence": "GeminiAdapter returns cost_usd=0.0, budget check always passes",
            "confidence": 0.91,
        },
    }
    return verdicts.get(
        req["id"],
        {"verdict": "UNCLEAR", "evidence": "Could not determine", "confidence": 0.3},
    )


## ─── The Scanner ─────────────────────────────────────────────────


def scan_spec_drift(
    spec_path: str = "specs/REQ-111.md",
    code_path: str = "rondo/src/rondo/",
) -> dict:
    """Full pipeline: extract reqs → check each against code → report drift.

    This is the REAL scripted workflow:
    1. Parse spec file for requirements (AI-assisted extraction)
    2. For each requirement, ask AI "does the code satisfy this?"
    3. Classify verdict: PASS / FAIL / CONFLICT / UNCLEAR
    4. CONFLICT = highest priority (spec says X, code does Y)
    5. FAIL = code is missing something the spec requires
    6. UNCLEAR = ambiguous, needs human review
    7. Return structured report with findings per requirement

    This catches the EXACT class of bugs Cursor found —
    count mismatches, ordering bugs, silent bypasses.
    """
    _out(f"  Scanning: {spec_path} against {code_path}")

    ## Step 1: Extract requirements
    requirements = _mock_extract_requirements(spec_path)
    _out(f"  Found {len(requirements)} requirements")

    ## Step 2: Check each requirement
    results: list[dict] = []
    for req in requirements:
        check = _mock_check_requirement(req, code_path)
        normalized = smart_return.normalize_response(
            {
                "passed": check["verdict"] == "PASS",
                "confidence": check["confidence"],
                "result": check["evidence"],
                "issues": [check["evidence"]] if check["verdict"] != "PASS" else [],
                "_meta": {"quality": 8, "complete": True, "limitations": ""},
            }
        )

        verdict = check["verdict"]
        results.append(
            {
                "req_id": req["id"],
                "section": req["section"],
                "text": req["text"][:60],
                "verdict": verdict,
                "evidence": check["evidence"],
                "confidence": normalized["confidence"],
            }
        )

        ## Status output with severity
        if verdict == "CONFLICT":
            _out(f"    CONFLICT {req['id']}: {check['evidence'][:60]}")
        elif verdict == "FAIL":
            _out(f"    FAIL     {req['id']}: {check['evidence'][:60]}")
        elif verdict == "UNCLEAR":
            _out(f"    UNCLEAR  {req['id']}: needs human review")
        else:
            _out(f"    PASS     {req['id']}: {check['evidence'][:60]}")

    ## Step 3: Summarize
    passes = [r for r in results if r["verdict"] == "PASS"]
    fails = [r for r in results if r["verdict"] == "FAIL"]
    conflicts = [r for r in results if r["verdict"] == "CONFLICT"]
    unclear = [r for r in results if r["verdict"] == "UNCLEAR"]

    _out("")
    _out(f"  Summary: {len(passes)} PASS, {len(fails)} FAIL, {len(conflicts)} CONFLICT, {len(unclear)} UNCLEAR")

    return {
        "spec": spec_path,
        "total_requirements": len(requirements),
        "pass_count": len(passes),
        "fail_count": len(fails),
        "conflict_count": len(conflicts),
        "unclear_count": len(unclear),
        "has_drift": len(fails) > 0 or len(conflicts) > 0,
        "results": results,
    }


def main() -> None:
    """Demonstrate spec-code drift scanner."""
    _out("=== Spec-Code Drift Scanner ===")
    _out("(Replaces: Cursor finds 'spec says 18, code has 21' manually)")
    _out("")

    report = scan_spec_drift()
    _out("")

    ## Show the findings that need action
    actionable = [r for r in report["results"] if r["verdict"] in ("FAIL", "CONFLICT")]
    if actionable:
        _out("Actionable findings:")
        for finding in actionable:
            _out(f"  [{finding['verdict']}] {finding['req_id']}: {finding['evidence'][:70]}")

    ## Verify the scanner detected real drift
    if not report["has_drift"]:
        _out("  -ERROR- Scanner should detect drift in test data")
        sys.exit(1)
    if report["conflict_count"] < 1:
        _out("  -ERROR- Should find at least 1 CONFLICT")
        sys.exit(1)

    _out("")
    _out("The key: AI checks EACH requirement against code.")
    _out("Catches count mismatches, ordering bugs, silent bypasses.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea22.1ea522
