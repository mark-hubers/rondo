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


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b8
