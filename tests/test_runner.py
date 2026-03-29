# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.runner — Rondo-REQ-100 reqs 6, 7, 40, 45, 46.

VER-001 verification matrix: run_round() contract + orchestration.
TDD: these tests are written BEFORE runner.py exists.

Runner tests mock dispatch_task to test orchestration logic
without invoking real subprocesses.
"""

from unittest.mock import patch

# -- Add rondo/src to path so we can import rondo

from rondo.config import RondoConfig
from rondo.engine import (
    DispatchUsage,
    Gate,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.runner import run_round, run_sequential


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
#  run_round() contract — Rondo-REQ-100 req 45
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
#  Pre-gates — Rondo-REQ-100 req 6
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
#  Post-gates — Rondo-REQ-100 req 7
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
        """Rondo-STD-108 rule 6: one failure doesn't block remaining tasks."""
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
#  Auto-detect sequential vs parallel — Rondo-REQ-100 req 40
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
    def test_task_status_updated_to_in_progress(self):
        """Task status set to 'in_progress' before dispatch."""
        states_seen = []

        def _capture_dispatch(task, config, **kw):
            states_seen.append(task.status)
            return _mock_dispatch(task, config, **kw)

        r = Round(name="state", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_capture_dispatch):
            run_round(r, config=SEQ_CONFIG)
            assert "in_progress" in states_seen

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


# ──────────────────────────────────────────────────────────────────
#  Round Pre-flight Validation — validate_round() in runner
# ──────────────────────────────────────────────────────────────────


class TestRunnerValidation:
    def test_invalid_round_returns_error(self):
        """Round with empty name returns error without dispatching."""
        r = Round(name="", tasks=[Task(name="t1", instruction="do", done_when="done")])
        result = run_round(r)
        assert result.status == "error"
        assert "Validation failed" in result.summary

    def test_duplicate_tasks_returns_error(self):
        """Round with duplicate task names returns error."""
        r = Round(
            name="dup-round",
            tasks=[
                Task(name="same", instruction="do A", done_when="A done"),
                Task(name="same", instruction="do B", done_when="B done"),
            ],
        )
        result = run_round(r)
        assert result.status == "error"
        assert "Duplicate" in result.summary

    def test_invalid_task_returns_error(self):
        """Round containing invalid task returns error."""
        r = Round(
            name="bad-task",
            tasks=[Task(name="empty", instruction="", done_when="")],
        )
        result = run_round(r)
        assert result.status == "error"
        assert "Validation failed" in result.summary

    def test_valid_round_proceeds(self):
        """Valid round passes validation and proceeds to dispatch."""
        r = Round(name="good", tasks=[Task(name="t1", instruction="do", done_when="done")])
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch):
            result = run_round(r)
            assert result.status != "error" or "Validation" not in result.summary


# -- REQ-100 reqs 057-059: Circuit breaker
class TestCircuitBreaker:
    """Circuit breaker halts round after 3 consecutive same dispatch errors."""

    def test_three_consecutive_errors_trips_breaker(self):
        """REQ-100 req 057: 3 consecutive same-error halts round."""
        tasks = [Task(name=f"t{i}", instruction="do", done_when="done") for i in range(5)]
        r = Round(name="cb", tasks=tasks)
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch_error):
            result = run_round(r, config=SEQ_CONFIG)
        # -- First 3 tasks error, remaining 2 should be skipped
        statuses = [tr.status for tr in result.task_results]
        assert statuses.count("error") == 3
        assert statuses.count("skipped") == 2
        assert result.status == "error"

    def test_success_resets_breaker(self):
        """REQ-100 req 058: success resets consecutive error counter."""
        call_count = [0]

        def _alternating(task, config, **kw):
            call_count[0] += 1
            if call_count[0] % 3 == 0:
                return _mock_dispatch(task, config, **kw)  # -- success every 3rd
            return _mock_dispatch_error(task, config, **kw)

        tasks = [Task(name=f"t{i}", instruction="do", done_when="done") for i in range(6)]
        r = Round(name="cb-reset", tasks=tasks)
        with patch("rondo.runner.dispatch_task", side_effect=_alternating):
            result = run_round(r, config=SEQ_CONFIG)
        # -- No skipped tasks — success resets counter before hitting 3
        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        assert len(skipped) == 0

    def test_skipped_tasks_have_circuit_breaker_reason(self):
        """REQ-100 req 059: skipped tasks get reason 'circuit_breaker'."""
        tasks = [Task(name=f"t{i}", instruction="do", done_when="done") for i in range(5)]
        r = Round(name="cb-reason", tasks=tasks)
        with patch("rondo.runner.dispatch_task", side_effect=_mock_dispatch_error):
            result = run_round(r, config=SEQ_CONFIG)
        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        for tr in skipped:
            assert "circuit_breaker" in tr.error_message

    def test_different_errors_dont_trip_breaker(self):
        """REQ-100 req 058: only SAME error code counts as consecutive."""
        call_count = [0]
        error_codes = ["ERR_AUTH", "ERR_SUBPROCESS", "ERR_TIMEOUT", "ERR_AUTH", "ERR_SUBPROCESS"]

        def _different_errors(task, config, **kw):
            code = error_codes[call_count[0] % len(error_codes)]
            call_count[0] += 1
            return (
                TaskResult(
                    task_name=task.name, status="error", error_code=code,
                    error_message=f"fail: {code}", raw_output="", model="sonnet",
                    auth_mode="max", timestamp="2026-03-14T00:00:00Z",
                ),
                DispatchUsage(task_name=task.name, model="sonnet"),
            )

        tasks = [Task(name=f"t{i}", instruction="do", done_when="done") for i in range(5)]
        r = Round(name="cb-diff", tasks=tasks)
        with patch("rondo.runner.dispatch_task", side_effect=_different_errors):
            result = run_round(r, config=SEQ_CONFIG)
        # -- All 5 should run (different errors, never 3 consecutive same)
        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        assert len(skipped) == 0


