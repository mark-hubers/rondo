# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=pipeline provider=multi category=flagship value="10-step code-refinement prompt program that proves its own output"

"""Rondo flagship: the code-refinement PROMPT PROGRAM (Rondo-REQ-114).

What this demonstrates
----------------------
PROMPT CODING — rondo's thesis. A 10-step declarative pipeline
(``examples/pipelines/code-refine.yaml``) takes an intentionally bare Python
file and runs a multi-provider assembly line over it:

  analyze -> add comments -> add error trapping -> HOSTILE REVIEW (different
  provider) -> apply fixes -> write tests -> critique tests (third provider,
  "green is not real") -> strengthen tests -> final polish -> summary

Then this runner does what no demo slide can fake: it saves the generated
code and the generated tests, and EXECUTES the tests against the code with
pytest. The pipeline proves its own output, and the audit trail has every
step's cost.

Run::

    cd rondo && uv run python examples/api/code_refine_pipeline.py --plan   # free preview
    cd rondo && uv run python examples/api/code_refine_pipeline.py          # live (~$0.10-0.40)

Honesty: the live run spends real money (budget-capped at $1.50 by the
pipeline) and the generated tests may legitimately FAIL — that result is
reported as-is; a red generated suite is information, not embarrassment.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404 -- runs pytest on the generated tests, fixed argv
import sys
from pathlib import Path

from rondo.pipeline import load_pipeline, run_pipeline, unwrap_smart_return

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_PIPELINE = _REPO / "examples" / "pipelines" / "code-refine.yaml"
_SUBJECT = _REPO / "examples" / "pipelines" / "subject" / "csv_report.py"


def _strip_fence(text: str) -> str:
    """Return the last ```python fenced block's body, or the text as-is."""
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    return blocks[-1].strip() + "\n" if blocks else text.strip() + "\n"


def _subject_code() -> str:
    """The bare subject file, minus the intent header (the model sees clean input)."""
    lines = _SUBJECT.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in lines if not ln.startswith("#")]
    return "\n".join(body).strip() + "\n"


def _show_plan(spec, inputs: dict[str, str]) -> int:
    """Plan mode: every step, model, and estimate — zero dispatches, zero cost."""
    plan = run_pipeline(spec, inputs=inputs, plan=True)
    print(f"PLAN — {plan['name']}: {len(plan['steps'])} steps")
    for step in plan["steps"]:
        print(f"  {step['name']:<22} {step['model']:<18} est ${step['estimated_cost_usd']:.4f}")
    print(f"  total estimate ${plan['total_estimated_cost_usd']:.4f} vs budget ${plan['budget_usd']:.2f}")
    print(f"  within budget estimate: {plan['within_budget_estimate']}")
    return 0


def _run_generated_tests(out_dir: Path) -> int:
    """Execute the pipeline's OWN test output against its OWN code output."""
    print("\n== Executing the generated tests against the generated code ==")
    proc = subprocess.run(  # nosec B603 -- fixed argv, local files
        [sys.executable, "-m", "pytest", str(out_dir / "test_csv_report_refined.py"), "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        check=False,
        cwd=out_dir,
        timeout=120,
    )
    print(proc.stdout.strip()[-1500:])
    if proc.returncode == 0:
        print("-PASS- the pipeline's generated tests PASS against its generated code")
    else:
        print("-WARNING- generated tests did not fully pass (reported honestly — inspect the artifacts)")
    return proc.returncode


def main() -> int:
    """Run the flagship pipeline: plan (free) or live apply + self-test."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", action="store_true", help="show the plan (no dispatches, no cost)")
    parser.add_argument("--out", default="", metavar="DIR", help="artifact dir (default: ./pipeline-out)")
    args = parser.parse_args()

    spec = load_pipeline(_PIPELINE)
    inputs = {"code": _subject_code()}

    if args.plan:
        return _show_plan(spec, inputs)

    print(f"== Running prompt program '{spec.name}' ({len(spec.steps)} steps, budget ${spec.budget_usd:.2f}) ==")
    envelope = run_pipeline(spec, inputs=inputs)

    print(f"\nstatus: {envelope['status']}   total cost: ${envelope['total_cost_usd']:.4f}")
    for record in envelope["steps"]:
        marker = "-PASS-" if record["status"] == "done" else "-ERROR-"
        print(f"  {marker} {record['name']:<22} ${record['cost_usd']:.4f}  ({len(record['raw_output'])} chars)")
        if record.get("error"):
            print(f"          {record['error'][:120]}")

    if envelope["status"] != "done":
        print(f"-WARNING- pipeline ended '{envelope['status']}': {envelope.get('error', 'see step records')}")
        return 1

    by_name = {r["name"]: r for r in envelope["steps"]}
    out_dir = Path(args.out) if args.out else Path.cwd() / "pipeline-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "csv_report_refined.py").write_text(
        _strip_fence(unwrap_smart_return(by_name["final_polish"]["raw_output"])), encoding="utf-8"
    )
    (out_dir / "test_csv_report_refined.py").write_text(
        _strip_fence(unwrap_smart_return(by_name["strengthen_tests"]["raw_output"])), encoding="utf-8"
    )
    (out_dir / "pipeline-envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    summary = by_name["summary"].get("parsed") or {}
    print("\n== Summary (step 10) ==")
    for change in summary.get("changes", [])[:8]:
        print(f"  * {change}")
    print(f"\nartifacts: {out_dir}/")

    return _run_generated_tests(out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
