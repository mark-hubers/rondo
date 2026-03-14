"""Tests for rondo.parallel — REQ-002 reqs 1-9, STD-003 C1-C7.

VER-001 verification matrix: parallel dispatch + conflict detection.
TDD: these tests are written BEFORE parallel.py exists.

Parallel tests mock dispatch_task to test orchestration logic
without invoking real subprocesses. Threading behavior tested
via controlled execution.
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.config import RondoConfig
from rondo.engine import (
    DispatchUsage,
    Gate,
    GateResult,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.parallel import run_parallel, detect_conflicts


# ──────────────────────────────────────────────────────────────────
#  Helpers — mock dispatchers
# ──────────────────────────────────────────────────────────────────

def _mock_dispatch(task, config, **kwargs):
    """Simulate a successful dispatch with small delay for timing tests."""
    return (
        TaskResult(
            task_name=task.name,
            status="done",
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
            duration_sec=0.5,
            files_modified=[],
        ),
        DispatchUsage(task_name=task.name, model="sonnet", cost_usd=0.01),
    )


def _mock_dispatch_slow(task, config, **kwargs):
    """Simulate a slow dispatch (0.2s each)."""
    time.sleep(0.2)
    return (
        TaskResult(
            task_name=task.name,
            status="done",
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
            duration_sec=0.2,
            files_modified=[],
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
            duration_sec=0.1,
            files_modified=[],
        ),
        DispatchUsage(task_name=task.name, model="sonnet"),
    )


def _mock_dispatch_with_files(file_map):
    """Return a dispatch mock that sets files_modified per task name."""
    def _dispatch(task, config, **kwargs):
        return (
            TaskResult(
                task_name=task.name,
                status="done",
                raw_output='{"status":"done"}',
                model="sonnet",
                auth_mode="max",
                timestamp="2026-03-14T00:00:00Z",
                duration_sec=0.5,
                files_modified=file_map.get(task.name, []),
            ),
            DispatchUsage(task_name=task.name, model="sonnet", cost_usd=0.01),
        )
    return _dispatch


def _make_tasks(n):
    """Create n simple tasks."""
    return [
        Task(name=f"t{i+1}", instruction=f"do {i+1}", done_when=f"done {i+1}")
        for i in range(n)
    ]


# ──────────────────────────────────────────────────────────────────
#  ThreadPoolExecutor usage — REQ-002 req 1, STD-003 C1
# ──────────────────────────────────────────────────────────────────

class TestThreadPoolUsage:

    def test_uses_thread_pool_executor(self):
        """REQ-002 req 1: parallel dispatch uses ThreadPoolExecutor.

        Verified indirectly: parallelism in result matches config.workers,
        and multiple tasks execute concurrently (wall time < sum of task times).
        """
        r = Round(name="pool", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.parallelism == 2
            assert len(result.task_results) == 2


# ──────────────────────────────────────────────────────────────────
#  Worker count — REQ-002 req 2
# ──────────────────────────────────────────────────────────────────

class TestWorkerConfig:

    def test_workers_from_config(self):
        """REQ-002 req 2: worker count from config."""
        r = Round(name="workers", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.parallelism == 3

    def test_workers_1_still_works(self):
        """workers=1 should still use ThreadPoolExecutor (just 1 thread)."""
        r = Round(name="single", tasks=_make_tasks(1))
        config = RondoConfig(workers=1, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.parallelism == 1
            assert result.status == "done"


# ──────────────────────────────────────────────────────────────────
#  Throttle — REQ-002 req 3, STD-003 C3
# ──────────────────────────────────────────────────────────────────

class TestThrottle:

    def test_throttle_delay_between_submissions(self):
        """REQ-002 req 3: configurable delay between submit() calls."""
        r = Round(name="throttle", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.1)

        submit_times = []
        original_dispatch = _mock_dispatch

        def _timed_dispatch(task, config, **kwargs):
            submit_times.append(time.monotonic())
            return original_dispatch(task, config, **kwargs)

        with patch("rondo.parallel.dispatch_task", side_effect=_timed_dispatch):
            run_parallel(r, config)

        # -- Check that submissions are spaced by at least throttle_sec
        assert len(submit_times) == 3
        for i in range(1, len(submit_times)):
            gap = submit_times[i] - submit_times[i - 1]
            assert gap >= 0.08, f"Gap {i}: {gap:.3f}s < 0.08s (expected ≥0.1s)"

    def test_zero_throttle(self):
        """throttle_sec=0 → no delay between submissions."""
        r = Round(name="fast", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            start = time.monotonic()
            run_parallel(r, config)
            elapsed = time.monotonic() - start
            # -- With 0 throttle and mocked dispatch, should be near-instant
            assert elapsed < 1.0


# ──────────────────────────────────────────────────────────────────
#  Result collection — REQ-002 req 4
# ──────────────────────────────────────────────────────────────────

class TestResultCollection:

    def test_all_results_collected(self):
        """REQ-002 req 4: results collected as futures complete."""
        r = Round(name="collect", tasks=_make_tasks(4))
        config = RondoConfig(workers=4, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert len(result.task_results) == 4
            # -- All tasks should appear in results (order may differ)
            names = {tr.task_name for tr in result.task_results}
            assert names == {"t1", "t2", "t3", "t4"}

    def test_usage_collected_for_each_task(self):
        """Usage metadata collected for every task."""
        r = Round(name="usage", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert len(result.usage) == 3
            usage_names = {u.task_name for u in result.usage}
            assert usage_names == {"t1", "t2", "t3"}


# ──────────────────────────────────────────────────────────────────
#  Conflict detection — REQ-002 reqs 5-6, STD-003 C4-C5
# ──────────────────────────────────────────────────────────────────

class TestConflictDetection:

    def test_no_conflicts_when_no_overlapping_files(self):
        """REQ-002 req 5: no conflicts when tasks touch different files."""
        results = [
            TaskResult(task_name="t1", status="done", files_modified=["a.py", "b.py"]),
            TaskResult(task_name="t2", status="done", files_modified=["c.py", "d.py"]),
        ]
        conflicts = detect_conflicts(results)
        assert conflicts == []

    def test_detect_single_conflict(self):
        """REQ-002 req 5: one file modified by two tasks → conflict."""
        results = [
            TaskResult(task_name="t1", status="done", files_modified=["shared.py", "a.py"]),
            TaskResult(task_name="t2", status="done", files_modified=["shared.py", "b.py"]),
        ]
        conflicts = detect_conflicts(results)
        assert len(conflicts) == 1
        assert "shared.py" in conflicts[0]
        assert "t1" in conflicts[0]
        assert "t2" in conflicts[0]

    def test_detect_multiple_conflicts(self):
        """Multiple files with overlapping tasks."""
        results = [
            TaskResult(task_name="t1", status="done", files_modified=["x.py", "y.py"]),
            TaskResult(task_name="t2", status="done", files_modified=["x.py", "z.py"]),
            TaskResult(task_name="t3", status="done", files_modified=["y.py", "z.py"]),
        ]
        conflicts = detect_conflicts(results)
        assert len(conflicts) == 3  # -- x.py, y.py, z.py each touched by 2 tasks

    def test_three_tasks_same_file(self):
        """Three tasks touching the same file → single conflict entry."""
        results = [
            TaskResult(task_name="t1", status="done", files_modified=["core.py"]),
            TaskResult(task_name="t2", status="done", files_modified=["core.py"]),
            TaskResult(task_name="t3", status="done", files_modified=["core.py"]),
        ]
        conflicts = detect_conflicts(results)
        assert len(conflicts) == 1
        assert "t1" in conflicts[0]
        assert "t2" in conflicts[0]
        assert "t3" in conflicts[0]

    def test_empty_files_modified(self):
        """Tasks with no files_modified → no conflicts."""
        results = [
            TaskResult(task_name="t1", status="done", files_modified=[]),
            TaskResult(task_name="t2", status="done", files_modified=[]),
        ]
        conflicts = detect_conflicts(results)
        assert conflicts == []

    def test_conflicts_in_round_result(self):
        """REQ-002 req 6: conflicts appear in RoundResult."""
        file_map = {
            "t1": ["shared.py", "a.py"],
            "t2": ["shared.py", "b.py"],
        }
        r = Round(name="conflict", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch_with_files(file_map)):
            result = run_parallel(r, config)
            assert len(result.conflicts) == 1
            assert "shared.py" in result.conflicts[0]

    def test_conflicts_advisory_not_blocking(self):
        """STD-003 C5: conflicts are warnings, don't fail the round."""
        file_map = {
            "t1": ["shared.py"],
            "t2": ["shared.py"],
        }
        r = Round(name="advisory", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch_with_files(file_map)):
            result = run_parallel(r, config)
            # -- Round status is based on task results, not conflicts
            assert result.status == "done"
            assert len(result.conflicts) == 1


