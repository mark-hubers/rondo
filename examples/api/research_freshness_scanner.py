"""Rondo Real-World: Research Freshness -> Essay Impact Scanner.

REAL WORKFLOW THIS REPLACES:
  Nightly BioMCP scan finds new papers but results are NOT connected
  to essays. Mark manually checks relevance. 661 research messages.

SCRIPTED VERSION:
  Take scan findings + essay list -> ask Claude which essays are
  impacted -> classify impact (HIGH/MEDIUM/LOW) -> alert on HIGH.

HOW TO RUN:
  python examples/api/research_freshness_scanner.py
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


## --- Sample Data (real finding + essay shapes) --------------------

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

IMPACT_PROMPT = """A new research finding just came out. Does it impact any of these published essays?

Finding: {finding_title}
Topic: {finding_topic}

Published essays and their claims:
{essays_json}

Return JSON:
{{"impact": "HIGH"|"MEDIUM"|"LOW",
  "essay": "which essay is affected",
  "reason": "why this matters",
  "action": "UPDATE_ESSAY"|"QUEUE_UPDATE"|"LOG_ONLY"}}

HIGH = contradicts a published claim (urgent)
MEDIUM = adds new supporting data
LOW = tangentially related"""


## --- The Scanner -------------------------------------------------


def scan_impact(findings: list[dict], essays: list[dict]) -> dict:
    """Match each finding against essay index via real AI."""
    impacts: list[dict] = []

    for finding in findings:
        _out(f"  Checking: {finding['title'][:50]}...")
        prompt = IMPACT_PROMPT.format(
            finding_title=finding["title"],
            finding_topic=finding["topic"],
            essays_json=json.dumps(essays, indent=2),
        )
        result = _dispatch(prompt)

        if result is None:
            _out("    SKIP: dispatch failed")
            continue

        ## Parse impact level from AI response
        result_text = result.get("result", "")
        impact_level = "LOW"
        if "HIGH" in result_text.upper():
            impact_level = "HIGH"
        elif "MEDIUM" in result_text.upper():
            impact_level = "MEDIUM"

        impacts.append(
            {
                "finding_id": finding["id"],
                "finding_title": finding["title"][:50],
                "impact": impact_level,
                "reason": result_text[:100],
            }
        )
        _out(f"    {impact_level}: {result_text[:60]}")

    high = [i for i in impacts if i["impact"] == "HIGH"]
    return {
        "findings_scanned": len(findings),
        "high_impact": len(high),
        "needs_attention": len(high) > 0,
        "impacts": impacts,
    }


def main() -> None:
    """Demonstrate research freshness scanner."""
    _out("=== Research Freshness -> Essay Impact Scanner ===")
    _out("")

    _out("(REAL dispatch -- Claude classifies each finding's impact)")
    _out("")
    report = scan_impact(SCAN_FINDINGS, ESSAY_INDEX)
    _out("")

    if report["needs_attention"]:
        _out("-WARNING- HIGH-impact findings need essay updates")
    else:
        _out("-PASS- No high-impact findings")

    _out(f"Scanned: {report['findings_scanned']}, HIGH: {report['high_impact']}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea27.1ea527
