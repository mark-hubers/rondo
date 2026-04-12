# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.cli — Rondo-REQ-100 reqs 36-41.

VER-001 verification matrix: CLI entry point, subcommands, flags.
TDD: tests written BEFORE cli.py exists.

CLI tests verify argument parsing, dynamic loading, and
integration wiring without invoking real subprocesses.
"""

import textwrap
from unittest.mock import patch

import pytest

# -- Add rondo/src to path so we can import rondo
from rondo.cli import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_SUCCESS,
    EXIT_USAGE,
    _build_config,
    build_parser,
    main,
)
from rondo.engine import (
    DispatchUsage,
    Round,
    RoundResult,
    TaskResult,
    load_phases_file,  # -- RONDO-213: moved from cli to engine
    load_round_file,  # -- RONDO-213: moved from cli to engine
)
from rondo.overnight import OvernightResult

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
#  CLI entry point — Rondo-REQ-100 req 36
# ──────────────────────────────────────────────────────────────────


class TestCliEntryPoint:
    def test_parser_exists(self):
        """Rondo-REQ-100 req 36: CLI entry point exists."""
        parser = build_parser()
        assert parser is not None

    def test_help_flag(self):
        """--help doesn't crash."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


# ──────────────────────────────────────────────────────────────────
#  Subcommands — Rondo-REQ-100 req 37
# ──────────────────────────────────────────────────────────────────


class TestSubcommands:
    def test_run_subcommand(self):
        """Rondo-REQ-100 req 37: 'run' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["run", "path/to/round.py"])
        assert args.command == "run"

    def test_overnight_subcommand(self):
        """Rondo-REQ-100 req 37: 'overnight' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["overnight", "path/to/phases.py"])
        assert args.command == "overnight"

    def test_report_subcommand(self):
        """Rondo-REQ-100 req 37: 'report' subcommand exists."""
        parser = build_parser()
        args = parser.parse_args(["report", "path/to/results/"])
        assert args.command == "report"


# ──────────────────────────────────────────────────────────────────
#  Run with file — Rondo-REQ-100 req 38
# ──────────────────────────────────────────────────────────────────


class TestRunWithFile:
    def test_run_accepts_file_path(self):
        """Rondo-REQ-100 req 38: run accepts round definition file."""
        parser = build_parser()
        args = parser.parse_args(["run", "rounds/my_round.py"])
        assert args.file == "rounds/my_round.py"

    def test_run_file_required(self):
        """File argument is required for run subcommand."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["run"])


# ──────────────────────────────────────────────────────────────────
#  Dynamic loading — Rondo-REQ-100 req 39
# ──────────────────────────────────────────────────────────────────


class TestDynamicImport:
    def test_load_round_file(self, tmp_path):
        """Rondo-REQ-100 req 39: load round definition from file."""
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
#  CLI flags — Rondo-REQ-100 req 41
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
        """Rondo-REQ-100 req 16: --dry-run flag."""
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
        """Rondo-REQ-100 req 48: --permission-mode flag parsed."""
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
        """main() with no args shows help and returns EXIT_USAGE."""
        exit_code = main([])
        assert exit_code == EXIT_USAGE


# ──────────────────────────────────────────────────────────────────
#  Exit code contract — Rondo-REQ-100 req 36
# ──────────────────────────────────────────────────────────────────


class TestExitCodes:
    def test_exit_constants_defined(self):
        """Exit code constants follow Unix convention."""
        assert EXIT_SUCCESS == 0
        assert EXIT_FAILURE == 1
        assert EXIT_USAGE == 2
        assert EXIT_INTERRUPTED == 130

    def test_success_exit_code(self, tmp_path):
        """Successful round returns EXIT_SUCCESS (0)."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.run_round", return_value=_mock_round_result()):
            assert main(["run", filepath]) == EXIT_SUCCESS

    def test_error_exit_code(self, tmp_path):
        """Failed round returns EXIT_FAILURE (1)."""
        filepath = _write_round_file(tmp_path)
        result = _mock_round_result()
        result.status = "error"
        with patch("rondo.cli.run_round", return_value=result):
            assert main(["run", filepath]) == EXIT_FAILURE

    def test_no_subcommand_exit_code(self):
        """No subcommand returns EXIT_USAGE (2)."""
        assert main([]) == EXIT_USAGE

    def test_keyboard_interrupt_exit_code(self, tmp_path):
        """KeyboardInterrupt returns EXIT_INTERRUPTED (130)."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.run_round", side_effect=KeyboardInterrupt):
            assert main(["run", filepath]) == EXIT_INTERRUPTED

    def test_unexpected_error_exit_code(self, tmp_path):
        """Unexpected exception returns EXIT_FAILURE (1)."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.run_round", side_effect=RuntimeError("boom")):
            assert main(["run", filepath]) == EXIT_FAILURE

    def test_file_not_found_exit_code(self):
        """Missing round file returns EXIT_FAILURE (1)."""
        assert main(["run", "/nonexistent/file.py"]) == EXIT_FAILURE

    def test_config_validation_error(self, tmp_path):
        """Invalid config returns EXIT_FAILURE before running."""
        filepath = _write_round_file(tmp_path)
        with patch("rondo.cli.validate_config", return_value=["workers must be positive"]):
            assert main(["run", filepath]) == EXIT_FAILURE