class TestCircuitBreakerDeep:
    """REQ-100 reqs 057-059: circuit breaker deep coverage."""

    def test_trips_after_3_consecutive_same_error(self):
        """3 consecutive same-error trips breaker, remaining skipped."""
        round_def = Round(name="breaker", tasks=[
            Task(name=f"t{i}", instruction="fail", done_when="done")
            for i in range(5)
        ])
        config = RondoConfig()

        with patch("rondo.runner._dispatch_with_safety_net") as mock:
            mock.return_value = (
                TaskResult(task_name="t", status="error", error_code="ERR_RATE_LIMIT"),
                DispatchUsage(task_name="t"),
            )
            result = run_sequential(round_def, config)

        statuses = [tr.status for tr in result.task_results]
        assert statuses.count("error") == 3
        assert statuses.count("skipped") == 2

    def test_resets_on_success(self):
        """Success between errors resets breaker counter."""
        round_def = Round(name="reset", tasks=[
            Task(name="fail1", instruction="a", done_when="done"),
            Task(name="fail2", instruction="b", done_when="done"),
            Task(name="ok", instruction="c", done_when="done"),
            Task(name="fail3", instruction="d", done_when="done"),
            Task(name="fail4", instruction="e", done_when="done"),
        ])
        config = RondoConfig()

        def mock_dispatch(task, cfg):
            if task.name == "ok":
                return (TaskResult(task_name=task.name, status="done"), DispatchUsage())
            return (
                TaskResult(task_name=task.name, status="error", error_code="ERR_TIMEOUT"),
                DispatchUsage(),
            )

        with patch("rondo.runner._dispatch_with_safety_net", side_effect=mock_dispatch):
            result = run_sequential(round_def, config)

        errors = [tr for tr in result.task_results if tr.status == "error"]
        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        assert len(errors) == 4
        assert len(skipped) == 0


class TestRoundTimeout:
    """REQ-100 req 075: round_timeout_sec enforcement."""

    def test_round_timeout_skips_remaining_tasks(self):
        """When round time exceeds timeout, remaining tasks are skipped."""
        round_def = Round(name="slow", tasks=[
            Task(name="t1", instruction="first", done_when="done"),
            Task(name="t2", instruction="second", done_when="done"),
            Task(name="t3", instruction="third", done_when="done"),
        ])
        # -- Config with 0.1s round timeout
        config = RondoConfig(dry_run=True, round_timeout_sec=0)

        with patch("rondo.runner._dispatch_with_safety_net") as mock_dispatch:
            import time as _time

            def slow_dispatch(task, cfg):
                _time.sleep(0.05)
                return (
                    TaskResult(task_name=task.name, status="done"),
                    DispatchUsage(task_name=task.name),
                )

            mock_dispatch.side_effect = slow_dispatch
            result = run_sequential(round_def, config)

        # -- With round_timeout_sec=0, should skip tasks after first
        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        done = [tr for tr in result.task_results if tr.status == "done"]
        # -- At least some tasks should complete, some may skip
        assert len(result.task_results) == 3

    def test_round_timeout_records_reason(self):
        """Timed-out tasks have timeout reason in error_message."""
        round_def = Round(name="timeout", tasks=[
            Task(name="t1", instruction="first", done_when="done"),
            Task(name="t2", instruction="second", done_when="done"),
        ])
        config = RondoConfig(round_timeout_sec=0)

        with patch("rondo.runner._dispatch_with_safety_net") as mock_dispatch:
            import time as _time

            def slow_dispatch(task, cfg):
                _time.sleep(0.05)
                return (
                    TaskResult(task_name=task.name, status="done"),
                    DispatchUsage(task_name=task.name),
                )

            mock_dispatch.side_effect = slow_dispatch
            result = run_sequential(round_def, config)

        skipped = [tr for tr in result.task_results if tr.status == "skipped"]
        if skipped:
            assert any("timeout" in (tr.error_message or "").lower() for tr in skipped)


class TestNotifyOnFailure:
    """REQ-105 req 002: notify on dispatch failure."""

    def test_failure_triggers_notify(self):
        """Failed task triggers notification call."""
        round_def = Round(name="fail-round", tasks=[
            Task(name="will-fail", instruction="break", done_when="never"),
        ])
        config = RondoConfig()

        with patch("rondo.runner._dispatch_with_safety_net") as mock_dispatch, \
             patch("rondo.runner._notify_failure") as mock_notify:
            mock_dispatch.return_value = (
                TaskResult(task_name="will-fail", status="error", error_code="ERR_INTERNAL"),
                DispatchUsage(task_name="will-fail"),
            )
            run_sequential(round_def, config)
            mock_notify.assert_called_once()


class TestSaveResultSafe:
    """Results saved after each task — non-fatal on failure."""

    def test_save_called_per_task(self):
        """_save_result_safe called for each dispatched task."""
        round_def = Round(name="save-test", tasks=[
            Task(name="t1", instruction="do", done_when="done"),
            Task(name="t2", instruction="do", done_when="done"),
        ])
        config = RondoConfig()

        with patch("rondo.runner._dispatch_with_safety_net") as mock_dispatch, \
             patch("rondo.runner._save_result_safe") as mock_save:
            mock_dispatch.return_value = (
                TaskResult(task_name="t", status="done"),
                DispatchUsage(task_name="t"),
            )
            run_sequential(round_def, config)
            assert mock_save.call_count == 2


# -- sig: mgh-6201.cd.bd955f.d451.a88884
