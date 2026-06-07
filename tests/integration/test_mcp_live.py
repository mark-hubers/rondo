# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Live MCP integration tests (RONDO-284, VER-001).

No mocks, no patches, no fakes: every test calls real MCP tools and dispatches.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import textwrap
import time
from pathlib import Path

import pytest

from rondo.mcp_server import create_mcp_server

# -- RONDO-341: live tests need the REAL binary — on a machine without it
# -- (Linux container, fresh CI) they SKIP honestly instead of failing.
# -- Never fake the binary here: that would silently mock an unmocked seam.
pytestmark = pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="live dispatch tests require the real claude binary (RONDO-341)",
)


def _call_mcp_tool(name: str, arguments: dict) -> dict:
    async def _inner() -> dict:
        server = create_mcp_server()
        payload = await server.call_tool(name, arguments)
        if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[1], dict):
            result_text = str(payload[1].get("result", "") or "")
        else:
            result_text = ""
        return json.loads(result_text) if result_text.strip() else {}

    return asyncio.run(_inner())


def _assert_results_envelope(payload: dict) -> None:
    assert payload.get("status") in {"done", "partial", "skipped"}, payload
    assert "tasks" in payload and isinstance(payload["tasks"], list), payload
    assert len(payload["tasks"]) >= 1, payload


def test_mcp_run_prompt_returns_results_envelope() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {"prompt": "Return JSON with result='MCP_PROMPT_OK_284'.", "model": "sonnet", "dry_run": False},
    )
    _assert_results_envelope(payload)


def test_mcp_run_round_file_python_multistep() -> None:
    with tempfile.TemporaryDirectory() as td:
        round_file = Path(td) / "round_live.py"
        round_file.write_text(
            textwrap.dedent(
                """\
                from rondo.engine import Round, Task

                def build_round():
                    return Round(
                        name="mcp-live-py",
                        tasks=[
                            Task(
                                name="step-1",
                                instruction="Return JSON with result='MCP_PY_STEP_1_284'.",
                                done_when="Return MCP_PY_STEP_1_284 in JSON.",
                            ),
                            Task(
                                name="step-2",
                                instruction="Return JSON with result='MCP_PY_STEP_2_284'.",
                                done_when="Return MCP_PY_STEP_2_284 in JSON.",
                            ),
                        ],
                    )
                """
            ),
            encoding="utf-8",
        )
        payload = _call_mcp_tool(
            "rondo_run",
            {"file_path": str(round_file), "model": "sonnet", "execution": "subprocess", "dry_run": False},
        )
    _assert_results_envelope(payload)
    assert len(payload["tasks"]) == 2, payload


def test_mcp_run_round_file_yaml_dispatches() -> None:
    with tempfile.TemporaryDirectory() as td:
        round_file = Path(td) / "round_live.yaml"
        round_file.write_text(
            textwrap.dedent(
                """\
                name: mcp-live-yaml
                tasks:
                  - name: yaml-1
                    instruction: "Return JSON with result='MCP_YAML_STEP_1_284'."
                    done_when: "Return MCP_YAML_STEP_1_284 in JSON."
                  - name: yaml-2
                    instruction: "Return JSON with result='MCP_YAML_STEP_2_284'."
                    done_when: "Return MCP_YAML_STEP_2_284 in JSON."
                """
            ),
            encoding="utf-8",
        )
        payload = _call_mcp_tool(
            "rondo_run",
            {"file_path": str(round_file), "model": "sonnet", "execution": "subprocess", "dry_run": False},
        )
    _assert_results_envelope(payload)
    assert len(payload["tasks"]) == 2, payload


def test_mcp_run_gemini_flash_http_results() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {"prompt": "Return JSON with result='MCP_HTTP_OK_284'.", "model": "gemini:flash", "dry_run": False},
    )
    _assert_results_envelope(payload)


def test_mcp_run_execution_subprocess_results() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {
            "prompt": "Return JSON with result='MCP_SUBPROCESS_OK_284'.",
            "model": "sonnet",
            "execution": "subprocess",
            "dry_run": False,
        },
    )
    _assert_results_envelope(payload)


def test_mcp_run_execution_inline_returns_plan_json() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {
            "prompt": "Return JSON with result='MCP_INLINE_PLAN_284'.",
            "model": "sonnet",
            "execution": "inline",
            "dry_run": False,
        },
    )
    assert payload.get("kind") == "inline_dispatch_plan", payload
    assert payload.get("status") == "plan", payload


def test_mcp_background_run_and_status_polling() -> None:
    start = _call_mcp_tool(
        "rondo_run",
        {
            "prompt": "Return JSON with result='MCP_BG_OK_284'.",
            "model": "sonnet",
            "execution": "subprocess",
            "background": True,
            "dry_run": False,
        },
    )
    dispatch_id = str(start.get("dispatch_id", "") or "")
    assert dispatch_id, start

    final_payload = {}
    for _ in range(45):
        status = _call_mcp_tool("rondo_run_status", {"dispatch_id": dispatch_id})
        if status.get("status") in {"done", "partial", "error"} and isinstance(status.get("tasks"), list):
            final_payload = status
            break
        time.sleep(2)

    _assert_results_envelope(final_payload)


def test_mcp_multi_review_three_providers() -> None:
    payload = _call_mcp_tool(
        "rondo_multi_review",
        {
            "prompt": "Find one issue in this code: def f(x): return x/0",
            "providers": json.dumps(["gemini:flash", "openai:gpt-4o", "grok:grok-3"]),
            "dry_run": False,
        },
    )
    assert payload.get("status") in {"done", "partial"}, payload
    per_provider = payload.get("per_provider", [])
    assert isinstance(per_provider, list) and len(per_provider) == 3, payload


def test_mcp_review_file_real_file_returns_findings() -> None:
    target = str(Path(__file__).resolve().parents[2] / "src" / "rondo" / "envelope.py")
    payload = _call_mcp_tool(
        "rondo_review_file",
        {
            "path": target,
            "providers": json.dumps(["gemini:flash"]),
            "dry_run": False,
        },
    )
    assert payload.get("status") in {"done", "partial", "error"}, payload
    assert isinstance(payload.get("per_provider"), list) and payload.get("per_provider"), payload


def test_mcp_chain_two_steps() -> None:
    steps = [
        {"prompt": "Return JSON with result='CHAIN_STEP_1_284'.", "model": "sonnet"},
        {"prompt": "Use previous output, return result='CHAIN_STEP_2_284'.", "model": "sonnet"},
    ]
    payload = _call_mcp_tool("rondo_chain", {"steps_json": json.dumps(steps), "dry_run": False})
    assert payload.get("status") in {"done", "partial"}, payload
    assert isinstance(payload.get("steps"), list) and len(payload["steps"]) == 2, payload


def test_mcp_run_bad_model_returns_clean_error() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {"prompt": "Return JSON with result='BAD_MODEL_284'.", "model": "bad-model-284", "dry_run": False},
    )
    assert payload.get("status") == "error", payload
    assert payload.get("error_code"), payload
    assert payload.get("error_help"), payload


def test_mcp_run_timeout_returns_clean_error() -> None:
    payload = _call_mcp_tool(
        "rondo_run",
        {
            "prompt": "Think for a long time before answering.",
            "model": "sonnet",
            "execution": "subprocess",
            "timeout_sec": 1,
            "dry_run": False,
        },
    )
    assert payload.get("status") in {"error", "partial"}, payload
    if payload.get("status") == "error":
        assert payload.get("error_code"), payload


# -- sig: mgh-bc0c.f2.fecb75.9b1f.17cf9f
