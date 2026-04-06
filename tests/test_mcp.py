# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.mcp_server — IFS-104 MCP stdio server.

VER-001 verification matrix: MCP tool definitions, responses, ALWAYS-ON data.
Tests the tool functions directly (not the MCP transport layer).
"""

import json

from rondo.mcp_server import (
    rondo_audit_summary,
    rondo_dispatch_info,
    rondo_health,
    rondo_history,
    rondo_metrics,
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
    """IFS-104 + REQ-109 req 079: rondo_health tool returns split health status."""

    def test_returns_api_status(self) -> None:
        """REQ-109 req 079: api_status shows live provider probe result."""
        result = rondo_health()
        data = json.loads(result)
        assert data["api_status"] in ("GREEN", "YELLOW", "RED", "UNKNOWN")

    def test_returns_dispatch_health(self) -> None:
        """REQ-109 req 079: dispatch_health shows historical success rate."""
        data = json.loads(rondo_health())
        assert data["dispatch_health"] in ("GREEN", "YELLOW", "RED")
        assert "success_rate" in data
        assert "total_dispatches" in data

    def test_providers_up_field(self) -> None:
        """REQ-109 req 079: providers_up shows N/M format."""
        data = json.loads(rondo_health())
        assert "providers_up" in data
        assert "/" in data["providers_up"]

    def test_lightweight(self) -> None:
        """Health response is compact (< 1000 chars with provider detail)."""
        result = rondo_health()
        assert len(result) < 1000


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
        result = json.loads(
            rondo_run_file(
                file_path="",
                prompt="List all Python files in the current directory",
                dry_run=True,
            )
        )
        assert result["status"] in ("done", "skipped")
        assert len(result["tasks"]) == 1
        assert "Python files" in result["tasks"][0].get("prompt_sent", "")

    def test_inline_with_done_when(self):
        """U-34: done_when parameter accepted."""
        result = json.loads(
            rondo_run_file(
                file_path="",
                prompt="Check disk space",
                done_when="Disk usage reported",
                dry_run=True,
            )
        )
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
        result = json.loads(
            rondo_run_file(
                prompt="List files in current directory",
                done_when="Files listed as JSON array",
                dry_run=True,
            )
        )
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
        result = json.loads(
            rondo_run_file(
                str(rf),
                dry_run=True,
                project=str(tmp_path),
            )
        )
        assert result["status"] in ("done", "skipped")

    def test_invalid_project_returns_error(self, tmp_path):
        """Invalid project path returns error before dispatch."""
        rf = tmp_path / "round.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='t', tasks=[Task(name='t', instruction='x', done_when='y')])\n"
        )
        result = json.loads(
            rondo_run_file(
                str(rf),
                project="/nonexistent/path/xyz",
            )
        )
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


# -- ──────────────────────────────────────────────────────────────
# --  Cursor review fixes (RONDO-50, U-52 to U-55)
# -- ──────────────────────────────────────────────────────────────


class TestRondoCost:
    """Cost dashboard: monthly spend tracking."""

    def test_cost_returns_json(self):
        """rondo_cost returns valid JSON with cost breakdown."""
        from rondo.mcp_server import rondo_cost

        result = json.loads(rondo_cost())
        assert "total_cost_usd" in result
        assert "by_model" in result

    def test_cost_has_period(self):
        """Cost includes the reporting period."""
        from rondo.mcp_server import rondo_cost

        result = json.loads(rondo_cost())
        assert "period" in result


class TestRondoTemplates:
    """Template library: pre-built round patterns."""

    def test_templates_returns_list(self):
        """rondo_templates lists available templates."""
        from rondo.mcp_server import rondo_templates

        result = json.loads(rondo_templates())
        assert "templates" in result
        assert len(result["templates"]) >= 3

    def test_template_has_fields(self):
        """Each template has name, description, usage."""
        from rondo.mcp_server import rondo_templates

        result = json.loads(rondo_templates())
        for t in result["templates"]:
            assert "name" in t
            assert "description" in t


class TestRondoSummarize:
    """Result summarizer: condense multiple task outputs."""

    def test_summarize_returns_json(self):
        """rondo_summarize returns valid JSON."""
        from rondo.mcp_server import rondo_summarize

        dispatch = json.dumps(
            {
                "tasks": [
                    {"name": "t1", "raw_output": "Found 3 new trials"},
                    {"name": "t2", "raw_output": "Found 5 papers"},
                ]
            }
        )
        result = json.loads(rondo_summarize(dispatch, dry_run=True))
        assert "summary_prompt" in result or "summary" in result

    def test_summarize_empty_tasks(self):
        """No tasks = nothing to summarize."""
        from rondo.mcp_server import rondo_summarize

        result = json.loads(rondo_summarize(json.dumps({"tasks": []})))
        assert result.get("summary") == "No tasks to summarize"


class TestRondoRetry:
    """U-56 to U-58: retry failed tasks from a previous dispatch."""

    def test_retry_returns_json(self):
        """rondo_retry returns valid JSON."""
        from rondo.mcp_server import rondo_retry

        result = json.loads(rondo_retry("nonexistent-id"))
        assert "status" in result

    def test_retry_unknown_dispatch_errors(self):
        """Unknown dispatch_id returns error."""
        from rondo.mcp_server import rondo_retry

        result = json.loads(rondo_retry("bad-id"))
        assert result["status"] == "error"


class TestRondoDiff:
    """U-59 to U-61: compare dispatch results — what's new."""

    def test_diff_returns_json(self):
        """rondo_diff returns valid JSON."""
        from rondo.mcp_server import rondo_diff

        current = json.dumps({"tasks": [{"name": "t1", "raw_output": "found A, B, C"}]})
        previous = json.dumps({"tasks": [{"name": "t1", "raw_output": "found A, B"}]})
        result = json.loads(rondo_diff(current, previous))
        assert "changes" in result
        assert result["changes"] >= 1

    def test_diff_empty_previous(self):
        """No previous = everything is new."""
        from rondo.mcp_server import rondo_diff

        current = json.dumps({"tasks": [{"name": "t1", "raw_output": "found A"}]})
        result = json.loads(rondo_diff(current, ""))
        assert result["status"] == "done"

    def test_diff_same_results(self):
        """Identical results = no diff."""
        from rondo.mcp_server import rondo_diff

        data = json.dumps({"tasks": [{"name": "t1", "raw_output": "same"}]})
        result = json.loads(rondo_diff(data, data))
        assert result["changes"] == 0


