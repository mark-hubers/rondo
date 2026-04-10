"""Rondo Real-World: Multi-AI Code Review → Sprint Findings.

REAL WORKFLOW THIS REPLACES:
  Mark builds code with Claude → copies to Cursor → pastes Cursor's
  findings back into Claude → Claude fixes → repeat. Every session.
  165 Cursor paste-backs in 90 days. Pure manual relay.

SCRIPTED VERSION:
  Send code to 3 AI providers simultaneously → parse structured
  findings → consensus check (2+ agree = confirmed) → create sprint
  findings automatically → flag disagreements for human review.

THE DECISION LOGIC:
  - All 3 agree "clean" → done, no findings
  - All 3 agree on same issue → HIGH confidence finding, auto-create
  - 2 of 3 agree → MEDIUM confidence, auto-create with note
  - Only 1 flags it → LOW confidence, flag for human review only
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Mock Providers ──────────────────────────────────────────────
## In production: replace with rondo_run() or rondo_multi_review()
## These simulate what Gemini, Grok, and Mistral actually return
## when reviewing code — sometimes they agree, sometimes they don't.


def _provider_gemini(code: str) -> dict:
    """Simulate Gemini reviewing code — finds SQL injection + XSS."""
    _ = code
    return {
        "passed": False,
        "confidence": 0.92,
        "issues": [
            "SQL injection: user input in query on line 42",
            "XSS: unescaped output on line 88",
        ],
        "result": "2 security issues found",
        "_meta": {"quality": 9, "complete": True, "limitations": ""},
    }


def _provider_grok(code: str) -> dict:
    """Simulate Grok reviewing code — finds SQL injection only."""
    _ = code
    return {
        "passed": False,
        "confidence": 0.88,
        "issues": [
            "SQL injection: raw string concatenation in query builder",
        ],
        "result": "1 security issue found",
        "_meta": {"quality": 8, "complete": True, "limitations": ""},
    }


def _provider_mistral(code: str) -> dict:
    """Simulate Mistral reviewing code — finds SQL injection + auth bypass."""
    _ = code
    return {
        "passed": False,
        "confidence": 0.85,
        "issues": [
            "SQL injection: parameterize all queries",
            "Missing authentication check on /admin endpoint",
        ],
        "result": "2 issues found",
        "_meta": {"quality": 8, "complete": True, "limitations": ""},
    }


## ─── Issue Matching ──────────────────────────────────────────────
## AI providers describe the same bug differently. We need fuzzy
## matching to detect consensus. In production, Rondo's normalize
## handles this — here we use keyword overlap.


def _issues_match(issue_a: str, issue_b: str) -> bool:
    """Check if two issues describe the same bug (keyword overlap)."""
    words_a = set(issue_a.lower().split())
    words_b = set(issue_b.lower().split())
    overlap = words_a & words_b
    ## If 3+ meaningful words overlap, likely same issue
    noise = {"the", "a", "an", "on", "in", "is", "of", "to", "and", "for"}
    meaningful = overlap - noise
    return len(meaningful) >= 2


def _find_consensus(reviews: list[dict]) -> list[dict]:
    """Find issues that 2+ providers agree on, and solo flags.

    Returns list of findings with confidence level:
      HIGH = all 3 agree
      MEDIUM = 2 of 3 agree
      LOW = only 1 provider flagged it (needs human review)
    """
    ## Collect all issues with their source provider
    all_issues: list[dict] = []
    for i, review in enumerate(reviews):
        provider = ["gemini", "grok", "mistral"][i]
        for issue in review.get("issues", []):
            all_issues.append({"text": issue, "provider": provider})

    ## Group by consensus
    findings: list[dict] = []
    used: set[int] = set()
    for i, issue_a in enumerate(all_issues):
        if i in used:
            continue
        matches = [issue_a["provider"]]
        used.add(i)
        for j, issue_b in enumerate(all_issues):
            if j in used or j == i:
                continue
            if _issues_match(issue_a["text"], issue_b["text"]):
                matches.append(issue_b["provider"])
                used.add(j)

        ## Determine confidence from provider count
        if len(matches) >= 3:
            confidence = "HIGH"
        elif len(matches) >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        findings.append(
            {
                "issue": issue_a["text"],
                "confidence": confidence,
                "providers": matches,
                "provider_count": len(matches),
            }
        )

    return findings


## ─── Sprint Integration ──────────────────────────────────────────
## In production, this calls: ace-sprint finding add <sprint> ...
## For testing, we simulate the creation and return what would happen.


def _create_sprint_finding(finding: dict, sprint_id: str = "TEST-001") -> dict:
    """Create a sprint finding from a consensus issue.

    In production:
      subprocess.run(["ace-sprint", "finding", "add", sprint_id,
                       "--category", "security", "--detail", finding["issue"]])

    For living test: simulate and return the action taken.
    """
    action = {
        "sprint": sprint_id,
        "issue": finding["issue"],
        "confidence": finding["confidence"],
        "providers": finding["providers"],
    }

    if finding["confidence"] in ("HIGH", "MEDIUM"):
        action["action"] = "AUTO_CREATED"
        action["status"] = "finding_created"
    else:
        action["action"] = "FLAGGED_FOR_REVIEW"
        action["status"] = "needs_human"

    return action


## ─── The Pipeline ────────────────────────────────────────────────


def multi_ai_review_to_findings(
    code: str,
    sprint_id: str = "TEST-001",
) -> dict:
    """Full pipeline: 3 providers → consensus → sprint findings.

    This is the REAL scripted workflow:
    1. Send code to 3 AI providers (parallel in production)
    2. Normalize all responses to structured format
    3. Find consensus — which issues do 2+ providers agree on?
    4. Auto-create sprint findings for confirmed issues
    5. Flag low-confidence issues for human review
    6. Return summary with action taken per finding
    """
    _out("  Step 1: Dispatching to 3 providers...")
    reviews = [
        smart_return.normalize_response(_provider_gemini(code)),
        smart_return.normalize_response(_provider_grok(code)),
        smart_return.normalize_response(_provider_mistral(code)),
    ]

    for i, name in enumerate(["Gemini", "Grok", "Mistral"]):
        r = reviews[i]
        _out(f"    {name}: passed={r['passed']}, issues={len(r['issues'])}")

    ## Step 2: Find consensus
    _out("  Step 2: Finding consensus...")
    findings = _find_consensus(reviews)

    high = [f for f in findings if f["confidence"] == "HIGH"]
    medium = [f for f in findings if f["confidence"] == "MEDIUM"]
    low = [f for f in findings if f["confidence"] == "LOW"]
    _out(f"    HIGH={len(high)}, MEDIUM={len(medium)}, LOW={len(low)}")

    ## Step 3: Create findings for confirmed issues
    _out("  Step 3: Creating sprint findings...")
    actions: list[dict] = []
    for finding in findings:
        action = _create_sprint_finding(finding, sprint_id)
        actions.append(action)
        if action["action"] == "AUTO_CREATED":
            _out(f"    CREATED: [{finding['confidence']}] {finding['issue'][:50]}...")
        else:
            _out(f"    FLAGGED: [{finding['confidence']}] {finding['issue'][:50]}... -> human review")

    return {
        "total_findings": len(findings),
        "auto_created": len([a for a in actions if a["action"] == "AUTO_CREATED"]),
        "needs_review": len([a for a in actions if a["action"] == "FLAGGED_FOR_REVIEW"]),
        "actions": actions,
    }


def main() -> None:
    """Demonstrate multi-AI code review → sprint findings pipeline."""
    _out("=== Multi-AI Code Review -> Sprint Findings ===")
    _out("(Replaces: copy to Cursor -> paste back -> fix -> repeat)")
    _out("")

    result = multi_ai_review_to_findings(
        "def login(user, pw): ...",
        sprint_id="RONDO-250",
    )
    _out("")
    _out(f"Result: {result['total_findings']} findings total")
    _out(f"  Auto-created: {result['auto_created']}")
    _out(f"  Needs review: {result['needs_review']}")

    ## Verify the pipeline did real work (not asserts — examples are not test-only)
    if result["total_findings"] < 2:
        _out("  -ERROR- Should find at least 2 issues")
        sys.exit(1)
    if result["auto_created"] < 1:
        _out("  -ERROR- Should auto-create at least 1 finding")
        sys.exit(1)
    if not all(a["sprint"] == "RONDO-250" for a in result["actions"]):
        _out("  -ERROR- All findings should be tagged to sprint")
        sys.exit(1)

    _out("")
    _out("The key: structured returns let Python make decisions.")
    _out("No human copy-paste relay needed.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea20.1ea520
