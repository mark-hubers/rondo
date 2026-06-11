# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for Rondo-REQ-116: the scope guard.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved). rondo.scope and the strict_scope/allow_broad fields DO NOT
EXIST at authoring time — import/load REDs are the expected initial state.
Transcription: added `-> None` hints + ruff import order; assertions untouched.

THE CONTRACT (Mark's words): rondo's basic job is one-or-two things per step.
The scope guard makes that the DEFAULT — it scores a step's ask, WARNS on fat
steps by default, blocks them in opt-in strict mode, and exempts genuinely
broad steps via allow_broad. A lie needs ambiguity; a one-thing step has none.
"""

from __future__ import annotations

import textwrap

import pytest

from rondo.pipeline import PipelineError, load_pipeline, run_pipeline
from rondo.scope import _SCOPE_THRESHOLD, scope_score

_FAT = "Create a.py and then write tests in b.py, also update c.py, additionally run the linter"


def mock_dispatch(prompt: str, model: str) -> dict:
    """Injected hermetic dispatch — always a clean done."""
    return {"status": "done", "raw_output": "done", "cost_usd": 0.0}


def test_r001_focused_prompt_low_score() -> None:
    """Rondo-REQ-116 r001: a focused prompt scores <= 1."""
    res = scope_score("Create the file foo.py with an add() function.")
    assert res["score"] <= 1


def test_r001_bundled_prompt_high_score() -> None:
    """Rondo-REQ-116 r001: a bundled prompt scores >= threshold with signals."""
    res = scope_score(_FAT)
    assert res["score"] >= _SCOPE_THRESHOLD
    assert len(res["signals"]) > 0


def test_r002_deterministic() -> None:
    """Rondo-REQ-116 r002: scope_score is pure and deterministic."""
    prompt = "Do X and then do Y, also Z."
    assert scope_score(prompt) == scope_score(prompt)


def test_r010_allow_broad_exempts(tmp_path) -> None:
    """Rondo-REQ-116 r010: allow_broad exempts a fat step even in strict mode."""
    pipe_file = tmp_path / "pipe.yaml"
    pipe_file.write_text(
        textwrap.dedent(f"""\
        name: test_pipe
        budget_usd: 1.0
        strict_scope: true
        steps:
          - name: fat_step
            prompt: "{_FAT}"
            allow_broad: true
    """)
    )
    pipe = load_pipeline(str(pipe_file))
    assert pipe is not None


def test_r011_strict_blocks_fat_step(tmp_path) -> None:
    """Rondo-REQ-116 r011: strict_scope blocks a fat step lacking allow_broad."""
    pipe_file = tmp_path / "pipe.yaml"
    pipe_file.write_text(
        textwrap.dedent(f"""\
        name: test_pipe
        budget_usd: 1.0
        strict_scope: true
        steps:
          - name: fat_step
            prompt: "{_FAT}"
    """)
    )
    with pytest.raises(PipelineError) as exc:
        load_pipeline(str(pipe_file))
    assert "fat_step" in str(exc.value)


def test_r012_default_warns_not_blocks(tmp_path) -> None:
    """Rondo-REQ-116 r012: default mode warns on a fat step, never blocks."""
    pipe_file = tmp_path / "pipe.yaml"
    pipe_file.write_text(
        textwrap.dedent(f"""\
        name: test_pipe
        budget_usd: 1.0
        steps:
          - name: fat_step
            prompt: "{_FAT}"
    """)
    )
    pipe = load_pipeline(str(pipe_file))
    env = run_pipeline(pipe, dispatch=mock_dispatch)
    assert "scope_warning" in env["steps"][0]
    assert env["steps"][0]["scope_warning"]["score"] >= _SCOPE_THRESHOLD


def test_r014_focused_no_warning(tmp_path) -> None:
    """Rondo-REQ-116 r014: a focused step produces no scope_warning."""
    pipe_file = tmp_path / "pipe.yaml"
    pipe_file.write_text(
        textwrap.dedent("""\
        name: test_pipe
        budget_usd: 1.0
        steps:
          - name: focused_step
            prompt: "Create the file foo.py with an add() function."
    """)
    )
    pipe = load_pipeline(str(pipe_file))
    env = run_pipeline(pipe, dispatch=mock_dispatch)
    assert env["steps"][0].get("scope_warning") is None


def test_r014_no_strict_no_regression(tmp_path) -> None:
    """Rondo-REQ-116 r014: a normal 2-step focused pipeline runs cleanly, no warnings."""
    pipe_file = tmp_path / "pipe.yaml"
    pipe_file.write_text(
        textwrap.dedent("""\
        name: test_pipe
        budget_usd: 1.0
        steps:
          - name: step_one
            prompt: "Create foo.py."
          - name: step_two
            prompt: "Create bar.py."
    """)
    )
    pipe = load_pipeline(str(pipe_file))
    env = run_pipeline(pipe, dispatch=mock_dispatch)
    for step in env["steps"]:
        assert step.get("scope_warning") is None


# -- sig: mgh-6201.cd.bd955f.f48b.bc714a
