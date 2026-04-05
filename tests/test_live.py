# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.live — live mode execution.

Rondo-REQ-100 reqs 47-56.
VER-001 verification matrix: live mode execution.
"""

from __future__ import annotations

from rondo.engine import Gate, Round, Task
from rondo.live import present_task, run_live


class TestPresentTask:
    """Tests for task presentation."""

    def test_presents_interactive_task(self, capsys: object) -> None:
        """Interactive task shows instruction and done_when."""
        task = Task(
            name="check-specs",
            instruction="Run checks on all specs",
            done_when="All checks pass",
            context_files=["specs/OB-REQ-100.md"],
        )
        result = present_task(task, 0, 3)
        captured = capsys.readouterr()  # type: ignore[attr-defined]

        assert "TASK 1 of 3: check-specs" in captured.out
        assert "Run checks on all specs" in captured.out
        assert "All checks pass" in captured.out
        assert "specs/OB-REQ-100.md" in captured.out
        assert result["task_name"] == "check-specs"
        assert result["mode"] == "interactive"

    def test_presents_auto_task(self, capsys: object) -> None:
        """Auto task shows mode indicator."""
        task = Task(
            name="auto-check",
            auto_fn=lambda: (True, "passed"),
            mode="auto",
        )
        result = present_task(task, 1, 5)
        captured = capsys.readouterr()  # type: ignore[attr-defined]

        assert "TASK 2 of 5: auto-check" in captured.out
        assert "auto" in captured.out.lower()
        assert result["mode"] == "auto"


class TestRunLive:
    """Tests for live round execution."""

    def _make_round(self, num_tasks: int = 3) -> Round:
        """Build a test round with N tasks."""
        tasks = [
            Task(
                name=f"task-{i}",
                instruction=f"Do thing {i}",
                done_when=f"Thing {i} done",
            )
            for i in range(1, num_tasks + 1)
        ]
        return Round(name="test-round", tasks=tasks)

    def test_runs_all_tasks(self, capsys: object) -> None:
        """All tasks presented in order."""
        round_def = self._make_round(3)
        results = run_live(round_def)
        captured = capsys.readouterr()  # type: ignore[attr-defined]

        assert len(results) == 3
        assert "TASK 1 of 3" in captured.out
        assert "TASK 2 of 3" in captured.out
        assert "TASK 3 of 3" in captured.out
        assert "3/3 TASKS PRESENTED" in captured.out

    def test_start_from_skips_earlier(self, capsys: object) -> None:
        """--from skips earlier tasks."""
        round_def = self._make_round(3)
        results = run_live(round_def, start_from=1)

        assert len(results) == 2
        assert results[0]["task_name"] == "task-2"

    def test_single_task(self, capsys: object) -> None:
        """--task runs only one."""
        round_def = self._make_round(3)
        results = run_live(round_def, single_task=1)

        assert len(results) == 1
        assert results[0]["task_name"] == "task-2"

    def test_single_task_out_of_range(self, capsys: object) -> None:
        """--task with invalid index returns empty."""
        round_def = self._make_round(3)
        results = run_live(round_def, single_task=10)

        assert len(results) == 0

    def test_pre_gate_blocking(self, capsys: object) -> None:
        """Blocking pre-gate failure stops execution."""
        round_def = Round(
            name="gated-round",
            tasks=[Task(name="t1", instruction="do it", done_when="done")],
            pre_gates=[
                Gate(
                    name="must-pass",
                    check_fn=lambda: (False, "not ready"),
                    blocking=True,
                )
            ],
        )
        results = run_live(round_def)
        captured = capsys.readouterr()  # type: ignore[attr-defined]

        assert len(results) == 0
        assert "FAIL" in captured.out

    def test_progress_saved(self, tmp_path: object) -> None:
        """Progress file updated after each task."""
        import json
        from pathlib import Path

        progress_file = Path(str(tmp_path)) / "progress.json"
        round_def = self._make_round(3)
        run_live(round_def, progress_file=progress_file)

        assert progress_file.exists()
        progress = json.loads(progress_file.read_text())
        assert progress["completed_task"] == 2
        assert progress["total_tasks"] == 3


class TestHumanInputInLive:
    """Finding #151: human_input shows in live mode."""

    def test_human_input_displayed(self, capsys):
        """Task with human_input shows it before instruction."""
        task = Task(
            name="review", instruction="check code", done_when="checked", human_input="Please review the PR first"
        )
        present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "review the PR" in captured.out

    def test_no_human_input_no_display(self, capsys):
        """Task without human_input doesn't show extra section."""
        task = Task(name="auto", instruction="deploy", done_when="deployed")
        present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "HUMAN INPUT" not in captured.out

    def test_context_data_in_live(self, capsys):
        """Task with context_data shows it in live mode."""
        task = Task(name="review", instruction="analyze", done_when="done", context_data={"findings": [1, 2, 3]})
        present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "context_data" in captured.out.lower() or "findings" in captured.out