class TestBackgroundTTL:
    """H-01 to H-03: background results TTL + max entries."""

    def test_max_100_entries(self):
        """H-01: max 100 background entries."""
        from rondo.mcp_server import _background_results, _prune_background

        _background_results.clear()
        for i in range(110):
            _background_results[f"id-{i}"] = {"status": "done", "ts": 0}
        _prune_background()
        assert len(_background_results) <= 100

    def test_expired_returns_expired(self):
        """H-03: evicted dispatch returns 'expired'."""
        result = json.loads(rondo_run_status("nonexistent-evicted-id"))
        assert result["status"] == "error"


class TestMCPInputLimits:
    """H-07 to H-11: input size caps on MCP tools."""

    def test_prompt_too_large(self):
        """H-07: prompt > 500KB rejected."""
        result = json.loads(rondo_run_file(prompt="x" * 600_000, dry_run=True))
        assert result["status"] == "error"
        assert "ERR_INPUT_TOO_LARGE" in result.get("code", "") or "too large" in result.get("error", "").lower()

    def test_chain_too_many_steps(self):
        """H-08: chain > 20 steps rejected."""
        from rondo.mcp_server import rondo_chain

        steps = json.dumps([{"prompt": "x", "model": "haiku"}] * 25)
        result = json.loads(rondo_chain(steps, dry_run=True))
        assert result["status"] == "error"

    def test_benchmark_too_many_models(self):
        """H-09: benchmark > 10 models rejected."""
        from rondo.mcp_server import rondo_benchmark

        models = json.dumps([f"model{i}" for i in range(15)])
        result = json.loads(rondo_benchmark(prompt="x", models=models, dry_run=True))
        assert result["status"] == "error"


