"""Rondo Real-World: Research Freshness -> Essay Impact Scanner.

REAL WORKFLOW THIS REPLACES:
  Nightly BioMCP scan runs and finds new papers/trial updates. But
  the results are NOT connected to Mark's essays. He manually checks
  "does this new finding matter for any essay I've published?" each
  session. 661 research-related messages in 90 days.

SCRIPTED VERSION:
  Take scan results -> match each finding to essay index (which
  essays mention related topics) -> classify impact level ->
  HIGH = contradicts published claim (urgent!)
  MEDIUM = adds supporting data (update when convenient)
  LOW = background context (log for reference)

THE DECISION LOGIC:
  - New finding matches published essay topic -> check deeper
  - Finding CONTRADICTS a claim in the essay -> HIGH (alert Mark)
  - Finding ADDS data to essay topic -> MEDIUM (queue update)
  - Finding is tangentially related -> LOW (log only)
  - Finding matches no essays -> SKIP (not relevant to published work)
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line -- examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## --- Mock Scan Results -------------------------------------------
## In production: loaded from nightly BioMCP scan output JSON


def _mock_scan_results() -> list[dict]:
    """Simulate nightly BioMCP scan findings.

    In production: json.loads(Path("data/nightly-scan/latest.json").read_text())
    """
    return [
        {
            "id": "SCAN-001",
            "source": "PubMed",
            "title": "Updated prevalence of Usher syndrome: 1 in 6,000",
            "date": "2026-04-08",
            "gene": "USH2A",
            "topic": "prevalence",
            "key_finding": "New estimate: 1 in 6,000 (previously 1 in 10,000)",
        },
        {
            "id": "SCAN-002",
            "source": "ClinicalTrials.gov",
            "title": "RTx-015 Phase 2 enrollment complete",
            "date": "2026-04-09",
            "gene": "USH2A",
            "topic": "gene_therapy",
            "key_finding": "Phase 2 fully enrolled, results expected Q4 2026",
        },
        {
            "id": "SCAN-003",
            "source": "PubMed",
            "title": "Cochlear implant outcomes in USH1 children",
            "date": "2026-04-07",
            "gene": "MYO7A",
            "topic": "hearing",
            "key_finding": "CI outcomes similar to non-syndromic deaf children",
        },
        {
            "id": "SCAN-004",
            "source": "bioRxiv",
            "title": "Novel USH2A splice variant in East Asian populations",
            "date": "2026-04-10",
            "gene": "USH2A",
            "topic": "genetics",
            "key_finding": "New pathogenic variant c.8559-2A>G found in 3 families",
        },
    ]


## --- Mock Essay Index --------------------------------------------


def _mock_essay_index() -> list[dict]:
    """Simulate the published essay index.

    In production: parsed from essay-index.md or database
    """
    return [
        {
            "id": "ESSAY-001",
            "title": "Usher Syndrome: The Numbers",
            "topics": ["prevalence", "demographics"],
            "claims": ["affects approximately 25,000 in the US", "1 in 10,000 prevalence"],
            "published": "2026-03-01",
            "url": "https://markhubers.substack.com/p/usher-the-numbers",
        },
        {
            "id": "ESSAY-002",
            "title": "Gene Therapy Hope: What Is Real",
            "topics": ["gene_therapy", "trials", "USH2A"],
            "claims": ["RTx-015 in Phase 1/2", "3 active trials"],
            "published": "2026-03-15",
            "url": "https://markhubers.substack.com/p/gene-therapy-hope",
        },
        {
            "id": "ESSAY-003",
            "title": "Know Your Gene",
            "topics": ["genetics", "USH2A", "testing"],
            "claims": ["most common variant is c.2299delG"],
            "published": "2026-03-20",
            "url": "https://markhubers.substack.com/p/know-your-gene",
        },
    ]


## --- Impact Classification ---------------------------------------


def _classify_impact(finding: dict, essay: dict) -> dict:
    """Classify how a finding impacts a published essay.

    In production: rondo_run asking AI to compare finding against
    essay claims and classify as HIGH/MEDIUM/LOW.
    """
    ## Check if finding contradicts any essay claims
    for claim in essay.get("claims", []):
        claim_lower = claim.lower()
        finding_lower = finding["key_finding"].lower()

        ## Prevalence contradiction check
        if "prevalence" in finding["topic"] and "prevalence" in claim_lower:
            if "1 in 10,000" in claim_lower and "1 in 6,000" in finding_lower:
                return {
                    "level": "HIGH",
                    "reason": "New prevalence contradicts published number",
                    "claim": claim,
                    "action": "UPDATE_ESSAY",
                }

        ## Trial phase advancement
        if "phase 1" in claim_lower and "phase 2" in finding_lower:
            return {
                "level": "HIGH",
                "reason": "Trial advanced to Phase 2 since essay published",
                "claim": claim,
                "action": "UPDATE_ESSAY",
            }

    ## Topic match but no contradiction -> supporting data
    if finding["topic"] in " ".join(essay.get("topics", [])):
        return {
            "level": "MEDIUM",
            "reason": "New supporting data for essay topic",
            "claim": None,
            "action": "QUEUE_UPDATE",
        }

    return {
        "level": "LOW",
        "reason": "Tangentially related",
        "claim": None,
        "action": "LOG_ONLY",
    }


## --- The Pipeline ------------------------------------------------


def scan_research_impact(scan_path: str = "data/nightly-scan/latest.json") -> dict:
    """Match scan results against essay index, classify impact.

    This is the REAL scripted workflow:
    1. Load latest scan results (nightly BioMCP output)
    2. Load essay index (published essays with claims)
    3. For each scan finding, check against each essay
    4. Classify impact: HIGH (contradicts) / MEDIUM (adds) / LOW (tangential)
    5. HIGH findings -> alert Mark immediately
    6. MEDIUM findings -> queue for next essay update
    7. LOW findings -> log for reference, no action needed
    """
    _ = scan_path
    _out("  Loading scan results...")
    findings = _mock_scan_results()
    essays = _mock_essay_index()
    _out(f"  Scan findings: {len(findings)}")
    _out(f"  Published essays: {len(essays)}")

    ## Match each finding against each essay
    impacts: list[dict] = []
    for finding in findings:
        best_impact: dict = {}
        best_essay: dict = {}

        for essay in essays:
            impact = _classify_impact(finding, essay)

            ## Keep the highest-impact match
            priority = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
            if not best_impact or priority.get(impact["level"], 0) > priority.get(best_impact["level"], 0):
                best_impact = impact
                best_essay = essay

        if best_impact and best_essay:
            normalized = smart_return.normalize_response(
                {
                    "passed": best_impact["level"] != "HIGH",
                    "confidence": 0.9,
                    "result": best_impact["reason"],
                    "issues": ([best_impact["reason"]] if best_impact["level"] == "HIGH" else []),
                    "_meta": {"quality": 8, "complete": True, "limitations": ""},
                }
            )

            record = {
                "finding_id": finding["id"],
                "finding_title": finding["title"][:50],
                "essay_id": best_essay["id"],
                "essay_title": best_essay["title"],
                "impact": best_impact["level"],
                "reason": best_impact["reason"],
                "action": best_impact["action"],
                "confidence": normalized["confidence"],
            }
            impacts.append(record)

            label = best_impact["level"]
            _out(f"    {label:6s} {finding['id']}: {best_impact['reason'][:50]}")
            _out(f"           -> {best_essay['title']}")

    ## Summary
    high = [i for i in impacts if i["impact"] == "HIGH"]
    medium = [i for i in impacts if i["impact"] == "MEDIUM"]
    low = [i for i in impacts if i["impact"] == "LOW"]

    _out("")
    _out(f"  Impact: {len(high)} HIGH, {len(medium)} MEDIUM, {len(low)} LOW")

    return {
        "scan_date": "2026-04-10",
        "findings_scanned": len(findings),
        "essays_checked": len(essays),
        "high_impact": len(high),
        "medium_impact": len(medium),
        "low_impact": len(low),
        "needs_attention": len(high) > 0,
        "impacts": impacts,
    }


def main() -> None:
    """Demonstrate research freshness -> essay impact scanner."""
    _out("=== Research Freshness -> Essay Impact Scanner ===")
    _out("(Replaces: manually checking 'does this new paper matter?')")
    _out("")

    report = scan_research_impact()
    _out("")

    if report["needs_attention"]:
        _out("-WARNING- HIGH-impact findings need essay updates:")
        for impact in report["impacts"]:
            if impact["impact"] == "HIGH":
                _out(f"  {impact['finding_id']}: {impact['reason']}")
                _out(f"    Essay: {impact['essay_title']}")
                _out(f"    Action: {impact['action']}")
    else:
        _out("-PASS- No high-impact findings -- essays are current")

    ## Verify the scanner caught the real issues
    if report["high_impact"] < 1:
        _out("  -ERROR- Should detect the prevalence contradiction")
        sys.exit(1)

    _out("")
    _out("The key: nightly scan CONNECTED to essay index.")
    _out("Mark only sees findings that affect published work.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea27.1ea527