# ──────────────────────────────────────────────────────────────────
#  Round validation at runner level
# ──────────────────────────────────────────────────────────────────


class TestRunnerValidation:
    def test_invalid_round_returns_error_result(self, tmp_path):
        """Round with validation errors returns error status without dispatch."""
        bad_content = textwrap.dedent("""\
            from rondo.engine import Round, Task

            def build_round():
                return Round(
                    name="",
                    tasks=[Task(name="t1", instruction="do", done_when="done")],
                )
        """)
        filepath = _write_round_file(tmp_path, content=bad_content)
        with patch("rondo.cli.run_round") as mock_run:
            # -- run_round should see validate_round errors and return error result
            mock_run.return_value = RoundResult(
                round_name="",
                status="error",
                summary="Validation failed: Round name is empty",
            )
            exit_code = main(["run", filepath])
            assert exit_code == EXIT_FAILURE


# ──────────────────────────────────────────────────────────────────
#  Dynamic loading — load_phases_file() (Rondo-REQ-100 req 39)
# ──────────────────────────────────────────────────────────────────


def _write_phases_file(tmp_path, content=None):
    """Write a minimal phases definition file and return path."""
    if content is None:
        content = textwrap.dedent("""\
            from rondo.engine import Round, Task

            def build_phases():
                return [
                    Round(
                        name="phase-1",
                        tasks=[Task(name="t1", instruction="do work", done_when="done")],
                    ),
                ]
        """)
    filepath = tmp_path / "my_phases.py"
    filepath.write_text(content)
    return str(filepath)


