# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.report — REQ-002 reqs 29-36.

VER-001 verification matrix: morning report generation.
TDD: tests written BEFORE report.py exists.
"""

import sys
from pathlib import Path

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.config import RondoConfig
from rondo.engine import (
    DispatchUsage,
    RoundResult,
    TaskResult,
)
from rondo.overnight import OvernightResult
from rondo.report import generate_report

# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────


def _make_overnight_result(
    phase_configs=None,
    event_log=None,
    mode="full",
):
    """Build an OvernightResult for testing.

    phase_configs: list of dicts with keys: name, n_done, n_error, cost, duration.
    """
    if phase_configs is None:
        phase_configs = [{"name": "test", "n_done": 1, "n_error": 0, "cost": 0.01, "duration": 60.0}]

    phase_results = []
    total_cost = 0.0

    for pc in phase_configs:
        done_results = [
            TaskResult(task_name=f"{pc['name']}-t{i + 1}", status="done") for i in range(pc.get("n_done", 0))
        ]
        error_results = [
            TaskResult(
                task_name=f"{pc['name']}-err{i + 1}",
                status="error",
                error_code="ERR_SUBPROCESS",
                error_message="Failed",
            )
            for i in range(pc.get("n_error", 0))
        ]
        blocked_results = [
            TaskResult(
                task_name=f"{pc['name']}-blk{i + 1}",
                status="blocked",
                error_message="Needs input",
            )
            for i in range(pc.get("n_blocked", 0))
        ]
        all_tasks = done_results + error_results + blocked_results
        total_tasks = len(all_tasks)

        # -- Determine status
        if pc.get("n_error", 0) == 0 and pc.get("n_blocked", 0) == 0:
            status = "done"
        elif pc.get("n_done", 0) > 0:
            status = "partial"
        else:
            status = "error"

        usage = [
            DispatchUsage(
                task_name=tr.task_name,
                model="sonnet",
                cost_usd=pc.get("cost", 0.01) / max(total_tasks, 1),
                input_tokens=100,
                output_tokens=50,
            )
            for tr in all_tasks
        ]
        total_cost += pc.get("cost", 0.01)

        phase_results.append(
            RoundResult(
                round_name=pc["name"],
                status=status,
                summary=f"{pc.get('n_done', 0)}/{total_tasks} tasks done",
                started_at="2026-03-14T00:00:00Z",
                completed_at="2026-03-14T00:01:00Z",
                duration_sec=pc.get("duration", 60.0),
                task_results=all_tasks,
                usage=usage,
                parallelism=1,
            )
        )

    return OvernightResult(
        mode=mode,
        started_at="2026-03-14T00:00:00Z",
        completed_at="2026-03-14T01:00:00Z",
        duration_sec=sum(pc.get("duration", 60.0) for pc in phase_configs),
        phase_results=phase_results,
        event_log=event_log or [],
        total_cost_usd=total_cost,
        status="done" if all(pr.status == "done" for pr in phase_results) else "partial",
    )


# ──────────────────────────────────────────────────────────────────
#  Aggregation — REQ-002 req 29
# ──────────────────────────────────────────────────────────────────


class TestAggregation:
    def test_report_aggregates_all_phases(self):
        """REQ-002 req 29: aggregate results from all phases."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "lint", "n_done": 3, "n_error": 0, "cost": 0.01, "duration": 30.0},
                {"name": "test", "n_done": 5, "n_error": 1, "cost": 0.05, "duration": 120.0},
            ]
        )
        report = generate_report(result)
        assert "lint" in report
        assert "test" in report

    def test_report_returns_string(self):
        """Report is a markdown string."""
        result = _make_overnight_result()
        report = generate_report(result)
        assert isinstance(report, str)
        assert len(report) > 0


# ──────────────────────────────────────────────────────────────────
#  Grouping by round — REQ-002 req 30
# ──────────────────────────────────────────────────────────────────


class TestGrouping:
    def test_each_phase_has_section(self):
        """REQ-002 req 30: results grouped by round type."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "phase-alpha", "n_done": 1, "n_error": 0, "cost": 0.01},
                {"name": "phase-beta", "n_done": 2, "n_error": 0, "cost": 0.02},
            ]
        )
        report = generate_report(result)
        # -- Each phase should have a section header
        assert "phase-alpha" in report
        assert "phase-beta" in report


# ──────────────────────────────────────────────────────────────────
#  Round stats — REQ-002 req 31
# ──────────────────────────────────────────────────────────────────


class TestRoundStats:
    def test_tasks_done_count(self):
        """REQ-002 req 31: show tasks done."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "work", "n_done": 3, "n_error": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "3" in report  # -- 3 done

    def test_tasks_failed_count(self):
        """REQ-002 req 31: show tasks failed."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "work", "n_done": 2, "n_error": 2, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "2" in report  # -- 2 failed

    def test_duration_shown(self):
        """REQ-002 req 31: show total duration."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "work", "n_done": 1, "n_error": 0, "cost": 0.01, "duration": 90.5},
            ]
        )
        report = generate_report(result)
        # -- Duration should appear somewhere (formatted)
        assert "90" in report or "1m" in report or "1:30" in report


