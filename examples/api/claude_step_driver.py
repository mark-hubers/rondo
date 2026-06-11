# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=flagship value="rondo drives Claude Code one verified step at a time — the prompt-coding thesis"

"""Rondo flagship: DRIVING CLAUDE CODE one verified step at a time.

What this demonstrates
----------------------
The actual thesis. CLAUDE.md / memory-file instructions are suggestions a
model drifts from after a few steps. This pipeline sits OUTSIDE the model:
10 steps, each a separate Claude Code (claude CLI) invocation that must do
ONE thing, VERIFY it by running it, and answer honestly — passed=true or
passed=false. The engine refuses to advance past a failed step; retries are
the fix loop. No drift is possible because the sequencing isn't in the
model's context — it's in rondo.

What gets built: a working todo-list CLI + test suite, from an EMPTY
directory, by Claude under rondo's control. Then this runner independently
re-runs the built test suite — trust nothing, verify everything.

Run::

    cd rondo && uv run python examples/api/claude_step_driver.py --plan   # free preview
    cd rondo && uv run python examples/api/claude_step_driver.py          # live ($0 on max auth)

Honesty: each step is a real `claude -p` subprocess with tool grants scoped
to the workspace; every step is audited (INTENT/OUTCOME); a red final
verification is reported as-is.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 -- re-runs the BUILT test suite, fixed argv
import sys
import tempfile
from pathlib import Path

from rondo.pipeline import load_pipeline, run_pipeline

_REPO = Path(__file__).resolve().parents[2]
_PIPELINE = _REPO / "examples" / "pipelines" / "claude-builder.yaml"


def _independent_verify(workspace: Path) -> int:
    """The runner re-runs the BUILT suite itself — never trust the report alone."""
    print("\n== Independent re-verification (runner runs the built tests itself) ==")
    proc = subprocess.run(  # nosec B603 -- fixed argv, local files
        [sys.executable, "-m", "pytest", str(workspace / "test_todo.py"), "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        check=False,
        cwd=workspace,
        timeout=120,
    )
    print(proc.stdout.strip()[-800:])
    if proc.returncode == 0:
        print("-PASS- independently verified: Claude's build passes Claude's tests")
    else:
        print("-WARNING- independent verification FAILED (reported honestly)")
    return proc.returncode


def main() -> int:
    """Plan (free) or live: drive Claude through the 10-step build."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", action="store_true", help="show the plan — no dispatches, no cost")
    parser.add_argument("--workspace", default="", metavar="DIR", help="build dir (default: a fresh temp dir)")
    args = parser.parse_args()

    spec = load_pipeline(_PIPELINE)
    workspace = (
        Path(args.workspace).resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="rondo-claude-build-"))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    inputs = {"workspace": str(workspace)}

    if args.plan:
        plan = run_pipeline(spec, inputs=inputs, plan=True)
        print(f"PLAN — {plan['name']}: {len(plan['steps'])} steps, budget ${plan['budget_usd']:.2f}")
        for step in plan["steps"]:
            print(f"  {step['name']:<22} {step['model']}")
        print(f"workspace would be: {workspace}")
        return 0

    print(f"== rondo drives Claude Code: '{spec.name}' ({len(spec.steps)} steps) ==")
    print(f"workspace: {workspace}\n")
    envelope = run_pipeline(spec, inputs=inputs)

    print(f"status: {envelope['status']}   total cost: ${envelope['total_cost_usd']:.4f}")
    for record in envelope["steps"]:
        marker = "-PASS-" if record["status"] == "done" else "-ERROR-"
        print(f"  {marker} {record['name']:<22} ${record['cost_usd']:.4f}")
        if record.get("error"):
            print(f"          {record['error'][:140]}")

    (workspace / "pipeline-envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    print(f"\nenvelope: {workspace}/pipeline-envelope.json")

    if envelope["status"] != "done":
        print(f"-WARNING- pipeline ended '{envelope['status']}' — the gate held; inspect the failed step above")
        return 1

    report = next((r.get("parsed") for r in envelope["steps"] if r["name"] == "report"), None) or {}
    result = report.get("result") if isinstance(report.get("result"), dict) else report
    print("\n== Claude's build report ==")
    print(json.dumps(result, indent=2)[:600])

    return _independent_verify(workspace)


if __name__ == "__main__":
    raise SystemExit(main())
