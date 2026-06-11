# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for Rondo-REQ-114: the prompt-pipeline engine.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run, in three parts (Cursor usage-limited;
separation of duties preserved — gemini authored, Claude implements).
The module under test (src/rondo/pipeline.py) DOES NOT EXIST at authoring
time: a collection/import RED is the expected initial state.

Transcription notes (documented, not silent): (1) Part B2 called
run_pipeline(spec, dispatch) positionally where the agreed signature is
run_pipeline(spec, inputs=None, dispatch=None, plan=False) — re-pointed to
dispatch= keyword. (2) Part B2's YAML fixtures omitted the REQUIRED
name/budget_usd fields its own Part A pins as the schema — added, matching
Part A/B1's fixtures. Assertions untouched throughout.

Contract: Rondo-REQ-114 reqs 001-024 — declarative YAML pipelines with
explicit placeholder wiring, per-step contracts, a hard budget ceiling,
plan-before-apply purity, and NO silent empty-output flow between steps
(the rondo_chain disease this engine exists to kill).
"""

from __future__ import annotations

import json
import textwrap

import pytest

from rondo.pipeline import PipelineError, load_pipeline, run_pipeline


def test_r001_unknown_fields_rejected(tmp_path) -> None:
    """R001: Reject unknown top-level and step-level fields, naming the field."""
    yaml_top = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        bogus_field: 123
        steps: []
    """)
    p_top = tmp_path / "top.yaml"
    p_top.write_text(yaml_top)
    with pytest.raises(PipelineError, match="bogus_field"):
        load_pipeline(p_top)

    yaml_step = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "hi"
            wrong_key: 123
    """)
    p_step = tmp_path / "step.yaml"
    p_step.write_text(yaml_step)
    with pytest.raises(PipelineError, match="wrong_key"):
        load_pipeline(p_step)


def test_r002_duplicate_step_names_rejected(tmp_path) -> None:
    """R002: Reject duplicate step names."""
    yaml_dup = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "hi"
          - name: s1
            prompt: "bye"
    """)
    p_dup = tmp_path / "dup.yaml"
    p_dup.write_text(yaml_dup)
    with pytest.raises(PipelineError):
        load_pipeline(p_dup)


def test_r002_bad_on_fail_and_retries_rejected(tmp_path) -> None:
    """R002: Reject invalid on_fail and retries values."""
    yaml_fail = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "hi"
            on_fail: "explode"
    """)
    p_fail = tmp_path / "fail.yaml"
    p_fail.write_text(yaml_fail)
    with pytest.raises(PipelineError):
        load_pipeline(p_fail)

    yaml_retries = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "hi"
            retries: 5
    """)
    p_retries = tmp_path / "retries.yaml"
    p_retries.write_text(yaml_retries)
    with pytest.raises(PipelineError):
        load_pipeline(p_retries)


def test_r003_unresolved_placeholder_never_dispatches(tmp_path) -> None:
    """R003: Unresolved placeholders abort BEFORE any dispatch happens."""
    yaml_unres = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "Hi {{inputs.missing}}"
    """)
    p_unres = tmp_path / "unres.yaml"
    p_unres.write_text(yaml_unres)

    calls = []

    def mock_dispatch(prompt: str, model: str):
        calls.append((prompt, model))
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    try:
        spec = load_pipeline(p_unres)
        run_pipeline(spec, inputs={}, dispatch=mock_dispatch)
    except PipelineError:
        pass

    assert calls == []


def test_r004_forward_reference_rejected(tmp_path) -> None:
    """R004: Reject forward references in placeholders at load time."""
    yaml_fwd = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "Use {{steps.s2.output}}"
          - name: s2
            prompt: "Generate"
    """)
    p_fwd = tmp_path / "fwd.yaml"
    p_fwd.write_text(yaml_fwd)
    with pytest.raises(PipelineError):
        load_pipeline(p_fwd)


def test_r005_expect_contract_failure(tmp_path) -> None:
    """R005: Missing expect.required key -> step error with ERR_CONTRACT naming the key."""
    yaml_expect = textwrap.dedent("""\
        name: p1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "Extract labels"
            expect:
              required: ["labels"]
    """)
    p_expect = tmp_path / "expect.yaml"
    p_expect.write_text(yaml_expect)

    def mock_dispatch(prompt: str, model: str):
        return {"status": "done", "raw_output": '{"other": 1}', "cost_usd": 0.0}

    spec = load_pipeline(p_expect)
    envelope = run_pipeline(spec, inputs={}, dispatch=mock_dispatch)

    steps = envelope.get("steps", [])
    step_record = steps["s1"] if isinstance(steps, dict) else steps[0]

    assert step_record.get("status") == "error"
    assert "ERR_CONTRACT" in step_record.get("error", "")
    assert "labels" in step_record.get("error", "")


