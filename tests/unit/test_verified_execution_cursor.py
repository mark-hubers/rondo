# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for Rondo-REQ-115: verified execution — rondo checks the work itself.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved — a different AI authored, Claude implements). The verify
feature DOES NOT EXIST at authoring time: verify being an unknown step field
today is itself a valid RED. Transcription notes (documented, not silent):
SPDX header normalized to the house form; the author's Windows backslash
.replace() escaping removed (POSIX paths). Assertions untouched.

THE CONTRACT (driver: reports/inline-control-review-2026-06-11.md — the
hostile reviewer's "honor system" finding): a step may DECLARE what the
world must look like afterwards (files, cmd exit); the ENGINE verifies it
ITSELF — the model's success claim cannot override rondo's own observation.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from rondo.pipeline import PipelineError, load_pipeline, run_pipeline


def test_r003_cmd_string_rejected(tmp_path) -> None:
    """Rondo-REQ-115 r003: verify.cmd as a string -> PipelineError at load. RED today."""
    yaml_content = textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              cmd: "echo hello"
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    with pytest.raises(PipelineError):
        load_pipeline(p)


def test_r020_missing_file_fails_step(tmp_path) -> None:
    """Rondo-REQ-115 r020: missing verify file -> step error, verification ok=false. RED today."""
    target = str(tmp_path / "out.txt")
    yaml_content = textwrap.dedent(f"""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              files: ["{target}"]
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    assert res["steps"][0]["status"] == "error"
    assert res["steps"][0]["verification"]["ok"] is False


def test_r020_file_present_passes(tmp_path) -> None:
    """Rondo-REQ-115 r020: present verify file -> step done, verification ok=true."""
    target_path = tmp_path / "out.txt"
    yaml_content = textwrap.dedent(f"""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              files: ["{target_path}"]
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        target_path.write_text("success")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    assert res["steps"][0]["status"] == "done"
    assert res["steps"][0]["verification"]["ok"] is True


def test_r020_cmd_exit_checked(tmp_path) -> None:
    """Rondo-REQ-115 r020: verify cmd exit code is checked against expect_exit."""
    yaml_content = textwrap.dedent(f"""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step_fail
            prompt: "fail"
            on_fail: continue
            verify:
              cmd: ["{sys.executable}", "-c", "import sys; sys.exit(3)"]
              expect_exit: 0
          - name: step_pass
            prompt: "pass"
            verify:
              cmd: ["{sys.executable}", "-c", "import sys; sys.exit(3)"]
              expect_exit: 3
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    assert res["steps"][0]["status"] == "error"
    assert res["steps"][1]["status"] == "done"


def test_r020_model_claim_cannot_override(tmp_path) -> None:
    """Rondo-REQ-115 r020: a loud passed=true claim cannot override a missing file."""
    target = str(tmp_path / "out.txt")
    yaml_content = textwrap.dedent(f"""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              files: ["{target}"]
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        return {"status": "done", "raw_output": '{"passed": true}', "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    assert res["steps"][0]["status"] == "error"


def test_r021_envelope_carries_verification(tmp_path) -> None:
    """Rondo-REQ-115 r021: passing verify populates the envelope verification dict."""
    target_path = tmp_path / "out.txt"
    yaml_content = textwrap.dedent(f"""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              files: ["{target_path}"]
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        target_path.write_text("data")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    ver = res["steps"][0].get("verification", {})
    assert ver.get("ok") is True
    assert len(ver.get("checked_files", [])) > 0


def test_r023_verify_block_placeholder_substitution(tmp_path) -> None:
    """RONDO-412: {{inputs.X}} inside a verify block IS substituted before the check.

    Labeled Claude test — closes REQ-115's documented v1 gap so the flagship
    pipeline (which verifies {{inputs.workspace}}/file) actually works.
    """
    yaml_content = textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
            verify:
              files: ["{{inputs.ws}}/made.txt"]
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)
    target = tmp_path / "made.txt"

    def mock_dispatch(prompt, model):
        target.write_text("real")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, inputs={"ws": str(tmp_path)}, dispatch=mock_dispatch)
    assert res["steps"][0]["status"] == "done"
    assert res["steps"][0]["verification"]["ok"] is True


def test_r022_no_verify_no_regression(tmp_path) -> None:
    """Rondo-REQ-115 r022: a step without verify behaves exactly as before."""
    yaml_content = textwrap.dedent("""\
        name: test
        budget_usd: 1.0
        steps:
          - name: step1
            prompt: "do it"
    """)
    p = tmp_path / "pipe.yaml"
    p.write_text(yaml_content)
    pipeline = load_pipeline(p)

    def mock_dispatch(prompt, model):
        return {"status": "done", "raw_output": "done", "cost_usd": 0.01}

    res = run_pipeline(pipeline, dispatch=mock_dispatch)
    step_record = res["steps"][0]
    assert step_record["status"] == "done"
    assert step_record.get("verification") is None


# -- sig: mgh-6201.cd.bd955f.90a7.bf353f