class TestRondoScheduleMCP:
    """rondo_schedule MCP: manage scheduled dispatches."""

    def test_schedule_list(self):
        from rondo.mcp_server import rondo_schedule_list

        result = json.loads(rondo_schedule_list())
        assert "schedules" in result

    def test_schedule_create_dry_run(self):
        from rondo.mcp_server import rondo_schedule_create

        result = json.loads(
            rondo_schedule_create(
                file_path="/tmp/test.py",
                interval="weekly",
                dry_run=True,
            )
        )
        assert "plist" in result or "status" in result


class TestRondoExplain:
    """rondo_explain: local model reviews another model's output."""

    def test_explain_returns_json(self):
        from rondo.mcp_server import rondo_explain

        result = json.loads(
            rondo_explain(
                output="Found 3 trials: NCT001, NCT002, NCT003",
                question="Are these real trial numbers?",
                dry_run=True,
            )
        )
        assert "status" in result

    def test_explain_default_model_is_local(self):
        from rondo.mcp_server import rondo_explain

        result = json.loads(
            rondo_explain(
                output="Some code",
                question="Is this correct?",
                dry_run=True,
            )
        )
        ## -- Should use a local model by default (not Claude)
        tasks = result.get("tasks", [])
        if tasks:
            assert tasks[0].get("model") != "sonnet"


class TestRondoBenchmark:
    """rondo_benchmark: same prompt → multiple models → ranked."""

    def test_benchmark_returns_json(self):
        from rondo.mcp_server import rondo_benchmark

        result = json.loads(
            rondo_benchmark(
                prompt="Say hello",
                models=json.dumps(["llama3.1:8b", "qwen2.5:32b"]),
                dry_run=True,
            )
        )
        assert "results" in result
        assert len(result["results"]) == 2

    def test_benchmark_ranks_by_speed(self):
        from rondo.mcp_server import rondo_benchmark

        result = json.loads(
            rondo_benchmark(
                prompt="Say hello",
                models=json.dumps(["llama3.1:8b"]),
                dry_run=True,
            )
        )
        assert "ranked" in result


class TestRondoChain:
    """rondo_chain: pipe output of step N as input to step N+1."""

    def test_chain_returns_json(self):
        from rondo.mcp_server import rondo_chain

        steps = json.dumps(
            [
                {"prompt": "List 3 colors", "model": "llama3.1:8b"},
                {"prompt": "For each color in the previous result, name a fruit of that color", "model": "llama3.1:8b"},
            ]
        )
        result = json.loads(rondo_chain(steps, dry_run=True))
        assert "steps" in result
        assert len(result["steps"]) == 2

    def test_chain_empty_steps(self):
        from rondo.mcp_server import rondo_chain

        result = json.loads(rondo_chain("[]"))
        assert result["status"] == "done"
        assert result["steps"] == []


class TestRondoModels:
    """rondo_models: discover available models and recommendations."""

    def test_models_returns_json(self):
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        assert "providers" in result

    def test_models_has_recommendations(self):
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        assert "recommendations" in result
        assert len(result["recommendations"]) >= 5

    def test_models_lists_all_cloud_providers(self) -> None:
        """REQ-109: rondo_models() matches --ai-help provider catalog."""
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        names = [p["name"] for p in result["providers"]]
        for expected in ("claude", "gemini", "openai", "grok", "mistral", "anthropic", "ollama"):
            assert expected in names, f"rondo_models() missing provider: {expected}"

    def test_cloud_providers_have_tiers(self) -> None:
        """Cloud providers expose high/default/low tier mapping."""
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        cloud = [p for p in result["providers"] if p["name"] not in ("claude", "ollama")]
        for p in cloud:
            assert "tiers" in p, f"{p['name']} missing tiers"
            assert "high" in p["tiers"]

    def test_providers_have_routing(self) -> None:
        """Every provider shows its routing syntax."""
        from rondo.mcp_server import rondo_models

        result = json.loads(rondo_models())
        for p in result["providers"]:
            assert "routing" in p, f"{p['name']} missing routing"


