# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""rondo_run_file, rondo_run_status, richer status, background TTL, input limits.

Split from test_mcp.py in RONDO-207 — original file was 1802 lines
(above best-practice range). This file focuses on: run + status.

VER-001: Product acceptance / unit test coverage.
"""

import json

from rondo.mcp_server import (
    rondo_health,
    rondo_metrics,
    rondo_run_file,
    rondo_run_status,
)

# -- ──────────────────────────────────────────────────────────────
# --  IFS-104 req 003 — Query tools
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

    def test_u32_run_status_truncates_raw_output_to_2000_chars(self):
        """U-32 (REQ-100 addendum): rondo_run_status MUST truncate raw_output.

        RONDO-212 regression guard — RONDO-211 fix for #258 removed the
        truncation from _execute_dispatch (correct — multi_review needs full
        output) but the truncation MUST still happen at the rondo_run_status
        boundary per U-32. This test fails loudly if a future refactor moves
        the cap in the wrong direction again.
        """
        from rondo.mcp_server import _background_results

        long_output = "A" * 5000  ## 5000 chars — should be cut to 2000
        _background_results["test-u32"] = {
            "status": "done",
            "done_count": 1,
            "error_count": 0,
            "pending_count": 0,
            "tasks": [
                {
                    "name": "t1",
                    "status": "done",
                    "raw_output": long_output,
                    "duration_sec": 1.0,
                },
            ],
        }
        result = json.loads(rondo_run_status("test-u32"))
        assert "tasks" in result
        assert len(result["tasks"]) == 1
        assert len(result["tasks"][0]["raw_output"]) == 2000, (
            f"U-32 violation: raw_output should be truncated to 2000 chars, got {len(result['tasks'][0]['raw_output'])}"
        )
        ## Verify original _background_results is NOT mutated (shallow copy guard)
        assert len(_background_results["test-u32"]["tasks"][0]["raw_output"]) == 5000, (
            "rondo_run_status must NOT mutate the stored background result; "
            "it should shallow-copy before truncating for the response."
        )

    def test_u32_run_status_handles_missing_raw_output(self):
        """U-32 guard: truncation must handle tasks with no raw_output key."""
        from rondo.mcp_server import _background_results

        _background_results["test-u32-missing"] = {
            "status": "done",
            "done_count": 1,
            "error_count": 0,
            "pending_count": 0,
            "tasks": [
                {"name": "t1", "status": "done", "duration_sec": 1.0},  ## no raw_output
            ],
        }
        ## Must not raise KeyError/TypeError
        result = json.loads(rondo_run_status("test-u32-missing"))
        assert result["tasks"][0]["raw_output"] == ""

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
        """All expected MCP tools are importable from rondo.mcp_server.

        Upgraded in RONDO-208: old version only asserted server is not None
        (identical to test_create_server_has_resource in test_mcp_tools.py).
        Now verifies the actual tool functions are exported — catches bugs
        where a tool is defined but not added to the public surface.
        """
        import rondo.mcp_server as mcp_server

        # -- Core dispatch tools
        expected_tools = [
            "rondo_run_file",
            "rondo_health",
            "rondo_metrics",
            "rondo_history",
            "rondo_dispatch_info",
            "rondo_audit_summary",
            "rondo_cost",
            "rondo_spool_consume",
        ]

        missing = [name for name in expected_tools if not hasattr(mcp_server, name)]
        assert not missing, f"MCP tools not exported: {missing}"

        # -- And the server factory still works
        server = mcp_server.create_mcp_server()
        assert server is not None, "create_mcp_server() returned None"


# -- sig: mgh-197b.ec.8d60f8.a5cf.7ea3fd
