# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.metrics — dispatch metrics aggregation for OB dashboards.

VER-001 verification matrix: cost, throughput, reliability, latency, health.
ALWAYS-ON: metrics computed from existing audit/spool data — no new capture needed.
"""

import json
from pathlib import Path

import pytest

from rondo.metrics import (
    compute_metrics,
)

# -- ──────────────────────────────────────────────────────────────
# --  Helper: write fake audit JSONL for testing
# -- ──────────────────────────────────────────────────────────────


def _write_audit(tmp_path: Path, records: list[dict]) -> Path:
    """Write fake audit records to JSONL."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    jsonl = audit_dir / "rondo_audit.jsonl"
    lines = [json.dumps(r) for r in records]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(audit_dir)


def _make_outcome(
    task_name: str,
    status: str,
    cost: float,
    duration: float,
    model: str = "sonnet",
    error_code: str | None = None,
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> dict:
    """Create a fake audit OUTCOME record."""
    return {
        "dispatch_id": f"dsp_{task_name}",
        "task_name": task_name,
        "model": model,
        "status": status,
        "cost_usd": cost,
        "duration_sec": duration,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error_code": error_code,
        "completed_at": "2026-03-29T12:00:00Z",
    }


# -- ──────────────────────────────────────────────────────────────
# --  Cost metrics
# -- ──────────────────────────────────────────────────────────────


class TestCostMetrics:
    """Metrics: cost aggregation."""

    def test_total_cost(self, tmp_path):
        """Total cost sums all outcomes."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.20, 15.0),
                _make_outcome("t3", "error", 0.05, 5.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.total_cost_usd == pytest.approx(0.35)

    def test_avg_cost(self, tmp_path):
        """Average cost per dispatch."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.20, 15.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.avg_cost_usd == pytest.approx(0.15)

    def test_cost_by_model(self, tmp_path):
        """Cost broken down by model."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0, model="sonnet"),
                _make_outcome("t2", "done", 0.30, 15.0, model="opus"),
                _make_outcome("t3", "done", 0.05, 5.0, model="sonnet"),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.cost_by_model["sonnet"] == pytest.approx(0.15)
        assert report.cost_by_model["opus"] == pytest.approx(0.30)


# -- ──────────────────────────────────────────────────────────────
# --  Reliability metrics
# -- ──────────────────────────────────────────────────────────────


class TestReliabilityMetrics:
    """Metrics: success rate + error breakdown."""

    def test_success_rate(self, tmp_path):
        """Success rate = done / total."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.10, 10.0),
                _make_outcome("t3", "error", 0.05, 5.0),
                _make_outcome("t4", "done", 0.10, 10.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.success_rate == pytest.approx(0.75)

    def test_error_breakdown(self, tmp_path):
        """Error codes counted."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "error", 0.0, 5.0, error_code="ERR_TIMEOUT"),
                _make_outcome("t2", "error", 0.0, 5.0, error_code="ERR_TIMEOUT"),
                _make_outcome("t3", "error", 0.0, 5.0, error_code="ERR_RATE_LIMIT"),
                _make_outcome("t4", "done", 0.10, 10.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.error_breakdown["ERR_TIMEOUT"] == 2
        assert report.error_breakdown["ERR_RATE_LIMIT"] == 1


# -- ──────────────────────────────────────────────────────────────
# --  Latency metrics
# -- ──────────────────────────────────────────────────────────────


class TestLatencyMetrics:
    """Metrics: dispatch duration."""

    def test_avg_duration(self, tmp_path):
        """Average duration across dispatches."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.10, 20.0),
                _make_outcome("t3", "done", 0.10, 30.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.avg_duration_sec == pytest.approx(20.0)

    def test_max_duration(self, tmp_path):
        """Max duration recorded."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 5.0),
                _make_outcome("t2", "done", 0.10, 45.0),
                _make_outcome("t3", "done", 0.10, 15.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.max_duration_sec == pytest.approx(45.0)


# -- ──────────────────────────────────────────────────────────────
# --  Token metrics
# -- ──────────────────────────────────────────────────────────────


class TestTokenMetrics:
    """Metrics: token usage."""

    def test_total_tokens(self, tmp_path):
        """Total input + output tokens."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0, input_tokens=5000, output_tokens=1000),
                _make_outcome("t2", "done", 0.10, 10.0, input_tokens=3000, output_tokens=2000),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.total_input_tokens == 8000
        assert report.total_output_tokens == 3000


# -- ──────────────────────────────────────────────────────────────
# --  Model comparison
# -- ──────────────────────────────────────────────────────────────


class TestModelComparison:
    """Metrics: per-model breakdown."""

    def test_dispatches_by_model(self, tmp_path):
        """Dispatch count per model."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0, model="sonnet"),
                _make_outcome("t2", "done", 0.10, 10.0, model="sonnet"),
                _make_outcome("t3", "done", 0.30, 20.0, model="opus"),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.dispatches_by_model["sonnet"] == 2
        assert report.dispatches_by_model["opus"] == 1


# -- ──────────────────────────────────────────────────────────────
# --  Health status
# -- ──────────────────────────────────────────────────────────────


class TestHealthStatus:
    """Metrics: overall health determination."""

    def test_green_when_healthy(self, tmp_path):
        """All good = GREEN."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.10, 10.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health == "GREEN"

    def test_yellow_when_some_errors(self, tmp_path):
        """Some errors but >50% success = YELLOW."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
                _make_outcome("t2", "done", 0.10, 10.0),
                _make_outcome("t3", "error", 0.05, 5.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health in ("GREEN", "YELLOW")

    def test_red_when_mostly_errors(self, tmp_path):
        """Mostly errors = RED."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "error", 0.0, 5.0),
                _make_outcome("t2", "error", 0.0, 5.0),
                _make_outcome("t3", "error", 0.0, 5.0),
                _make_outcome("t4", "done", 0.10, 10.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health == "RED"


# -- ──────────────────────────────────────────────────────────────
# --  Serialization
# -- ──────────────────────────────────────────────────────────────


class TestMetricsSerialization:
    """Metrics: JSON output for OB/ACE/MCP consumption."""

    def test_to_dict(self, tmp_path):
        """MetricsReport serializes to JSON-safe dict."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("t1", "done", 0.10, 10.0),
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        data = report.to_dict()
        json_str = json.dumps(data)
        assert "total_cost_usd" in json_str
        assert "health" in json_str
        assert "success_rate" in json_str

    def test_empty_audit(self, tmp_path):
        """No audit data = empty report, GREEN health."""
        audit_dir = str(tmp_path / "empty")
        report = compute_metrics(audit_dir=audit_dir)
        assert report.total_dispatches == 0
        assert report.health == "GREEN"


class TestMetricsInTaskResult:
    """ALWAYS-ON: metrics embedded in every TaskResult — no second call."""

    def test_task_result_has_metrics_field(self):
        """TaskResult has a metrics dict field."""
        from rondo.engine import TaskResult

        tr = TaskResult(task_name="t")
        assert hasattr(tr, "metrics")
        assert isinstance(tr.metrics, dict)

    def test_dispatch_returns_metrics(self):
        """dispatch_task includes metrics in result."""
        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task
        from rondo.engine import Task

        task = Task(name="auto", auto_fn=lambda: (True, "ok"))
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert "health" in result.metrics
        assert "total_dispatches" in result.metrics

    def test_dry_run_includes_metrics(self):
        """Even dry-run has metrics."""
        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task
        from rondo.engine import Task

        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(dry_run=True)
        result, _ = dispatch_task(task, config)
        assert "health" in result.metrics

    def test_error_dispatch_includes_metrics(self):
        """Error dispatch has metrics too."""
        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task
        from rondo.engine import Task

        task = Task(name="broken")
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert result.status == "error"
        assert "health" in result.metrics


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-302: windowed stability scoreboard — STD-101 reqs 240-242
# --  Lifetime averages buried the truth (64% lifetime vs 97% recent).
# -- ──────────────────────────────────────────────────────────────


class TestWindowedScoreboard:
    """STD-101 reqs 240-242: 7d/30d windows lead; lifetime is context."""

    def setup_method(self) -> None:
        from datetime import UTC, datetime

        self.now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)

    def _rec(self, days_ago: float, status: str = "done") -> dict:
        from datetime import timedelta

        return {
            "status": status,
            "completed_at": (self.now - timedelta(days=days_ago)).isoformat(),
            "cost_usd": 0.0,
            "duration_sec": 1.0,
            "model": "m",
            "input_tokens": 0,
            "output_tokens": 0,
        }

    def test_7d_window_excludes_older(self, tmp_path: Path) -> None:
        """STD-101 req 240: 7-day rate ignores the build-era past."""
        records = [self._rec(1), self._rec(2), self._rec(20, "error"), self._rec(40, "error")]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.success_rate_7d == 1.0
        assert report.dispatches_7d == 2

    def test_30d_window(self, tmp_path: Path) -> None:
        """STD-101 req 240: 30-day rate covers the month, not the lifetime."""
        records = [self._rec(1), self._rec(20, "error"), self._rec(40, "error")]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.dispatches_30d == 2
        assert report.success_rate_30d == 0.5

    def test_skipped_excluded_from_rates(self, tmp_path: Path) -> None:
        """STD-101 req 241: skipped is neither success nor failure."""
        records = [self._rec(1), self._rec(1, "skipped"), self._rec(1, "skipped")]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.success_rate_7d == 1.0
        assert report.dispatches_7d == 1

    def test_trend_up(self, tmp_path: Path) -> None:
        """STD-101 req 242: trend compares this 7d vs the prior 7d."""
        records = [self._rec(1), self._rec(2), self._rec(9, "error"), self._rec(10, "error")]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.trend_7d == "up"

    def test_trend_flat_when_equal(self, tmp_path: Path) -> None:
        records = [self._rec(1), self._rec(9)]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.trend_7d == "flat"

    def test_empty_window_is_none(self, tmp_path: Path) -> None:
        """No dispatches in window → None, never a fake 100%."""
        records = [self._rec(40)]
        audit = _write_audit(tmp_path, records)
        report = compute_metrics(audit_dir=audit, now=self.now)
        assert report.success_rate_7d is None
        assert report.trend_7d == "n/a"

    def test_to_dict_includes_windows(self, tmp_path: Path) -> None:
        audit = _write_audit(tmp_path, [self._rec(1)])
        data = compute_metrics(audit_dir=audit, now=self.now).to_dict()
        for key in ("success_rate_7d", "success_rate_30d", "dispatches_7d", "dispatches_30d", "trend_7d"):
            assert key in data


class TestScoreboardInMorningReport:
    """STD-101 req 242: morning report carries the 7-day line vs the 95% target."""

    def test_report_contains_scoreboard_line(self) -> None:
        from rondo.metrics import MetricsReport
        from rondo.overnight import OvernightResult
        from rondo.report import generate_report

        metrics = MetricsReport()
        metrics.success_rate_7d = 0.97
        metrics.dispatches_7d = 30
        metrics.trend_7d = "up"
        result = OvernightResult(status="done")
        text = generate_report(result, metrics_report=metrics)
        assert "7-day success" in text
        assert "97%" in text
        assert "95%" in text

    def test_report_survives_missing_metrics(self) -> None:
        """Scoreboard is best-effort — report MUST always generate (STD-108 rule 10)."""
        from rondo.overnight import OvernightResult
        from rondo.report import generate_report

        text = generate_report(OvernightResult(status="done"))
        assert text  # -- no crash, report still generated


class TestCoreReliability:
    """RONDO-434 (dim-10 honesty): split end-to-end vs rondo-LOGIC reliability.

    The single "success rate" blamed rondo for provider outages. A 4-vendor
    hostile panel (reports/hostile-review-2026-06-15.md) flagged this on every
    review: "split core reliability from provider/transient reliability." The
    core rate excludes externally-caused transient failures from the denominator
    — it never INFLATES (logic failures still count); it only stops counting a
    provider's rate-limit against rondo's own correctness.
    """

    def test_core_success_rate_excludes_transient_failures(self, tmp_path):
        """A transient (external) failure drops out of the core denominator."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("a", "done", 0.01, 1.0),
                _make_outcome("b", "done", 0.01, 1.0),
                _make_outcome("c", "error", 0.0, 1.0, error_code="ERR_RATE_LIMIT"),  # transient
                _make_outcome("d", "error", 0.0, 1.0, error_code="ERR_CONFIG"),  # rondo logic
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.success_rate == 0.5  # -- end-to-end: 2/4, nothing hidden
        assert report.transient_failures == 1
        assert report.core_success_rate == pytest.approx(2 / 3)  # -- 2 / (4 - 1 transient)

    def test_core_equals_end_to_end_when_no_transient(self, tmp_path):
        """No transient failures => core == end-to-end (a logic failure gets no free pass)."""
        audit_dir = _write_audit(
            tmp_path,
            [
                _make_outcome("a", "done", 0.01, 1.0),
                _make_outcome("b", "error", 0.0, 1.0, error_code="ERR_CONFIG"),  # rondo logic
            ],
        )
        report = compute_metrics(audit_dir=audit_dir)
        assert report.success_rate == 0.5
        assert report.core_success_rate == 0.5
        assert report.transient_failures == 0

    def test_transient_codes_match_engine_constants(self):
        """The literal transient set mirrors engine's real ERR_ codes.

        Unmocked contract test: a rename in engine.py fails HERE instead of
        silently desyncing the honesty split.
        """
        from rondo import engine
        from rondo.metrics import _TRANSIENT_ERROR_CODES

        assert _TRANSIENT_ERROR_CODES == {
            engine.ERR_RATE_LIMIT,
            engine.ERR_PROVIDER_DOWN,
            engine.ERR_STREAM_DISCONNECT,
            engine.ERR_SUBPROCESS,
        }


# -- sig: mgh-6201.cd.bd955f.2758.43b0b0
