# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=flagship value="if/else prompt coding: Python branching drives Claude Code with 100% control"

"""THE CONDUCTOR — if/else prompt coding, run from inside a live Claude Code session.

What this demonstrates
----------------------
Prompt coding in its purest form: a PYTHON program is the brain, Claude Code
is the hands. ~14 steps with REAL branching — if/else, a fix-retry while
loop, a skip branch — where every decision is made by THIS script based on
a verified answer, never by the model. CLAUDE.md says "please follow these
steps"; this script MAKES the steps happen, in order, with proof, every time.

Control flow you can read like code (because it IS code):

    scaffold -> independent smoke-verify
        IF verify fails:  fix -> re-verify (loop, max 2)
    add feature -> verify
    write tests -> run tests
        WHILE tests fail (max 3): fix the CODE (never the tests) -> re-run
    hostile self-review
        IF findings:      apply fixes -> re-run tests
        ELSE:             skip (and say so)
    IF test count < 8:    add more tests
    docstrings -> final full gate -> JSON report
    ...then THIS script re-runs the built tests itself. Trust nothing.

Every Claude step: a separate Max-plan subprocess (auth=max, $0 API cost),
tool-scoped to the workspace, audited INTENT/OUTCOME, budget-tracked here
with a hard Python-side ceiling.

Run it (from a terminal, or from INSIDE Claude Code via a Bash call)::

    cd rondo && uv run python examples/api/conductor_if_else.py          # live
    cd rondo && uv run python examples/api/conductor_if_else.py --dry    # show the choreography, no dispatches
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 -- re-runs the BUILT test suite, fixed argv
import sys
import tempfile
from pathlib import Path

from rondo.mcp_dispatch import rondo_run_file
from rondo.pipeline import unwrap_smart_return

BUDGET_USD = 4.00  # -- hard Python-side ceiling (plan-quota accounting)
_spent = 0.0


class StepFailedError(RuntimeError):
    """A step could not be verified after its branches were exhausted."""


def step(name: str, prompt: str, *, tools: str = "Read,Edit,Bash", turns: int = 14, timeout: int = 600) -> dict:
    """ONE Claude Code subprocess: do the work, verify it, answer honestly.

    Returns {"passed": bool, "payload": dict|None, "text": str, "cost": float}.
    The CALLER branches on `passed` — that's the whole point.
    """
    global _spent
    if _spent >= BUDGET_USD:
        raise StepFailedError(f"budget ceiling ${BUDGET_USD:.2f} reached before step '{name}' — refusing to dispatch")
    print(f"\n>> STEP {name}")
    envelope = json.loads(
        rondo_run_file(
            prompt=prompt,
            model="sonnet",
            dry_run=False,
            allowed_tools=tools,
            max_turns=turns,
            add_dir=str(WORKSPACE),
            timeout_sec=timeout,
        )
    )
    task = (envelope.get("tasks") or [{}])[0]
    cost = float(task.get("cost_usd") or 0.0)
    _spent += cost
    raw = task.get("raw_output", "")
    parsed = None
    try:
        parsed = json.loads(raw) if raw.strip().startswith("{") else None
    except ValueError:
        parsed = None
    passed = bool(task.get("status") == "done" and (parsed or {}).get("passed") is not False)
    marker = "-PASS-" if passed else "-FAIL-"
    print(f"   {marker} ${cost:.4f} (total ${_spent:.4f}/{BUDGET_USD:.2f})")
    return {"passed": passed, "payload": parsed, "text": unwrap_smart_return(raw), "cost": cost}


def must(result: dict, name: str) -> dict:
    """Hard gate: no branch can rescue this step — stop the program."""
    if not result["passed"]:
        raise StepFailedError(f"step '{name}' failed its verification — conductor stops here (no drift past failures)")
    return result


def field(result: dict, key: str, default):  # noqa: ANN001, ANN201
    """Robust payload field lookup — providers diverge on WHERE keys land.

    Checks the parsed payload top level, then inside payload["result"] when
    it is a dict, then parses payload["result"] when it is a JSON string
    (all three shapes observed LIVE on 2026-06-10).
    """
    payload = result.get("payload") or {}
    if key in payload:
        return payload[key]
    inner = payload.get("result")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except ValueError:
            inner = None
    if isinstance(inner, dict) and key in inner:
        return inner[key]
    return default


def _verify_prompt(what: str) -> str:
    return (
        f"In {WORKSPACE}: {what} Run the actual commands to verify. "
        "Set passed=true ONLY if everything verified; else passed=false with issues."
    )


def run_conductor() -> int:
    """The choreography — read the if/else; that's the demo."""
    # -- 1-2: scaffold, then an INDEPENDENT smoke verify (different session)
    must(
        step(
            "scaffold",
            _verify_prompt(
                "create journal.py: add_entry(text) and list_entries() storing JSON lines in journal.jsonl. "
                "Verify by importing and adding one entry."
            ),
            tools="Read,Write,Bash",
        ),
        "scaffold",
    )

    verify = step(
        "smoke_verify",
        _verify_prompt(
            "WITHOUT changing anything, verify journal.py: import it, add an entry, list entries, "
            "confirm the file format."
        ),
        tools="Read,Bash",
        turns=8,
    )
    if not verify["passed"]:
        # -- IF branch: targeted fix, then ONE re-verify (bounded loop)
        for attempt in (1, 2):
            print(f"   DECISION: smoke verify failed -> fix attempt {attempt}")
            step(
                "fix_scaffold",
                _verify_prompt(f"smoke verification reported: {verify['text'][:400]}. Fix journal.py accordingly."),
            )
            verify = step(
                "re_verify",
                _verify_prompt("re-verify journal.py end to end after the fix."),
                tools="Read,Bash",
                turns=8,
            )
            if verify["passed"]:
                break
        must(verify, "smoke_verify")
    else:
        print("   DECISION: smoke verify clean -> no fix branch needed")

    # -- 3-4: feature + gate
    must(
        step(
            "add_search",
            _verify_prompt(
                "add search_entries(term) to journal.py (case-insensitive substring). "
                "Verify by adding two entries and searching."
            ),
        ),
        "add_search",
    )

    # -- 5-6: tests, then the WHILE fix-loop (fix the CODE, never the tests)
    must(
        step(
            "write_tests",
            _verify_prompt(
                "write test_journal.py (pytest, tmp_path-isolated) covering add/list/search + "
                "empty store + unicode. Run pytest to verify it is green."
            ),
            tools="Read,Write,Bash",
        ),
        "write_tests",
    )

    tests = step(
        "run_tests",
        _verify_prompt("run python3 -m pytest test_journal.py -q and report the counts."),
        tools="Read,Bash",
        turns=8,
    )
    fix_rounds = 0
    while not tests["passed"] and fix_rounds < 3:
        fix_rounds += 1
        print(f"   DECISION: tests RED -> fix-the-code loop round {fix_rounds}/3")
        step(
            "fix_code",
            _verify_prompt(f"tests are failing: {tests['text'][:400]}. Fix journal.py — do NOT weaken the tests."),
        )
        tests = step(
            "rerun_tests", _verify_prompt("re-run python3 -m pytest test_journal.py -q."), tools="Read,Bash", turns=8
        )
    must(tests, "run_tests")

    # -- 7-9: hostile review with a TRUE skip branch
    review = step(
        "hostile_review",
        _verify_prompt(
            'hostile-review journal.py + test_journal.py. Set result to {"findings": [...]} — '
            "empty list if genuinely clean. Do not fix anything."
        ),
        tools="Read,Bash",
        turns=10,
    )
    findings = (review["payload"] or {}).get("result") or {}
    findings = findings.get("findings", []) if isinstance(findings, dict) else []
    if findings:
        print(f"   DECISION: {len(findings)} finding(s) -> apply-fixes branch")
        must(
            step(
                "apply_findings",
                _verify_prompt(
                    f"apply these review findings: {json.dumps(findings)[:500]}. Re-run pytest to verify green."
                ),
            ),
            "apply_findings",
        )
    else:
        print("   DECISION: zero findings -> SKIP the fix branch entirely")

    # -- 10: coverage floor with an if/else top-up
    count_probe = step(
        "count_tests",
        _verify_prompt(
            'count tests: python3 -m pytest test_journal.py --collect-only -q. Set result to {"test_count": N}.'
        ),
        tools="Read,Bash",
        turns=6,
    )
    n_tests = int(field(count_probe, "test_count", 0) or 0)
    if n_tests < 8:
        print(f"   DECISION: only {n_tests} tests -> add-tests branch (floor is 8)")
        must(
            step(
                "more_tests",
                _verify_prompt(
                    "add edge-case tests (long text, duplicate entries, search no-match) until there are "
                    "at least 8 tests total. Run pytest to verify green."
                ),
            ),
            "more_tests",
        )
    else:
        print(f"   DECISION: {n_tests} tests >= 8 -> skip top-up")

    # -- 11-13: polish, final gate, report
    must(
        step(
            "docstrings",
            _verify_prompt(
                "add docstrings to every function in journal.py; change no behavior; re-run pytest to prove it."
            ),
        ),
        "docstrings",
    )
    must(
        step(
            "final_gate",
            _verify_prompt("the FULL final check: pytest green AND a fresh end-to-end add/list/search exercise."),
        ),
        "final_gate",
    )
    report = step(
        "report",
        _verify_prompt('produce the build report: set result to {"files": [...], "test_count": N, "loc": N}.'),
        tools="Read,Bash",
        turns=10,
    )
    if not report["passed"]:
        # -- IF branch: one retry with more headroom (found live: 6 turns was too tight)
        print("   DECISION: report failed -> one retry with more turns")
        report = must(
            step(
                "report_retry",
                _verify_prompt('produce the build report: set result to {"files": [...], "test_count": N, "loc": N}.'),
                tools="Read,Bash",
                turns=14,
            ),
            "report",
        )
    print("\n== Claude's report ==")
    print(json.dumps(field(report, "files", []), indent=2)[:200])
    print(f"   test_count={field(report, 'test_count', '?')}  loc={field(report, 'loc', '?')}")

    # -- 14: trust nothing — THIS script runs the built tests itself
    print("\n== Independent re-verification (the conductor runs the tests itself) ==")
    proc = subprocess.run(  # nosec B603 -- fixed argv, local files
        [sys.executable, "-m", "pytest", str(WORKSPACE / "test_journal.py"), "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        check=False,
        cwd=WORKSPACE,
        timeout=120,
    )
    print(proc.stdout.strip()[-600:])
    print(f"\ntotal plan-quota spent: ${_spent:.4f} (ceiling ${BUDGET_USD:.2f})")
    if proc.returncode == 0:
        print("-PASS- independently verified — the conductor controlled every step")
        return 0
    print("-WARNING- independent verification failed (reported honestly)")
    return 1


def main() -> int:
    """Entry: live run or dry choreography display."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry", action="store_true", help="print the choreography only — no dispatches")
    parser.add_argument("--workspace", default="", metavar="DIR", help="build dir (default: fresh temp dir)")
    args = parser.parse_args()

    global WORKSPACE
    WORKSPACE = Path(args.workspace).resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="rondo-conductor-"))
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    if args.dry:
        print(
            __doc__.split("Control flow you can read like code (because it IS code):")[1].split("Every Claude step:")[0]
        )
        print(f"workspace would be: {WORKSPACE}\nbudget ceiling: ${BUDGET_USD:.2f}")
        return 0

    print(f"== THE CONDUCTOR: Python if/else drives Claude Code (workspace {WORKSPACE}) ==")
    try:
        return run_conductor()
    except StepFailedError as exc:
        print(f"-ERROR- {exc}")
        print(f"total plan-quota spent: ${_spent:.4f}")
        return 1


WORKSPACE = Path(".")  # -- set in main()

if __name__ == "__main__":
    raise SystemExit(main())
