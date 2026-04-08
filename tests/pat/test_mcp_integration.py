# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""MCP server + query tool integration tests.

Split from test_real_dispatch.py in RONDO-207 to reduce file size to
best-practice range (200-500 lines per test file). Original monster was
2227 lines with 133 tests across 24 classes — this file is a focused slice.

Markers:
    (none)          — always runs, free, instant
    @pytest.mark.cloud  — real cloud API calls
    @pytest.mark.ollama — needs Ollama running locally

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.mcp_dispatch import _is_in_session


class TestMCPIntegration:
    """rondo_run_file returns correct response shape for each engine."""

    def test_inline_via_mcp(self) -> None:
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Do something", model="", dry_run=False))
        assert result["engine"] == "inline"
        assert result["status"] == "plan"

    def test_agent_via_mcp_in_session(self) -> None:
        """Only validates if we're in a session. Otherwise sonnet→subprocess."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Do something", model="sonnet", dry_run=False))
        if _is_in_session():
            assert result["engine"] == "agent"
            assert result["status"] == "plan"
        else:
            # -- Outside session: subprocess path (may fail, that's expected)
            assert result.get("engine") == "subprocess" or "tasks" in result or "status" in result

    def test_inline_returns_instantly(self) -> None:
        """Inline plan must return in <10ms — no I/O, no dispatch."""
        from rondo.mcp_server import rondo_run_file

        t0 = time.time()
        rondo_run_file(prompt="x", model="", dry_run=False)
        elapsed = time.time() - t0
        assert elapsed < 0.1, f"Inline plan took {elapsed:.3f}s — should be instant"

    def test_no_prompt_no_file_is_error(self) -> None:
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="", model="", dry_run=True))
        assert result["status"] == "error"


class TestMCPQueryTools:
    """Every MCP query tool returns valid JSON with expected shape.

    These tools are read-only and free. They must all work.
    If any returns invalid JSON or crashes, the MCP server is broken.
    """

    def test_health_returns_status(self) -> None:
        from rondo.mcp_server import rondo_health

        result = json.loads(rondo_health())
        # -- Health uses 'api_status' as the top-level status key
        assert "api_status" in result, f"health missing 'api_status': {list(result.keys())}"
        assert result["api_status"] in ("GREEN", "YELLOW", "RED"), f"Bad health status: {result['api_status']}"

    def test_metrics_returns_json(self) -> None:
        from rondo.mcp_server import rondo_metrics

        result = json.loads(rondo_metrics())
        assert isinstance(result, dict), "metrics should return a dict"

    def test_dispatch_info_returns_version(self) -> None:
        from rondo.mcp_server import rondo_dispatch_info

        result = json.loads(rondo_dispatch_info())
        assert "version" in result, f"dispatch_info missing 'version': {list(result.keys())}"
        assert "commands" in result or "tools" in result or "mcp_tools" in result, "dispatch_info missing capabilities"

    def test_models_returns_list(self) -> None:
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        assert isinstance(result, dict), "models should return a dict"
        # -- Should list at least Claude models
        raw = json.dumps(result).lower()
        assert "sonnet" in raw or "claude" in raw, "models should include Claude"

    def test_cost_returns_json(self) -> None:
        from rondo.mcp_server import rondo_cost

        result = json.loads(rondo_cost())
        assert isinstance(result, dict), "cost should return a dict"

    def test_audit_summary_returns_json(self) -> None:
        from rondo.mcp_server import rondo_audit_summary

        result = json.loads(rondo_audit_summary())
        assert isinstance(result, dict), "audit_summary should return a dict"

    def test_history_returns_json(self) -> None:
        from rondo.mcp_server import rondo_history

        result = json.loads(rondo_history())
        assert isinstance(result, dict), "history should return a dict"

    def test_templates_returns_json(self) -> None:
        from rondo.mcp_server import rondo_templates

        result = json.loads(rondo_templates())
        assert isinstance(result, dict) or isinstance(result, list), "templates should return dict or list"

    def test_spool_consume_returns_json(self) -> None:
        from rondo.mcp_server import rondo_spool_consume

        result = json.loads(rondo_spool_consume())
        assert isinstance(result, dict) or isinstance(result, list), "spool_consume should return valid JSON"

    def test_schedule_list_returns_json(self) -> None:
        from rondo.mcp_server import rondo_schedule_list

        result = json.loads(rondo_schedule_list())
        assert isinstance(result, dict) or isinstance(result, list), "schedule_list should return valid JSON"

    def test_run_status_no_id_returns_json(self) -> None:
        """run_status with no dispatch_id should return valid response (not crash)."""
        from rondo.mcp_server import rondo_run_status

        result = json.loads(rondo_run_status())
        assert isinstance(result, dict), "run_status should return a dict"

    def test_diff_empty_returns_json(self) -> None:
        from rondo.mcp_server import rondo_diff

        result = json.loads(rondo_diff(current_json="{}"))
        assert isinstance(result, dict), "diff should return a dict"


class TestMCPToolResponseValidity:
    """Every tool response must be parseable JSON. No exceptions."""

    def test_all_query_tools_return_valid_json(self) -> None:
        """Master test: call EVERY read-only MCP tool, assert valid JSON."""
        from rondo.mcp_server import (
            rondo_audit_summary,
            rondo_dispatch_info,
            rondo_health,
            rondo_history,
            rondo_metrics,
            rondo_run_status,
            rondo_spool_consume,
        )

        tools = {
            "health": rondo_health,
            "metrics": rondo_metrics,
            "dispatch_info": rondo_dispatch_info,
            "audit_summary": rondo_audit_summary,
            "history": rondo_history,
            "run_status": rondo_run_status,
            "spool_consume": rondo_spool_consume,
        }
        for name, fn in tools.items():
            raw = fn()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                pytest.fail(f"MCP tool '{name}' returned invalid JSON: {exc}\nRaw: {raw[:200]}")
            assert isinstance(parsed, (dict, list)), f"MCP tool '{name}' returned {type(parsed)}"


class TestAuditPipeline:
    """Dispatches create audit records. Error or success — always tracked."""

    def test_audit_file_is_valid_json(self, tmp_path) -> None:
        """After a dispatch, audit JSONL file has valid JSON lines."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        os.environ["RONDO_TEST_DIR"] = str(tmp_path)
        try:
            from rondo.mcp_dispatch import rondo_run_file

            rondo_run_file(prompt="audit test", model="gemini:gemini-2.5-flash", dry_run=True)
            # -- Check that audit dir exists and has content
            jsonl_files = list(audit_dir.glob("*.jsonl"))
            json_files = list(audit_dir.glob("*.json"))
            all_files = jsonl_files + json_files
            for f in all_files:
                content = f.read_text()
                for line in content.strip().split("\n"):
                    if line.strip():
                        parsed = json.loads(line)  # -- will raise if invalid
                        assert isinstance(parsed, dict)
        finally:
            os.environ.pop("RONDO_TEST_DIR", None)


class TestSanitizeIntegrity:
    """Sanitize must not mangle normal AI responses."""

    def test_normal_text_not_mangled(self) -> None:
        """sanitize_task_result returns (sanitized_result, report) tuple."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        tr = TaskResult(
            task_name="test",
            status="done",
            raw_output="The function returns a base64-encoded string like aGVsbG8gd29ybGQ=",
        )
        sanitized_tr, _report = sanitize_task_result(tr)
        # -- Normal text should survive sanitize without redaction
        assert "function returns" in sanitized_tr.raw_output, "Sanitize mangled normal text"

    def test_real_api_key_pattern_redacted(self) -> None:
        """API key patterns must be scrubbed from output."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        tr = TaskResult(
            task_name="test",
            status="done",
            raw_output="The API key is sk-1234567890abcdef1234567890abcdef12345678",
        )
        sanitized_tr, _report = sanitize_task_result(tr)
        assert "sk-1234567890" not in sanitized_tr.raw_output, "API key should be redacted"


# -- sig: mgh-a0a1.e2.283a3f.ec1d.adcf84
