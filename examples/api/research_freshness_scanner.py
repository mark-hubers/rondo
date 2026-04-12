# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=research value="Research freshness scoring and stale-source detection"

"""Rondo example: classify scan headlines against an essay index (structured JSON).

What this demonstrates
------------------------
* Passing **structured lists inside the prompt** (JSON dumps of essays).
* Preferring a typed **``impact``** field, with a transparent string fallback only when needed.
* Exit status reflecting **HIGH** impact rows.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/research_freshness_scanner.py
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

SCAN_FINDINGS: list[dict[str, str]] = [
    {"id": "SCAN-001", "title": "Updated prevalence of Usher syndrome: 1 in 6,000", "topic": "prevalence"},
    {"id": "SCAN-002", "title": "RTx-015 Phase 2 enrollment complete", "topic": "gene_therapy"},
    {"id": "SCAN-003", "title": "Novel USH2A splice variant in East Asian populations", "topic": "genetics"},
]

ESSAY_INDEX: list[dict[str, Any]] = [
    {"title": "Usher Syndrome: The Numbers", "claims": ["1 in 10,000 prevalence", "25,000 in the US"]},
    {"title": "Gene Therapy Hope: What Is Real", "claims": ["RTx-015 in Phase 1/2", "3 active trials"]},
    {"title": "Know Your Gene", "claims": ["most common variant is c.2299delG"]},
]


def impact_level(parsed: dict[str, Any]) -> str:
    """Normalize HIGH | MEDIUM | LOW from structured output or prose fallback."""
    raw = parsed.get("impact")
    if isinstance(raw, str) and raw.strip():
        up = raw.strip().upper()
        if up in ("HIGH", "MEDIUM", "LOW"):
            return up
        if "HIGH" in up:
            return "HIGH"
        if "MEDIUM" in up:
            return "MEDIUM"
        if "LOW" in up:
            return "LOW"
    blob = str(parsed.get("result", parsed.get("reason", "")))
    if "HIGH" in blob.upper():
        return "HIGH"
    if "MEDIUM" in blob.upper():
        return "MEDIUM"
    return "LOW"


def scan_impact(
    findings: list[dict[str, str]],
    essays: list[dict[str, Any]],
    *,
    timeout_sec: int,
) -> dict[str, Any]:
    """One model call per finding."""
    impacts: list[dict[str, Any]] = []
    for finding in findings:
        print(f"  {finding['id']}: {finding['title'][:52]}…")
        prompt = (
            "Does this finding impact any listed essay enough to update it?\n"
            f'Return JSON only: {{"impact": "HIGH" or "MEDIUM" or "LOW", "essay": "title or none", "reason": "short"}}\n\n'
            f"Finding: {finding['title']}\nEssays:\n{json.dumps(essays, indent=2)}"
        )
        try:
            env, parsed = run_prompt_json(
                prompt=prompt,
                model="",
                dry_run=False,
                timeout_sec=timeout_sec,
                rules="You classify editorial impact conservatively. JSON only.",
            )
        except RuntimeError as exc:
            print(f"    -ERROR- {exc}", file=sys.stderr)
            continue

        if parsed.get("_non_json"):
            print("    -WARNING- Non-JSON; skipping row.")
            continue

        level = impact_level(parsed)
        reason = str(parsed.get("reason", parsed.get("result", "")))[:160]
        impacts.append(
            {
                "finding_id": finding["id"],
                "impact": level,
                "essay": parsed.get("essay", ""),
                "reason": reason,
                "round_status": env.get("status"),
            }
        )
        print(f"    → {level}: {reason[:56]}…")

    high = [i for i in impacts if i["impact"] == "HIGH"]
    return {
        "scanned": len(findings),
        "rows": len(impacts),
        "high_impact": len(high),
        "needs_attention": len(high) > 0,
        "impacts": impacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Research scan → essay impact (sample)"))
    report = scan_impact(SCAN_FINDINGS, ESSAY_INDEX, timeout_sec=args.timeout)
    print()
    if report["needs_attention"]:
        print(f"-WARNING- {report['high_impact']} HIGH-impact row(s)")
        return 1
    print("-PASS- No HIGH impact in parsed rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
