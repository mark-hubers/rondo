# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Live Python API integration tests (RONDO-284, VER-001).

No mocks, no patches, no fakes: every test calls real API dispatch paths.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import textwrap
import time
from pathlib import Path

import pytest

from rondo.mcp_dispatch import rondo_run_file, rondo_run_status

# -- RONDO-341: live tests need the REAL binary — on a machine without it
# -- (Linux container, fresh CI) they SKIP honestly instead of failing.
# -- Never fake the binary here: that would silently mock an unmocked seam.
## -- RONDO-435: marked `cloud` so the live/paid dispatches are opt-in
## -- (`pytest -m cloud`) and never run in the default/CI gate, where real-LLM
## -- output variance + provider latency caused nondeterministic flakes.
pytestmark = [
    pytest.mark.cloud,
    pytest.mark.skipif(
        shutil.which("claude") is None,
        reason="live dispatch tests require the real claude binary (RONDO-341)",
    ),
]


def _run_json(**kwargs) -> dict:
    return json.loads(rondo_run_file(**kwargs))


def _assert_results(payload: dict) -> None:
    assert payload.get("status") in {"done", "partial", "skipped"}, payload
    assert isinstance(payload.get("tasks"), list) and payload["tasks"], payload


def test_api_prompt_returns_results() -> None:
    payload = _run_json(prompt="Return JSON with result='API_PROMPT_OK_284'.", model="sonnet", dry_run=False)
    _assert_results(payload)


def test_api_round_file_python_multistep() -> None:
    with tempfile.TemporaryDirectory() as td:
        round_file = Path(td) / "api_live.py"
        round_file.write_text(
            textwrap.dedent(
                """\
                from rondo.engine import Round, Task

                def build_round():
                    return Round(
                        name="api-live-py",
                        tasks=[
                            Task(
                                name="a",
                                instruction="Return JSON with result='API_PY_1_284'.",
                                done_when="Return API_PY_1_284 in JSON.",
                            ),
                            Task(
                                name="b",
                                instruction="Return JSON with result='API_PY_2_284'.",
                                done_when="Return API_PY_2_284 in JSON.",
                            ),
                        ],
                    )
                """
            ),
            encoding="utf-8",
        )
        payload = _run_json(file_path=str(round_file), model="sonnet", execution="subprocess", dry_run=False)
    _assert_results(payload)
    assert len(payload["tasks"]) == 2, payload


def test_api_round_file_yaml_dispatches() -> None:
    with tempfile.TemporaryDirectory() as td:
        round_file = Path(td) / "api_live.yaml"
        round_file.write_text(
            textwrap.dedent(
                """\
                name: api-live-yaml
                tasks:
                  - name: one
                    instruction: "Return JSON with result='API_YAML_1_284'."
                    done_when: "Return API_YAML_1_284 in JSON."
                  - name: two
                    instruction: "Return JSON with result='API_YAML_2_284'."
                    done_when: "Return API_YAML_2_284 in JSON."
                """
            ),
            encoding="utf-8",
        )
        payload = _run_json(file_path=str(round_file), model="sonnet", execution="subprocess", dry_run=False)
    _assert_results(payload)
    assert len(payload["tasks"]) == 2, payload


def test_api_gemini_flash_http_works() -> None:
    payload = _run_json(prompt="Return JSON with result='API_HTTP_OK_284'.", model="gemini:flash", dry_run=False)
    _assert_results(payload)


def test_api_execution_subprocess_works() -> None:
    payload = _run_json(
        prompt="Return JSON with result='API_SUBPROCESS_OK_284'.",
        model="sonnet",
        execution="subprocess",
        dry_run=False,
    )
    _assert_results(payload)


def test_api_execution_inline_with_session_returns_plan() -> None:
    payload = _run_json(
        prompt="Return JSON with result='API_INLINE_PLAN_284'.",
        model="sonnet",
        execution="inline",
        _session=object(),
        dry_run=False,
    )
    assert payload.get("kind") == "inline_dispatch_plan", payload
    assert payload.get("status") == "plan", payload


def test_api_background_dispatch_starts_and_finishes() -> None:
    start = _run_json(
        prompt="Return JSON with result='API_BG_OK_284'.",
        model="sonnet",
        execution="subprocess",
        background=True,
        dry_run=False,
    )
    dispatch_id = str(start.get("dispatch_id", "") or "")
    assert dispatch_id, start

    final_payload = {}
    for _ in range(45):
        status = json.loads(rondo_run_status(dispatch_id=dispatch_id))
        if status.get("status") in {"done", "partial", "error"} and isinstance(status.get("tasks"), list):
            final_payload = status
            break
        time.sleep(2)
    _assert_results(final_payload)


def test_api_rules_override_propagates() -> None:
    payload = _run_json(
        prompt="Reply with one line only.",
        model="sonnet",
        execution="subprocess",
        rules="Always include token RULES_OVERRIDE_284 in the final result field.",
        dry_run=False,
    )
    _assert_results(payload)
    combined = json.dumps(payload)
    assert "RULES_OVERRIDE_284" in combined, payload


def test_api_json_schema_enforced() -> None:
    schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "confidence": {"type": "number"},
                "result": {"type": "string"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "rondo_schema_marker": {"type": "string"},
            },
            "required": ["passed", "confidence", "result", "issues", "rondo_schema_marker"],
            "additionalProperties": False,
        }
    )
    payload = _run_json(
        prompt="Return a response with rondo_schema_marker='SCHEMA_284'.",
        model="sonnet",
        execution="subprocess",
        json_schema=schema,
        dry_run=False,
    )
    _assert_results(payload)
    raw = str(payload["tasks"][0].get("raw_output", "") or "")
    assert "SCHEMA_284" in raw, payload


def test_api_bad_model_returns_error_envelope() -> None:
    payload = _run_json(prompt="Return JSON.", model="bad-model-284", dry_run=False)
    assert payload.get("status") == "error", payload
    assert payload.get("error_code"), payload
    assert payload.get("error_help"), payload


def test_api_timeout_returns_clean_error() -> None:
    payload = _run_json(
        prompt="Take your time and think deeply before answering.",
        model="sonnet",
        execution="subprocess",
        timeout_sec=1,
        dry_run=False,
    )
    assert payload.get("status") in {"error", "partial"}, payload
    if payload.get("status") == "error":
        assert payload.get("error_code"), payload


def test_api_dry_run_true_returns_plan_no_live_call() -> None:
    payload = _run_json(
        prompt="Return JSON with result='API_DRYRUN_PLAN_284'.",
        model="sonnet",
        execution="inline",
        dry_run=True,
    )
    assert payload.get("kind") == "inline_dispatch_plan", payload
    assert payload.get("status") == "plan", payload


# -- sig: mgh-bc0c.f2.fecb75.4de6.538f7f
