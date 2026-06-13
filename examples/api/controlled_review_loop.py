# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=mixed provider=anthropic,gemini,grok category=flagship value="Live controlled loop: rondo drives Claude step-by-step (verifying itself) then convenes OTHER AI bodies as a review gate before accepting"

"""CONTROLLED REVIEW LOOP — drive Claude live, then let OTHER AI bodies vote.

What this demonstrates (the two things that matter right now)
------------------------------------------------------------
1. CONTROL CLAUDE LIVE: rondo drives a real Claude Code subprocess to do the
   work, then VERIFIES it itself (runs the test, checks the file) — the model's
   word is never the gate.
2. BE NICE WITH OTHER AI BODIES: before accepting the step, rondo convenes a
   PANEL of DIFFERENT vendors (Gemini + Grok) to review the actual output. The
   step is accepted ONLY if rondo's mechanical check passes AND the panel agrees.

This is the loop a CLAUDE.md can't be: one driver (rondo), one set of hands
(Claude), and an independent jury (other vendors) — every verdict observed, not
asserted. Run it from a terminal OR from inside a live Claude Code session.

    accept = rondo_verifies(work) AND panel_of_other_AIs_agree(work)

Run it::

    cd rondo && uv run python examples/api/controlled_review_loop.py        # live
    cd rondo && uv run python examples/api/controlled_review_loop.py --dry  # choreography only
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import extract_json_object, run_verification

BUILDER_MODEL = "sonnet"  # -- Claude subprocess: the hands (can edit files)
PANEL = ["gemini:high", "grok:grok-4.3"]  # -- other AI bodies: the independent jury


def claude_builds(task: str, workspace: Path) -> dict:
    """Drive a real Claude Code subprocess to do the work; return its claim + content."""
    print(f"\n>> CLAUDE ({BUILDER_MODEL}) builds: {task[:70]}...")
    envelope = json.loads(
        rondo_run_file(
            prompt=f"In {workspace}: {task}",
            model=BUILDER_MODEL,
            dry_run=False,
            allowed_tools="Read,Write,Bash",
            max_turns=10,
            add_dir=str(workspace),
            timeout_sec=400,
        )
    )
    task_rec = (envelope.get("tasks") or [{}])[0]
    return {"claimed_done": task_rec.get("status") == "done"}


def panel_reviews(code: str, question: str) -> list[dict]:
    """Convene the other AI bodies — each independently reviews the REAL output.

    Each returns {provider, reached, correct}. An unreachable vendor is
    INCONCLUSIVE (reached=False), never a silent vote — honesty over a full panel.
    """
    verdicts: list[dict] = []
    for model in PANEL:
        print(f">> PANEL ({model}) reviews...")
        # -- Verdict channel = the smart-return `passed` field, which rondo normalizes
        # -- across ALL vendors. (Asking for a custom `{correct}` key is unreliable:
        # -- some vendors wrap the answer in {passed, result} and the key goes missing —
        # -- a real false-negative caught while building this. `passed` is the robust seam.)
        prompt = (
            f"You are an independent reviewer from a DIFFERENT team. Review this code:\n\n"
            f"```python\n{code}\n```\n\n{question}\n"
            "Judge BEHAVIORAL correctness only (ignore style). Set passed=true ONLY if it is "
            "correct; else passed=false with the reason. Respond with ONLY JSON: "
            '{"passed": true|false, "result": "one-line reason"}'
        )
        raw = json.loads(rondo_run_file(prompt=prompt, model=model, dry_run=False))
        rec = (raw.get("tasks") or [{}])[0]
        verdict = extract_json_object(str(rec.get("raw_output", "")))
        # -- HONEST: unreachable OR no parseable passed -> INCONCLUSIVE, never a silent "no" vote
        if rec.get("status") != "done" or verdict is None or "passed" not in verdict:
            print(f"   {model}: inconclusive ({rec.get('error_code') or 'no parseable verdict'})")
            verdicts.append({"provider": model, "reached": False, "correct": False})
            continue
        ok = bool(verdict.get("passed"))
        print(f"   {model}: passed={ok} — {str(verdict.get('result', ''))[:70]}")
        verdicts.append({"provider": model, "reached": True, "correct": ok})
    return verdicts


def run_loop(workspace: Path) -> int:
    """One controlled step: Claude builds -> rondo verifies -> other AI bodies vote."""
    target = workspace / "stats.py"
    test_file = workspace / "test_stats.py"
    pytest_cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider"]

    # -- 1. CONTROL: drive Claude to do the work
    claude_builds(
        "create stats.py with `def mean(nums: list[float]) -> float` (the arithmetic mean; "
        "raise ValueError on empty input). Also create test_stats.py (pytest) covering a normal "
        "case and the empty-input error. Run pytest to confirm green.",
        workspace,
    )

    # -- 2. rondo's OWN check: files exist AND the real pytest passes (not Claude's say-so)
    mech = run_verification(
        {"files": [str(target), str(test_file)], "cmd": pytest_cmd, "expect_exit": 0}, cwd=str(workspace)
    )
    print(f"\n   rondo mechanical: files+pytest ok={mech['ok']} (exit={mech.get('exit_code')})")
    if not mech["ok"]:
        print("-FAIL- rondo's own check failed — not even asking the panel")
        return 1

    # -- 3. OTHER AI BODIES: independent jury on the actual code
    code = target.read_text(encoding="utf-8")
    verdicts = panel_reviews(code, "Does mean() compute the arithmetic mean and reject empty input?")

    # -- 4. THE GATE: accept only if rondo verified AND every reached vendor agrees
    reached = [v for v in verdicts if v["reached"]]
    agree = [v for v in reached if v["correct"]]
    accepted = mech["ok"] and len(reached) >= 1 and len(agree) == len(reached)

    print("\n== CONTROLLED REVIEW RESULT ==")
    print(f"   rondo mechanical: {mech['ok']}")
    print(f"   panel reached: {len(reached)}/{len(PANEL)}; agreed: {len(agree)}/{len(reached)}")
    print(f"   ACCEPT = rondo_verified AND panel_unanimous -> {accepted}")
    if accepted:
        print("-PASS- Claude was driven, rondo verified it, and other AI bodies concurred")
        return 0
    print("-WARN- not accepted — a real disagreement or unreachable panel (reported honestly)")
    return 1


def main() -> int:
    """Live controlled-review loop, or --dry to show the choreography."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry", action="store_true", help="print the choreography only — no dispatches")
    args = parser.parse_args()

    if args.dry:
        print("CHOREOGRAPHY (no dispatches):")
        print(f"  1 CONTROL: drive Claude ({BUILDER_MODEL}) to build stats.py + tests")
        print("  2 rondo VERIFIES itself: files exist AND real pytest green")
        print(f"  3 OTHER AI BODIES review: {', '.join(PANEL)}")
        print("  4 GATE: accept iff rondo_verified AND every reached vendor agrees")
        return 0

    workspace = Path(tempfile.mkdtemp(prefix="rondo-controlled-"))
    print(f"== CONTROLLED REVIEW LOOP (workspace {workspace}) ==")
    return run_loop(workspace)


if __name__ == "__main__":
    raise SystemExit(main())


# -- sig: mgh-6201.cd.bd955f.24dd.97bfd6
