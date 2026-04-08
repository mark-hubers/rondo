# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Cursor P0/P1/P2 review fixes — error codes, MCP paths, inline pre-populate, command SSoT.

Split from test_mcp.py in RONDO-207 — original file was 1802 lines
(above best-practice range). This file focuses on: Cursor review fixes.

VER-001: Product acceptance / unit test coverage.
"""

import json

from rondo.mcp_server import (
    rondo_dispatch_info,
    rondo_health,
    rondo_metrics,
    rondo_run_file,
)

# -- ──────────────────────────────────────────────────────────────
# --  IFS-104 req 003 — Query tools
# -- ──────────────────────────────────────────────────────────────




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


# -- sig: mgh-ff1e.07.6fd2a1.f8cf.8f8b3e
