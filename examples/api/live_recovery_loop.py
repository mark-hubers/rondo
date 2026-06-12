# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=flagship value="Live recovery loop: a real AI, a real failure, rondo catches it and the if/else recovers — end to end"

"""LIVE RECOVERY LOOP — a real AI fails for real, rondo catches it, the loop recovers.

What this demonstrates
----------------------
The lie-trap tests prove the traps fire deterministically. This proves the
SAME machinery works against a LIVE model, with a GENUINE failure and a
GENUINE recovery — no scripting, no fixture.

The honest trick to make recovery reliably observable on a nondeterministic
AI: step 1 asks for a STUB on purpose (c_to_f returns 0.0). The real pytest
in step 2 therefore genuinely FAILS. rondo runs that pytest ITSELF (verify
cmd), sees the red, and the Python if/else branches to a fix step — which asks
the live AI to implement the function for real. rondo re-runs pytest, sees
green, and the loop completes. Finally THIS script runs the tests one more
time itself: trust nothing.

    1 scaffold stub + test   -> rondo verifies the files exist
    2 run tests              -> rondo runs pytest itself: RED (the stub is wrong)
        IF red (it will be): 3 fix the code -> rondo re-runs pytest: GREEN
    4 independent re-verify  -> this script runs pytest, confirms exit 0

Every step is a real Max-plan subprocess (auth=max, $0 API), tool-scoped to a
throwaway workspace, with a hard Python-side budget ceiling.

Run it::

    cd rondo && uv run python examples/api/live_recovery_loop.py        # live
    cd rondo && uv run python examples/api/live_recovery_loop.py --dry  # choreography only
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 -- re-runs the BUILT test suite, fixed argv
import sys
import tempfile
from pathlib import Path

from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import run_verification

BUDGET_USD = 2.00  # -- hard Python-side ceiling
_spent = 0.0


class RecoveryFailedError(RuntimeError):
    """The loop could not reach a verified-green state within its branches."""


def dispatch(name: str, prompt: str, *, tools: str, workspace: Path, turns: int = 12) -> str:
    """One live Claude Code subprocess; returns its raw output. Tracks spend."""
    global _spent
    if _spent >= BUDGET_USD:
        raise RecoveryFailedError(f"budget ${BUDGET_USD:.2f} reached before step '{name}'")
    print(f"\n>> STEP {name}")
    envelope = json.loads(
        rondo_run_file(
            prompt=prompt,
            model="sonnet",
            dry_run=False,
            allowed_tools=tools,
            max_turns=turns,
            add_dir=str(workspace),
            timeout_sec=600,
        )
    )
    task = (envelope.get("tasks") or [{}])[0]
    cost = float(task.get("cost_usd") or 0.0)
    _spent += cost
    print(f"   dispatched (${cost:.4f}, total ${_spent:.4f}/{BUDGET_USD:.2f})")
    return str(task.get("raw_output", ""))


def rondo_says(files: list[str] | None = None, cmd: list[str] | None = None, workspace: Path | None = None) -> dict:
    """Rondo's OWN observation of the world — the verdict the loop branches on."""
    block: dict = {}
    if files:
        block["files"] = files
    if cmd:
        block["cmd"] = cmd
        block["expect_exit"] = 0
    return run_verification(block, cwd=str(workspace) if workspace else "")


def run_loop(workspace: Path) -> int:
    """The choreography — a real failure, caught by rondo, recovered by the if/else."""
    converter = workspace / "converter.py"
    test_file = workspace / "test_converter.py"
    pytest_cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider"]

    # -- STEP 1: ask for a STUB on purpose + a real test (so the failure is genuine)
    dispatch(
        "scaffold_stub",
        f"In {workspace}: create converter.py with `def c_to_f(c): return 0.0` (a STUB — leave it "
        f"returning 0.0, do not implement it). Also create test_converter.py (pytest) asserting "
        f"c_to_f(100) == 212.0 and c_to_f(0) == 32.0. Do not run anything.",
        tools="Read,Write",
        workspace=workspace,
    )
    scaffold = rondo_says(files=[str(converter), str(test_file)], workspace=workspace)
    if not scaffold["ok"]:
        raise RecoveryFailedError(f"scaffold did not produce the files: {scaffold.get('error')}")
    print("   rondo: both files exist ✓")

    # -- STEP 2: rondo runs the REAL pytest itself. The stub WILL fail.
    print("\n>> STEP run_tests (rondo runs pytest itself)")
    tests = rondo_says(cmd=pytest_cmd, workspace=workspace)
    print(f"   rondo: pytest exit_code={tests.get('exit_code')} -> {'GREEN' if tests['ok'] else 'RED'}")

    # -- THE BRANCH: if rondo saw red, recover. (The stub guarantees we exercise this.)
    rounds = 0
    while not tests["ok"] and rounds < 3:
        rounds += 1
        print(f"\n   DECISION: rondo saw RED -> fix-the-code branch (round {rounds}/3)")
        dispatch(
            "fix_code",
            f"In {workspace}: the tests fail because c_to_f is a stub. Implement c_to_f(c) correctly "
            f"(celsius to fahrenheit: c * 9/5 + 32). Do NOT change the tests. Then stop.",
            tools="Read,Edit",
            workspace=workspace,
        )
        tests = rondo_says(cmd=pytest_cmd, workspace=workspace)
        print(f"   rondo: pytest exit_code={tests.get('exit_code')} -> {'GREEN' if tests['ok'] else 'RED'}")

    if not tests["ok"]:
        raise RecoveryFailedError("could not recover to green within 3 fix rounds")
    print("   DECISION: rondo confirms GREEN -> loop complete")

    # -- STEP 4: trust nothing — THIS script runs the tests itself, independently.
    print("\n== Independent re-verification (this script runs pytest) ==")
    proc = subprocess.run(  # nosec B603 -- fixed argv, local files
        pytest_cmd, capture_output=True, text=True, check=False, cwd=workspace, timeout=120
    )
    print(proc.stdout.strip()[-400:])
    print(f"\ntotal plan-quota spent: ${_spent:.4f} (ceiling ${BUDGET_USD:.2f})")
    if proc.returncode == 0:
        print("-PASS- live recovery proven: real AI stubbed, rondo caught it, the loop fixed it")
        return 0
    print("-FAIL- independent re-verification did not pass (reported honestly)")
    return 1


def main() -> int:
    """Live run, or --dry to show the choreography without dispatching."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry", action="store_true", help="print the choreography only — no dispatches")
    parser.add_argument("--workspace", default="", metavar="DIR", help="build dir (default: fresh temp dir)")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="rondo-recovery-"))
    workspace.mkdir(parents=True, exist_ok=True)

    if args.dry:
        print("CHOREOGRAPHY (no dispatches):")
        print("  1 scaffold STUB + test   -> rondo verifies files exist")
        print("  2 run tests              -> rondo runs pytest itself: RED")
        print("    WHILE red (max 3):     3 fix code -> rondo re-runs pytest")
        print("  4 independent re-verify  -> this script runs pytest")
        print(f"\nworkspace would be: {workspace}\nbudget ceiling: ${BUDGET_USD:.2f}")
        return 0

    print(f"== LIVE RECOVERY LOOP (workspace {workspace}) ==")
    try:
        return run_loop(workspace)
    except RecoveryFailedError as exc:
        print(f"-ERROR- {exc}")
        print(f"total plan-quota spent: ${_spent:.4f}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


# -- sig: mgh-6201.cd.bd955f.cbf7.0963ae