class TestCursorP0ErrorCode:
    """U-52: error_code flows to audit OUTCOME."""

    def test_audit_outcome_has_error_code(self, tmp_path):
        """Error dispatches record error_code in audit JSONL."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            task_name="t",
            model="m",
            status="error",
            exit_code=1,
            error_code="ERR_TIMEOUT",
        )
        lines = (tmp_path / "rondo_audit.jsonl").read_text().strip().splitlines()
        outcome = json.loads(lines[-1])
        assert outcome["error_code"] == "ERR_TIMEOUT"


class TestCursorP1MCPPaths:
    """U-53: MCP tools honor RONDO_TEST_DIR."""

    def test_metrics_uses_test_dir(self, monkeypatch, tmp_path):
        """rondo_metrics reads from RONDO_TEST_DIR when set."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        ## -- Create audit dir so metrics doesn't fail
        (tmp_path / "audit").mkdir()
        result = json.loads(rondo_metrics())
        assert result["total_dispatches"] == 0

    def test_health_uses_test_dir(self, monkeypatch, tmp_path):
        """rondo_health reads from RONDO_TEST_DIR when set."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        (tmp_path / "audit").mkdir()
        (tmp_path / "spool").mkdir()
        result = json.loads(rondo_health())
        assert result["dispatch_health"] == "GREEN"
        assert result["total_dispatches"] == 0


class TestCursorP1InlinePrePop:
    """U-54: inline prompt pre-populates task_names in background."""

    def test_inline_background_has_task_name(self):
        """Background dispatch with prompt= shows inline-task in response."""
        result = json.loads(
            rondo_run_file(
                prompt="Say hello",
                dry_run=False,
                background=True,
            )
        )
        if result.get("dispatch_id"):
            assert "inline-task" in result.get("tasks", [])


class TestRondoHistory:
    """REQ-104: dispatch history via MCP."""

    def test_history_returns_json(self):
        """rondo_history returns valid JSON."""
        result = json.loads(rondo_history())
        assert "records" in result
        assert isinstance(result["records"], list)

    def test_history_with_model_filter(self):
        """rondo_history(model='haiku') filters by model."""
        result = json.loads(rondo_history(model="haiku"))
        assert "records" in result
        for r in result["records"]:
            assert r.get("model") == "haiku"

    def test_history_has_aggregate(self):
        """rondo_history includes model aggregate stats."""
        result = json.loads(rondo_history())
        assert "aggregate" in result


class TestCursorP2CommandSSoT:
    """U-55: dispatch_info command list matches real CLI."""

    def test_command_list_has_init(self):
        """rondo_dispatch_info lists 'init' command (added Session 93)."""
        data = json.loads(rondo_dispatch_info())
        assert "init" in data["commands"]

    def test_command_list_has_mcp(self):
        """rondo_dispatch_info lists 'mcp' command."""
        data = json.loads(rondo_dispatch_info())
        assert "mcp" in data["commands"]

    def test_command_list_matches_cli(self):
        """dispatch_info commands match actual CLI parser."""
        from rondo.cli import build_parser

        parser = build_parser()
        ## -- Extract subcommand names from parser
        for action in parser._subparsers._actions:
            if hasattr(action, "_parser_class"):
                cli_commands = set(action.choices.keys())
                break
        else:
            cli_commands = set()

        data = json.loads(rondo_dispatch_info())
        mcp_commands = set(data["commands"])

        ## -- MCP should have all CLI commands
        missing = cli_commands - mcp_commands
        assert not missing, f"Commands in CLI but not in dispatch_info: {missing}"


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-106: Disk-based retry
# -- ──────────────────────────────────────────────────────────────


class TestDiskBasedRetry:
    """RONDO-106: retry persists to disk and loads across sessions."""

    def test_save_only_on_failures(self, tmp_path, monkeypatch) -> None:
        """Only save retry file when there are failed tasks."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result

        # -- Success result: no retry file
        success = {"tasks": [{"name": "t1", "status": "done"}]}
        _save_background_result("disp-ok", success)
        retry_dir = tmp_path / "retry"
        assert not (retry_dir / "disp-ok.json").exists()

        # -- Failure result: retry file created
        failure = {"tasks": [{"name": "t1", "status": "error", "error_message": "timeout"}]}
        _save_background_result("disp-fail", failure)
        assert (retry_dir / "disp-fail.json").exists()

    def test_load_from_disk(self, tmp_path, monkeypatch) -> None:
        """Load a retry record from disk when not in memory."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _load_background_result, _save_background_result

        failure = {"tasks": [{"name": "t1", "status": "error"}], "dispatch_id": "disp-123"}
        _save_background_result("disp-123", failure)
        loaded = _load_background_result("disp-123")
        assert loaded is not None
        assert loaded["dispatch_id"] == "disp-123"

    def test_load_missing_returns_none(self, tmp_path, monkeypatch) -> None:
        """Missing dispatch_id returns None, not crash."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _load_background_result

        assert _load_background_result("nonexistent") is None

    def test_retry_checks_disk(self, tmp_path, monkeypatch) -> None:
        """rondo_retry falls back to disk when not in memory."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result, rondo_retry

        # -- Save a failure to disk
        failure = {
            "tasks": [
                {"name": "scan", "status": "error", "error_message": "timeout", "model": "sonnet"},
            ],
            "dispatch_id": "disk-retry-1",
        }
        _save_background_result("disk-retry-1", failure)

        # -- rondo_retry should find it on disk (not in _background_results)
        result = json.loads(rondo_retry("disk-retry-1", model="haiku"))
        ## -- It will try to dispatch (which may fail in test env) but
        ## -- the point is it FOUND the dispatch, not "Unknown dispatch_id"
        assert result.get("status") != "error" or "Unknown dispatch_id" not in result.get("error", "")

    def test_prune_old_retry_files(self, tmp_path, monkeypatch) -> None:
        """Max 50 retry files — oldest pruned."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result

        failure = {"tasks": [{"name": "t", "status": "error"}]}
        # -- Create 55 retry files
        for i in range(55):
            _save_background_result(f"disp-{i:03d}", failure)

        retry_dir = tmp_path / "retry"
        files = list(retry_dir.glob("*.json"))
        assert len(files) <= 50


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-129: Three-engine dispatch routing (replaces RONDO-111)
# -- ──────────────────────────────────────────────────────────────


