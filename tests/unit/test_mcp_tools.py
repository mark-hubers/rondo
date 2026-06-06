# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""MCP query tools — metrics, health, audit, dispatch info, templates, cost, retry, diff, chain.

Split from test_mcp.py in RONDO-207 — original file was 1802 lines
(above best-practice range). This file focuses on: query tools.

VER-001: Product acceptance / unit test coverage.
"""

import json

from rondo.mcp_server import (
    rondo_audit_summary,
    rondo_dispatch_info,
    rondo_health,
    rondo_history,
    rondo_metrics,
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
        """Explain uses local model by default — assert actual model name."""
        from rondo.mcp_server import rondo_explain

        result = json.loads(
            rondo_explain(
                output="Some code",
                question="Is this correct?",
                dry_run=True,
            )
        )
        tasks = result.get("tasks", [])
        assert len(tasks) >= 1, "Explain should return at least one task"
        model = tasks[0].get("model", "")
        # -- Must be a local/Ollama model, not Claude
        assert model not in ("sonnet", "opus", "haiku", ""), f"Explain should use local model, got: {model!r}"


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


class TestSpoolConsumeMCP:
    """rondo_spool_consume MCP tool."""

    def test_empty_spool_returns_zero(self):
        """Empty spool returns count=0."""
        result = json.loads(rondo_spool_consume())
        assert result["count"] == 0
        assert result["consumed"] == []


class TestDoctorTool:
    """RONDO-324 (REQ-103 reqs 030-035 over MCP): rondo_doctor tool."""

    def test_returns_checks_and_healthy_flag(self, tmp_path, monkeypatch) -> None:
        from rondo.mcp_tools import rondo_doctor

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        data = json.loads(rondo_doctor())
        assert isinstance(data["healthy"], bool)
        assert len(data["checks"]) >= 5
        for check in data["checks"]:
            assert check["result"] in ("PASS", "WARN", "FAIL")

    def test_no_full_keys_in_output(self, tmp_path, monkeypatch) -> None:
        """Req 035 holds over MCP too: keys appear as last-4 only."""
        import re

        from rondo.mcp_tools import rondo_doctor

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        out = rondo_doctor()
        assert not re.search(r"sk-(?:ant-)?[A-Za-z0-9_-]{8,}", out)


class TestFleetTool:
    """RONDO-324: rondo_fleet — the watchdog sweep over MCP, never notifying."""

    def test_returns_watchdog_report(self, tmp_path, monkeypatch) -> None:
        from rondo.mcp_tools import rondo_fleet

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        data = json.loads(rondo_fleet())
        assert data["status"] in ("OK", "ALERT")
        assert "alerts" in data
        assert "retry_sweep" in data

    def test_never_fires_notifications(self, tmp_path, monkeypatch) -> None:
        """MCP caller IS the watcher — a macOS banner would be noise."""
        from rondo import nightly
        from rondo.mcp_tools import rondo_fleet

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        sent: list = []
        monkeypatch.setattr(nightly, "notify_watchdog", lambda alerts, title="": sent.append(alerts))
        monkeypatch.setattr(
            nightly, "_gather_drift", lambda refresh: [{"provider": "x", "model": "dead", "state": "STALE"}]
        )
        data = json.loads(rondo_fleet())
        assert data["status"] == "ALERT"
        assert sent == []


# -- sig: mgh-6c6d.cb.407ae3.6835.6478a2
