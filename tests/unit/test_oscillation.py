# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Oscillation detection — STD-116 minimal (RONDO-430).

VER-001: Product acceptance / loop-thrash detection.

Cross-vendor decision (gemini+grok via rondo_multi_review, 2026-06-13): a SPLIT.
Grok: a heavy circuit-breaker is redundant with rondo's capped retries + budget.
Gemini: a deterministic round-signature is cheap, field-rare, and a real signal.
Adjudication: build the MINIMAL version — detect when a retry produces the EXACT
same observable result (error + raw_output) as a prior attempt (the model is
repeating itself, not converging) → FLAG it as ERR_OSCILLATION on the step record.
FLAG-ONLY: it does NOT break early; retries + budget still bound the loop and the
retry contract is preserved (see test_oscillation_flag_preserves_retry_count).

Authored TDD (RED before the module existed, 2026-06-14).
"""

from __future__ import annotations

from rondo.oscillation import detect_repeat, round_signature


def test_signature_is_deterministic() -> None:
    """Same (error, raw_output) -> same signature; pure + stable."""
    a = round_signature("boom", '{"passed": false}')
    b = round_signature("boom", '{"passed": false}')
    assert a == b
    assert len(a) == 64  # -- sha256 hex


def test_signature_distinguishes_different_results() -> None:
    """Different error OR different output -> different signature."""
    base = round_signature("boom", "out")
    assert round_signature("other", "out") != base
    assert round_signature("boom", "different") != base


def test_signature_separates_error_and_output_fields() -> None:
    """The field separator prevents ('a','bc') colliding with ('ab','c')."""
    assert round_signature("a", "bc") != round_signature("ab", "c")


def test_detect_repeat_none_when_all_distinct() -> None:
    """No repeat among distinct signatures -> None."""
    assert detect_repeat(["s1", "s2", "s3"]) is None
    assert detect_repeat([]) is None
    assert detect_repeat(["only"]) is None


def test_detect_repeat_two_element_minimum() -> None:
    """The MINIMUM oscillation: 2 rounds, the 2nd repeating the 1st -> index 0.

    This is the retries=1 case (the smallest loop that can oscillate). Kills the
    L42 `len < 2` boundary mutants — with `< 3` or `<= 2` this would wrongly None.
    """
    assert detect_repeat(["s1", "s1"]) == 0
    assert detect_repeat(["s1", "s2"]) is None  # -- two distinct -> no repeat


def test_detect_repeat_returns_earlier_index_on_oscillation() -> None:
    """The LAST signature matching an earlier one -> that earlier index (the thrash)."""
    assert detect_repeat(["s1", "s2", "s1"]) == 0  # -- round 3 reverted to round 1
    assert detect_repeat(["s1", "s2", "s2"]) == 1  # -- round 3 reverted to round 2


def test_detect_repeat_only_checks_the_latest() -> None:
    """A repeat NOT involving the last signature is not flagged (we act per new round)."""
    # -- s1 repeats at idx 0/1 but the LAST (s3) is new -> no halt this round
    assert detect_repeat(["s1", "s1", "s3"]) is None


# ── wiring into the pipeline retry loop (flag-only; retries still honored) ──


def test_pipeline_flags_oscillation_on_repeated_failure() -> None:
    """A step whose dispatch repeats its EXACT failure gets record['oscillation'] (RONDO-430)."""
    from rondo.pipeline import PipelineSpec, PipelineStep, run_pipeline

    def stuck(prompt, model, opts=None):
        return {"status": "error", "raw_output": "same output", "cost_usd": 0.0, "error": "same boom"}

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p", retries=2)])
    env = run_pipeline(spec, dispatch=stuck)
    osc = env["steps"][0].get("oscillation")
    assert osc is not None, "repeated identical failure should be flagged as oscillation"
    assert osc["error_code"] == "ERR_OSCILLATION"
    assert osc["repeated_attempt"] == 0  # -- attempt 1 reproduced attempt 0


def test_pipeline_no_oscillation_flag_when_failures_differ() -> None:
    """Distinct failures each round -> no oscillation flag (no false positive)."""
    from rondo.pipeline import PipelineSpec, PipelineStep, run_pipeline

    seq = [
        {"status": "error", "raw_output": "a", "cost_usd": 0.0, "error": "boom-1"},
        {"status": "error", "raw_output": "b", "cost_usd": 0.0, "error": "boom-2"},
        {"status": "error", "raw_output": "c", "cost_usd": 0.0, "error": "boom-3"},
    ]

    def changing(prompt, model, opts=None):
        return seq.pop(0)

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p", retries=2)])
    env = run_pipeline(spec, dispatch=changing)
    assert "oscillation" not in env["steps"][0]


def test_oscillation_flag_preserves_retry_count() -> None:
    """Flag-only: a stuck step still uses ALL its retries (the retry contract is intact)."""
    calls = {"n": 0}

    def stuck(prompt, model, opts=None):
        calls["n"] += 1
        return {"status": "error", "raw_output": "x", "cost_usd": 0.0, "error": "boom"}

    from rondo.pipeline import PipelineSpec, PipelineStep, run_pipeline

    spec = PipelineSpec(name="t", budget_usd=10.0, steps=[PipelineStep(name="s", prompt="p", retries=2)])
    env = run_pipeline(spec, dispatch=stuck)
    assert calls["n"] == 3  # -- retries=2 -> 3 attempts, NOT short-circuited by the flag
    assert env["steps"][0].get("oscillation") is not None


# -- sig: mgh-6201.cd.bd955f.7221.e9c788
