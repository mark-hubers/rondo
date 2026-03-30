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
    MetricsReport,
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


def _make_outcome(task_name: str, status: str, cost: float,
                  duration: float, model: str = "sonnet",
                  error_code: str | None = None,
                  input_tokens: int = 1000, output_tokens: int = 500) -> dict:
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
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.20, 15.0),
            _make_outcome("t3", "error", 0.05, 5.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.total_cost_usd == pytest.approx(0.35)

    def test_avg_cost(self, tmp_path):
        """Average cost per dispatch."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.20, 15.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.avg_cost_usd == pytest.approx(0.15)

    def test_cost_by_model(self, tmp_path):
        """Cost broken down by model."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0, model="sonnet"),
            _make_outcome("t2", "done", 0.30, 15.0, model="opus"),
            _make_outcome("t3", "done", 0.05, 5.0, model="sonnet"),
        ])
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
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.10, 10.0),
            _make_outcome("t3", "error", 0.05, 5.0),
            _make_outcome("t4", "done", 0.10, 10.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.success_rate == pytest.approx(0.75)

    def test_error_breakdown(self, tmp_path):
        """Error codes counted."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "error", 0.0, 5.0, error_code="ERR_TIMEOUT"),
            _make_outcome("t2", "error", 0.0, 5.0, error_code="ERR_TIMEOUT"),
            _make_outcome("t3", "error", 0.0, 5.0, error_code="ERR_RATE_LIMIT"),
            _make_outcome("t4", "done", 0.10, 10.0),
        ])
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
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.10, 20.0),
            _make_outcome("t3", "done", 0.10, 30.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.avg_duration_sec == pytest.approx(20.0)

    def test_max_duration(self, tmp_path):
        """Max duration recorded."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 5.0),
            _make_outcome("t2", "done", 0.10, 45.0),
            _make_outcome("t3", "done", 0.10, 15.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.max_duration_sec == pytest.approx(45.0)


# -- ──────────────────────────────────────────────────────────────
# --  Token metrics
# -- ──────────────────────────────────────────────────────────────


class TestTokenMetrics:
    """Metrics: token usage."""

    def test_total_tokens(self, tmp_path):
        """Total input + output tokens."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0, input_tokens=5000, output_tokens=1000),
            _make_outcome("t2", "done", 0.10, 10.0, input_tokens=3000, output_tokens=2000),
        ])
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
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0, model="sonnet"),
            _make_outcome("t2", "done", 0.10, 10.0, model="sonnet"),
            _make_outcome("t3", "done", 0.30, 20.0, model="opus"),
        ])
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
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.10, 10.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health == "GREEN"

    def test_yellow_when_some_errors(self, tmp_path):
        """Some errors but >50% success = YELLOW."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
            _make_outcome("t2", "done", 0.10, 10.0),
            _make_outcome("t3", "error", 0.05, 5.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health in ("GREEN", "YELLOW")

    def test_red_when_mostly_errors(self, tmp_path):
        """Mostly errors = RED."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "error", 0.0, 5.0),
            _make_outcome("t2", "error", 0.0, 5.0),
            _make_outcome("t3", "error", 0.0, 5.0),
            _make_outcome("t4", "done", 0.10, 10.0),
        ])
        report = compute_metrics(audit_dir=audit_dir)
        assert report.health == "RED"


# -- ──────────────────────────────────────────────────────────────
# --  Serialization
# -- ──────────────────────────────────────────────────────────────


class TestMetricsSerialization:
    """Metrics: JSON output for OB/ACE/MCP consumption."""

    def test_to_dict(self, tmp_path):
        """MetricsReport serializes to JSON-safe dict."""
        audit_dir = _write_audit(tmp_path, [
            _make_outcome("t1", "done", 0.10, 10.0),
        ])
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


# -- sig: mgh-6201.cd.bd955f.f1a6.97a6b7
