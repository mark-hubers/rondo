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


# -- sig: mgh-6201.cd.bd955f.f1a7.98a7b8
