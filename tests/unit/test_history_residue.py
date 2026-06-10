# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""History residue contracts — RONDO-386 (Claude-authored top-up).

VER-001 verification matrix: history query/aggregate edge contract.

The Cursor-authored test_history_contracts_cursor.py + the fixed mutation gate
(RONDO-385 pyc purge) left exactly three REAL survivors; these pin them:
the query_history task_name filter (never exercised anywhere) and the
aggregate r.get(..., 0) defaults for records missing cost/duration keys.
"""

from __future__ import annotations

import pytest

from rondo.history import aggregate_by_model, query_history


def test_query_history_filters_by_task_name() -> None:
    """task_name= keeps only matching records — the one filter nothing tested."""
    records = [
        {"task_name": "scan", "model": "sonnet"},
        {"task_name": "fix", "model": "sonnet"},
        {"task_name": "scan", "model": "opus"},
    ]
    got = query_history(records, task_name="scan")
    assert [r["model"] for r in got] == ["sonnet", "opus"]
    assert query_history(records, task_name="nope") == []


def test_aggregate_tolerates_missing_cost_and_duration_keys() -> None:
    """Records lacking cost_usd/duration_sec contribute 0 — not a crash, not 1."""
    records = [
        {"model": "sonnet", "status": "done"},  # -- no cost_usd, no duration_sec
        {"model": "sonnet", "status": "done", "cost_usd": 0.50, "duration_sec": 2.0},
    ]
    agg = aggregate_by_model(records)
    assert agg["sonnet"]["count"] == 2
    assert agg["sonnet"]["total_cost"] == pytest.approx(0.50)
    assert agg["sonnet"]["total_duration"] == pytest.approx(2.0)


# -- sig: mgh-6201.cd.bd955f.e2d3.d4a35d