def test_r010_budget_ceiling_stops_with_partials(tmp_path) -> None:
    """R010: Budget ceiling stops execution early; completed results preserved."""
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: p1
          - name: s2
            prompt: p2
          - name: s3
            prompt: p3
    """)
    )
    calls = []

    def mock_dispatch(prompt, model=None):
        calls.append(prompt)
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.6}

    spec = load_pipeline(yaml_path)
    envelope = run_pipeline(spec, dispatch=mock_dispatch)
    out_str = json.dumps(envelope)
    assert "ERR_BUDGET_EXCEEDED" in out_str
    assert envelope["steps"][0]["raw_output"] == "ok"
    assert len(calls) < 3


def test_r011_plan_mode_never_dispatches(tmp_path) -> None:
    """R011: Plan mode never dispatches; lists steps and an estimate."""
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 5.0
        steps:
          - name: s1
            prompt: p1
          - name: s2
            prompt: p2
    """)
    )
    calls = []

    def mock_dispatch(prompt, model=None):
        calls.append(prompt)
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.1}

    spec = load_pipeline(yaml_path)
    envelope = run_pipeline(spec, dispatch=mock_dispatch, plan=True)
    out_str = json.dumps(envelope)
    assert calls == []
    assert "s1" in out_str and "s2" in out_str
    assert "estimate" in out_str


def test_r012_plan_mode_zero_side_effects(tmp_path, monkeypatch) -> None:
    """R012: Plan mode has zero filesystem side effects (RONDO-403 purity)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: p1
    """)
    )

    def mock_dispatch(prompt, model=None):
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.1}

    spec = load_pipeline(yaml_path)
    run_pipeline(spec, dispatch=mock_dispatch, plan=True)
    audit_dir = tmp_path / "audit"
    assert not audit_dir.exists() or not any(audit_dir.iterdir())


def test_r021_on_fail_stop_halts(tmp_path) -> None:
    """R021: on_fail stop (default) halts the pipeline at the failed step."""
    yaml_path = tmp_path / "pipe.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "p1"
          - name: s2
            prompt: "p2"
    """)
    )
    calls = 0

    def dispatch(prompt, model):
        nonlocal calls
        calls += 1
        return {"status": "error", "raw_output": "", "cost_usd": 0.0}

    pipeline = load_pipeline(yaml_path)
    envelope = run_pipeline(pipeline, dispatch=dispatch)
    assert envelope["status"] == "partial"
    assert calls == 1


def test_r021_continue_no_silent_empty_flow(tmp_path) -> None:
    """R021: continue never silently feeds a FAILED step's empty output onward."""
    yaml_path = tmp_path / "pipe.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "s1-marker"
            on_fail: continue
          - name: s2
            prompt: "Use {{steps.s1.output}}"
    """)
    )
    prompts = []

    def dispatch(prompt, model):
        prompts.append(prompt)
        if "s1-marker" in prompt:
            return {"status": "error", "raw_output": "", "cost_usd": 0.0}
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    pipeline = load_pipeline(yaml_path)
    try:
        envelope = run_pipeline(pipeline, dispatch=dispatch)
        assert envelope["status"] == "error"
    except PipelineError:
        pass
    assert "Use " not in prompts
    assert "Use" not in prompts


def test_r022_retries_redispatch(tmp_path) -> None:
    """R022: retries re-dispatch a failed step; success on retry ends done."""
    yaml_path = tmp_path / "pipe.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "p1"
            retries: 1
    """)
    )
    calls = 0

    def dispatch(prompt, model):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "error", "raw_output": "", "cost_usd": 0.0}
        return {"status": "done", "raw_output": "fine", "cost_usd": 0.0}

    pipeline = load_pipeline(yaml_path)
    envelope = run_pipeline(pipeline, dispatch=dispatch)
    assert calls == 2
    assert envelope["steps"][0]["status"] == "done"


def test_r023_r024_envelope_and_explicit_wiring(tmp_path) -> None:
    """R023/R024: full envelope + exact placeholder wiring, no auto-append banner."""
    yaml_path = tmp_path / "pipe.yaml"
    yaml_path.write_text(
        textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "p1"
          - name: s2
            prompt: "Refine: {{steps.s1.output}} now"
    """)
    )
    prompts = []

    def dispatch(prompt, model):
        prompts.append(prompt)
        if "p1" in prompt:
            return {"status": "done", "raw_output": "ALPHA-7", "cost_usd": 0.01}
        return {"status": "done", "raw_output": "beta", "cost_usd": 0.01}

    pipeline = load_pipeline(yaml_path)
    envelope = run_pipeline(pipeline, dispatch=dispatch)
    assert "Refine: ALPHA-7 now" in prompts
    assert not any("Previous step output" in p for p in prompts)
    assert envelope["total_cost_usd"] == pytest.approx(0.02)
    assert all(step["raw_output"] for step in envelope["steps"])


# -- sig: mgh-6201.cd.bd955f.f764.d0a330
