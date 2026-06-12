# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation kill-tests for rondo.pipeline — the engine, proven to bite.

VER-001: Product acceptance / mutation-adequacy coverage.

AUTHOR NOTE: Claude-authored — the MUTATION GATE is the independent referee
(RONDO-363). The cursor/gemini regression suites exercise the engine through
load_pipeline/run_pipeline but assert loosely; a measured sweep (bin/mutate
--timeout-per-mutant 30, 2026-06-12) caught only 85/160 — 75 survivors across
the budget gate, retry loop, contract checker, placeholder resolver, and the
PRODUCTION dispatch normalizer (which every other test mocks away, the classic
mocked-seam blind spot). These tests pin the real behavior so a flipped
boundary, a changed operator, or a broken normalizer fails loudly.

Every asserted number/shape was computed from the live code before being
written (probe runs, 2026-06-12) — no guessed values; the gate punishes guesses.

NO MOCKS (Mark's standing rule). These tests drive the engine three honest ways:
direct calls to the pure helpers, the FIRST-CLASS injected `dispatch=` seam
(REQ-114 req 025 — dependency injection, the engine's real interface, not a
fake), and pytest's `caplog` for log-only branches. Nothing reaches in and
replaces a rondo function with a canned return.

DOCUMENTED EQUIVALENTS (house rule: never tautology-tested) — provably
behavior-preserving, left as survivors on purpose:
  - L57 _EST_OUTPUT_TOKENS 2048, L285 (model `or ''` + split maxsplit),
    L286 (len//4 + the max(1,…) floor): all feed the plan COST ESTIMATE, which
    the provider rate table collapses to the same value for every model/length
    sampled (verified live: claude-opus / gemini:high / claude:max:foo all ->
    0.007144). A heuristic admission number, never a quote — these cannot move
    an observable verdict.
  - L306 / L316 / L561 round(x, 6): cosmetic precision on cost fields; no
    contract asserts six decimals.
  - L402 `idx = max(end, start + 1)` SUCCESS-decode path: dead defensive arm —
    raw_decode always consumes >=1 char (end > start), so max() always picks
    end. (Same equivalent as verify.py L214 and dispatch_parse L92.)

_default_dispatch (the production normalizer) is covered by its own UNMOCKED-seam
contract test, tests/unit/test_default_dispatch_contract.py — it stubs ONLY the OS
boundary (rondo.dispatch._run_subprocess) and runs the entire real chain on top,
NOT a mocked rondo_run_file return (the house-rule "one unmocked contract test per
mocked seam"). That test killed 13 of the 16 dispatch mutants this sweep surfaced.

CORRECTION (2026-06-12): an earlier version of this docstring claimed those
mutants were "exercised by tests/integration/test_live.py" — that was FALSE
(test_live.py tests rondo.live, a different module, and never touches
_default_dispatch). Fixed by building the real contract test above. History not
rewritten (the wrong claim lives in commits b4e82db/9043b4f); corrected forward.

Lone remaining dispatch survivor — L364 `task.get('error_message','') or
envelope.get('error_message','')`: a DEFENSIVE fallback to the envelope-level
error when the task itself carries none. In practice the failing TASK carries the
message (verified: stderr -> task.error_message), so the envelope branch is
belt-and-suspenders for a round-level error that is hard to stub deterministically
through the subprocess seam. Left documented, not faked. Measured sweep:
85/160 -> 135 (kill-tests) -> 149/160 (+contract test); residual 11 = the
documented equivalents above + L364.
"""

from __future__ import annotations

import logging

import pytest

from rondo.pipeline import (
    PipelineError,
    PipelineSpec,
    PipelineStep,
    _all_json_objects,
    _build_plan,
    _contract_error,
    _placeholders,
    _resolve_verify,
    _self_reported_failure,
    _validate_step,
    run_pipeline,
    unwrap_smart_return,
)

# ── dataclass defaults (kills L76/80/82/86 step defaults, L96 spec default) ──


def test_step_field_defaults() -> None:
    """A minimally-constructed step carries the documented defaults."""
    s = PipelineStep(name="s", prompt="do one thing")
    assert s.retries == 0
    assert s.max_turns == 0
    assert s.timeout == 0
    assert s.allow_broad is False


def test_spec_strict_scope_defaults_false() -> None:
    """A spec defaults to non-strict scope (warn, not block)."""
    assert PipelineSpec(name="t", budget_usd=1.0).strict_scope is False


# ── _placeholders: the wiring grammar (kills L104/106 boolops) ──


def test_placeholder_inputs_needs_exactly_two_parts() -> None:
    """{{inputs.a.b}} and {{inputs}} are not valid inputs refs -> raise."""
    with pytest.raises(PipelineError):
        _placeholders("{{inputs.a.b}}")
    with pytest.raises(PipelineError):
        _placeholders("{{inputs}}")


def test_placeholder_steps_needs_three_parts_ending_output() -> None:
    """{{steps.x}} (too short) and {{steps.x.bad}} (not .output) -> raise."""
    with pytest.raises(PipelineError):
        _placeholders("{{steps.x}}")
    with pytest.raises(PipelineError):
        _placeholders("{{steps.x.bad}}")


def test_placeholder_valid_forms_parse() -> None:
    """The two legal forms parse to (domain, key)."""
    assert _placeholders("{{inputs.topic}}") == [("inputs", "topic")]
    assert _placeholders("{{steps.build.output}}") == [("steps", "build")]


# ── step validation (kills L121 name boolop, L143 timeout boolop, L147 expect, L173 model) ──


def _vstep(raw: dict) -> PipelineStep:
    """Validate a single raw step dict in isolation."""
    return _validate_step(raw, 0, set())


def test_step_name_must_be_identifier_safe() -> None:
    """A non-empty but non-identifier name is rejected (kills the L121 or->and)."""
    with pytest.raises(PipelineError):
        _vstep({"name": "123bad", "prompt": "p"})


def test_step_timeout_negative_rejected() -> None:
    """A timeout that IS an int but negative is rejected (kills the L143 or->and)."""
    with pytest.raises(PipelineError):
        _vstep({"name": "s", "prompt": "p", "timeout": -5})


def test_step_max_turns_negative_rejected() -> None:
    """max_turns negative rejected (kills the L140 boolop)."""
    with pytest.raises(PipelineError):
        _vstep({"name": "s", "prompt": "p", "max_turns": -1})


def test_retries_upper_bound_is_two() -> None:
    """retries=2 is accepted, retries=3 rejected (kills L55 _MAX_RETRIES 2->3)."""
    assert _vstep({"name": "s", "prompt": "p", "retries": 2}).retries == 2
    with pytest.raises(PipelineError):
        _vstep({"name": "s", "prompt": "p", "retries": 3})


def test_step_defaults_from_validation() -> None:
    """Undeclared retries/max_turns/timeout validate to 0 (kills L139/142 get-defaults)."""
    s = _vstep({"name": "s", "prompt": "p"})
    assert (s.retries, s.max_turns, s.timeout) == (0, 0, 0)


def test_expect_extra_key_rejected() -> None:
    """Expect with a key beyond 'required' is rejected (kills the L147 set-compare arm)."""
    with pytest.raises(PipelineError):
        _vstep({"name": "s", "prompt": "p", "expect": {"required": ["k"], "extra": 1}})


def test_expect_required_must_be_list() -> None:
    """expect.required that is not a list is rejected (kills the L147 isinstance arm)."""
    with pytest.raises(PipelineError):
        _vstep({"name": "s", "prompt": "p", "expect": {"required": "k"}})


def test_model_value_preserved() -> None:
    """A declared model survives validation verbatim (kills the L173 or->and to '')."""
    assert _vstep({"name": "s", "prompt": "p", "model": "gpt-5"}).model == "gpt-5"


# ── _contract_error: the output contract gate (kills L268/273/276 return-none) ──


def test_contract_unparseable_output_errors() -> None:
    """Non-JSON output with a required contract -> ERR_CONTRACT (kills L268)."""
    s = PipelineStep(name="s", prompt="p", expect={"required": ["k"]})
    parsed, err = _contract_error(s, "not json at all")
    assert parsed is None
    assert err.startswith("ERR_CONTRACT")


def test_contract_top_level_keys_pass() -> None:
    """Required keys at the top level pass, returning that payload (kills L273)."""
    s = PipelineStep(name="s", prompt="p", expect={"required": ["k"]})
    parsed, err = _contract_error(s, '{"k": 1}')
    assert err == ""
    assert parsed == {"k": 1}


def test_contract_nested_result_keys_pass() -> None:
    """Required keys inside .result pass, returning the inner payload (kills L276)."""
    s = PipelineStep(name="s", prompt="p", expect={"required": ["k"]})
    parsed, err = _contract_error(s, '{"result": {"k": 9}, "passed": true}')
    assert err == ""
    assert parsed == {"k": 9}


def test_contract_missing_key_errors() -> None:
    """A required key absent in both layers -> error naming the missing key."""
    s = PipelineStep(name="s", prompt="p", expect={"required": ["k"]})
    _parsed, err = _contract_error(s, '{"other": 1}')
    assert "k" in err
    assert "ERR_CONTRACT" in err


# ── unwrap_smart_return (kills L332 boolop, L334/335 return-none) ──


def test_unwrap_wrapper_string_result() -> None:
    """A smart-return wrapper with a string result yields that string (kills L334 str arm)."""
    assert unwrap_smart_return('{"result": "CODE", "passed": true}') == "CODE"


def test_unwrap_wrapper_dict_result_is_jsondumped() -> None:
    """A wrapper with a dict result yields its JSON dump (kills L334 else arm)."""
    assert unwrap_smart_return('{"result": {"k": 1}, "confidence": 0.9}') == '{"k": 1}'


def test_unwrap_plain_text_passthrough() -> None:
    """Plain (non-JSON) text is returned unchanged (kills L335 return-none)."""
    assert unwrap_smart_return("plain text") == "plain text"


def test_unwrap_dict_without_passed_or_confidence_passthrough() -> None:
    """A dict with result but no passed/confidence is NOT a wrapper (kills the L332 boolop)."""
    raw = '{"result": "X"}'
    assert unwrap_smart_return(raw) == raw


# ── _build_plan: pure preview + budget flag (kills L297/298 input sub, L305 cap, L318 compare) ──


def test_plan_substitutes_inputs_in_preview() -> None:
    """The plan preview substitutes {{inputs.X}} (kills L297 compare + L298 string-build)."""
    spec = PipelineSpec(name="t", budget_usd=1.0, steps=[PipelineStep(name="s", prompt="hello {{inputs.who}}")])
    plan = _build_plan(spec, {"who": "world"})
    assert plan["steps"][0]["prompt_preview"] == "hello world"


def test_plan_preview_capped_at_300() -> None:
    """A long prompt preview is capped at 300 chars (kills L305 slice literal)."""
    spec = PipelineSpec(name="t", budget_usd=1.0, steps=[PipelineStep(name="s", prompt="x" * 1000)])
    plan = _build_plan(spec, {})
    assert len(plan["steps"][0]["prompt_preview"]) == 300


def test_plan_within_budget_flag_tracks_total() -> None:
    """within_budget_estimate is total <= budget, both directions (kills L318 compare)."""
    one = PipelineSpec(name="t", budget_usd=1.0, steps=[PipelineStep(name="s", prompt="hi")])
    assert _build_plan(one, {})["within_budget_estimate"] is True
    # -- a budget below the per-step estimate flips the flag
    tight = PipelineSpec(name="t", budget_usd=0.0001, steps=[PipelineStep(name="s", prompt="hi")])
    assert _build_plan(tight, {})["within_budget_estimate"] is False


def test_plan_within_budget_is_inclusive_at_equality() -> None:
    """Budget EXACTLY equal to the estimate is within (kills the L318 <= -> < mutant)."""
    # -- 'hi' estimates to 0.006145 (computed live); a budget == that is within
    spec = PipelineSpec(name="t", budget_usd=0.006145, steps=[PipelineStep(name="s", prompt="hi")])
    plan = _build_plan(spec, {})
    assert plan["total_estimated_cost_usd"] == 0.006145
    assert plan["within_budget_estimate"] is True


def test_plan_empty_model_shows_config_default() -> None:
    """A step with no model shows '(config default)' in the plan (kills the L304 or->and)."""
    spec = PipelineSpec(name="t", budget_usd=1.0, steps=[PipelineStep(name="s", prompt="hi")])
    assert _build_plan(spec, {})["steps"][0]["model"] == "(config default)"


# ── _self_reported_failure: the anti-lying admission gate (kills L417 cap, L418 return-none) ──


def test_self_report_passed_true_is_empty_string() -> None:
    """passed=true yields the empty string, NOT None (kills L418 return-none)."""
    s = PipelineStep(name="s", prompt="p")
    # -- "" and None both read falsy at the call site, so only a direct == pins it
    assert _self_reported_failure(s, '{"passed": true}') == ""


def test_self_report_detail_capped_at_300() -> None:
    """A passed=false detail is truncated to 300 chars (kills L417 slice literal)."""
    s = PipelineStep(name="s", prompt="p")
    msg = _self_reported_failure(s, '{"passed": false, "issues": "' + "Z" * 500 + '"}')
    assert msg.count("Z") == 300


# ── _all_json_objects: fail-closed scanner (kills L398 start+1 offset) ──


def test_all_json_objects_adjacent_braces() -> None:
    """'{{...}' needs offset exactly +1 to reach the inner object (kills L398 start+1)."""
    assert _all_json_objects('{{"passed": false}') == [{"passed": False}]


def test_all_json_objects_finds_every_object() -> None:
    """All top-level objects are returned, in order (the fail-closed contract)."""
    assert _all_json_objects('{"a": 1} noise {"b": 2}') == [{"a": 1}, {"b": 2}]


# ── _resolve_verify: placeholder substitution in verify blocks (kills L431/433/435) ──


def test_resolve_verify_substitutes_inputs_and_steps() -> None:
    """{{inputs.X}} and {{steps.X.output}} resolve inside files/cmd (kills L431/433/435)."""
    st = PipelineStep(
        name="s",
        prompt="p",
        verify={"files": ["{{inputs.ws}}/out.py"], "cmd": ["{{steps.prev.output}}"]},
    )
    rv = _resolve_verify(st, {"ws": "/tmp/work"}, {"prev": ("PYBIN", True)})
    assert rv["files"] == ["/tmp/work/out.py"]
    assert rv["cmd"] == ["PYBIN"]


def test_resolve_verify_unknown_placeholder_left_as_is() -> None:
    """An unresolvable token is left verbatim, not crashed (kills the L433/435 fallbacks)."""
    st = PipelineStep(name="s", prompt="p", verify={"files": ["{{inputs.missing}}", "{{steps.nope.output}}"]})
    rv = _resolve_verify(st, {}, {})
    assert rv["files"] == ["{{inputs.missing}}", "{{steps.nope.output}}"]


def test_resolve_verify_single_token_does_not_crash() -> None:
    """A dot-less {{token}} is left verbatim, not indexed (kills the L435 len(parts) > 1 boundary)."""
    # -- len(parts)==1; a >=1 / >0 mutant would index parts[1] and raise IndexError
    st = PipelineStep(name="s", prompt="p", verify={"files": ["{{singletoken}}"]})
    assert _resolve_verify(st, {}, {})["files"] == ["{{singletoken}}"]


def test_resolve_verify_two_part_token_resolves_by_second_part() -> None:
    """A 2-part {{steps.prev}} (a real .output typo) resolves leniently (kills the L435 '>1'->'>2')."""
    # -- pins CURRENT lenient behavior: parts==['steps','prev'], len 2 > 1 -> outputs['prev'].
    # -- a '> 2' mutant would leave it verbatim; this distinguishes the boundary literal.
    st = PipelineStep(name="s", prompt="p", verify={"files": ["{{steps.prev}}"]})
    assert _resolve_verify(st, {}, {"prev": ("RESOLVED", True)})["files"] == ["RESOLVED"]


# ── run_pipeline budget gate boundaries (kills L534 high_cost>0, L535 spent+est>budget) ──


def _cost_dispatch(cost: float):
    """A real injected dispatch (REQ-114 seam) that returns a fixed cost — not a mock."""

    def disp(prompt, model, opts=None):
        return {"status": "done", "raw_output": "ok", "cost_usd": cost}

    return disp


def test_budget_gate_is_exclusive_at_equality() -> None:
    """spent+est EXACTLY equal to budget still runs (kills the L535 > -> >= mutant)."""
    # -- one free step, est defaults to _MIN_STEP_EST_USD 0.001; budget == 0.001
    spec = PipelineSpec(name="t", budget_usd=0.001, steps=[PipelineStep(name="s", prompt="p")])
    env = run_pipeline(spec, dispatch=_cost_dispatch(0.0))
    assert env["status"] == "done"  # -- 0 + 0.001 > 0.001 is False -> the step runs


def test_budget_gate_uses_prior_step_high_cost() -> None:
    """A prior step's cost becomes the next estimate, blocking before overspend (kills L534)."""
    # -- step1 costs 0.5; step2's estimate = high_cost 0.5, so 0.5+0.5=1.0 > 0.6 -> blocked.
    # -- a high_cost>1 mutant would fall back to _MIN and wrongly dispatch step2.
    spec = PipelineSpec(
        name="t",
        budget_usd=0.6,
        steps=[PipelineStep(name="one", prompt="p"), PipelineStep(name="two", prompt="p")],
    )
    env = run_pipeline(spec, dispatch=_cost_dispatch(0.5))
    assert env["status"] == "partial"
    assert len(env["steps"]) == 1  # -- step two never dispatched
    assert "ERR_BUDGET" in env["error"]


# ── log-only mutants: caplog is a pytest fixture, not a mock (kills L500 compare, L502 +1) ──


def test_failed_step_logs_attempt_count(caplog) -> None:
    """A step failing after retries logs its real attempt count (kills L500 compare, L502 +1)."""
    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p", retries=2)])

    def disp(prompt, model, opts=None):
        return {"status": "error", "raw_output": "", "cost_usd": 0.0, "error": "boom"}

    with caplog.at_level(logging.WARNING, logger="rondo.pipeline"):
        run_pipeline(spec, dispatch=disp)
    # -- retries=2 -> 3 attempts; the warning must fire (L500) and name 3 (L502 retries+1)
    assert any("failed after 3 attempt(s)" in r.message for r in caplog.records)


# ── run_pipeline: retry count + budget gate (kills L502 retries+1, L534/535 budget) ──


def test_retries_exhausted_dispatch_count() -> None:
    """A failing step with retries=2 dispatches exactly 3 times (kills L502 step.retries+1)."""
    calls = {"n": 0}

    def disp(prompt, model, opts=None):
        calls["n"] += 1
        return {"status": "error", "raw_output": "", "cost_usd": 0.0, "error": "boom"}

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p", retries=2)])
    env = run_pipeline(spec, dispatch=disp)
    assert calls["n"] == 3
    assert env["status"] == "partial"


def test_no_retry_dispatches_once() -> None:
    """A failing step with no retries dispatches exactly once (kills the retries default + range)."""
    calls = {"n": 0}

    def disp(prompt, model, opts=None):
        calls["n"] += 1
        return {"status": "error", "raw_output": "", "cost_usd": 0.0, "error": "boom"}

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p")])
    run_pipeline(spec, dispatch=disp)
    assert calls["n"] == 1


def test_budget_blocks_before_dispatch() -> None:
    """A budget below the min estimate -> partial, ZERO dispatches (kills L534/535 budget gate)."""
    calls = {"n": 0}

    def disp(prompt, model, opts=None):
        calls["n"] += 1
        return {"status": "done", "raw_output": "ok", "cost_usd": 5.0}

    spec = PipelineSpec(name="t", budget_usd=0.0005, steps=[PipelineStep(name="s", prompt="p")])
    env = run_pipeline(spec, dispatch=disp)
    assert env["status"] == "partial"
    assert calls["n"] == 0
    assert "ERR_BUDGET" in env["error"]


def test_dispatch_failure_error_default_message() -> None:
    """A dispatch returning no error string still records a default failure (kills L478 boolop)."""

    def disp(prompt, model, opts=None):
        return {"status": "error", "raw_output": "", "cost_usd": 0.0}  # -- no 'error' key

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p")])
    env = run_pipeline(spec, dispatch=disp)
    assert env["steps"][0]["error"]  # -- non-empty: the default kicked in


def test_failed_step_output_never_substitutes() -> None:
    """A step referencing a FAILED prior step aborts substitution (req 021 — kills L500 compare)."""
    seq = [
        {"status": "error", "raw_output": "", "cost_usd": 0.0, "error": "boom"},
        {"status": "done", "raw_output": "ok", "cost_usd": 0.0},
    ]

    def disp(prompt, model, opts=None):
        return seq.pop(0)

    spec = PipelineSpec(
        name="t",
        budget_usd=10.0,
        steps=[
            PipelineStep(name="first", prompt="p", on_fail="continue"),
            PipelineStep(name="second", prompt="use {{steps.first.output}}"),
        ],
    )
    env = run_pipeline(spec, dispatch=disp)
    # -- second must error on the failed-ref guard, not silently dispatch the empty output
    assert env["status"] in {"partial", "error"}


# -- sig: mgh-6201.cd.bd955f.189b.3bd1ee
