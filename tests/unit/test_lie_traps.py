# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Lie traps — the QA of rondo's thesis: a lying AI is CAUGHT, then RECOVERED.

VER-001: Product acceptance / anti-lying behavior.

THE POINT (Mark's framing): rondo's loop must test 1-2 steps at a time with the
KNOWN BAD answers an AI actually returns, TRAP each lie with if/else, and take
the right next action. These tests feed the engine the exact lies and assert
the REAL machinery catches them — then that the recovery branch fixes it.

NOT MOCKS. The "AI" here is an ADVERSARIAL DISPATCH plugged into the engine's
first-class injection seam (REQ-114 req 025, the same point _default_dispatch
uses). The SUBJECT UNDER TEST — verify (REQ-115), the contract gate, the
fail-closed self-report scanner (RONDO-411 F3), the failed-ref guard (req 021),
and the retry loop — runs 100% for real and must ACTUALLY catch the lie. A mock
fakes the thing under test to go green; an adversary feeds the trap its prey.

Each test is the unit Mark described: a lie in, a trap fires, a branch is taken.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rondo.pipeline import PipelineSpec, PipelineStep, run_pipeline


def _done(raw: str = "", cost: float = 0.0):
    """An honest 'done' dispatch reply (raw is the model's claimed output)."""
    return {"status": "done", "raw_output": raw, "cost_usd": cost}


# ── Lie 1: "I wrote the file" — it isn't there. Trap: verify files. Recover: retry writes it. ──


def test_lie_file_not_written_is_caught_then_recovered(tmp_path: Path) -> None:
    """The AI claims passed=true but never wrote the file; verify catches it; the retry fixes it."""
    target = tmp_path / "journal.py"
    attempts = {"n": 0}

    def lying_then_fixing(prompt, model, opts=None):
        attempts["n"] += 1
        # -- attempt 1: claim success, write NOTHING (the lie)
        # -- attempt 2 (the recovery dispatch): actually do the work
        if attempts["n"] >= 2:
            target.write_text("def add_entry(t): ...\n")
        return _done('{"passed": true, "result": "created journal.py"}')

    spec = PipelineSpec(
        name="lie1",
        budget_usd=10.0,
        steps=[PipelineStep(name="scaffold", prompt="create journal.py", retries=1, verify={"files": [str(target)]})],
    )
    env = run_pipeline(spec, dispatch=lying_then_fixing)

    # -- TRAP fired on attempt 1 (passed=true did NOT override rondo's own file check)...
    # -- ...and the bounded retry RECOVERED on attempt 2.
    assert attempts["n"] == 2
    assert env["status"] == "done"
    assert env["steps"][0]["verification"]["ok"] is True


def test_lie_file_never_written_stays_failed(tmp_path: Path) -> None:
    """If the AI keeps lying, rondo NEVER advances — passed=true cannot buy a pass."""
    target = tmp_path / "never.py"

    def always_lying(prompt, model, opts=None):
        return _done('{"passed": true, "result": "definitely wrote it"}')  # -- it didn't

    spec = PipelineSpec(
        name="lie1b",
        budget_usd=10.0,
        steps=[PipelineStep(name="scaffold", prompt="create never.py", retries=2, verify={"files": [str(target)]})],
    )
    env = run_pipeline(spec, dispatch=always_lying)
    assert env["status"] == "partial"
    assert env["steps"][0]["verification"]["ok"] is False
    assert not target.exists()


# ── Lie 2: "tests pass" — pytest actually exits 1. Trap: verify cmd expect_exit 0. ──


def test_lie_tests_pass_but_command_fails(tmp_path: Path) -> None:
    """The AI says tests are green; rondo runs the command itself and sees exit 1."""

    def claims_green(prompt, model, opts=None):
        return _done('{"passed": true, "result": "all tests pass"}')

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
    env = run_pipeline(spec, dispatch=claims_green)
    assert env["status"] == "partial"
    assert env["steps"][0]["verification"]["ok"] is False
    assert env["steps"][0]["verification"]["exit_code"] == 1


# ── Lie 3: passed=true but the file is an empty stub. Trap: verify min_bytes / contains. ──


def test_lie_empty_stub_caught_by_content_assertion(tmp_path: Path) -> None:
    """The file EXISTS but is a hollow stub; contains[] proves it lacks the real function."""
    target = tmp_path / "calc.py"
    target.write_text("# stub\n")  # -- a hollow placeholder, not the real thing

    def claims_implemented(prompt, model, opts=None):
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
    env = run_pipeline(spec, dispatch=claims_implemented)
    assert env["status"] == "partial"
    assert env["steps"][0]["verification"]["ok"] is False
    assert "def add" in env["steps"][0]["verification"]["error"]


# ── Lie 4: append {"passed":true} to bury an admitted {"passed":false}. Trap: fail-closed scan. ──


def test_lie_appended_fake_success_is_fail_closed() -> None:
    """A real passed=false hidden behind an appended passed=true still fails the step (F3)."""

    def buries_failure(prompt, model, opts=None):
        # -- the model admits failure, then tries to bury it under a fake success token
        return _done('{"passed": false, "issues": "could not finish"} ... {"passed": true}')

    spec = PipelineSpec(
        name="lie4",
        budget_usd=10.0,
        steps=[PipelineStep(name="work", prompt="do the work")],
    )
    env = run_pipeline(spec, dispatch=buries_failure)
    assert env["status"] == "partial"
    assert "REPORTED_FAILURE" in env["steps"][0]["error"]


# ── Lie 5: "done" but the output is missing a contracted key. Trap: contract gate. ──


def test_lie_missing_required_key_caught_by_contract() -> None:
    """The AI returns JSON lacking the required key; the contract gate refuses it."""

    def wrong_shape(prompt, model, opts=None):
        return _done('{"summary": "did stuff"}')  # -- missing "answer"

    spec = PipelineSpec(
        name="lie5",
        budget_usd=10.0,
        steps=[PipelineStep(name="ask", prompt="answer the question", expect={"required": ["answer"]})],
    )
    env = run_pipeline(spec, dispatch=wrong_shape)
    assert env["status"] == "partial"
    assert "ERR_CONTRACT" in env["steps"][0]["error"]


# ── Lie 6: a later step feeds off a FAILED step's output. Trap: failed-ref guard (no drift). ──


def test_failed_step_output_never_flows_downstream() -> None:
    """A step referencing a FAILED prior step is refused — a lie never drifts forward (req 021)."""
    replies = [
        _done('{"passed": false, "issues": "step one broke"}'),  # -- step one FAILS honestly
        _done('{"passed": true}'),  # -- step two would happily run on garbage if allowed
    ]

    def sequenced(prompt, model, opts=None):
        return replies.pop(0)

    spec = PipelineSpec(
        name="lie6",
        budget_usd=10.0,
        steps=[
            PipelineStep(name="one", prompt="produce X", on_fail="continue"),
            PipelineStep(name="two", prompt="use {{steps.one.output}}"),
        ],
    )
    env = run_pipeline(spec, dispatch=sequenced)
    # -- the engine stops at the failed-ref guard; step two's garbage input never dispatches
    assert env["status"] in {"partial", "error"}
    assert len(env["steps"]) == 1


# ── The whole point: a self-correcting loop that survives a lie mid-stream ──


def test_loop_recovers_and_completes_after_a_mid_stream_lie(tmp_path: Path) -> None:
    """Three steps; step 2's AI lies once then fixes on retry; the loop reaches done."""
    out_a = tmp_path / "a.txt"
    out_b = tmp_path / "b.txt"
    out_c = tmp_path / "c.txt"
    seen = {"b": 0}

    def adversary(prompt, model, opts=None):
        if "step A" in prompt:
            out_a.write_text("A")
        elif "step B" in prompt:
            seen["b"] += 1
            if seen["b"] >= 2:  # -- lies on attempt 1, does it on the retry
                out_b.write_text("B")
        elif "step C" in prompt:
            out_c.write_text("C")
        return _done('{"passed": true}')

    spec = PipelineSpec(
        name="loop",
        budget_usd=10.0,
        steps=[
            PipelineStep(name="a", prompt="do step A", verify={"files": [str(out_a)]}),
            PipelineStep(name="b", prompt="do step B", retries=1, verify={"files": [str(out_b)]}),
            PipelineStep(name="c", prompt="do step C", verify={"files": [str(out_c)]}),
        ],
    )
    env = run_pipeline(spec, dispatch=adversary)
    assert env["status"] == "done"
    assert seen["b"] == 2  # -- step B was caught lying once, recovered on retry
    assert out_a.exists() and out_b.exists() and out_c.exists()


# -- sig: mgh-6201.cd.bd955f.7583.ad325d
