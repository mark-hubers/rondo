# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Pipeline v1.1 — the Claude-driver additions (RONDO-407).

VER-001: Product acceptance / unit test coverage.

LABELED CLAUDE TESTS (the v1.0 engine is judged by the gemini-authored
tests/unit/test_pipeline_engine_cursor.py; these pin the two additions the
Claude-driver flagship needs):

1. passed=false GATE — Mark's core demand: the engine must get a real
   did-it-or-didn't answer from each step and REFUSE to advance when the
   model itself says passed=false. Retries become the fix loop.
2. STEP TOOL GRANTS — tools/max_turns/add_dir step fields reach the
   dispatch seam (3-arg), while 2-arg injected dispatches keep working.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from rondo.pipeline import PipelineError, load_pipeline, run_pipeline


def _pipe(tmp_path: Path, body: str) -> object:
    """Write + load a pipeline YAML."""
    path = tmp_path / "p.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_pipeline(path)


def test_passed_false_blocks_advancement(tmp_path: Path) -> None:
    """A step whose output says passed=false FAILS — the next step never runs."""
    spec = _pipe(
        tmp_path,
        """\
        name: gate
        budget_usd: 1.0
        steps:
          - name: build
            prompt: "do the thing"
          - name: next_step
            prompt: "should never run"
        """,
    )
    calls: list[str] = []

    def dispatch(prompt: str, model: str) -> dict:
        calls.append(prompt)
        return {"status": "done", "raw_output": '{"passed": false, "issues": ["did not finish"]}', "cost_usd": 0.0}

    envelope = run_pipeline(spec, dispatch=dispatch)
    assert envelope["status"] == "partial"
    assert len(calls) == 1, "the engine must not advance past a self-reported failure"
    assert "ERR_STEP_REPORTED_FAILURE" in envelope["steps"][0]["error"]
    assert "did not finish" in envelope["steps"][0]["error"]


def test_passed_false_then_retry_fix_loop(tmp_path: Path) -> None:
    """retries: 1 — first attempt admits failure, second succeeds: the fix loop."""
    spec = _pipe(
        tmp_path,
        """\
        name: fixloop
        budget_usd: 1.0
        steps:
          - name: build
            prompt: "do the thing"
            retries: 1
        """,
    )
    n = {"v": 0}

    def dispatch(prompt: str, model: str) -> dict:
        n["v"] += 1
        if n["v"] == 1:
            return {"status": "done", "raw_output": '{"passed": false, "issues": ["broke"]}', "cost_usd": 0.0}
        return {"status": "done", "raw_output": '{"passed": true, "result": "fixed"}', "cost_usd": 0.0}

    envelope = run_pipeline(spec, dispatch=dispatch)
    assert n["v"] == 2
    assert envelope["steps"][0]["status"] == "done"
    assert envelope["status"] == "done"


def test_step_tool_grants_reach_dispatch(tmp_path: Path) -> None:
    """tools/max_turns/add_dir flow to a 3-arg dispatch seam."""
    spec = _pipe(
        tmp_path,
        """\
        name: grants
        budget_usd: 1.0
        steps:
          - name: edit_files
            prompt: "edit"
            tools: "Read,Write,Edit,Bash"
            max_turns: 12
            add_dir: "/tmp/workspace"
            timeout: 600
        """,
    )
    seen: dict = {}

    def dispatch(prompt: str, model: str, opts: dict) -> dict:
        seen.update(opts)
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    run_pipeline(spec, dispatch=dispatch)
    assert seen == {"tools": "Read,Write,Edit,Bash", "max_turns": 12, "add_dir": "/tmp/workspace", "timeout": 600}


def test_two_arg_dispatch_still_supported(tmp_path: Path) -> None:
    """Rail (req 025): plain (prompt, model) injected dispatches keep working."""
    spec = _pipe(
        tmp_path,
        """\
        name: compat
        budget_usd: 1.0
        steps:
          - name: s1
            prompt: "hi"
            tools: "Read"
        """,
    )

    def dispatch(prompt: str, model: str) -> dict:
        return {"status": "done", "raw_output": "ok", "cost_usd": 0.0}

    envelope = run_pipeline(spec, dispatch=dispatch)
    assert envelope["status"] == "done"


def test_bad_max_turns_rejected(tmp_path: Path) -> None:
    """Validation: negative max_turns is a definition error."""
    with pytest.raises(PipelineError, match="max_turns"):
        _pipe(
            tmp_path,
            """\
            name: bad
            budget_usd: 1.0
            steps:
              - name: s1
                prompt: "hi"
                max_turns: -3
            """,
        )


# -- sig: mgh-6201.cd.bd955f.88b3.d44316