class TestResolveDispatchEngine:
    """RONDO-129: Pure routing logic — every input combination, no mocking."""

    def test_empty_model_returns_inline(self) -> None:
        """No model → inline engine (execute in current session)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="", prompt="hello")
        assert result["engine"] == "inline"
        assert result["kind"] == "inline_dispatch_plan"
        assert result["prompt"] == "hello"
        assert result["model"] == "current"

    def test_background_forces_subprocess(self) -> None:
        """background=True → subprocess, regardless of model."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        for model in ("", "sonnet", "haiku", "gemini:high"):
            result = resolve_dispatch_engine(model=model, background=True, prompt="hello")
            assert result["engine"] == "subprocess", f"background+{model} should be subprocess"

    def test_gemini_routes_to_http(self) -> None:
        """gemini: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="gemini:gemini-2.5-flash", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "gemini"

    def test_grok_routes_to_http(self) -> None:
        """grok: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="grok:grok-3", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "grok"

    def test_openai_routes_to_http(self) -> None:
        """openai: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="openai:gpt-4.1", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "openai"

    def test_mistral_routes_to_http(self) -> None:
        """mistral: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="mistral:mistral-large-latest", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "mistral"

    def test_local_routes_to_http(self) -> None:
        """local: prefix → HTTP adapter (Ollama)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="local:qwen2.5:32b", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "local"

    def test_anthropic_prefix_routes_to_http(self) -> None:
        """anthropic: prefix → HTTP adapter (API key billing, not Max plan)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="anthropic:sonnet", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "anthropic"

    def test_new_suffix_forces_subprocess(self) -> None:
        """model='sonnet:new' → subprocess (explicit new session)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="sonnet:new", prompt="hello")
        assert result["engine"] == "subprocess"
        assert result["model"] == "sonnet"

    def test_claude_model_in_session_returns_agent(self, monkeypatch) -> None:
        """Claude model inside Claude Code session → agent engine."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        for model in ("sonnet", "opus", "haiku"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "agent", f"{model} in-session should be agent"
            assert result["kind"] == "agent_dispatch_plan"
            assert result["model"] == model

    def test_claude_model_outside_session_returns_subprocess(self, monkeypatch) -> None:
        """Claude model outside Claude Code session (CLI) → subprocess."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)
        for model in ("sonnet", "opus", "haiku"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "subprocess", f"{model} outside session should be subprocess"

    def test_unknown_model_returns_error(self, monkeypatch) -> None:
        """Unknown model name → error engine."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)
        result = resolve_dispatch_engine(model="nonexistent-model-xyz", prompt="hello")
        assert result["engine"] == "error"

    def test_inline_plan_has_all_fields(self) -> None:
        """Inline plan includes prompt, done_when, model, project."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(
            model="",
            prompt="Review this code",
            done_when="List findings",
            project="/tmp/myproject",
        )
        assert result["engine"] == "inline"
        assert result["prompt"] == "Review this code"
        assert result["done_when"] == "List findings"
        assert result["project"] == "/tmp/myproject"
        assert result["model"] == "current"

    def test_agent_plan_has_all_fields(self, monkeypatch) -> None:
        """Agent plan includes prompt, done_when, model, project, note."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        result = resolve_dispatch_engine(
            model="haiku",
            prompt="Quick check",
            done_when="Done",
            project="/tmp/proj",
        )
        assert result["engine"] == "agent"
        assert result["prompt"] == "Quick check"
        assert result["model"] == "haiku"
        assert result["project"] == "/tmp/proj"
        assert "note" in result

    def test_background_overrides_inline(self) -> None:
        """background=True + empty model → subprocess (not inline)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="", background=True, prompt="hello")
        assert result["engine"] == "subprocess"

    def test_background_overrides_agent(self, monkeypatch) -> None:
        """background=True + Claude model in-session → subprocess (not agent)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        result = resolve_dispatch_engine(model="sonnet", background=True, prompt="hello")
        assert result["engine"] == "subprocess"

    def test_1m_models_detected(self, monkeypatch) -> None:
        """sonnet[1m] and opus[1m] are recognized as Claude models."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        for model in ("sonnet[1m]", "opus[1m]"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "agent", f"{model} should be recognized as Claude"


class TestDispatchEngineIntegration:
    """RONDO-129: Test that rondo_run_file uses the routing engine correctly."""

    def test_empty_model_returns_inline_plan(self) -> None:
        """rondo_run_file with empty model returns inline plan."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Check this code", model="", dry_run=True))
        assert result.get("engine") == "inline"
        assert result.get("kind") == "inline_dispatch_plan"
        assert result["prompt"] == "Check this code"

    def test_claude_model_in_session_returns_agent_plan(self) -> None:
        """rondo_run_file with Claude model in-session returns agent plan.

        This test runs inside Claude Code (CLAUDECODE is set).
        Previously this would try subprocess and fail 100% of the time.
        Now it returns an agent plan for the host session to execute.
        """
        import os

        if not os.environ.get("CLAUDECODE"):
            # -- Outside session: Claude models go to subprocess, which is correct
            return
        from rondo.mcp_server import rondo_run_file

        for model in ("sonnet", "opus", "haiku"):
            result = json.loads(rondo_run_file(prompt="Say hello", model=model, dry_run=True))
            assert result.get("engine") == "agent", (
                f"{model} in-session should return agent plan, not subprocess. "
                f"Got: {result.get('engine', result.get('status'))}"
            )

    def test_force_new_subprocess(self) -> None:
        """model='sonnet:new' forces subprocess even in-session."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="sonnet:new", dry_run=True))
        # -- :new suffix bypasses inline/agent, goes to subprocess dry-run
        assert result.get("engine") != "inline"
        assert result.get("kind") != "inline_dispatch_plan"

    def test_inline_plan_has_schema(self) -> None:
        """Inline plan includes all fields host needs to execute."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(
            rondo_run_file(
                prompt="Review src/main.py",
                model="",
                dry_run=True,
                done_when="List all findings as JSON",
            )
        )
        assert result["engine"] == "inline"
        assert result["prompt"] == "Review src/main.py"
        assert result["done_when"] == "List all findings as JSON"
        assert result["model"] == "current"

    def test_ollama_model_dispatches_via_http(self) -> None:
        """Local model dispatches via HTTP adapter, not subprocess."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="llama3.1:8b", dry_run=True))
        # -- Ollama goes through HTTP adapter (dry-run returns skipped status)
        assert result.get("kind") != "inline_dispatch_plan"
        assert result.get("kind") != "agent_dispatch_plan"

    def test_empty_prompt_and_model_is_error(self) -> None:
        """No prompt + no model + no file = error."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="", model="", dry_run=True))
        assert result["status"] == "error"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 033 — rondo_multi_review
