# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.cli — REQ-001 reqs 36-41.

VER-001 verification matrix: CLI entry point, subcommands, flags.
TDD: tests written BEFORE cli.py exists.

CLI tests verify argument parsing, dynamic loading, and
integration wiring without invoking real subprocesses.
"""

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.cli import (
    build_parser,
    load_round_file,
    main,
)
from rondo.engine import DispatchUsage, Round, RoundResult, TaskResult

# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────


def _mock_round_result(name="test"):
    return RoundResult(
        round_name=name,
        status="done",
        summary="1/1 tasks done",
        started_at="2026-03-14T00:00:00Z",
        completed_at="2026-03-14T00:01:00Z",
        duration_sec=60.0,
        task_results=[TaskResult(task_name=f"{name}-t1", status="done")],
        usage=[DispatchUsage(task_name=f"{name}-t1", model="sonnet", cost_usd=0.01)],
        parallelism=1,
    )


def _write_round_file(tmp_path, content=None):
    """Write a minimal round definition file and return path."""
    if content is None:
        content = textwrap.dedent("""\
            from rondo.engine import Round, Task

            def build_round():
                return Round(
                    name="test-round",
                    tasks=[Task(name="t1", instruction="do work", done_when="done")],
                )
        """)
    filepath = tmp_path / "my_round.py"
    filepath.write_text(content)
    return str(filepath)


# ──────────────────────────────────────────────────────────────────
#  CLI entry point — REQ-001 req 36
# ──────────────────────────────────────────────────────────────────


class TestCliEntryPoint:
    def test_parser_exists(self):
        """REQ-001 req 36: CLI entry point exists."""
        parser = build_parser()
        assert parser is not None

    def test_help_flag(self):
        """--help doesn't crash."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


# ──────────────────────────────────────────────────────────────────
#  Subcommands — REQ-001 req 37
# ──────────────────────────────────────────────────────────────────


class TestSubcommands:
    def test_run_subcommand(self):
        """REQ-001 req 37: 'run' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["run", "path/to/round.py"])
        assert args.command == "run"

    def test_overnight_subcommand(self):
        """REQ-001 req 37: 'overnight' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["overnight", "path/to/phases.py"])
        assert args.command == "overnight"

    def test_report_subcommand(self):
        """REQ-001 req 37: 'report' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["report", "path/to/results/"])
        assert args.command == "report"


# ──────────────────────────────────────────────────────────────────
#  Run with file — REQ-001 req 38
# ──────────────────────────────────────────────────────────────────


class TestRunWithFile:
    def test_run_accepts_file_path(self):
        """REQ-001 req 38: run accepts round definition file."""
        parser = build_parser()
        args = parser.parse_args(["run", "rounds/my_round.py"])
        assert args.file == "rounds/my_round.py"

    def test_run_file_required(self):
        """File argument is required for run subcommand."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["run"])


# ──────────────────────────────────────────────────────────────────
#  Dynamic loading — REQ-001 req 39
# ──────────────────────────────────────────────────────────────────


class TestDynamicImport:
    def test_load_round_file(self, tmp_path):
        """REQ-001 req 39: load round definition from file."""
        filepath = _write_round_file(tmp_path)
        round_def = load_round_file(filepath)
        assert isinstance(round_def, Round)
        assert round_def.name == "test-round"
        assert len(round_def.tasks) == 1

    def test_load_round_file_not_found(self):
        """Missing file → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_round_file("/nonexistent/path.py")

    def test_load_round_file_no_build_round(self, tmp_path):
        """File without build_round() → AttributeError."""
        filepath = tmp_path / "bad_round.py"
        filepath.write_text("x = 42\n")
        with pytest.raises(AttributeError, match="build_round"):
            load_round_file(str(filepath))

    def test_load_round_file_returns_wrong_type(self, tmp_path):
        """build_round() returning wrong type → TypeError."""
        filepath = tmp_path / "wrong_type.py"
        filepath.write_text("def build_round(): return 'not a round'\n")
        with pytest.raises(TypeError, match="Round"):
            load_round_file(str(filepath))


# ──────────────────────────────────────────────────────────────────
#  CLI flags — REQ-001 req 41
# ──────────────────────────────────────────────────────────────────


class TestCliFlags:
    def test_workers_flag(self):
        """--workers flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--workers", "8"])
        assert args.workers == 8

    def test_model_flag(self):
        """--model flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--model", "opus"])
        assert args.model == "opus"

    def test_auth_flag(self):
        """--auth flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--auth", "api"])
        assert args.auth == "api"

    def test_timeout_flag(self):
        """--timeout flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--timeout", "600"])
        assert args.timeout == 600

    def test_config_flag(self):
        """--config flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--config", "rondo.toml"])
        assert args.config == "rondo.toml"

    def test_dry_run_flag(self):
        """REQ-001 req 16: --dry-run flag."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--dry-run"])
        assert args.dry_run is True

    def test_verbose_flag(self):
        """--verbose flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--verbose"])
        assert args.verbose is True

    def test_default_flags(self):
        """Default flag values."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py"])
        assert args.workers is None
        assert args.model is None
        assert args.auth is None
        assert args.timeout is None
        assert args.config is None
        assert args.dry_run is False
        assert args.verbose is False
        assert args.permission_mode is None

    def test_effort_flag(self):
        """--effort flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--effort", "low"])
        assert args.effort == "low"

    def test_on_overage_flag(self):
        """--on-overage flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--on-overage", "stop"])
        assert args.on_overage == "stop"

    def test_permission_mode_flag(self):
        """REQ-001 req 48: --permission-mode flag parsed."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--permission-mode", "bypassPermissions"])
        assert args.permission_mode == "bypassPermissions"

    def test_permission_mode_overnight(self):
        """--permission-mode available on overnight subcommand too."""
        parser = build_parser()
        args = parser.parse_args(["overnight", "file.py", "--permission-mode", "acceptEdits"])
        assert args.permission_mode == "acceptEdits"


# ──────────────────────────────────────────────────────────────────
#  Main integration — runs run_round with correct config
# ──────────────────────────────────────────────────────────────────


class TestMainIntegration:
    def test_main_run_calls_run_round(self, tmp_path):
        """main() with 'run' subcommand calls run_round."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.run_round", return_value=_mock_round_result()) as mock_run:
            exit_code = main(["run", filepath])
            mock_run.assert_called_once()
            assert exit_code == 0

    def test_main_run_with_flags(self, tmp_path):
        """main() passes CLI flags through config."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.run_round", return_value=_mock_round_result()) as mock_run:
            main(["run", filepath, "--workers", "1", "--dry-run"])
            call_args = mock_run.call_args
            config = call_args[1].get("config") or call_args[0][1]
            assert config.dry_run is True
            assert config.workers == 1

    def test_main_run_error_exit_code(self, tmp_path):
        """main() returns non-zero exit code on round error."""
        filepath = _write_round_file(tmp_path)
        error_result = _mock_round_result()
        error_result.status = "error"
        with patch("rondo.cli.run_round", return_value=error_result):
            exit_code = main(["run", filepath])
            assert exit_code == 1

    def test_main_run_partial_exit_code(self, tmp_path):
        """main() returns non-zero for partial status."""
        filepath = _write_round_file(tmp_path)
        partial_result = _mock_round_result()
        partial_result.status = "partial"
        with patch("rondo.cli.run_round", return_value=partial_result):
            exit_code = main(["run", filepath])
            assert exit_code == 1

    def test_main_no_args(self):
        """main() with no args shows help and exits."""
        with pytest.raises(SystemExit):
            main([])
