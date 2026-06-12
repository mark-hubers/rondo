# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=flagship value="Lie-trap loop: feed the engine the lies an AI returns, prove each trap fires and the if/else recovers"

"""THE LIE-TRAP LOOP — prove rondo catches an AI lying, one or two steps at a time.

What this demonstrates
----------------------
This is the QA of rondo's whole reason to exist. An AI will say "I wrote the
file" (it didn't), "tests pass" (they don't), "passed=true" (the file is an
empty stub). A CLAUDE.md asks nicely and hopes. Rondo TRAPS each lie with its
own observation, branches with if/else, and takes the next action — recover,
or refuse to advance. Trust nothing; verify everything.

Each scenario below is the unit Mark described: ONE-or-TWO steps, a KNOWN lie
fed in, a trap fires, a branch is taken. The engine (verify, the contract
gate, the fail-closed scanner, the failed-ref guard, the retry loop) runs FOR
REAL. The lying "AI" is an adversarial dispatch on rondo's first-class
`dispatch=` seam — the lying INPUT, never a mock of the thing under test.

The six lies and their traps::

    1  "I created journal.py"   (absent)        -> verify files   -> retry recovers
    2  "all tests pass"         (exit 1)        -> verify cmd     -> caught, refuse
    3  "implemented add()"      (empty stub)    -> contains/min_bytes -> caught
    4  passed=false buried under {passed:true}  -> fail-closed scan   -> caught
    5  "done"                   (missing key)   -> contract gate  -> caught
    6  step 2 uses a FAILED step's output       -> failed-ref guard -> no drift

Run it::

    cd rondo && uv run python examples/api/lie_trap_loop.py          # deterministic, $0
    cd rondo && uv run python examples/api/lie_trap_loop.py --live   # one scenario vs a real AI
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from rondo.pipeline import PipelineSpec, PipelineStep, run_pipeline


def _done(raw: str) -> dict:
    """A dispatch reply that CLAIMS success — raw is the model's asserted output."""
    return {"status": "done", "raw_output": raw, "cost_usd": 0.0}


def _scenario(title: str, ok: bool, detail: str) -> bool:
    """Print one scenario's verdict; return whether the trap behaved correctly."""
    marker = "-PASS-" if ok else "-FAIL-"
    print(f"  {marker} {title}")
    print(f"         {detail}")
    return ok


def lie1_file_absent_then_recover(work: Path) -> bool:
    """Lie: 'I wrote the file.' Trap: verify files. Branch: bounded retry that fixes it."""
    target = work / "journal.py"
    attempts = {"n": 0}

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        attempts["n"] += 1
        if attempts["n"] >= 2:  # -- the retry actually does the work
            target.write_text("def add_entry(text):\n    return text\n")
        return _done('{"passed": true, "result": "created journal.py"}')

    spec = PipelineSpec(
        name="lie1",
        budget_usd=10.0,
        steps=[PipelineStep(name="scaffold", prompt="create journal.py", retries=1, verify={"files": [str(target)]})],
    )
    env = run_pipeline(spec, dispatch=adversary)
    recovered = env["status"] == "done" and attempts["n"] == 2
    return _scenario(
        "Lie 1: 'I wrote the file' (absent)",
        recovered,
        f"trap caught the empty claim on attempt 1; retry recovered -> {env['status']} after {attempts['n']} tries",
    )


def lie2_tests_pass_but_exit_1() -> bool:
    """Lie: 'all tests pass.' Trap: verify cmd — rondo runs it and sees exit 1."""

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        return _done('{"passed": true, "result": "all green"}')

    spec = PipelineSpec(
        name="lie2",
        budget_usd=10.0,
        steps=[
            PipelineStep(
                name="tests",
                prompt="run the tests",
                verify={"cmd": [sys.executable, "-c", "import sys; sys.exit(1)"], "expect_exit": 0},
            )
        ],
    )
    env = run_pipeline(spec, dispatch=adversary)
    caught = env["status"] == "partial" and env["steps"][0]["verification"]["exit_code"] == 1
    return _scenario(
        "Lie 2: 'tests pass' (exit 1)",
        caught,
        f"rondo ran the command itself: exit_code={env['steps'][0]['verification']['exit_code']} -> {env['status']}",
    )


def lie3_empty_stub(work: Path) -> bool:
    """Lie: 'implemented add().' Trap: contains/min_bytes — exists is not right."""
    target = work / "calc.py"
    target.write_text("# placeholder\n")

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        return _done('{"passed": true, "result": "implemented add()"}')

    spec = PipelineSpec(
        name="lie3",
        budget_usd=10.0,
        steps=[
            PipelineStep(
                name="impl",
                prompt="implement add()",
                verify={"files": [str(target)], "contains": ["def add"], "min_bytes": 20},
            )
        ],
    )
    env = run_pipeline(spec, dispatch=adversary)
    caught = env["status"] == "partial" and "def add" in env["steps"][0]["verification"]["error"]
    return _scenario(
        "Lie 3: 'implemented it' (empty stub)",
        caught,
        f"content assertion saw the missing 'def add' -> {env['status']}",
    )