class TestLoadPhasesFile:
    def test_load_phases_file_success(self, tmp_path):
        """load_phases_file returns list[Round] from build_phases()."""
        filepath = _write_phases_file(tmp_path)
        phases = load_phases_file(filepath)
        assert isinstance(phases, list)
        assert len(phases) == 1
        assert isinstance(phases[0], Round)
        assert phases[0].name == "phase-1"

    def test_load_phases_file_not_found(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_phases_file("/nonexistent/phases.py")

    def test_load_phases_file_no_build_phases(self, tmp_path):
        """File without build_phases() raises AttributeError."""
        filepath = tmp_path / "bad_phases.py"
        filepath.write_text("x = 42\n")
        with pytest.raises(AttributeError, match="build_phases"):
            load_phases_file(str(filepath))

    def test_load_phases_file_wrong_return_type(self, tmp_path):
        """build_phases() returning wrong type raises TypeError."""
        filepath = tmp_path / "wrong_type.py"
        filepath.write_text("def build_phases(): return 'not a list'\n")
        with pytest.raises(TypeError, match="list"):
            load_phases_file(str(filepath))

    def test_load_phases_file_import_error(self, tmp_path):
        """File that can't produce a module spec raises ImportError."""
        # -- A directory can't be loaded as a module
        dirpath = tmp_path / "not_a_file.py"
        dirpath.mkdir()
        with pytest.raises((ImportError, IsADirectoryError)):
            load_phases_file(str(dirpath))


# ──────────────────────────────────────────────────────────────────
#  Config construction — _build_config()
# ──────────────────────────────────────────────────────────────────


class TestBuildConfig:
    def test_build_config_no_overrides(self):
        """_build_config with no flags returns defaults."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py"])
        config = _build_config(args)
        assert config.workers == 4
        assert config.default_model == "sonnet"
        assert config.dry_run is False
        assert config.verbose is False

    def test_build_config_workers_override(self):
        """--workers flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--workers", "8"])
        config = _build_config(args)
        assert config.workers == 8

    def test_build_config_model_override(self):
        """--model flag flows into config as default_model."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--model", "opus"])
        config = _build_config(args)
        assert config.default_model == "opus"

    def test_build_config_auth_override(self):
        """--auth flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--auth", "api"])
        config = _build_config(args)
        assert config.auth == "api"

    def test_build_config_timeout_override(self):
        """--timeout flag flows into config as task_timeout_sec."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--timeout", "600"])
        config = _build_config(args)
        assert config.task_timeout_sec == 600

    def test_build_config_effort_override(self):
        """--effort flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--effort", "low"])
        config = _build_config(args)
        assert config.effort == "low"

    def test_build_config_on_overage_override(self):
        """--on-overage flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--on-overage", "stop"])
        config = _build_config(args)
        assert config.on_overage == "stop"

    def test_build_config_permission_mode_override(self):
        """--permission-mode flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--permission-mode", "plan"])
        config = _build_config(args)
        assert config.permission_mode == "plan"

    def test_build_config_dry_run_flag(self):
        """--dry-run boolean flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--dry-run"])
        config = _build_config(args)
        assert config.dry_run is True

    def test_build_config_verbose_flag(self):
        """--verbose boolean flag flows into config."""
        parser = build_parser()
        args = parser.parse_args(["run", "file.py", "--verbose"])
        config = _build_config(args)
        assert config.verbose is True

    def test_build_config_all_overrides(self):
        """All flags at once flow into config correctly."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "run",
                "file.py",
                "--workers",
                "2",
                "--model",
                "haiku",
                "--auth",
                "api",
                "--timeout",
                "120",
                "--effort",
                "medium",
                "--on-overage",
                "pause",
                "--permission-mode",
                "acceptEdits",
                "--dry-run",
                "--verbose",
            ]
        )
        config = _build_config(args)
        assert config.workers == 2
        assert config.default_model == "haiku"
        assert config.auth == "api"
        assert config.task_timeout_sec == 120
        assert config.effort == "medium"
        assert config.on_overage == "pause"
        assert config.permission_mode == "acceptEdits"
        assert config.dry_run is True
        assert config.verbose is True


# ──────────────────────────────────────────────────────────────────
#  Overnight subcommand — _cmd_overnight()
# ──────────────────────────────────────────────────────────────────


def _mock_overnight_result(status="done"):
    """Build a minimal OvernightResult for testing."""
    return OvernightResult(
        mode="all",
        started_at="2026-03-14T00:00:00Z",
        completed_at="2026-03-14T01:00:00Z",
        duration_sec=3600.0,
        phase_results=[_mock_round_result("phase-1")],
        total_cost_usd=0.50,
        status=status,
    )


