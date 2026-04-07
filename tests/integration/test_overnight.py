# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.overnight — Rondo-REQ-101 reqs 10-28.

VER-001 verification matrix: phase scheduler + watchdog + usage gating.
TDD: tests written BEFORE overnight.py exists.

Overnight tests mock run_round to test orchestration logic
without invoking real subprocesses.
"""

import json
import time
from unittest.mock import patch

import pytest

# -- Add rondo/src to path so we can import rondo
from rondo.config import RondoConfig
from rondo.engine import (
    DispatchUsage,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.overnight import (
    EventLog,
    OvernightResult,
    check_usage_gate,
    run_overnight,
)

# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────


def _make_round(name, n_tasks=1):
    """Create a simple Round with n tasks."""
    tasks = [
        Task(name=f"{name}-t{i + 1}", instruction=f"do {i + 1}", done_when=f"done {i + 1}") for i in range(n_tasks)
    ]
    return Round(name=name, tasks=tasks)


def _mock_round_result(round_name, status="done", n_tasks=1):
    """Create a RoundResult for mocking run_round."""
    task_results = [TaskResult(task_name=f"{round_name}-t{i + 1}", status=status) for i in range(n_tasks)]
    usage = [DispatchUsage(task_name=f"{round_name}-t{i + 1}", model="sonnet", cost_usd=0.01) for i in range(n_tasks)]
    return RoundResult(
        round_name=round_name,
        status=status,
        summary=f"{n_tasks}/{n_tasks} tasks {status}",
        started_at="2026-03-14T00:00:00Z",
        completed_at="2026-03-14T00:01:00Z",
        duration_sec=60.0,
        task_results=task_results,
        usage=usage,
        parallelism=1,
    )


def _make_run_round_mock(status_map=None):
    """Return a mock for run_round that returns configurable results.

    status_map: dict of round_name -> status. Default: all "done".
    """

    def _mock(round_def, config=None):
        status = "done"
        if status_map and round_def.name in status_map:
            status = status_map[round_def.name]
        return _mock_round_result(round_def.name, status=status, n_tasks=len(round_def.tasks))

    return _mock


# ──────────────────────────────────────────────────────────────────
#  Phase list acceptance — Rondo-REQ-101 req 10
# ──────────────────────────────────────────────────────────────────


class TestPhaseList:
    def test_accepts_phase_list(self):
        """Rondo-REQ-101 req 10: accepts list of round definitions."""
        phases = [_make_round("phase-1"), _make_round("phase-2")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            assert isinstance(result, OvernightResult)
            assert len(result.phase_results) == 2

    def test_single_phase(self):
        """Single phase round."""
        phases = [_make_round("only")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            assert len(result.phase_results) == 1

    def test_empty_phases(self):
        """Empty phase list → completed immediately."""
        config = RondoConfig(workers=1)
        result = run_overnight(phases=[], config=config)
        assert isinstance(result, OvernightResult)
        assert result.status == "done"
        assert len(result.phase_results) == 0


# ──────────────────────────────────────────────────────────────────
#  Phase sequencing — Rondo-REQ-101 req 11
# ──────────────────────────────────────────────────────────────────


class TestPhaseSequencing:
    def test_phases_execute_in_order(self):
        """Rondo-REQ-101 req 11: phases execute sequentially."""
        execution_order = []

        def _ordered_mock(round_def, config=None):
            execution_order.append(round_def.name)
            return _mock_round_result(round_def.name)

        phases = [_make_round("first"), _make_round("second"), _make_round("third")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_ordered_mock):
            run_overnight(phases=phases, config=config)
            assert execution_order == ["first", "second", "third"]


# ──────────────────────────────────────────────────────────────────
#  Phase failure isolation — Rondo-REQ-101 req 12
# ──────────────────────────────────────────────────────────────────


class TestPhaseIsolation:
    def test_phase_failure_doesnt_block_next(self):
        """Rondo-REQ-101 req 12: phase failure continues to next phase."""
        phases = [_make_round("fail-phase"), _make_round("ok-phase")]
        config = RondoConfig(workers=1)
        status_map = {"fail-phase": "error", "ok-phase": "done"}
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock(status_map)):
            result = run_overnight(phases=phases, config=config)
            assert len(result.phase_results) == 2
            assert result.phase_results[0].status == "error"
            assert result.phase_results[1].status == "done"

    def test_phase_exception_caught(self):
        """Phase that throws exception → error result, next phase still runs."""
        call_count = [0]

        def _exploding_mock(round_def, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Phase explosion")
            return _mock_round_result(round_def.name)

        phases = [_make_round("explode"), _make_round("survive")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_exploding_mock):
            result = run_overnight(phases=phases, config=config)
            assert len(result.phase_results) == 2
            assert result.phase_results[0].status == "error"
            assert result.phase_results[1].status == "done"

    def test_all_phases_fail_status_error(self):
        """All phases fail → overnight status error."""
        phases = [_make_round("f1"), _make_round("f2")]
        config = RondoConfig(workers=1)
        status_map = {"f1": "error", "f2": "error"}
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock(status_map)):
            result = run_overnight(phases=phases, config=config)
            assert result.status == "error"

    def test_mixed_phases_partial_status(self):
        """Mix of done + error phases → overnight status partial."""
        phases = [_make_round("ok"), _make_round("fail")]
        config = RondoConfig(workers=1)
        status_map = {"ok": "done", "fail": "error"}
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock(status_map)):
            result = run_overnight(phases=phases, config=config)
            assert result.status == "partial"


# ──────────────────────────────────────────────────────────────────
#  Mode configuration — Rondo-REQ-101 reqs 13-15
# ──────────────────────────────────────────────────────────────────


class TestModeConfig:
    def test_mode_selects_phases(self):
        """Rondo-REQ-101 req 13: mode selects which phases run."""
        all_phases = [_make_round("lint"), _make_round("test"), _make_round("build")]
        modes = {
            "minimal": ["lint"],
            "standard": ["lint", "test"],
            "full": ["lint", "test", "build"],
        }
        config = RondoConfig(workers=1)

        execution_order = []

        def _tracking_mock(round_def, config=None):
            execution_order.append(round_def.name)
            return _mock_round_result(round_def.name)

        with patch("rondo.overnight.run_round", side_effect=_tracking_mock):
            result = run_overnight(
                phases=all_phases,
                config=config,
                mode="minimal",
                modes=modes,
            )
            assert execution_order == ["lint"]
            assert len(result.phase_results) == 1

    def test_standard_mode(self):
        """Standard mode runs 3-4 phases."""
        all_phases = [_make_round("a"), _make_round("b"), _make_round("c"), _make_round("d")]
        modes = {
            "minimal": ["a"],
            "standard": ["a", "b", "c"],
            "full": ["a", "b", "c", "d"],
        }
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=all_phases, config=config, mode="standard", modes=modes)
            assert len(result.phase_results) == 3

    def test_no_mode_runs_all_phases(self):
        """Rondo-REQ-101 req 15: no mode specified → run all phases."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            assert len(result.phase_results) == 2

    def test_unknown_mode_raises(self):
        """Unknown mode name → ValueError."""
        phases = [_make_round("a")]
        modes = {"minimal": ["a"]}
        config = RondoConfig(workers=1)
        with pytest.raises(ValueError, match="Unknown mode"):
            run_overnight(phases=phases, config=config, mode="bogus", modes=modes)


