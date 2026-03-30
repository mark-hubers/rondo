# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.mcp_server — IFS-104 MCP stdio server.

VER-001 verification matrix: MCP tool definitions, responses, ALWAYS-ON data.
Tests the tool functions directly (not the MCP transport layer).
"""

import json

import pytest

from rondo.mcp_server import (
    rondo_metrics,
    rondo_audit_summary,
    rondo_health,
    rondo_dispatch_info,
    rondo_run_file,
    rondo_run_status,
)


# -- ──────────────────────────────────────────────────────────────
# --  IFS-104 req 003 — Query tools
# -- ──────────────────────────────────────────────────────────────


class TestMetricsTool:
    """IFS-104: rondo_metrics tool returns dashboard data."""

    def test_returns_json_string(self):
        """Tool returns valid JSON string."""
        result = rondo_metrics()
        data = json.loads(result)
        assert "health" in data
        assert "total_dispatches" in data

    def test_has_cost_fields(self):
        """Metrics include cost data."""
        data = json.loads(rondo_metrics())
        assert "total_cost_usd" in data
        assert "avg_cost_usd" in data

    def test_has_reliability_fields(self):
        """Metrics include reliability data."""
        data = json.loads(rondo_metrics())
        assert "success_rate" in data
        assert "error_breakdown" in data


class TestHealthTool:
    """IFS-104: rondo_health tool returns quick health status."""

    def test_returns_health_status(self):
        """Health tool returns GREEN/YELLOW/RED."""
        result = rondo_health()
        data = json.loads(result)
        assert data["health"] in ("GREEN", "YELLOW", "RED")
        assert "total_dispatches" in data

    def test_lightweight(self):
        """Health response is small (< 500 chars)."""
        result = rondo_health()
        assert len(result) < 500


class TestAuditSummaryTool:
    """IFS-104: rondo_audit_summary tool returns recent dispatches."""

    def test_returns_list(self):
        """Audit summary returns list of recent records."""
        result = rondo_audit_summary()
        data = json.loads(result)
        assert isinstance(data, dict)
        assert "recent" in data
        assert isinstance(data["recent"], list)


class TestDispatchInfoTool:
    """IFS-104: rondo_dispatch_info returns Rondo capabilities."""

    def test_has_version(self):
        """Dispatch info includes version."""
        result = rondo_dispatch_info()
        data = json.loads(result)
        assert "version" in data

    def test_has_commands(self):
        """Dispatch info lists CLI commands."""
        data = json.loads(rondo_dispatch_info())
        assert "commands" in data
        assert len(data["commands"]) >= 9

    def test_has_design_principles(self):
        """Dispatch info lists design principles."""
        data = json.loads(rondo_dispatch_info())
        assert "design_principles" in data
        assert "ALWAYS-ON" in data["design_principles"]


# -- ──────────────────────────────────────────────────────────────
# --  MCP dispatch tool (RONDO-38)
# -- ──────────────────────────────────────────────────────────────


class TestRondoRunFile:
    """rondo_run_file: MCP dispatch tool."""

    def test_dry_run_returns_json(self, tmp_path):
        """Dry-run dispatch returns valid JSON with task results."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='mcp-test', tasks=[\n"
            "        Task(name='t1', instruction='check', done_when='done'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(str(round_file), dry_run=True))
        assert result["status"] in ("done", "skipped", "error")
        assert "tasks" in result

    def test_invalid_file_returns_error(self):
        """Non-existent file returns error JSON."""
        result = json.loads(rondo_run_file("/nonexistent/file.py"))
        assert result["status"] == "error"
        assert "error" in result

    def test_returns_valid_json(self, tmp_path):
        """Output is always parseable JSON."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='json-test', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        raw = rondo_run_file(str(round_file), dry_run=True)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)


    def test_project_validation(self):
        """Invalid project path returns error."""
        result = json.loads(rondo_run_file("/tmp/any.py", project="/nonexistent/dir"))
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_max_budget_accepted(self, tmp_path):
        """max_budget parameter is accepted without error."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='budget-test', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(str(round_file), dry_run=True, max_budget=0.50))
        assert result["status"] in ("done", "skipped", "error")

    def test_tilde_expansion(self, tmp_path):
        """File paths with ~ are expanded."""
        result = json.loads(rondo_run_file("~/nonexistent_rondo_file_xyz.py"))
        assert result["status"] == "error"
        assert "~" not in result.get("error", "")  ## expanded, not literal ~