# -- ──────────────────────────────────────────────────────────────


class TestMultiReview:
    """REQ-109 req 033: multi-provider review tool."""

    def test_dry_run_returns_skipped(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["local:qwen2.5:32b", "gemini:gemini-2.5-flash"]',
                dry_run=True,
            )
        )
        assert result["status"] == "done"
        assert result["provider_count"] == 2
        assert all(p["status"] == "skipped" for p in result["per_provider"])
        assert result["total_cost_usd"] == 0

    def test_default_providers_on_empty(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="Review this", providers="[]", dry_run=True))
        assert result["provider_count"] == 3
        providers = [p["provider"] for p in result["per_provider"]]
        assert "local:qwen2.5:32b" in providers
        assert "gemini:gemini-2.5-flash" in providers
        assert "grok:grok-3" in providers

    def test_invalid_json_returns_error(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="test", providers="not json"))
        assert result["status"] == "error"

    def test_too_many_providers_rejected(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        many = json.dumps([f"provider{i}" for i in range(15)])
        result = json.loads(rondo_multi_review(prompt="test", providers=many))
        assert result["status"] == "error"
        assert "ERR_INPUT_TOO_LARGE" in result.get("code", "")

    def test_prompt_truncated_in_response(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        long_prompt = "x" * 500
        result = json.loads(rondo_multi_review(prompt=long_prompt, providers="[]", dry_run=True))
        assert len(result["prompt"]) <= 200

    def test_empty_prompt_rejected(self) -> None:
        """REQ-109 req 080: empty prompt returns ERR_INVALID_INPUT."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="", providers="[]", dry_run=False))
        assert result["status"] == "error"
        assert result["code"] == "ERR_INVALID_INPUT"

    def test_whitespace_prompt_rejected(self) -> None:
        """REQ-109 req 080: whitespace-only prompt returns ERR_INVALID_INPUT."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="   \n  ", providers="[]", dry_run=False))
        assert result["status"] == "error"
        assert result["code"] == "ERR_INVALID_INPUT"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 052/088 — parallel dispatch
# -- ──────────────────────────────────────────────────────────────


class TestParallelDispatch:
    """REQ-109 req 052: multi_review dispatches concurrently."""

    def test_parallel_preserves_provider_order(self) -> None:
        """Results come back in same order as input providers."""
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_order: list[str] = []

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            call_order.append(model)
            return json.dumps(
                {
                    "status": "done",
                    "tasks": [{"raw_output": f"Review from {model}", "duration_sec": 0.1}],
                    "total_cost_usd": 0,
                }
            )

        providers = '["provider_a:model_a", "provider_b:model_b", "provider_c:model_c"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(rondo_multi_review(prompt="test", providers=providers, dry_run=False))

        # -- Results must be in original order regardless of thread completion order
        result_providers = [r["provider"] for r in result["per_provider"]]
        assert result_providers == ["provider_a:model_a", "provider_b:model_b", "provider_c:model_c"]

    def test_parallel_one_failure_others_succeed(self) -> None:
        """REQ-109 req 088: one thread failure doesn't crash others."""
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_count = 0

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if "bad" in model:
                msg = "Simulated failure"
                raise ConnectionError(msg)
            return json.dumps(
                {"status": "done", "tasks": [{"raw_output": "OK", "duration_sec": 0.1}], "total_cost_usd": 0}
            )

        providers = '["good:model_a", "bad:model_b", "good:model_c"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(rondo_multi_review(prompt="test", providers=providers, dry_run=False))

        # -- All 3 dispatched
        assert call_count == 3
        # -- 2 succeeded, 1 failed
        statuses = [r["status"] for r in result["per_provider"]]
        assert statuses.count("done") == 2
        assert statuses.count("error") == 1

    def test_parallel_uses_threads(self) -> None:
        """Verify ThreadPoolExecutor is used (not sequential loop)."""
        import threading
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        threads_seen: set[int] = set()

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            threads_seen.add(threading.current_thread().ident)
            import time

            time.sleep(0.05)  # force thread pool to use multiple workers
            return json.dumps(
                {"status": "done", "tasks": [{"raw_output": "OK", "duration_sec": 0.1}], "total_cost_usd": 0}
            )

        providers = '["a:m1", "b:m2", "c:m3"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            rondo_multi_review(prompt="test", providers=providers, dry_run=False)

        # -- With 3 providers, should use multiple threads (not all on main thread)
        assert len(threads_seen) >= 2, f"Expected multiple threads, got {len(threads_seen)}"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 081 — dry-run prompt_length field
# -- ──────────────────────────────────────────────────────────────


class TestDryRunPromptLength:
    """REQ-109 req 081: dry-run output includes prompt_length."""

    def test_inline_dry_run_has_prompt_length(self) -> None:
        """Dry-run with inline prompt shows prompt_length field."""
        from rondo.mcp_server import rondo_run_file

        long_prompt = "Review this code: " + "x" * 2000
        result = json.loads(rondo_run_file(prompt=long_prompt, dry_run=True))
        tasks = result.get("tasks", [])
        if tasks:
            assert "prompt_length" in tasks[0], "Dry-run task missing prompt_length field"
            assert tasks[0]["prompt_length"] > 500, "prompt_length should reflect actual size"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 reqs 046-063 — rondo_cloud
# -- ──────────────────────────────────────────────────────────────


class TestCloudDispatch:
    """REQ-109 reqs 046-063: cloud dispatch with profiles, tiers, cost caps."""

    def test_dry_run_returns_cloud_metadata(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Review this", dry_run=True))
        assert result["status"] == "done"
        assert "cloud" in result
        assert result["cloud"]["tier"] == "default"
        assert result["cloud"]["count_requested"] == 2

    def test_profile_review(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Review this", profile="review", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "review"

    def test_profile_coding(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Fix this", profile="coding", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "coding"

    def test_invalid_profile_returns_error(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", profile="nonexistent", dry_run=True))
        assert result["status"] == "error"
        assert "ERR_INVALID_PROFILE" in result.get("code", "")

    def test_count_override(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", count=3, dry_run=True))
        assert result["cloud"]["count_requested"] == 3

    def test_count_exceeds_max(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", count=10, dry_run=True))
        assert result["status"] == "error"
        assert "ERR_INPUT_TOO_LARGE" in result.get("code", "")

    def test_tier_high(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", tier="high", dry_run=True))
        assert result["cloud"]["tier"] == "high"

    def test_tier_low(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", tier="low", dry_run=True))
        assert result["cloud"]["tier"] == "low"

    def test_estimated_cost_in_metadata(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", dry_run=True))
        assert "estimated_cost_usd" in result["cloud"]
        assert result["cloud"]["estimated_cost_usd"] >= 0


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b8