# ──────────────────────────────────────────────────────────────────
#  Event logging — Rondo-REQ-101 reqs 17-18
# ──────────────────────────────────────────────────────────────────


class TestEventLogging:
    def test_start_event_logged(self):
        """Rondo-REQ-101 req 17: start event logged."""
        phases = [_make_round("a")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            start_events = [e for e in result.event_log if e["type"] == "start_overnight"]
            assert len(start_events) == 1
            assert "timestamp" in start_events[0]

    def test_end_event_logged(self):
        """Rondo-REQ-101 req 17: end event logged."""
        phases = [_make_round("a")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            end_events = [e for e in result.event_log if e["type"] == "end_overnight"]
            assert len(end_events) == 1

    def test_phase_events_logged(self):
        """Each phase start/end logged."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            phase_starts = [e for e in result.event_log if e["type"] == "phase_start"]
            phase_ends = [e for e in result.event_log if e["type"] == "phase_end"]
            assert len(phase_starts) == 2
            assert len(phase_ends) == 2

    def test_rolling_log_max_100(self, tmp_path):
        """Rondo-REQ-101 req 18: event log keeps max 100 entries."""
        log = EventLog(log_path=str(tmp_path / "events.json"))
        # -- Add 110 entries
        for i in range(110):
            log.append({"type": "test", "index": i})
        log.save()

        # -- Reload and check
        log2 = EventLog(log_path=str(tmp_path / "events.json"))
        assert len(log2.entries) == 100
        # -- Oldest entries should be trimmed (kept last 100)
        assert log2.entries[0]["index"] == 10

    def test_event_log_persistence(self, tmp_path):
        """Event log saved to disk as JSON."""
        log = EventLog(log_path=str(tmp_path / "events.json"))
        log.append({"type": "test", "data": "hello"})
        log.save()

        # -- Read back
        data = json.loads((tmp_path / "events.json").read_text())
        assert len(data) == 1
        assert data[0]["type"] == "test"


# ──────────────────────────────────────────────────────────────────
#  Usage gating — Rondo-REQ-101 reqs 24-28
# ──────────────────────────────────────────────────────────────────


class TestUsageGating:
    def test_no_overage_continues(self):
        """Rondo-REQ-101 req 25: no overage → continue."""
        usage = DispatchUsage(
            task_name="t1",
            model="sonnet",
            rate_limit_status="active",
            is_using_overage=False,
        )
        action = check_usage_gate(usage, on_overage="continue")
        assert action == "continue"

    def test_overage_continue_action(self):
        """Rondo-REQ-101 req 25: overage + on_overage=continue → continue."""
        usage = DispatchUsage(
            task_name="t1",
            model="sonnet",
            rate_limit_status="active",
            is_using_overage=True,
        )
        action = check_usage_gate(usage, on_overage="continue")
        assert action == "continue"

    def test_overage_stop_action(self):
        """Rondo-REQ-101 req 25: overage + on_overage=stop → stop."""
        usage = DispatchUsage(
            task_name="t1",
            model="sonnet",
            rate_limit_status="active",
            is_using_overage=True,
        )
        action = check_usage_gate(usage, on_overage="stop")
        assert action == "stop"

    def test_overage_pause_action(self):
        """Rondo-REQ-101 req 25: overage + on_overage=pause → pause."""
        usage = DispatchUsage(
            task_name="t1",
            model="sonnet",
            rate_limit_status="active",
            is_using_overage=True,
        )
        action = check_usage_gate(usage, on_overage="pause")
        assert action == "pause"

    def test_blocked_status_returns_blocked(self):
        """Rondo-REQ-101 req 26: rate_limit_status=blocked → blocked action."""
        usage = DispatchUsage(
            task_name="t1",
            model="sonnet",
            rate_limit_status="blocked",
            is_using_overage=False,
            rate_limit_resets_at=9999999999,
        )
        action = check_usage_gate(usage, on_overage="continue")
        assert action == "blocked"

    def test_stop_action_ends_overnight(self):
        """Rondo-REQ-101 req 25: stop action ends overnight run early."""
        phases = [_make_round("phase-1"), _make_round("phase-2"), _make_round("phase-3")]
        config = RondoConfig(workers=1, on_overage="stop")

        call_count = [0]

        def _overage_mock(round_def, config=None):
            call_count[0] += 1
            result = _mock_round_result(round_def.name)
            # -- Simulate overage on first phase
            if call_count[0] == 1:
                result.usage = [
                    DispatchUsage(
                        task_name=f"{round_def.name}-t1",
                        model="sonnet",
                        cost_usd=0.01,
                        rate_limit_status="active",
                        is_using_overage=True,
                    )
                ]
            return result

        with patch("rondo.overnight.run_round", side_effect=_overage_mock):
            result = run_overnight(phases=phases, config=config)
            # -- Should stop after first phase (overage detected)
            assert len(result.phase_results) == 1
            assert result.status == "stopped"

    def test_usage_gate_logged(self):
        """Rondo-REQ-101 req 28: usage gate decisions logged."""
        phases = [_make_round("phase-1"), _make_round("phase-2")]
        config = RondoConfig(workers=1, on_overage="stop")

        def _overage_mock(round_def, config=None):
            result = _mock_round_result(round_def.name)
            result.usage = [
                DispatchUsage(
                    task_name=f"{round_def.name}-t1",
                    model="sonnet",
                    rate_limit_status="active",
                    is_using_overage=True,
                )
            ]
            return result

        with patch("rondo.overnight.run_round", side_effect=_overage_mock):
            result = run_overnight(phases=phases, config=config)
            gate_events = [e for e in result.event_log if e["type"] == "usage_gate"]
            assert len(gate_events) >= 1
            assert gate_events[0]["action"] == "stop"


# ──────────────────────────────────────────────────────────────────
#  Rate limit backoff — Rondo-REQ-101 req 22
# ──────────────────────────────────────────────────────────────────


class TestRateLimitBackoff:
    def test_rate_limit_error_triggers_backoff(self):
        """Rondo-REQ-101 req 22: ERR_RATE_LIMIT triggers backoff pause."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1, rate_limit_backoff_sec=0.1)

        call_count = [0]

        def _rate_limit_mock(round_def, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                result = _mock_round_result(round_def.name, status="error")
                result.task_results[0].error_code = "ERR_RATE_LIMIT"
                return result
            return _mock_round_result(round_def.name)

        with patch("rondo.overnight.run_round", side_effect=_rate_limit_mock):
            start = time.monotonic()
            run_overnight(phases=phases, config=config)
            elapsed = time.monotonic() - start
            # -- Should have paused at least backoff_sec between phases
            assert elapsed >= 0.08  # -- 0.1s with tolerance


# ──────────────────────────────────────────────────────────────────
#  Watchdog response — Rondo-REQ-101 reqs 19-23
# ──────────────────────────────────────────────────────────────────


class TestWatchdogResponse:
    def test_watchdog_error_continues_to_next_phase(self):
        """Rondo-REQ-101 req 21: after watchdog kill, continue to next phase."""
        phases = [_make_round("hung"), _make_round("ok")]
        config = RondoConfig(workers=1)

        call_count = [0]

        def _watchdog_mock(round_def, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                result = _mock_round_result(round_def.name, status="error")
                result.task_results[0].error_code = "ERR_WATCHDOG_TIMEOUT"
                return result
            return _mock_round_result(round_def.name)

        with patch("rondo.overnight.run_round", side_effect=_watchdog_mock):
            result = run_overnight(phases=phases, config=config)
            assert len(result.phase_results) == 2
            assert result.phase_results[1].status == "done"

    def test_watchdog_event_logged(self):
        """Rondo-REQ-101 req 23: watchdog interventions logged."""
        phases = [_make_round("hung")]
        config = RondoConfig(workers=1)

        def _watchdog_mock(round_def, config=None):
            result = _mock_round_result(round_def.name, status="error")
            result.task_results[0].error_code = "ERR_WATCHDOG_TIMEOUT"
            return result

        with patch("rondo.overnight.run_round", side_effect=_watchdog_mock):
            result = run_overnight(phases=phases, config=config)
            watchdog_events = [e for e in result.event_log if e["type"] == "watchdog_kill"]
            assert len(watchdog_events) >= 1


# ──────────────────────────────────────────────────────────────────
#  OvernightResult structure
# ──────────────────────────────────────────────────────────────────


class TestOvernightResult:
    def test_has_timing_fields(self):
        """OvernightResult has ISO 8601 timestamps and non-negative duration."""
        phases = [_make_round("a")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            assert result.started_at.startswith("20"), f"Not ISO 8601: {result.started_at!r}"
            assert "T" in result.started_at
            assert result.completed_at.startswith("20"), f"Not ISO 8601: {result.completed_at!r}"
            assert "T" in result.completed_at
            assert result.duration_sec >= 0

    def test_has_total_cost(self):
        """OvernightResult aggregates total cost."""
        phases = [_make_round("a", n_tasks=2), _make_round("b", n_tasks=1)]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            # -- 3 tasks × $0.01 each
            assert result.total_cost_usd == pytest.approx(0.03)

    def test_has_mode(self):
        """OvernightResult records which mode was used."""
        phases = [_make_round("a")]
        modes = {"quick": ["a"]}
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config, mode="quick", modes=modes)
            assert result.mode == "quick"

    def test_all_done_status(self):
        """All phases done → overnight status done."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1)
        with patch("rondo.overnight.run_round", side_effect=_make_run_round_mock()):
            result = run_overnight(phases=phases, config=config)
            assert result.status == "done"

    def test_all_skipped_status(self):
        """All phases skipped → overnight status skipped (not done)."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1)
        with patch(
            "rondo.overnight.run_round",
            side_effect=lambda rd, config=None: _mock_round_result(rd.name, status="skipped"),
        ):
            result = run_overnight(phases=phases, config=config)
            assert result.status == "skipped"

    def test_mixed_done_skipped_is_partial(self):
        """One done + one skipped → partial (not done)."""
        phases = [_make_round("a"), _make_round("b")]
        config = RondoConfig(workers=1)
        call_count = [0]

        def _mixed_mock(round_def, config=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_round_result(round_def.name, status="done")
            return _mock_round_result(round_def.name, status="skipped")

        with patch("rondo.overnight.run_round", side_effect=_mixed_mock):
            result = run_overnight(phases=phases, config=config)
            assert result.status == "partial"


class TestOvernightSpoolIntegration:
    """REQ-101: overnight results written to spool (ALWAYS-ON)."""

    def test_overnight_writes_spool(self):
        """Overnight result triggers spool write."""
        phases = [
            Round(
                name="phase1",
                tasks=[
                    Task(name="auto", auto_fn=lambda: (True, "done")),
                ],
            ),
        ]
        config = RondoConfig(dry_run=True)

        with patch("rondo.spool.spool_result") as mock_spool:
            run_overnight(phases=phases, config=config)
            mock_spool.assert_called_once()
            call_kwargs = mock_spool.call_args[1]
            assert "overnight" in call_kwargs["task_name"]


class TestOvernightEventLog:
    """REQ-101 req 017: events logged with timestamps."""

    def test_event_log_has_start_and_end(self):
        """Event log contains start and end entries."""
        phases = [
            Round(
                name="phase1",
                tasks=[
                    Task(name="auto", auto_fn=lambda: (True, "ok")),
                ],
            ),
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        types = [e.get("type") for e in result.event_log]
        assert "start_overnight" in types
        assert "end_overnight" in types

    def test_event_log_has_timestamps(self):
        """Every event has a timestamp."""
        phases = [
            Round(
                name="phase1",
                tasks=[
                    Task(name="auto", auto_fn=lambda: (True, "ok")),
                ],
            ),
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        for event in result.event_log:
            assert "timestamp" in event


class TestEventLogDeep:
    """REQ-101 req 018: rolling event log keeps last 100 entries."""

    def test_max_entries_enforced(self):
        """Log trims to 100 entries."""
        log = EventLog()
        for i in range(150):
            log.append({"type": f"event_{i}"})
        assert len(log.entries) == 100
        assert log.entries[0]["type"] == "event_50"

    def test_persist_and_reload(self, tmp_path):
        """Log saves to disk and reloads."""
        log_path = str(tmp_path / "events.json")
        log1 = EventLog(log_path=log_path)
        log1.append({"type": "test", "value": 42})
        log1.save()

        log2 = EventLog(log_path=log_path)
        assert len(log2.entries) == 1
        assert log2.entries[0]["value"] == 42

    def test_corrupt_file_recovers(self, tmp_path):
        """Corrupt JSON file doesn't crash — starts empty."""
        log_path = tmp_path / "events.json"
        log_path.write_text("not json {{{{", encoding="utf-8")
        log = EventLog(log_path=str(log_path))
        assert log.entries == []

    def test_no_path_no_save(self):
        """Log with no path doesn't crash on save."""
        log = EventLog()
        log.append({"type": "test"})
        log.save()  # -- should not raise


class TestUsageGatingDeep:
    """REQ-101 reqs 024-028: usage gating for overnight safety."""

    def test_normal_status_continues(self):
        """Normal rate limit → continue."""
        usage = DispatchUsage(rate_limit_status="ok")
        assert check_usage_gate(usage) == "continue"

    def test_blocked_always_blocks(self):
        """Blocked status → always blocks regardless of config."""
        usage = DispatchUsage(rate_limit_status="blocked")
        assert check_usage_gate(usage, on_overage="continue") == "blocked"

    def test_overage_respects_config_continue(self):
        """Overage + on_overage=continue → continue."""
        usage = DispatchUsage(is_using_overage=True)
        assert check_usage_gate(usage, on_overage="continue") == "continue"

    def test_overage_respects_config_stop(self):
        """Overage + on_overage=stop → stop."""
        usage = DispatchUsage(is_using_overage=True)
        assert check_usage_gate(usage, on_overage="stop") == "stop"

    def test_overage_respects_config_pause(self):
        """Overage + on_overage=pause → pause."""
        usage = DispatchUsage(is_using_overage=True)
        assert check_usage_gate(usage, on_overage="pause") == "pause"

    def test_no_overage_no_block_continues(self):
        """No overage + not blocked → continue."""
        usage = DispatchUsage(is_using_overage=False, rate_limit_status="ok")
        assert check_usage_gate(usage) == "continue"


class TestOvernightPhaseOrdering:
    """REQ-101 req 011: phases execute sequentially."""

    def test_phases_run_in_order(self):
        """Phase results are in submission order."""
        phases = [
            Round(
                name=f"phase-{i}",
                tasks=[
                    Task(name=f"t{i}", auto_fn=lambda: (True, "ok")),
                ],
            )
            for i in range(3)
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        names = [pr.round_name for pr in result.phase_results]
        assert names == ["phase-0", "phase-1", "phase-2"]

    def test_req012_phase_failure_continues(self):
        """REQ-101 req 012: phase failure doesn't block next phase."""
        call_count = 0

        def failing_fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("phase 1 crashed")
            return (True, "ok")

        phases = [
            Round(
                name="fail-phase",
                tasks=[
                    Task(name="fail", auto_fn=failing_fn),
                ],
            ),
            Round(
                name="ok-phase",
                tasks=[
                    Task(name="ok", auto_fn=lambda: (True, "ok")),
                ],
            ),
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        assert len(result.phase_results) == 2


class TestOvernightResults:
    """REQ-101: overnight result has required fields."""

    def test_result_has_timing(self):
        """OvernightResult has started_at, completed_at, duration_sec."""
        phases = [
            Round(
                name="t",
                tasks=[
                    Task(name="t", auto_fn=lambda: (True, "ok")),
                ],
            )
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        assert result.started_at.startswith("20"), f"Not ISO 8601: {result.started_at!r}"
        assert "T" in result.started_at
        assert result.completed_at.startswith("20"), f"Not ISO 8601: {result.completed_at!r}"
        assert "T" in result.completed_at
        assert result.duration_sec >= 0

    def test_result_has_cost(self):
        """OvernightResult has total_cost_usd."""
        phases = [
            Round(
                name="t",
                tasks=[
                    Task(name="t", auto_fn=lambda: (True, "ok")),
                ],
            )
        ]
        config = RondoConfig(dry_run=True)
        result = run_overnight(phases=phases, config=config)
        assert result.total_cost_usd >= 0


# -- sig: mgh-6201.cd.bd955f.1c5d.a91c4a