# ──────────────────────────────────────────────────────────────────
#  Health indicators — REQ-002 req 32
# ──────────────────────────────────────────────────────────────────


class TestHealthIndicators:
    def test_all_pass_health(self):
        """REQ-002 req 32: all succeeded → PASS."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "clean", "n_done": 5, "n_error": 0, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "PASS" in report

    def test_partial_health(self):
        """REQ-002 req 32: some failed → PARTIAL."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "mixed", "n_done": 3, "n_error": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "PARTIAL" in report

    def test_fail_health(self):
        """REQ-002 req 32: majority failed → FAIL."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "bad", "n_done": 0, "n_error": 5, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "FAIL" in report


# ──────────────────────────────────────────────────────────────────
#  Action items — REQ-002 req 33
# ──────────────────────────────────────────────────────────────────


class TestActionItems:
    def test_failed_tasks_listed(self):
        """REQ-002 req 33: failed tasks appear in action items."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "run", "n_done": 1, "n_error": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "err1" in report  # -- error task name

    def test_blocked_tasks_listed(self):
        """REQ-002 req 33: blocked tasks appear in action items."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "run", "n_done": 1, "n_error": 0, "n_blocked": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "blk1" in report  # -- blocked task name

    def test_no_action_items_when_clean(self):
        """No action items when all tasks succeeded."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "clean", "n_done": 3, "n_error": 0, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "No action items" in report or "action items" not in report.lower() or "0 action" in report.lower()


# ──────────────────────────────────────────────────────────────────
#  Dated filename — REQ-002 req 34
# ──────────────────────────────────────────────────────────────────


class TestDatedFilename:
    def test_save_to_dated_file(self, tmp_path):
        """REQ-002 req 34: report saved with dated filename."""
        result = _make_overnight_result()
        config = RondoConfig(report_dir=str(tmp_path))
        from rondo.report import save_report

        filepath = save_report(result, config)
        assert "rondo-morning-" in filepath
        assert filepath.endswith(".md")
        assert Path(filepath).exists()

    def test_file_contains_report(self, tmp_path):
        """Saved file contains the full report."""
        result = _make_overnight_result()
        config = RondoConfig(report_dir=str(tmp_path))
        from rondo.report import save_report

        filepath = save_report(result, config)
        content = Path(filepath).read_text()
        assert "test" in content  # -- phase name


# ──────────────────────────────────────────────────────────────────
#  Report totals — REQ-002 req 35
# ──────────────────────────────────────────────────────────────────


class TestReportTotals:
    def test_total_duration(self):
        """REQ-002 req 35: total duration in report."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "a", "n_done": 1, "n_error": 0, "cost": 0.01, "duration": 60.0},
                {"name": "b", "n_done": 1, "n_error": 0, "cost": 0.01, "duration": 120.0},
            ]
        )
        report = generate_report(result)
        # -- Total: 180s = 3m
        assert "180" in report or "3m" in report or "3:00" in report

    def test_total_tasks(self):
        """REQ-002 req 35: total tasks run."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "a", "n_done": 3, "n_error": 0, "cost": 0.01},
                {"name": "b", "n_done": 2, "n_error": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        assert "6" in report  # -- 3 + 2 + 1 = 6 total tasks

    def test_total_errors(self):
        """REQ-002 req 35: total errors."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "a", "n_done": 1, "n_error": 2, "cost": 0.01},
                {"name": "b", "n_done": 1, "n_error": 1, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        # -- 2 + 1 = 3 errors
        assert "3" in report


# ──────────────────────────────────────────────────────────────────
#  Usage summary — REQ-002 req 36
# ──────────────────────────────────────────────────────────────────


class TestUsageSummary:
    def test_total_cost_in_report(self):
        """REQ-002 req 36: total cost in report."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "a", "n_done": 1, "n_error": 0, "cost": 0.05},
                {"name": "b", "n_done": 1, "n_error": 0, "cost": 0.10},
            ]
        )
        report = generate_report(result)
        assert "$0.15" in report or "0.15" in report

    def test_total_tokens_in_report(self):
        """REQ-002 req 36: total tokens in report."""
        result = _make_overnight_result(
            phase_configs=[
                {"name": "a", "n_done": 2, "n_error": 0, "cost": 0.01},
            ]
        )
        report = generate_report(result)
        # -- 2 tasks × (100 input + 50 output) = 300 total tokens
        assert "300" in report or "token" in report.lower()

    def test_watchdog_count_in_report(self):
        """REQ-002 req 36: watchdog intervention count."""
        result = _make_overnight_result(
            phase_configs=[{"name": "a", "n_done": 1, "n_error": 0, "cost": 0.01}],
            event_log=[
                {"type": "watchdog_kill", "task": "t1", "reason": "timeout"},
                {"type": "watchdog_kill", "task": "t2", "reason": "timeout"},
                {"type": "start_overnight", "mode": "full"},
            ],
        )
        report = generate_report(result)
        assert "2" in report  # -- 2 watchdog interventions

# -- sig: MgH-8829a2.eed4f3