class TestOvernightSubcommand:
    def test_overnight_file_not_found(self):
        """Overnight with missing file returns EXIT_FAILURE."""
        assert main(["overnight", "/nonexistent/phases.py"]) == EXIT_FAILURE

    def test_overnight_success(self, tmp_path):
        """Overnight with valid phases returns EXIT_SUCCESS."""
        filepath = _write_phases_file(tmp_path)
        result = _mock_overnight_result("done")
        with (
            patch("rondo.overnight.run_overnight", return_value=result),
            patch("rondo.report.save_report", return_value="/tmp/report.md"),
        ):
            assert main(["overnight", filepath]) == EXIT_SUCCESS

    def test_overnight_error_status(self, tmp_path):
        """Overnight with error status returns EXIT_FAILURE."""
        filepath = _write_phases_file(tmp_path)
        result = _mock_overnight_result("error")
        with (
            patch("rondo.overnight.run_overnight", return_value=result),
            patch("rondo.report.save_report", return_value="/tmp/report.md"),
        ):
            assert main(["overnight", filepath]) == EXIT_FAILURE

    def test_overnight_config_validation_error(self, tmp_path):
        """Overnight with invalid config returns EXIT_FAILURE before running."""
        filepath = _write_phases_file(tmp_path)
        with patch("rondo.cli.validate_config", return_value=["workers out of range"]):
            assert main(["overnight", filepath]) == EXIT_FAILURE

    def test_overnight_report_save_failure(self, tmp_path):
        """Overnight continues even if report save fails."""
        filepath = _write_phases_file(tmp_path)
        result = _mock_overnight_result("done")
        with (
            patch("rondo.overnight.run_overnight", return_value=result),
            patch("rondo.report.save_report", side_effect=OSError("disk full")),
        ):
            # -- Still returns EXIT_SUCCESS because phases succeeded
            assert main(["overnight", filepath]) == EXIT_SUCCESS

    def test_overnight_with_mode_flag(self, tmp_path):
        """--mode flag passed through to run_overnight."""
        filepath = _write_phases_file(tmp_path)
        result = _mock_overnight_result("done")
        with (
            patch("rondo.overnight.run_overnight", return_value=result) as mock_run,
            patch("rondo.report.save_report", return_value="/tmp/report.md"),
        ):
            main(["overnight", filepath, "--mode", "minimal"])
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["mode"] == "minimal"

    def test_overnight_no_build_phases(self, tmp_path):
        """Overnight with file missing build_phases() returns EXIT_FAILURE."""
        filepath = tmp_path / "bad_phases.py"
        filepath.write_text("x = 42\n")
        assert main(["overnight", str(filepath)]) == EXIT_FAILURE


# ──────────────────────────────────────────────────────────────────
#  Report subcommand — _cmd_report()
# ──────────────────────────────────────────────────────────────────


class TestReportSubcommand:
    def test_report_not_yet_implemented(self):
        """Report subcommand returns EXIT_FAILURE (not yet implemented)."""
        assert main(["report", "/some/results/"]) == EXIT_FAILURE


# ──────────────────────────────────────────────────────────────────
#  Verbose output path
# ──────────────────────────────────────────────────────────────────


class TestVerboseOutput:
    def test_verbose_run_prints_details(self, tmp_path, capsys):
        """Verbose mode prints round name, status, summary, duration, tasks."""
        filepath = _write_round_file(tmp_path)
        result = _mock_round_result("verbose-test")
        with patch("rondo.cli.run_round", return_value=result):
            main(["run", filepath, "--verbose"])
        captured = capsys.readouterr()
        assert "Round: verbose-test" in captured.out
        assert "Status: done" in captured.out
        assert "Duration:" in captured.out

    def test_non_verbose_run_prints_summary_only(self, tmp_path, capsys):
        """Non-verbose mode prints only status: summary."""
        filepath = _write_round_file(tmp_path)
        result = _mock_round_result("quiet-test")
        with patch("rondo.cli.run_round", return_value=result):
            main(["run", filepath])
        captured = capsys.readouterr()
        assert "done: 1/1 tasks done" in captured.out
        assert "Round:" not in captured.out


# ──────────────────────────────────────────────────────────────────
#  __main__.py entry point
# ──────────────────────────────────────────────────────────────────


class TestMainModule:
    def test_main_module_calls_main(self):
        """Python -m rondo calls main() and sys.exit()."""
        with (
            patch("rondo.cli.main", return_value=0) as mock_main,
            pytest.raises(SystemExit) as exc_info,
        ):
            import importlib

            import rondo.__main__  # noqa: F811

            importlib.reload(rondo.__main__)
        mock_main.assert_called_once()
        assert exc_info.value.code == 0


class TestInlinePromptOutputNormalization:
    """CLI inline output should keep normalized smart-return shape."""

    def test_inline_prompt_prints_normalized_json_fields(self, capsys):
        from rondo.engine import DispatchUsage, RoundResult, TaskResult

        result = RoundResult(
            round_name="inline",
            status="done",
            task_results=[
                TaskResult(
                    task_name="inline",
                    status="done",
                    raw_output='{"result":"ok"}',
                    model="sonnet",
                )
            ],
            usage=[DispatchUsage(task_name="inline", model="sonnet", cost_usd=0.0)],
        )
        with (
            patch("rondo.cli._dispatch_with_provider", return_value=result),
            patch("sys.stdin.isatty", return_value=True),
        ):
            exit_code = main(["write a quick summary"])
        captured = capsys.readouterr()
        assert exit_code in (EXIT_SUCCESS, EXIT_FAILURE)
        assert '"result": "ok"' in captured.out
        assert '"_meta"' in captured.out
        assert '"issues"' in captured.out
        assert '"_json_valid"' in captured.out