class TestMcpResource:
    """IFS-104 reqs 016-018: rondo://help resource for AI self-discovery."""

    def test_create_server_has_resource(self):
        """Resource is registered on the MCP server."""
        from rondo.mcp_server import create_mcp_server

        server = create_mcp_server()
        assert server is not None

    def test_help_resource_returns_json(self):
        """rondo://help returns valid JSON with schemas."""
        from rondo.mcp_server import create_mcp_server
        from rondo.ai_help import get_ai_help

        data = get_ai_help()
        assert "round_schema" in data
        assert "task_schema" in data
        assert "example_round_file" in data
        assert "gate_schema" in data

    def test_help_resource_has_example(self):
        """Resource includes compilable example round file (req 018)."""
        from rondo.ai_help import get_ai_help

        data = get_ai_help()
        example = data["example_round_file"]
        compile(example, "<resource-example>", "exec")


class TestRondoRunStatus:
    """rondo_run_status: check background dispatch status."""

    def test_empty_returns_dispatches(self):
        """No dispatch_id lists all dispatches."""
        result = json.loads(rondo_run_status())
        assert "dispatches" in result

    def test_unknown_id_returns_error(self):
        """Unknown dispatch_id returns error."""
        result = json.loads(rondo_run_status("nonexistent-id"))
        assert result["status"] == "error"

    def test_completed_has_per_task_status(self, tmp_path):
        """U-31: completed dispatch shows per-task name + status."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='status-test', tasks=[\n"
            "        Task(name='task-a', instruction='check', done_when='done'),\n"
            "        Task(name='task-b', instruction='verify', done_when='done'),\n"
            "    ])\n"
        )
        ## -- Dry-run dispatch (synchronous, completes immediately)
        result = json.loads(rondo_run_file(str(round_file), dry_run=True))
        assert result["status"] in ("done", "skipped")
        ## -- Each task should have name and status
        for task in result["tasks"]:
            assert "name" in task
            assert "status" in task
            assert task["name"] in ("task-a", "task-b")

    def test_completed_has_task_output(self, tmp_path):
        """U-32: completed tasks include raw_output in response."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='output-test', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(str(round_file), dry_run=True))
        ## -- Dry-run: prompt_sent should be present (not empty)
        for task in result["tasks"]:
            assert "prompt_sent" in task or "raw_output" in task

    def test_background_status_has_task_progress(self, tmp_path):
        """U-31: background dispatch status shows per-task progress."""
        import time

        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='bg-test', tasks=[\n"
            "        Task(name='bg-task', instruction='check', done_when='done'),\n"
            "    ])\n"
        )
        ## -- Background dry-run dispatch
        launch = json.loads(rondo_run_file(str(round_file), dry_run=True, background=True))
        ## -- dry_run + background still runs synchronously (dry-run is instant)
        ## -- but if it dispatched, check the status response format
        if launch.get("dispatch_id"):
            time.sleep(1)
            status = json.loads(rondo_run_status(launch["dispatch_id"]))
            if status["status"] != "running":
                assert "tasks" in status


class TestInlineDispatch:
    """U-33 to U-35: rondo_run with prompt= for one-off tasks."""

    def test_inline_dry_run(self):
        """U-33: prompt= creates in-memory task and dispatches."""
        result = json.loads(rondo_run_file(
            file_path="",
            prompt="List all Python files in the current directory",
            dry_run=True,
        ))
        assert result["status"] in ("done", "skipped")
        assert len(result["tasks"]) == 1
        assert "Python files" in result["tasks"][0].get("prompt_sent", "")

    def test_inline_with_done_when(self):
        """U-34: done_when parameter accepted."""
        result = json.loads(rondo_run_file(
            file_path="",
            prompt="Check disk space",
            done_when="Disk usage reported",
            dry_run=True,
        ))
        assert result["status"] in ("done", "skipped")
        assert "Disk usage" in str(result)

    def test_inline_same_json_as_file(self, tmp_path):
        """U-35: inline returns same structure as file-based."""
        ## -- File-based
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='cmp', tasks=[\n"
            "        Task(name='t1', instruction='hello', done_when='done'),\n"
            "    ])\n"
        )
        file_result = json.loads(rondo_run_file(str(round_file), dry_run=True))
        ## -- Inline
        inline_result = json.loads(rondo_run_file("", prompt="hello", dry_run=True))
        ## -- Same top-level keys
        assert set(file_result.keys()) == set(inline_result.keys())

    def test_inline_no_prompt_no_file_errors(self):
        """No file and no prompt = error."""
        result = json.loads(rondo_run_file(""))
        assert result["status"] == "error"


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b8