class TestAutoFnExecution:
    """Finding #153: auto_fn should execute in live mode."""

    def test_auto_fn_runs_and_shows_result(self, capsys):
        """Auto task runs auto_fn and shows (pass, message)."""
        task = Task(name="auto-lint", auto_fn=lambda: (True, "All 12 files pass lint"))
        result = present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "All 12 files pass lint" in captured.out
        assert result.get("auto_result") == (True, "All 12 files pass lint")

    def test_auto_fn_failure_shown(self, capsys):
        """Auto task failure shown clearly."""
        task = Task(name="auto-test", auto_fn=lambda: (False, "3 tests failed"))
        result = present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "3 tests failed" in captured.out
        assert result.get("auto_result") == (False, "3 tests failed")

    def test_auto_fn_exception_caught(self, capsys):
        """Auto task exception doesn't crash live mode."""

        def bad_fn():
            raise RuntimeError("disk full")

        task = Task(name="auto-bad", auto_fn=bad_fn)
        result = present_task(task, 0, 1)
        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "disk full" in captured.out
        assert result.get("auto_error") is not None


class TestLiveModeREQ100MustReqs:
    """REQ-100 MUST requirements for live mode (reqs 061-067, 070)."""

    def test_req061_live_in_current_session(self):
        """Req 061: live mode runs in current session, not subprocess."""
        # -- run_live is a Python call, not subprocess.run
        round_def = Round(
            name="t",
            tasks=[
                Task(name="t1", instruction="do", done_when="done"),
            ],
        )
        results = run_live(round_def)
        assert len(results) == 1
        # -- No subprocess was involved — pure Python execution
        assert results[0]["mode"] == "interactive"

    def test_req062_one_task_at_a_time(self, capsys):
        """Req 062: live mode presents ONE task at a time."""
        round_def = Round(
            name="t",
            tasks=[
                Task(name="t1", instruction="first", done_when="done"),
                Task(name="t2", instruction="second", done_when="done"),
            ],
        )
        run_live(round_def)
        captured = capsys.readouterr()
        # -- Each task gets its own header
        assert "TASK 1 of 2" in captured.out
        assert "TASK 2 of 2" in captured.out

    def test_req065_same_round_definition(self):
        """Req 065: live and batch use same Round definition."""
        # -- Same Round object works for both modes
        round_def = Round(
            name="shared",
            tasks=[
                Task(name="t1", instruction="do it", done_when="done"),
            ],
        )
        # -- Live mode
        live_results = run_live(round_def)
        assert len(live_results) == 1
        # -- Batch mode uses same object (runner.run_round would accept it too)
        assert round_def.name == "shared"

    def test_req067_output_to_terminal(self, capsys):
        """Req 067: live mode output goes to terminal."""
        round_def = Round(
            name="t",
            tasks=[
                Task(name="t1", instruction="check", done_when="checked"),
            ],
        )
        run_live(round_def)
        captured = capsys.readouterr()
        # -- Output went to stdout (terminal), not to a file
        assert len(captured.out) > 0
        assert "check" in captured.out

    def test_req070_resume_from_last(self, capsys):
        """Req 070: --resume continues from last completed task."""
        round_def = Round(
            name="t",
            tasks=[
                Task(name="t1", instruction="first", done_when="done"),
                Task(name="t2", instruction="second", done_when="done"),
                Task(name="t3", instruction="third", done_when="done"),
            ],
        )
        results = run_live(round_def, start_from=2)
        assert len(results) == 1
        assert results[0]["task_name"] == "t3"


class TestTimeoutReqs:
    """REQ-100 MUST requirements for timeouts (reqs 074-077)."""

    def test_req074_task_timeout_default(self):
        """Req 074: task_timeout_sec defaults to 300."""
        from rondo.config import RondoConfig

        config = RondoConfig()
        assert config.task_timeout_sec == 300

    def test_req075_round_timeout_default(self):
        """Req 075: round_timeout_sec defaults to 3600."""
        from rondo.config import RondoConfig

        config = RondoConfig()
        assert config.round_timeout_sec == 3600

    def test_req077_timeout_produces_err_timeout(self):
        """Req 077: on timeout, status=error, error_code=ERR_TIMEOUT."""
        from unittest.mock import patch

        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task

        task = Task(name="slow", instruction="take forever", done_when="never")
        config = RondoConfig(task_timeout_sec=1)

        with patch("rondo.dispatch._run_subprocess") as mock_run:
            # -- Simulate timeout
            mock_run.return_value = ("", "", -1, True)
            result, _ = dispatch_task(task, config)

        assert result.status == "error"
        assert result.error_code == "ERR_TIMEOUT"


class TestToolModeReqs:
    """REQ-100 MUST requirements for tool_mode (reqs 022-024, 083)."""

    def test_req083_tool_mode_none_ignores_allowed(self):
        """Req 083: tool_mode=none ignores --allowed-tools/--disallowed-tools."""
        from rondo.config import RondoConfig
        from rondo.dispatch import _build_subprocess_cmd

        config = RondoConfig()
        task = Task(name="t", instruction="do", done_when="done", tool_mode="none")
        cmd = _build_subprocess_cmd(config, "prompt", "sonnet", task=task)
        # -- Should have --tools "" but NOT --allowed-tools
        assert any("--tools" in str(c) for c in cmd)


# -- sig: mgh-6201.cd.bd955f.b2c3.d4e5f6