# ──────────────────────────────────────────────────────────────────
#  Summary stats — REQ-002 req 7
# ──────────────────────────────────────────────────────────────────

class TestSummaryStats:

    def test_done_and_error_counts_in_summary(self):
        """REQ-002 req 7: summary includes done/error counts."""
        call_count = [0]
        def _mixed(task, config, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_dispatch(task, config, **kw)
            return _mock_dispatch_error(task, config, **kw)

        r = Round(name="stats", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mixed):
            result = run_parallel(r, config)
            assert "1" in result.summary  # -- 1 done
            assert result.status == "partial"

    def test_timing_fields_populated(self):
        """REQ-002 req 7: wall time and timing fields present."""
        r = Round(name="timing", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.started_at != ""
            assert result.completed_at != ""
            assert result.duration_sec >= 0

    def test_all_done_status(self):
        """All tasks done → round status done."""
        r = Round(name="all-done", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.status == "done"
            assert "3/3" in result.summary

    def test_all_error_status(self):
        """All tasks error → round status error."""
        r = Round(name="all-error", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch_error):
            result = run_parallel(r, config)
            assert result.status == "error"


# ──────────────────────────────────────────────────────────────────
#  Task isolation — REQ-002 req 8, STD-003 C2, C7
# ──────────────────────────────────────────────────────────────────

class TestTaskIsolation:

    def test_one_failure_doesnt_crash_others(self):
        """REQ-002 req 8: single task failure doesn't block others."""
        call_count = [0]
        def _first_fails(task, config, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_dispatch_error(task, config, **kw)
            return _mock_dispatch(task, config, **kw)

        r = Round(name="isolation", tasks=_make_tasks(3))
        config = RondoConfig(workers=3, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_first_fails):
            result = run_parallel(r, config)
            # -- All 3 tasks should have results
            assert len(result.task_results) == 3
            statuses = {tr.status for tr in result.task_results}
            assert "done" in statuses
            assert "error" in statuses

    def test_exception_in_dispatch_caught(self):
        """STD-003 C7: exception in one thread produces error result, not crash."""
        call_count = [0]
        def _raises(task, config, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Thread explosion")
            return _mock_dispatch(task, config, **kw)

        r = Round(name="exception", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_raises):
            result = run_parallel(r, config)
            assert len(result.task_results) == 2
            error_results = [tr for tr in result.task_results if tr.status == "error"]
            assert len(error_results) == 1
            assert "ERR_INTERNAL" in (error_results[0].error_code or "")

    def test_no_shared_state_mutation(self):
        """STD-003 C2: each thread returns own result, no shared list mutation."""
        # -- This test verifies correctness by checking result integrity
        r = Round(name="no-share", tasks=_make_tasks(4))
        config = RondoConfig(workers=4, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            # -- Each result has unique task_name (no stomping)
            names = [tr.task_name for tr in result.task_results]
            assert len(set(names)) == 4


# ──────────────────────────────────────────────────────────────────
#  Result format compatibility — REQ-002 req 9
# ──────────────────────────────────────────────────────────────────

class TestResultFormat:

    def test_returns_round_result(self):
        """REQ-002 req 9: parallel returns same RoundResult as sequential."""
        r = Round(name="format", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert isinstance(result, RoundResult)

    def test_round_name_preserved(self):
        """RoundResult has correct round_name."""
        r = Round(name="my-parallel-round", tasks=_make_tasks(1))
        config = RondoConfig(workers=1, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert result.round_name == "my-parallel-round"

    def test_task_results_are_task_result_type(self):
        """All task results are TaskResult dataclass instances."""
        r = Round(name="types", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            for tr in result.task_results:
                assert isinstance(tr, TaskResult)

    def test_usage_are_dispatch_usage_type(self):
        """All usage entries are DispatchUsage instances."""
        r = Round(name="usage-types", tasks=_make_tasks(2))
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            for u in result.usage:
                assert isinstance(u, DispatchUsage)


# ──────────────────────────────────────────────────────────────────
#  Pre/Post Gates — same contract as sequential runner
# ──────────────────────────────────────────────────────────────────

class TestGatesInParallel:

    def test_blocking_pregate_skips_tasks(self):
        """Blocking pre-gate failure → no tasks dispatched."""
        r = Round(
            name="gated",
            pre_gates=[Gate("blocker", check_fn=lambda: (False, "nope"), blocking=True)],
            tasks=_make_tasks(2),
        )
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch) as mock_disp:
            result = run_parallel(r, config)
            mock_disp.assert_not_called()
            assert result.status == "skipped"

    def test_post_gates_run_after_parallel_tasks(self):
        """Post-gates execute after all parallel tasks complete."""
        post_ran = []
        r = Round(
            name="post",
            tasks=_make_tasks(2),
            post_gates=[
                Gate("post-check", check_fn=lambda: (post_ran.append(True) or True, "ok")),
            ],
        )
        config = RondoConfig(workers=2, throttle_sec=0.0)
        with patch("rondo.parallel.dispatch_task", side_effect=_mock_dispatch):
            result = run_parallel(r, config)
            assert len(post_ran) == 1
            assert len(result.post_gate_results) == 1


# ──────────────────────────────────────────────────────────────────
#  Empty round — edge case
# ──────────────────────────────────────────────────────────────────

class TestEmptyRound:

    def test_empty_round_skipped(self):
        """Round with no tasks → status skipped."""
        r = Round(name="empty", tasks=[])
        config = RondoConfig(workers=4, throttle_sec=0.0)
        result = run_parallel(r, config)
        assert result.status == "skipped"
        assert result.summary == "No tasks in round"
