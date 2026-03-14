# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.runner — REQ-001 reqs 6, 7, 40, 45, 46.

VER-001 verification matrix: run_round() contract + orchestration.
TDD: these tests are written BEFORE runner.py exists.

Runner tests mock dispatch_task to test orchestration logic
without invoking real subprocesses.
"""

import sys
from pathlib import Path
from unittest.mock import patch

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.config import RondoConfig
from rondo.engine import (
    DispatchUsage,
    Gate,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.runner import run_round


def _mock_dispatch(task, config, **kwargs):
    """Simulate a successful dispatch."""
    return (
        TaskResult(
            task_name=task.name,
            status="done",
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
            duration_sec=1.0,
        ),
        DispatchUsage(task_name=task.name, model="sonnet", cost_usd=0.01),
    )


def _mock_dispatch_error(task, config, **kwargs):
    """Simulate a failed dispatch."""
    return (
        TaskResult(
            task_name=task.name,
            status="error",
            error_code="ERR_SUBPROCESS",
            error_message="Process crashed",
            raw_output="",
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
            duration_sec=1.0,
        ),
        DispatchUsage(task_name=task.name, model="sonnet"),
    )


# -- Sequential config: forces run_round() to use run_sequential()
SEQ_CONFIG = RondoConfig(workers=1)


# ──────────────────────────────────────────────────────────────────
#  run_round() contract — REQ-001 req 45
# ──────────────────────────────────────────────────────────────────


class TestRunRoundContract:
    def test_returns_round_result(self):
        """run_round() returns a RoundResult."""
        r = Round(name="test", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert isinstance(result, RoundResult)

    def test_default_config_when_none(self):
        """run_round() with no config uses defaults (workers=4 → parallel)."""
        r = Round(name="test", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r)
            assert result.parallelism == 4  # -- default workers=4 routes to parallel

    def test_round_name_in_result(self):
        """RoundResult has the correct round_name."""
        r = Round(name="my-round", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert result.round_name == "my-round"

    def test_timing_fields_populated(self):
        """started_at, completed_at, duration_sec are populated."""
        r = Round(name="test", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert result.started_at != ""
            assert result.completed_at != ""
            assert result.duration_sec >= 0


# ──────────────────────────────────────────────────────────────────
#  Pre-gates — REQ-001 req 6
# ──────────────────────────────────────────────────────────────────


class TestPreGates:
    def test_blocking_pregate_fails_skips_tasks(self):
        """Blocking pre-gate failure → no tasks dispatched, status skipped."""
        r = Round(
            name="gated",
            pre_gates=[Gate("blocker", check_fn=lambda: (False, "nope"), blocking=True)],
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch) as mock_disp:
            result = run_round(r, config=SEQ_CONFIG)
            mock_disp.assert_not_called()
            assert result.status == "skipped"

    def test_non_blocking_pregate_fails_tasks_still_run(self):
        """Non-blocking pre-gate failure → warning, tasks proceed."""
        r = Round(
            name="warned",
            pre_gates=[Gate("warn", check_fn=lambda: (False, "eh"), blocking=False)],
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch) as mock_disp:
            result = run_round(r, config=SEQ_CONFIG)
            mock_disp.assert_called_once()
            assert result.status == "done"

    def test_all_pregates_pass_tasks_run(self):
        """All pre-gates pass → tasks dispatched normally."""
        r = Round(
            name="clear",
            pre_gates=[
                Gate("g1", check_fn=lambda: (True, "ok")),
                Gate("g2", check_fn=lambda: (True, "fine")),
            ],
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch) as mock_disp:
            result = run_round(r, config=SEQ_CONFIG)
            mock_disp.assert_called_once()
            assert result.status == "done"

    def test_pregate_results_in_round_result(self):
        """Pre-gate results captured in RoundResult."""
        r = Round(
            name="gated",
            pre_gates=[Gate("check", check_fn=lambda: (True, "passed"))],
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(result.pre_gate_results) == 1
            assert result.pre_gate_results[0].gate_name == "check"
            assert result.pre_gate_results[0].passed is True


# ──────────────────────────────────────────────────────────────────
#  Post-gates — REQ-001 req 7
# ──────────────────────────────────────────────────────────────────


class TestPostGates:
    def test_post_gates_run_after_tasks(self):
        """Post-gates execute after all tasks complete."""
        post_gate_ran = []
        r = Round(
            name="post",
            tasks=[Task(name="t1", instruction="do", done_when="done")],
            post_gates=[
                Gate("post-check", check_fn=lambda: (post_gate_ran.append(True) or True, "ok")),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(post_gate_ran) == 1
            assert len(result.post_gate_results) == 1

    def test_post_gates_skipped_when_pregate_blocks(self):
        """Post-gates don't run when pre-gate blocked the round."""
        post_gate_ran = []
        r = Round(
            name="blocked",
            pre_gates=[Gate("blocker", check_fn=lambda: (False, "no"), blocking=True)],
            tasks=[Task(name="t1", instruction="do", done_when="done")],
            post_gates=[
                Gate("post", check_fn=lambda: (post_gate_ran.append(True) or True, "ok")),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(post_gate_ran) == 0
            assert len(result.post_gate_results) == 0

    def test_post_gate_results_captured(self):
        """Post-gate results stored in RoundResult."""
        r = Round(
            name="post",
            tasks=[Task(name="t1", instruction="do", done_when="done")],
            post_gates=[
                Gate("quality", check_fn=lambda: (True, "looks good"), blocking=False),
                Gate("coverage", check_fn=lambda: (False, "low"), blocking=False),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(result.post_gate_results) == 2
            assert result.post_gate_results[0].passed is True
            assert result.post_gate_results[1].passed is False


# ──────────────────────────────────────────────────────────────────
#  Task Dispatch Orchestration
# ──────────────────────────────────────────────────────────────────


class TestTaskOrchestration:
    def test_all_tasks_dispatched(self):
        """Every task in the round gets dispatched."""
        r = Round(
            name="multi",
            tasks=[
                Task(name="t1", instruction="do A", done_when="A done"),
                Task(name="t2", instruction="do B", done_when="B done"),
                Task(name="t3", instruction="do C", done_when="C done"),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch) as mock_disp:
            result = run_round(r, config=SEQ_CONFIG)
            assert mock_disp.call_count == 3
            assert len(result.task_results) == 3

    def test_task_results_collected(self):
        """Task results from dispatch are in RoundResult."""
        r = Round(
            name="collect",
            tasks=[Task(name="my-task", instruction="do", done_when="done")],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(result.task_results) == 1
            assert result.task_results[0].task_name == "my-task"
            assert result.task_results[0].status == "done"

    def test_mixed_results_partial_status(self):
        """Mix of done + error tasks → round status partial."""
        call_count = [0]

        def _mixed_dispatch(task, config, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_dispatch(task, config, **kw)
            return _mock_dispatch_error(task, config, **kw)

        r = Round(
            name="mixed",
            tasks=[
                Task(name="t1", instruction="do A", done_when="A"),
                Task(name="t2", instruction="do B", done_when="B"),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mixed_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert result.status == "partial"

    def test_all_error_status(self):
        """All tasks error → round status error."""
        r = Round(
            name="fail",
            tasks=[
                Task(name="t1", instruction="do", done_when="done"),
                Task(name="t2", instruction="do", done_when="done"),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch_error):
            result = run_round(r, config=SEQ_CONFIG)
            assert result.status == "error"

    def test_usage_collected(self):
        """DispatchUsage from each task is in RoundResult.usage."""
        r = Round(
            name="usage",
            tasks=[
                Task(name="t1", instruction="do", done_when="done"),
                Task(name="t2", instruction="do", done_when="done"),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=SEQ_CONFIG)
            assert len(result.usage) == 2
            assert result.usage[0].task_name == "t1"
            assert result.usage[1].task_name == "t2"

    def test_empty_round_skipped(self):
        """Round with no tasks → status skipped."""
        r = Round(name="empty", tasks=[])
        result = run_round(r, config=SEQ_CONFIG)
        assert result.status == "skipped"

    def test_task_failure_doesnt_crash_others(self):
        """STD-001 rule 6: one failure doesn't block remaining tasks."""
        call_count = [0]

        def _first_fails(task, config, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_dispatch_error(task, config, **kw)
            return _mock_dispatch(task, config, **kw)

        r = Round(
            name="resilient",
            tasks=[
                Task(name="fail-first", instruction="do", done_when="done"),
                Task(name="succeed-second", instruction="do", done_when="done"),
            ],
        )
        with patch("rondo.runner.dispatch_task", side_effect=_first_fails) as mock_disp:
            result = run_round(r, config=SEQ_CONFIG)
            assert mock_disp.call_count == 2  # -- second still ran
            assert result.status == "partial"  # -- mix of done + error


# ──────────────────────────────────────────────────────────────────
#  Auto-detect sequential vs parallel — REQ-001 req 40
# ──────────────────────────────────────────────────────────────────


class TestAutoDetect:
    def test_workers_1_uses_sequential(self):
        """workers=1 → run_sequential."""
        r = Round(name="seq", tasks=[Task(name="t1", instruction="do", done_when="done")])
        config = RondoConfig(workers=1)
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r, config=config)
            assert result.parallelism == 1

    def test_default_config_routes_to_parallel(self):
        """Default config with workers=4 routes to run_parallel."""
        r = Round(name="test", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r)
            assert isinstance(result, RoundResult)
            assert result.parallelism == 4


# ──────────────────────────────────────────────────────────────────
#  Task State Updates
# ──────────────────────────────────────────────────────────────────


class TestTaskStateUpdates:
    def test_task_status_updated_to_running(self):
        """Task status set to 'running' before dispatch."""
        states_seen = []

        def _capture_dispatch(task, config, **kw):
            states_seen.append(task.status)
            return _mock_dispatch(task, config, **kw)

        r = Round(name="state", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_capture_dispatch):
            run_round(r, config=SEQ_CONFIG)
            assert "running" in states_seen

    def test_task_status_updated_after_dispatch(self):
        """Task status set to terminal state after dispatch."""
        r = Round(name="state", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            run_round(r, config=SEQ_CONFIG)
            # -- Task object's status should be updated
            assert r.tasks[0].status in ("done", "error", "partial", "blocked", "skipped")


# ──────────────────────────────────────────────────────────────────
#  Result Saving
# ──────────────────────────────────────────────────────────────────


class TestResultSaving:
    def test_results_saved_to_dir(self, tmp_path):
        """Task results saved to results_dir."""
        r = Round(name="save", tasks=[Task(name="t1", instruction="do", done_when="done")])
        config = RondoConfig(results_dir=str(tmp_path / "results"), workers=1)
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            run_round(r, config=config)
            # -- Check that results dir was created and has files
            results_dir = tmp_path / "results"
            assert results_dir.exists()

    def test_round_summary_saved(self, tmp_path):
        """Round summary JSON saved to results_dir."""
        r = Round(name="save", tasks=[Task(name="t1", instruction="do", done_when="done")])
        config = RondoConfig(results_dir=str(tmp_path / "results"), workers=1)
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            run_round(r, config=config)
            # -- Should have at least one file in results dir
            results_dir = tmp_path / "results"
            files = list(results_dir.glob("*.json"))
            assert len(files) >= 1

# -- sig: MgH-252076.cf46a2
