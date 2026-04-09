# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo metrics — aggregate dispatch data for OB dashboards and health.

STD-101 observability + ALWAYS-ON infrastructure.
Reads audit JSONL (already captured by every dispatch) and computes:
cost, throughput, reliability, latency, token usage, model comparison, health.

No new data capture needed — metrics are computed from existing ALWAYS-ON data.
Designed for OB dashboard, ACE health checks, and future MCP server (IFS-104).

Import direction:
    metrics.py → no rondo imports (reads JSONL files directly)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Metrics report — the single JSON blob OB needs
# -- ──────────────────────────────────────────────────────────────


@dataclass
class MetricsReport:  # pylint: disable=too-many-instance-attributes
    """Complete metrics snapshot — one call, everything OB needs."""

    # -- summary
    total_dispatches: int = 0
    health: str = "GREEN"

    # -- cost
    total_cost_usd: float = 0.0
    avg_cost_usd: float = 0.0
    cost_by_model: dict[str, float] = field(default_factory=dict)

    # -- reliability
    success_rate: float = 1.0
    success_count: int = 0
    error_count: int = 0
    error_breakdown: dict[str, int] = field(default_factory=dict)

    # -- latency
    avg_duration_sec: float = 0.0
    max_duration_sec: float = 0.0
    min_duration_sec: float = 0.0

    # -- tokens
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # -- model comparison
    dispatches_by_model: dict[str, int] = field(default_factory=dict)

    # -- spool
    spool_pending: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict for OB/ACE/MCP consumption."""
        return {
            "total_dispatches": self.total_dispatches,
            "health": self.health,
            "total_cost_usd": self.total_cost_usd,
            "avg_cost_usd": self.avg_cost_usd,
            "cost_by_model": self.cost_by_model,
            "success_rate": self.success_rate,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "error_breakdown": self.error_breakdown,
            "avg_duration_sec": self.avg_duration_sec,
            "max_duration_sec": self.max_duration_sec,
            "min_duration_sec": self.min_duration_sec,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "dispatches_by_model": self.dispatches_by_model,
            "spool_pending": self.spool_pending,
        }


# -- ──────────────────────────────────────────────────────────────
# --  Compute metrics from audit JSONL
# -- ──────────────────────────────────────────────────────────────


def _load_outcomes(audit_dir: str) -> list[dict[str, Any]]:
    """Load outcome records from audit JSONL (skip INTENTs)."""
    jsonl_path = Path(audit_dir).expanduser() / "rondo_audit.jsonl"
    if not jsonl_path.exists():
        return []

    outcomes: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        # -- Skip INTENT records — only count outcomes
        if record.get("status") == "INTENT":
            continue
        outcomes.append(record)
    return outcomes


def _count_spool(spool_dir: str = "~/.rondo/spool") -> int:
    """Count pending spool files."""
    spool_path = Path(spool_dir).expanduser()
    if not spool_path.exists():
        return 0
    return len(list(spool_path.glob("*.json")))


def _determine_health(success_rate: float, total: int) -> str:
    """Determine health status from success rate.

    GREEN: >80% success or no dispatches
    YELLOW: 50-80% success
    RED: <50% success
    """
    if total == 0:
        return "GREEN"
    if success_rate >= 0.80:
        return "GREEN"
    if success_rate >= 0.50:
        return "YELLOW"
    return "RED"


def compute_metrics(
    *,
    audit_dir: str = "~/.rondo/audit",
    spool_dir: str = "~/.rondo/spool",
) -> MetricsReport:
    """Compute all metrics from existing ALWAYS-ON data.

    One function call, one JSON blob — everything OB needs for dashboards.
    Reads audit JSONL + spool directory. No new data capture needed.
    """
    outcomes = _load_outcomes(audit_dir)
    report = MetricsReport()

    if not outcomes:
        report.spool_pending = _count_spool(spool_dir)
        return report

    report.total_dispatches = len(outcomes)

    # -- Cost metrics
    costs = [r.get("cost_usd", 0) or 0 for r in outcomes]
    report.total_cost_usd = sum(costs)
    report.avg_cost_usd = report.total_cost_usd / len(outcomes)

    for r in outcomes:
        model = r.get("model", "unknown")
        report.cost_by_model[model] = report.cost_by_model.get(model, 0) + (r.get("cost_usd", 0) or 0)
        report.dispatches_by_model[model] = report.dispatches_by_model.get(model, 0) + 1

    # -- Reliability metrics
    success_statuses = {"done", "partial"}
    successes = [r for r in outcomes if r.get("status") in success_statuses]
    errors = [r for r in outcomes if r.get("status") not in success_statuses]
    report.success_count = len(successes)
    report.error_count = len(errors)
    report.success_rate = len(successes) / len(outcomes)

    for r in errors:
        code = r.get("error_code") or r.get("status", "unknown")
        report.error_breakdown[code] = report.error_breakdown.get(code, 0) + 1

    # -- Latency metrics
    durations = [r.get("duration_sec", 0) or 0 for r in outcomes if r.get("duration_sec")]
    if durations:
        report.avg_duration_sec = sum(durations) / len(durations)
        report.max_duration_sec = max(durations)
        report.min_duration_sec = min(durations)

    # -- Token metrics
    report.total_input_tokens = sum(r.get("input_tokens", 0) or 0 for r in outcomes)
    report.total_output_tokens = sum(r.get("output_tokens", 0) or 0 for r in outcomes)

    # -- Health
    report.health = _determine_health(report.success_rate, report.total_dispatches)

    # -- Spool
    report.spool_pending = _count_spool(spool_dir)

    return report


# -- sig: mgh-6201.cd.bd955f.f1a6.97a6b8
