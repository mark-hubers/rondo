"""Rondo Real-World: Research Freshness -> Essay Impact Scanner.

REAL WORKFLOW THIS REPLACES:
  Nightly scan finds new papers but results not connected to essays.

SCRIPTED VERSION:
  Take scan findings + essay list -> ask Claude which essays are
  impacted -> classify impact (HIGH/MEDIUM/LOW) -> alert on HIGH.

HOW TO RUN:
  python examples/api/research_freshness_scanner.py
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
        return {"result": output, "passed": True, "issues": [], "confidence": 0.5}


SCAN_FINDINGS = [
    {"id": "SCAN-001", "title": "Updated prevalence of Usher syndrome: 1 in 6,000", "topic": "prevalence"},
    {"id": "SCAN-002", "title": "RTx-015 Phase 2 enrollment complete", "topic": "gene_therapy"},
    {"id": "SCAN-003", "title": "Novel USH2A splice variant in East Asian populations", "topic": "genetics"},
]

ESSAY_INDEX = [
    {"title": "Usher Syndrome: The Numbers", "claims": ["1 in 10,000 prevalence", "25,000 in the US"]},
    {"title": "Gene Therapy Hope: What Is Real", "claims": ["RTx-015 in Phase 1/2", "3 active trials"]},
    {"title": "Know Your Gene", "claims": ["most common variant is c.2299delG"]},
]


def scan_impact(findings: list[dict], essays: list[dict]) -> dict:
    """Match each finding against essay index via real AI."""
    impacts: list[dict] = []
    for finding in findings:
        _out(f"  Checking: {finding['title'][:50]}...")
        result = dispatch(
            f"Does this finding impact any published essay? Return JSON:\n"
            f'{{"impact": "HIGH/MEDIUM/LOW", "essay": "which one", "reason": "why"}}\n\n'
            f"Finding: {finding['title']}\nEssays: {json.dumps(essays)}",
            rules="You classify research impact on published essays. Return JSON only.",
        )
        if result is None:
            _out("    SKIP")
            continue
        result_text = str(result.get("result", result.get("impact", "")))
        level = "LOW"
        if "HIGH" in result_text.upper():
            level = "HIGH"
        elif "MEDIUM" in result_text.upper():
            level = "MEDIUM"
        impacts.append({"finding_id": finding["id"], "impact": level, "reason": result_text[:80]})
        _out(f"    {level}: {result_text[:60]}")

    high = [i for i in impacts if i["impact"] == "HIGH"]
    return {"scanned": len(findings), "high_impact": len(high), "needs_attention": len(high) > 0, "impacts": impacts}


def main() -> None:
    """Run research freshness scanner."""
    _out("=== Research Freshness -> Essay Impact ===")
    _out("")
    report = scan_impact(SCAN_FINDINGS, ESSAY_INDEX)
    _out("")
    if report["needs_attention"]:
        _out(f"-WARNING- {report['high_impact']} HIGH-impact finding(s)")
    else:
        _out("-PASS- No high-impact findings")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea27.1ea527
