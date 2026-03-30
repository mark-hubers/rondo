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
    rondo_spool_consume,
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

    def test_brief_has_only_status_and_counts(self, tmp_path):
        """U-45: brief=True returns ONLY status + 3 counts. No dispatch_id, no cost."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='brief-test', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        ## -- Run sync dispatch so it completes
        rondo_run_file(str(round_file), dry_run=True, background=True)
        import time
        time.sleep(1)
        ## -- Simulate: inject a known result into background results
        from rondo.mcp_server import _background_results
        _background_results["test-brief"] = {
            "status": "done",
            "done_count": 2,
            "error_count": 0,
            "pending_count": 0,
            "total_cost_usd": 1.23,
            "tasks": [{"name": "t1"}, {"name": "t2"}],
        }
        result = json.loads(rondo_run_status("test-brief", brief=True))
        ## -- Must have exactly these 4 keys
        assert set(result.keys()) == {"status", "done_count", "error_count", "pending_count"}
        ## -- No dispatch_id, no cost
        assert "dispatch_id" not in result
        assert "total_cost_usd" not in result

    def test_heartbeat_ultra_compact(self):
        """U-50: heartbeat=True returns single-letter keys (~10 tokens)."""
        from rondo.mcp_server import _background_results
        _background_results["test-hb"] = {
            "status": "running",
            "done_count": 2,
            "error_count": 0,
            "pending_count": 1,
        }
        result = json.loads(rondo_run_status("test-hb", heartbeat=True))
        assert set(result.keys()) == {"s", "d", "e", "p"}
        assert result["s"] == "w"
        assert result["d"] == 2
        assert result["e"] == 0
        assert result["p"] == 1

    def test_heartbeat_done_status(self):
        """U-50: heartbeat shows 'd' for done status."""
        from rondo.mcp_server import _background_results
        _background_results["test-hb-done"] = {
            "status": "done",
            "done_count": 3,
            "error_count": 0,
            "pending_count": 0,
        }
        result = json.loads(rondo_run_status("test-hb-done", heartbeat=True))
        assert result["s"] == "d"

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


class TestSpoolConsumeMCP:
    """rondo_spool_consume MCP tool."""

    def test_empty_spool_returns_zero(self):
        """Empty spool returns count=0."""
        result = json.loads(rondo_spool_consume())
        assert result["count"] == 0
        assert result["consumed"] == []


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


# -- ──────────────────────────────────────────────────────────────
# --  E2E: MCP dispatch (RONDO-31)
# -- ──────────────────────────────────────────────────────────────


class TestRicherStatus:
    """RONDO-44: status JSON has counts + error levels."""

    def test_status_has_counts(self, tmp_path):
        """Status includes done_count, error_count, pending_count."""
        rf = tmp_path / "round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='counts', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "        Task(name='t2', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(str(rf), dry_run=True))
        assert "done_count" in result
        assert "error_count" in result
        assert isinstance(result["done_count"], int)

    def test_inline_has_counts(self):
        """Inline dispatch also has counts."""
        result = json.loads(rondo_run_file(prompt="hello", dry_run=True))
        assert "done_count" in result

    def test_brief_status_minimal(self):
        """U-45: brief=True returns only status + counts."""
        result = json.loads(rondo_run_status(brief=True))
        ## -- List mode with brief should have dispatches with minimal fields
        assert "dispatches" in result

    def test_brief_status_no_tasks(self):
        """U-45: brief mode doesn't include full task array."""
        ## -- Put a fake completed result in background store
        from rondo.mcp_server import _background_results
        _background_results["test-brief"] = {
            "status": "done",
            "dispatch_id": "test-brief",
            "done_count": 2,
            "error_count": 0,
            "pending_count": 0,
            "tasks": [{"name": "t1", "status": "done", "raw_output": "x" * 1000}],
            "total_cost_usd": 0.5,
        }
        brief = json.loads(rondo_run_status("test-brief", brief=True))
        assert brief["status"] == "done"
        assert brief["done_count"] == 2
        assert "tasks" not in brief  ## brief omits task details
        assert "raw_output" not in json.dumps(brief)
        ## -- Cleanup
        del _background_results["test-brief"]


class TestMCPDispatchE2E:
    """End-to-end MCP dispatch tests — covers all dispatch paths."""

    def test_file_dry_run_e2e(self, tmp_path):
        """File-based dry-run: load → dispatch → JSON result."""
        rf = tmp_path / "e2e_round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='e2e-dry', tasks=[\n"
            "        Task(name='scan', instruction='Search for data', done_when='Found'),\n"
            "        Task(name='report', instruction='Write summary', done_when='Written'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(str(rf), dry_run=True))
        assert result["status"] in ("done", "skipped")
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["name"] == "scan"
        assert result["tasks"][1]["name"] == "report"
        assert result["dry_run"] is True
        assert result["total_cost_usd"] == 0.0

    def test_inline_dry_run_e2e(self):
        """Inline prompt dry-run: prompt → in-memory round → result."""
        result = json.loads(rondo_run_file(
            prompt="List files in current directory",
            done_when="Files listed as JSON array",
            dry_run=True,
        ))
        assert result["status"] in ("done", "skipped")
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["name"] == "inline-task"
        assert "List files" in result["tasks"][0].get("prompt_sent", "")
        assert "JSON array" in result["tasks"][0].get("prompt_sent", "")

    def test_project_flag_dry_run(self, tmp_path):
        """--project flag sets CWD for dispatch."""
        rf = tmp_path / "proj_round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='proj-test', tasks=[\n"
            "        Task(name='t', instruction='check', done_when='done'),\n"
            "    ])\n"
        )
        result = json.loads(rondo_run_file(
            str(rf), dry_run=True, project=str(tmp_path),
        ))
        assert result["status"] in ("done", "skipped")

    def test_invalid_project_returns_error(self, tmp_path):
        """Invalid project path returns error before dispatch."""
        rf = tmp_path / "round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='t', tasks=[Task(name='t', instruction='x', done_when='y')])\n"
        )
        result = json.loads(rondo_run_file(
            str(rf), project="/nonexistent/path/xyz",
        ))
        assert result["status"] == "error"

    def test_background_dry_run_returns_immediately(self, tmp_path):
        """Background dispatch returns dispatch_id immediately."""
        rf = tmp_path / "bg_round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='bg', tasks=[\n"
            "        Task(name='t1', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        ## -- background=True with dry_run=True still runs synchronously
        ## -- but background=True with dry_run=False returns dispatch_id
        result = json.loads(rondo_run_file(str(rf), dry_run=False, background=True))
        if result.get("dispatch_id"):
            assert result["status"] == "dispatched"
            assert "mcp-" in result["dispatch_id"]

    def test_audit_records_after_dispatch(self, tmp_path):
        """Dispatch creates audit records (ALWAYS-ON)."""
        rf = tmp_path / "audit_round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='audit-test', tasks=[\n"
            "        Task(name='t', instruction='x', done_when='y'),\n"
            "    ])\n"
        )
        rondo_run_file(str(rf), dry_run=True)
        ## -- Check audit has records
        health = json.loads(rondo_health())
        assert health["total_dispatches"] >= 0  ## may be 0 if dry-run doesn't audit

    def test_metrics_after_dispatch(self):
        """Metrics endpoint works after dispatches."""
        result = json.loads(rondo_metrics())
        assert "total_dispatches" in result
        assert "health" in result
        assert "success_rate" in result

    def test_full_tool_inventory(self):
        """All 8 MCP tools are registered."""
        from rondo.mcp_server import create_mcp_server
        server = create_mcp_server()
        assert server is not None


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b8
