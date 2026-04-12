# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=drift value="Spec-vs-code drift checks with PASS/FAIL verdicts"

"""Rondo example: requirement-by-requirement drift check against sample code.

What this demonstrates
------------------------
* One prompt per requirement with a **strict JSON contract** (``verdict``, ``evidence``, ``confidence``).
* **Verdict parsing** prefers the model's ``verdict`` field; falls back only if absent.
* Surfacing **non-JSON** model output without pretending the check passed.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/spec_code_drift_scanner.py
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

SAMPLE_REQUIREMENTS: list[dict[str, str]] = [
    {"id": "REQ-001", "text": "normalize_response SHALL return passed, confidence, issues, and result fields"},
    {"id": "REQ-002", "text": "Provider scoring SHALL track quality, latency, and cost per call"},
    {"id": "REQ-003", "text": "MCP server SHALL register tools (exact count may drift — judge intent)"},
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
        # NOTE: cost_usd field is missing — intentional for FAIL demos
"""

CHECK_PROMPT = """Does this code satisfy this requirement? Return JSON only (no markdown):
{{"verdict": "PASS" or "FAIL", "evidence": "what you found", "confidence": 0.9}}

Requirement: {req}
Code:
{code}"""


def verdict_from_result(result: dict[str, Any]) -> tuple[str, str]:
    """Return (PASS|FAIL, evidence_snippet)."""
    verdict_raw = result.get("verdict")
    if isinstance(verdict_raw, str) and verdict_raw.strip():
        vnorm = verdict_raw.strip().upper()
        if "FAIL" in vnorm:
            verdict = "FAIL"
        elif "PASS" in vnorm:
            verdict = "PASS"
        else:
            verdict = "FAIL"
    else:
        verdict = "FAIL" if not result.get("passed", True) else "PASS"
        if "FAIL" in str(result.get("result", "")).upper():
            verdict = "FAIL"
    evidence = str(result.get("evidence", result.get("result", "")))[:200]
    return verdict, evidence


def scan_drift(
    requirements: list[dict[str, str]],
    code: str,
    *,
    timeout_sec: int,
) -> dict[str, Any]:
    """Run one Rondo call per requirement."""
    results: list[dict[str, Any]] = []
    for req in requirements:
        print(f"  {req['id']} …")
        prompt = CHECK_PROMPT.format(req=req["text"], code=code)
        try:
            env, parsed = run_prompt_json(
                prompt=prompt,
                model="",
                dry_run=False,
                timeout_sec=timeout_sec,
                rules="You verify code against requirements. JSON only.",
            )
        except RuntimeError as exc:
            print(f"    -ERROR- {exc}", file=sys.stderr)
            continue

        if parsed.get("_non_json"):
            print("    -WARNING- Non-JSON model output; marking UNKNOWN.")
            results.append(
                {
                    "req_id": req["id"],
                    "verdict": "UNKNOWN",
                    "evidence": str(parsed.get("snippet", ""))[:120],
                    "round_status": env.get("status"),
                }
            )
            continue

        if not parsed:
            print("    (Empty first-task output; marking SKIPPED.)")
            results.append(
                {
                    "req_id": req["id"],
                    "verdict": "SKIPPED",
                    "evidence": "",
                    "round_status": env.get("status"),
                }
            )
            continue

        verdict, evidence = verdict_from_result(parsed)
        conf = parsed.get("confidence", "")
        print(f"    {verdict} (confidence={conf!r}) — {evidence[:72]}")
        results.append({"req_id": req["id"], "verdict": verdict, "evidence": evidence})

    return {
        "total": len(results),
        "pass_count": len([r for r in results if r["verdict"] == "PASS"]),
        "fail_count": len([r for r in results if r["verdict"] == "FAIL"]),
        "unknown_count": len([r for r in results if r.get("verdict") == "UNKNOWN"]),
        "skipped_count": len([r for r in results if r.get("verdict") == "SKIPPED"]),
        "has_drift": any(r["verdict"] == "FAIL" for r in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Spec ↔ code drift (sample corpus)"))
    report = scan_drift(SAMPLE_REQUIREMENTS, SAMPLE_CODE, timeout_sec=args.timeout)
    print()
    print(
        f"PASS={report['pass_count']} FAIL={report['fail_count']} "
        f"UNKNOWN={report['unknown_count']} SKIPPED={report['skipped_count']} drift_flag={report['has_drift']}"
    )
    return 1 if report["has_drift"] or report["unknown_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