def lie4_buried_failure() -> bool:
    """Lie: admit passed=false, then bury it under an appended {passed:true}. Trap: fail-closed."""

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        return _done('{"passed": false, "issues": "could not finish"} trailing {"passed": true}')

    spec = PipelineSpec(name="lie4", budget_usd=10.0, steps=[PipelineStep(name="work", prompt="do the work")])
    env = run_pipeline(spec, dispatch=adversary)
    caught = env["status"] == "partial" and "REPORTED_FAILURE" in env["steps"][0]["error"]
    return _scenario(
        "Lie 4: fake success appended over real failure",
        caught,
        f"fail-closed scan honored the admitted passed=false -> {env['status']}",
    )


def lie5_missing_contract_key() -> bool:
    """Lie: 'done', but the output lacks a required key. Trap: the contract gate."""

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        return _done('{"summary": "did stuff"}')  # -- no "answer"

    spec = PipelineSpec(
        name="lie5",
        budget_usd=10.0,
        steps=[PipelineStep(name="ask", prompt="answer the question", expect={"required": ["answer"]})],
    )
    env = run_pipeline(spec, dispatch=adversary)
    caught = env["status"] == "partial" and "ERR_CONTRACT" in env["steps"][0]["error"]
    return _scenario(
        "Lie 5: 'done' but missing the required key",
        caught,
        f"contract gate refused the wrong shape -> {env['status']}",
    )


def lie6_no_drift_past_failure() -> bool:
    """Lie: a later step happily consumes a FAILED step's output. Trap: the failed-ref guard."""
    replies = [
        _done('{"passed": false, "issues": "step one broke"}'),
        _done('{"passed": true}'),
    ]

    def adversary(prompt: str, model: str, opts: dict | None = None) -> dict:
        return replies.pop(0)

    spec = PipelineSpec(
        name="lie6",
        budget_usd=10.0,
        steps=[
            PipelineStep(name="one", prompt="produce X", on_fail="continue"),
            PipelineStep(name="two", prompt="use {{steps.one.output}}"),
        ],
    )
    env = run_pipeline(spec, dispatch=adversary)
    no_drift = len(env["steps"]) == 1  # -- step two's garbage input never dispatched
    return _scenario(
        "Lie 6: consuming a failed step's output",
        no_drift,
        f"failed-ref guard stopped the drift; steps dispatched={len(env['steps'])} -> {env['status']}",
    )


def run_live() -> int:
    """One scenario against a REAL AI: ask it to claim a file, let rondo check.

    The honest live proof — we instruct a real model to REPORT success without
    creating the file, then rondo_verify observes the truth. Tiny canary.
    """
    from rondo.mcp_dispatch import rondo_run_file  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    work = Path(tempfile.mkdtemp(prefix="rondo-lietrap-live-"))
    target = work / "proof.txt"
    print(f"== LIVE: workspace {work} ==")
    print(">> Asking a real AI to REPORT it created proof.txt WITHOUT actually creating it...")
    envelope = json.loads(
        rondo_run_file(
            prompt=(
                f"Do NOT create any file. Just reply with this exact JSON and nothing else: "
                f'{{"passed": true, "result": "created {target}"}}'
            ),
            model="sonnet",
            dry_run=False,
            allowed_tools="",
            max_turns=2,
            timeout_sec=120,
        )
    )
    task = (envelope.get("tasks") or [{}])[0]
    print(f"   AI claimed: {task.get('raw_output', '')[:120]}")

    # -- rondo's OWN observation: did the file actually appear? (the trap)
    spec = PipelineSpec(
        name="live",
        budget_usd=1.0,
        steps=[PipelineStep(name="check", prompt="noop", verify={"files": [str(target)]})],
    )

    def already_claimed(prompt: str, model: str, opts: dict | None = None) -> dict:
        return _done(task.get("raw_output", ""))

    env = run_pipeline(spec, dispatch=already_claimed)
    caught = env["status"] == "partial" and not target.exists()
    ok = _scenario(
        "LIVE: real AI claimed success, file absent",
        caught,
        f"rondo verified the filesystem itself: file exists={target.exists()} -> {env['status']}",
    )
    return 0 if ok else 1


def main() -> int:
    """Run the deterministic lie-trap loop, or a single live scenario with --live."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="run one scenario against a real AI (small canary cost)")
    args = parser.parse_args()

    if args.live:
        return run_live()

    work = Path(tempfile.mkdtemp(prefix="rondo-lietrap-"))
    print("== THE LIE-TRAP LOOP: rondo catches a lying AI (deterministic, $0) ==\n")
    results = [
        lie1_file_absent_then_recover(work),
        lie2_tests_pass_but_exit_1(),
        lie3_empty_stub(work),
        lie4_buried_failure(),
        lie5_missing_contract_key(),
        lie6_no_drift_past_failure(),
    ]
    passed = sum(results)
    print(f"\n== {passed}/{len(results)} traps fired correctly ==")
    if passed == len(results):
        print("-PASS- every lie was caught and the right branch was taken")
        return 0
    print("-FAIL- a trap did not behave as designed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


# -- sig: mgh-6201.cd.bd955f.50fa.b07364