# -- Rondo-REQ-103 req 015: preflight standalone command
class TestPreflightSubcommand:
    def test_preflight_returns_success_when_green(self, capsys):
        """Rondo preflight returns 0 when all checks pass."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            exit_code = main(["preflight"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "GREEN" in captured.out

    def test_preflight_returns_failure_when_red(self, capsys):
        """Rondo preflight returns 1 when critical check fails."""
        with patch("shutil.which", return_value=None):
            exit_code = main(["preflight"])
        assert exit_code == EXIT_FAILURE
        captured = capsys.readouterr()
        assert "RED" in captured.err or "RED" in captured.out

    def test_preflight_shows_checks(self, capsys):
        """Preflight output shows individual check results."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            main(["preflight"])
        captured = capsys.readouterr()
        assert "claude" in captured.out.lower()

    def test_preflight_json_output(self, capsys):
        """Rondo preflight --json returns valid JSON."""
        import json

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            exit_code = main(["preflight", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "GREEN"
        assert "checks" in data
        assert "errors" in data
        assert exit_code == EXIT_SUCCESS


class TestHistorySubcommand:
    def test_history_empty(self, capsys):
        """Rondo history with no data shows message."""
        exit_code = main(["history", "--results-dir", "/tmp/nonexistent-rondo"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "no dispatch" in captured.out.lower() or "No dispatch" in captured.out

    def test_history_json_empty(self, capsys):
        """Rondo history --json with no data returns empty array."""
        import json

        exit_code = main(["history", "--json", "--results-dir", "/tmp/nonexistent-rondo"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []


class TestVersionFlag:
    def test_version_output(self, capsys):
        """Rondo --version shows version string."""
        from rondo.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])
        captured = capsys.readouterr()
        assert "0.2.0" in captured.out or "rondo" in captured.out


# -- Retroactive tests for Sprints 25-28 (Finding #148: TDD skipped)
class TestCostDisplay:
    """Sprint 25: cost appears in CLI output."""

    def test_verbose_shows_cost(self, tmp_path, capsys):
        """Verbose run output includes cost line."""
        round_file = _write_round_file(tmp_path)
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.runner.dispatch_task") as mock_disp,
        ):
            from rondo.engine import DispatchUsage, TaskResult

            mock_disp.return_value = (
                TaskResult(task_name="t1", status="done", model="sonnet", auth_mode="max"),
                DispatchUsage(task_name="t1", model="sonnet", cost_usd=0.05),
            )
            main(["run", round_file, "--verbose"])
        captured = capsys.readouterr()
        assert "$" in captured.out or "Cost" in captured.out


class TestNewCLIFlags:
    """Sprint 24: --bare, --json-schema, --system-prompt, --max-budget passed to config."""

    def test_bare_flag_in_config(self):
        """--bare sets config.bare=True."""
        from rondo.cli import _build_config, build_parser

        parser = build_parser()
        args = parser.parse_args(["run", "/tmp/test-round-e2e.py", "--bare"])
        config = _build_config(args)
        assert config.bare is True

    def test_json_schema_auto_in_config(self):
        """--json-schema auto sets config.json_schema='auto'."""
        from rondo.cli import _build_config, build_parser

        parser = build_parser()
        args = parser.parse_args(["run", "/tmp/test-round-e2e.py", "--json-schema", "auto"])
        config = _build_config(args)
        assert config.json_schema == "auto"

    def test_system_prompt_in_config(self):
        """--system-prompt sets config.dispatch_system_prompt."""
        from rondo.cli import _build_config, build_parser

        parser = build_parser()
        args = parser.parse_args(["run", "/tmp/test-round-e2e.py", "--system-prompt", "auto"])
        config = _build_config(args)
        assert config.dispatch_system_prompt == "auto"

    def test_max_budget_in_config(self):
        """--max-budget sets config.max_budget_usd."""
        from rondo.cli import _build_config, build_parser

        parser = build_parser()
        args = parser.parse_args(["run", "/tmp/test-round-e2e.py", "--max-budget", "0.50"])
        config = _build_config(args)
        assert config.max_budget_usd == 0.50


class TestHumanInputField:
    """Sprint 26: human_input field on Task."""

    def test_task_has_human_input_default(self):
        """human_input defaults to empty string."""
        from rondo.engine import Task

        t = Task(name="t")
        assert t.human_input == ""

    def test_task_accepts_human_input(self):
        """human_input can be set."""
        from rondo.engine import Task

        t = Task(name="t", human_input="Please review this first")
        assert t.human_input == "Please review this first"


class TestExpensiveSort:
    """Sprint 27: --expensive sorts by cost."""

    def test_expensive_flag_accepted(self):
        """Rondo history --expensive doesn't error."""
        exit_code = main(["history", "--expensive", "--results-dir", "/tmp/nonexistent-rondo"])
        assert exit_code == EXIT_SUCCESS


class TestFailureNotification:
    """Sprint 28: failure notifications wired into runner."""

    def test_failure_notify_called_on_error(self):
        """notify_failure called when task has error_code."""
        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("rondo.runner.dispatch_task") as mock_disp,
            patch("rondo.runner._notify_failure") as mock_notify,
        ):
            from rondo.config import RondoConfig
            from rondo.engine import DispatchUsage, Round, Task, TaskResult
            from rondo.runner import run_round

            mock_disp.return_value = (
                TaskResult(
                    task_name="t1",
                    status="error",
                    error_code="ERR_AUTH",
                    error_message="bad key",
                    model="sonnet",
                    auth_mode="max",
                ),
                DispatchUsage(task_name="t1", model="sonnet"),
            )
            r = Round(name="fail-test", tasks=[Task(name="t1", instruction="do", done_when="done")])
            run_round(r, config=RondoConfig(workers=1))
            mock_notify.assert_called_once()


# -- ──────────────────────────────────────────────────────────────
# --  rondo providers — REQ-109 req 020
# -- ──────────────────────────────────────────────────────────────


class TestProvidersSubcommand:
    """rondo providers shows all configured providers with health status."""

    def test_no_providers_configured(self, capsys) -> None:
        """Returns 0 and message when no providers configured."""
        with patch("rondo.adapters.health.get_all_providers_health", return_value={}):
            exit_code = main(["providers"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "No providers" in captured.out

    def test_shows_healthy_provider(self, capsys) -> None:
        """Healthy provider shows UP in output."""
        import time

        from rondo.adapters.health import HealthStatus

        mock_map = {"gemini": HealthStatus(provider="gemini", healthy=True, latency_ms=55.0, checked_at=time.time())}
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_map):
            exit_code = main(["providers"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "gemini" in captured.out
        assert "UP" in captured.out

    def test_shows_unhealthy_provider(self, capsys) -> None:
        """Unhealthy provider shows DOWN in output."""
        import time

        from rondo.adapters.health import HealthStatus

        mock_map = {
            "openai": HealthStatus(
                provider="openai", healthy=False, latency_ms=0.0, checked_at=time.time(), error="timeout"
            )
        }
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_map):
            exit_code = main(["providers"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "openai" in captured.out
        assert "DOWN" in captured.out

    def test_json_output(self, capsys) -> None:
        """--json returns valid JSON with providers list."""
        import json
        import time

        from rondo.adapters.health import HealthStatus

        mock_map = {"gemini": HealthStatus(provider="gemini", healthy=True, latency_ms=30.0, checked_at=time.time())}
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_map):
            exit_code = main(["providers", "--json"])
        assert exit_code == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "providers" in data
        assert data["providers"][0]["provider"] == "gemini"
        assert data["providers"][0]["healthy"] is True

    def test_json_empty_when_no_providers(self, capsys) -> None:
        """--json returns empty list when no providers configured."""
        import json

        with patch("rondo.adapters.health.get_all_providers_health", return_value={}):
            main(["providers", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == {"providers": []}


# -- sig: mgh-6201.cd.bd955f.90ef.7572f7
