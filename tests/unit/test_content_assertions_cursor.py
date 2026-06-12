# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for Rondo-REQ-115 v0.2 reqs 040-043: content assertions.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved). The contains/min_bytes verify fields DO NOT EXIST at
authoring time — load/verify REDs are the expected initial state.

Transcription re-points (documented, not silent): the author read the result
off `pipe.steps[0].verification` (spec attribute) — the verdict actually
lives in the ENVELOPE returned by run_pipeline, so re-pointed to
env["steps"][0][...]; and added the required `name:` to each step (the loader
mandates it). Assertions (ok/error/status, the substrings) untouched.

THE CONTRACT: file EXISTS is not file is RIGHT. contains[] requires every
substring present in the declared files; min_bytes requires a real size —
both catch the "I wrote it" lie when the file is empty/stub/wrong.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from rondo.pipeline import PipelineError, load_pipeline, run_pipeline


def test_r040_contains_present_passes(tmp_path) -> None:
    """Req 040: a declared substring present in the file -> verified."""
    target = tmp_path / "out.py"
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent(f"""\
        name: t1
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "write add"
            verify:
              files: ["{target}"]
              contains: ["def add"]
    """)
    )
    pipe = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch(prompt, model):
        Path(target).write_text("def add(a, b): return a + b")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env = run_pipeline(pipe, dispatch=dispatch)
    assert env["steps"][0]["verification"]["ok"] is True
    assert env["steps"][0]["status"] == "done"


def test_r040_contains_missing_fails(tmp_path) -> None:
    """Req 040: a declared substring missing -> error, naming the absent substring."""
    target = tmp_path / "out.py"
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent(f"""\
        name: t2
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "write add"
            verify:
              files: ["{target}"]
              contains: ["def add"]
    """)
    )
    pipe = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch(prompt, model):
        Path(target).write_text("def sub(): pass")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env = run_pipeline(pipe, dispatch=dispatch)
    assert env["steps"][0]["verification"]["ok"] is False
    assert env["steps"][0]["status"] == "error"
    assert "def add" in env["steps"][0]["verification"]["error"]


def test_r040_contains_multiple_all_required(tmp_path) -> None:
    """Req 040: every substring required — one missing fails, naming it."""
    target = tmp_path / "out.txt"
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent(f"""\
        name: t3
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "write alpha beta"
            verify:
              files: ["{target}"]
              contains: ["alpha", "beta"]
    """)
    )
    pipe = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch(prompt, model):
        Path(target).write_text("alpha only here")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env = run_pipeline(pipe, dispatch=dispatch)
    assert env["steps"][0]["verification"]["ok"] is False
    assert "beta" in env["steps"][0]["verification"]["error"]


def test_r041_min_bytes_enforced(tmp_path) -> None:
    """Req 041: min_bytes enforced on total declared-file size, both directions."""
    target = tmp_path / "out.txt"
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent(f"""\
        name: t4
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "write big"
            verify:
              files: ["{target}"]
              min_bytes: 50
    """)
    )

    pipe1 = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch_tiny(prompt, model):
        Path(target).write_text("tiny")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env1 = run_pipeline(pipe1, dispatch=dispatch_tiny)
    assert env1["steps"][0]["verification"]["ok"] is False

    pipe2 = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch_big(prompt, model):
        Path(target).write_text("x" * 50)
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env2 = run_pipeline(pipe2, dispatch=dispatch_big)
    assert env2["steps"][0]["verification"]["ok"] is True


def test_r042_contains_without_files_rejected(tmp_path) -> None:
    """Req 042: contains with no files key is a definition error."""
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent("""\
        name: t5
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "no files"
            verify:
              contains: ["x"]
    """)
    )
    with pytest.raises(PipelineError):
        load_pipeline(tmp_path / "pipe.yaml")


def test_r040_no_regression_files_only(tmp_path) -> None:
    """Req 040: a files-only verify (no contains/min_bytes) is unchanged."""
    target = tmp_path / "out.txt"
    (tmp_path / "pipe.yaml").write_text(
        textwrap.dedent(f"""\
        name: t6
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "just file"
            verify:
              files: ["{target}"]
    """)
    )
    pipe = load_pipeline(tmp_path / "pipe.yaml")

    def dispatch(prompt, model):
        Path(target).write_text("exists")
        return {"status": "done", "raw_output": "done", "cost_usd": 0.0}

    env = run_pipeline(pipe, dispatch=dispatch)
    assert env["steps"][0]["verification"]["ok"] is True


# -- sig: mgh-6201.cd.bd955f.bb04.8e17c5
