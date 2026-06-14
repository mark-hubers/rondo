# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=mixed provider=anthropic,gemini,grok category=flagship value="THE FLAGSHIP — cross-vendor jury: the AI that writes the code does NOT get to certify it; a DIFFERENT vendor does, and disagreements are the signal"

"""THE CROSS-VENDOR JURY — the one thing single-vendor tools structurally can't copy.

Why this is rondo's flagship
----------------------------
Every coding agent runs tests. Anthropic, Cursor, and Copilot will all ship
"verified loops". The one thing they CANNOT ship — because they are single-vendor
— is a jury where the model that WROTE the code does not get to certify it, and a
DIFFERENT vendor independently judges it. rondo orchestrates that.

    accept = rondo_verifies(work) AND a DIFFERENT vendor agrees
    the DISAGREEMENT is the product — it's the bug nobody else would have caught.

Two scenarios, run live:

  1. LIVE CONTROL + CONCUR: rondo drives Claude to build mean(); rondo runs the
     real pytest ITSELF (green); the Gemini + Grok jury concur -> ACCEPTED.

  2. THE PROOF (why mechanical verify alone is NOT enough): a function that PASSES
     its (shallow) test but is latently WRONG. A single-vendor "tests pass" loop
     ships it. rondo's mechanical check is ALSO green — but the cross-vendor jury
     reads the LOGIC and catches the bug. THAT is the value a competitor with one
     model cannot reproduce.

The verdict channel is the smart-return `passed` field, which rondo normalizes
across every vendor (a custom key goes missing on some vendors — see git log).

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

from rondo.jury import jury_review
from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import run_verification

BUILDER_MODEL = "sonnet"  # -- Claude subprocess: the hands (writes the code)
JURY = ["gemini:high", "grok:grok-4.3"]  # -- DIFFERENT vendors: the independent jury


def claude_builds(task: str, workspace: Path) -> bool:
    """Drive a real Claude Code subprocess to do the work; return whether it claimed done."""
    print(f"\n>> CLAUDE ({BUILDER_MODEL}) builds: {task[:66]}...")
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
    return (envelope.get("tasks") or [{}])[0].get("status") == "done"


def convene_jury(code: str, question: str) -> dict:
    """Convene the DIFFERENT-vendor jury via the SHIPPED feature (rondo.jury.jury_review).

    This is the dogfood: the example calls the same `jury_review()` the MCP tool
    `rondo_jury` exposes — no hand-wired copy to drift. Returns the full result
    dict: {accepted, reached, agree, verdicts, disagreement}.
    """
    print(f">> JURY ({', '.join(JURY)}) reviews the logic...")
    result = jury_review(code, question, jurors=JURY)
    for v in result["verdicts"]:
        mark = "CONCUR" if v["passed"] else ("INCONCLUSIVE" if not v["reached"] else "OBJECT")
        print(f"   {v['model']}: {mark} — {v['why'][:90]}")
    return result


def report_round(label: str, mech_ok: bool, jury: dict) -> bool:
    """Report a round: mechanical result + the jury_review verdict + the DISAGREEMENT.

    accept = rondo's own mechanical check GREEN *and* the cross-vendor jury accepted.
    The two halves compose: mechanical verify (REQ-115) AND a DIFFERENT vendor agrees.
    """
    objections = jury["disagreement"]
    accepted = mech_ok and jury["accepted"]
    print(f"\n   == {label} ==")
    print(f"   rondo mechanical check (tests/files): {'GREEN' if mech_ok else 'RED'}")
    print(f"   jury: {jury['reached']}/{len(JURY)} reached, {len(objections)} objection(s)")
    if objections:
        # -- the DISAGREEMENT is the product: name who objected and why
        for o in objections:
            print(f"   >>> {o['model']} OBJECTED: {o['why'][:90]}")
    print(f"   ACCEPT = mechanical GREEN AND cross-vendor jury accepted -> {accepted}")
    return accepted


# -- an empty jury result for rounds that never reach the jury (mechanical RED first)
_NO_JURY: dict = {"accepted": False, "reached": 0, "agree": 0, "verdicts": [], "disagreement": []}


def scenario_live_concur(workspace: Path) -> bool:
    """Scenario 1: Claude builds correct code, rondo verifies, the jury concurs."""
    print("\n========== SCENARIO 1: live control + jury concur ==========")
    target, test_file = workspace / "stats.py", workspace / "test_stats.py"
    pytest_cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider"]
    claude_builds(
        "create stats.py with `def mean(nums: list[float]) -> float` (arithmetic mean; raise "
        "ValueError on empty input) and test_stats.py covering a normal case + the empty error. "
        "Run pytest to confirm green.",
        workspace,
    )
    mech = run_verification(
        {"files": [str(target), str(test_file)], "cmd": pytest_cmd, "expect_exit": 0}, cwd=str(workspace)
    )
    if not mech["ok"]:
        print("   (Claude's build did not pass rondo's own check — honest miss this run)")
        return report_round("SCENARIO 1", False, _NO_JURY)
    jury = convene_jury(
        target.read_text(encoding="utf-8"),
        "Given nums is a list[float], does mean() correctly average the list and raise ValueError on empty input?",
    )
    return report_round("SCENARIO 1: should ACCEPT", mech["ok"], jury)


def scenario_proof(workspace: Path) -> bool:
    """Scenario 2 (THE PROOF): tests pass, but the cross-vendor jury catches a latent bug.

    A single-vendor 'tests pass' loop ships this. rondo's mechanical check is ALSO
    green (the shallow test passes). Only the DIFFERENT-vendor jury, reading the
    logic, catches that days_in_month is hard-coded wrong.
    """
    print("\n========== SCENARIO 2: THE PROOF — jury beats green tests ==========")
    target, test_file = workspace / "cal.py", workspace / "test_cal.py"
    # -- a latent bug: passes its shallow test (only checks April) but is wrong for every other month
    target.write_text("def days_in_month(m: int) -> int:\n    return 30  # latent bug: not 30 for all months\n")
    test_file.write_text("from cal import days_in_month\n\n\ndef test_april():\n    assert days_in_month(4) == 30\n")
    pytest_cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider"]
    mech = run_verification(
        {"files": [str(target), str(test_file)], "cmd": pytest_cmd, "expect_exit": 0}, cwd=str(workspace)
    )
    print(f"   shallow test result: {'GREEN (a single-vendor loop would SHIP this)' if mech['ok'] else 'RED'}")
    jury = convene_jury(
        target.read_text(encoding="utf-8"),
        "Does days_in_month return the correct days for ALL months 1-12 (Feb=28, some 30, some 31)?",
    )
    return report_round("SCENARIO 2: should REJECT (jury catches the latent bug)", mech["ok"], jury)


def run_demo(workspace: Path) -> int:
    """The flagship: scenario 1 (concur->accept) then scenario 2 (proof->jury rejects)."""
    print(f"== THE CROSS-VENDOR JURY (workspace {workspace}) ==")
    s1_accepted = scenario_live_concur(workspace)
    s2_accepted = scenario_proof(workspace)
    print("\n========== RESULT ==========")
    # -- the flagship is correct when S1 is ACCEPTED and S2 is REJECTED-by-the-jury
    proof_held = s1_accepted and not s2_accepted
    print(f"  Scenario 1 (correct code)  -> {'ACCEPTED' if s1_accepted else 'not accepted'}")
    print(f"  Scenario 2 (latent bug)    -> {'REJECTED by the jury' if not s2_accepted else 'WRONGLY ACCEPTED'}")
    if proof_held:
        print("-PASS- the cross-vendor jury caught a bug that GREEN TESTS + a single-vendor loop would ship")
        return 0
    print("-WARN- the demo did not land as designed this run (reported honestly)")
    return 1


def main() -> int:
    """Live flagship, or --dry to show the choreography."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry", action="store_true", help="print the choreography only — no dispatches")
    args = parser.parse_args()
    if args.dry:
        print("CHOREOGRAPHY (no dispatches):")
        print(f"  builder = {BUILDER_MODEL} (writes the code)")
        print(f"  jury    = {', '.join(JURY)} (DIFFERENT vendors, judge the logic)")
        print("  S1 correct code  -> mechanical GREEN + jury CONCUR -> ACCEPT")
        print("  S2 latent bug    -> tests GREEN but jury OBJECTS  -> REJECT (the proof)")
        print("  the moat: a single-vendor tool can't have a DIFFERENT vendor judge its own model")
        return 0
    workspace = Path(tempfile.mkdtemp(prefix="rondo-jury-"))
    return run_demo(workspace)


if __name__ == "__main__":
    raise SystemExit(main())


# -- sig: mgh-6201.cd.bd955f.24dd.766a32
