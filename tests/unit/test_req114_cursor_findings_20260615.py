# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Conformance regressions for the REQ-114 gaps Cursor's independent audit found.

VER-001: Product acceptance / conformance coverage.

PROVENANCE (the cross-vendor jury at work): the findings these tests pin were
raised by an INDEPENDENT Cursor (claude-opus-4-8-thinking-high) deep review on
2026-06-15 — author/auditor separation, since Claude wrote most of REQ-114.
Report: reports/cursor-reviews/review-20260615-081804.md. Each finding was
re-verified against live code before a test was written (jury rule: an
objection's value is forcing a LOOK; verify each). RONDO-433.

NO MOCKS (Mark's standing rule): every test drives the engine through the
FIRST-CLASS injected `dispatch=` seam (REQ-114 req 025 — dependency injection,
not a fake) or through real load_pipeline/run_pipeline / CLI main(). Nothing
reaches in and replaces a rondo function with a canned return. The numeric
thresholds were computed from the live estimator before being written.

Findings pinned here:
  1  (HIGH)     budget hard-ceiling was soft on the first/single step
  2  (HIGH-MED) req 023 lists per-step `duration` as a MUST — it was absent
  4  (MED)      req 030 apply-path exit codes (done->0, partial->1) were untested
  6  (LOW-MED)  the failed-ref guard was domain-blind (inputs.X vs steps.X)
  10 (LOW)      the run envelope omitted budget_usd (overshoot was invisible)
"""

from __future__ import annotations

import textwrap

from rondo.cli import main
from rondo.pipeline import (
    PipelineSpec,
    PipelineStep,
    _estimate_step_cost,
    run_pipeline,
)

# ── Finding 1: the hard budget ceiling must use the MODEL-AWARE estimate ──
# -- The old run-mode gate admitted step 0 against _MIN_STEP_EST_USD ($0.001),
# -- never the model-aware estimate (that lived only in plan mode). So a single
# -- step on an expensive model under a small budget was admitted and could
# -- overshoot by its full actual cost — the "ONE hard budget ceiling" thesis
# -- was false for step 0. The fix: admit against max(prior_high_cost, estimate).


def test_finding1_single_expensive_step_blocked_before_dispatch() -> None:
    """Single over-budget step is refused before any dispatch — req 010 (MUST).

    The ceiling must not be soft on step 0: admission uses the model-aware
    estimate, so an expensive single step under a small budget never dispatches.
    """
    step = PipelineStep(name="big", prompt="x" * 8000, model="claude-opus-4-8")
    est = _estimate_step_cost(step)
    # -- non-vacuity guard: the estimate must be meaningfully above the old
    # -- $0.001 floor, else this would pass even with the bug present.
    assert est > 0.002, f"estimator too cheap to exercise the gap (est=${est})"
    budget = est / 2  # -- below the model-aware estimate, above the old floor

    called: list[str] = []

    def dispatch(prompt: str, model: str, opts=None) -> dict:
        called.append(prompt)
        return {"status": "done", "raw_output": "ok", "cost_usd": 5.0}

    spec = PipelineSpec(name="t", budget_usd=budget, steps=[step])
    env = run_pipeline(spec, dispatch=dispatch)

    assert called == [], "expensive single step was dispatched despite over-budget estimate"
    assert env["status"] == "partial"
    assert "ERR_BUDGET_EXCEEDED" in env.get("error", "")


# ── Finding 10: the run envelope must surface budget_usd ──


def test_finding10_run_envelope_includes_budget_usd() -> None:
    """The apply envelope carries budget_usd so an overshoot is visible in-band."""
    spec = PipelineSpec(name="t", budget_usd=2.5, steps=[PipelineStep(name="s", prompt="p")])

    def dispatch(prompt: str, model: str, opts=None) -> dict:
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    env = run_pipeline(spec, dispatch=dispatch)
    assert env["budget_usd"] == 2.5


# ── Finding 2: req 023 lists per-step `duration` as a MUST ──


def test_finding2_step_record_carries_measured_duration() -> None:
    """Each step record carries a measured duration_sec — req 023 (MUST).

    A sleeping dispatch proves it is timed, not hardcoded to zero.
    """
    spec = PipelineSpec(name="t", budget_usd=1.0, steps=[PipelineStep(name="s", prompt="p")])

    def slow_dispatch(prompt: str, model: str, opts=None) -> dict:
        import time as _time  # noqa: PLC0415

        _time.sleep(0.02)
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    env = run_pipeline(spec, dispatch=slow_dispatch)
    rec = env["steps"][0]
    assert "duration_sec" in rec, "step record is missing the MUST field duration_sec"
    assert isinstance(rec["duration_sec"], float)
    # -- Two-sided: the lower bound kills a hardcoded-0; the upper bound kills the
    # -- arithmetic-direction mutant (monotonic()+start / *start / /start all
    # -- explode far past 0.5s, since monotonic() is seconds-since-boot). The real
    # -- elapsed is the 0.02s sleep plus a few ms of overhead — well inside [0.02, 0.5).
    assert 0.02 <= rec["duration_sec"] < 0.5, "duration_sec not actually measured"


# ── Finding 6: the failed-ref guard must respect the placeholder DOMAIN ──


def test_finding6_input_named_like_failed_step_is_not_falsely_aborted() -> None:
    """An inputs.X ref colliding with a FAILED step's name still resolves.

    The failed-ref guard only fires on steps.* refs, not inputs.* (req 021/024).
    """
    spec = PipelineSpec(
        name="t",
        budget_usd=1.0,
        steps=[
            PipelineStep(name="build", prompt="do build", on_fail="continue"),
            PipelineStep(name="use", prompt="ship {{inputs.build}}"),
        ],
    )
    seen: list[str] = []

    def dispatch(prompt: str, model: str, opts=None) -> dict:
        seen.append(prompt)
        if "do build" in prompt:
            return {"status": "error", "raw_output": "", "cost_usd": 0.0}
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    env = run_pipeline(spec, inputs={"build": "ARTIFACT"}, dispatch=dispatch)

    assert "ship ARTIFACT" in seen, "the inputs.build placeholder was falsely treated as a failed step ref"
    assert env["steps"][1]["status"] == "done"


# ── Finding 4: req 030 apply-path exit codes (done->0, partial->1) ──
# -- Both legs are pinned with ZERO dispatch and ZERO mocking: a zero-step
# -- pipeline is status "done" (-> exit 0); a sub-floor budget trips the gate on
# -- step 0 before any dispatch (-> partial -> exit 1). The dangerous direction
# -- (a partial silently reported as success) is the one this repo exists to stop.


def test_finding4_cli_done_exits_0(tmp_path, capsys) -> None:
    """A fully-successful (zero-step) pipeline exits 0 (req 030)."""
    p = tmp_path / "pipe.yaml"
    p.write_text("name: t\nbudget_usd: 1.0\nsteps: []\n")
    code = main(["pipeline", str(p)])
    out = capsys.readouterr().out
    assert code == 0
    assert '"status": "done"' in out


def test_finding4_cli_partial_exits_1(tmp_path, capsys) -> None:
    """A partial pipeline (budget tripped pre-dispatch) exits 1 — req 030.

    A partial must never masquerade as success.
    """
    p = tmp_path / "pipe.yaml"
    p.write_text(
        textwrap.dedent("""\
        name: t
        budget_usd: 0.0000001
        steps:
          - name: s
            prompt: "x"
    """)
    )
    code = main(["pipeline", str(p)])
    out = capsys.readouterr().out
    assert code == 1
    assert "ERR_BUDGET_EXCEEDED" in out
    assert '"status": "partial"' in out


# -- sig: mgh-6201.cd.bd955f.25b9.28dc6c
