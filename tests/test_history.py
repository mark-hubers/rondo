# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.history — Rondo-REQ-104 dispatch history.

VER-001 verification matrix: dispatch telemetry logging + querying.
TDD: tests written BEFORE history.py exists.
"""

import json
from datetime import UTC, datetime


import pytest

from rondo.history import DispatchRecord, log_dispatch, load_history, query_history


class TestDispatchRecord:
    """Rondo-REQ-104 req 002: per-task telemetry."""

    def test_record_has_required_fields(self):
        r = DispatchRecord(
            round_name="test", task_name="t1", model="sonnet",
            status="done", cost_usd=0.01, duration_sec=1.5,
        )
        assert r.round_name == "test"
        assert r.task_name == "t1"
        assert r.model == "sonnet"
        assert r.cost_usd == 0.01

    def test_record_has_timestamp(self):
        r = DispatchRecord(round_name="r", task_name="t", model="sonnet", status="done")
        assert r.timestamp != ""


class TestLogDispatch:
    """Rondo-REQ-104 req 001: per-round telemetry logging."""

    def test_log_creates_file(self, tmp_path):
        r = DispatchRecord(round_name="r", task_name="t", model="sonnet", status="done")
        log_dispatch(r, str(tmp_path))
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1

    def test_log_appends_jsonl(self, tmp_path):
        r1 = DispatchRecord(round_name="r", task_name="t1", model="sonnet", status="done")
        r2 = DispatchRecord(round_name="r", task_name="t2", model="opus", status="error")
        log_dispatch(r1, str(tmp_path))
        log_dispatch(r2, str(tmp_path))
        files = list(tmp_path.glob("*.jsonl"))
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_is_valid_json_per_line(self, tmp_path):
        r = DispatchRecord(round_name="r", task_name="t", model="sonnet", status="done", cost_usd=0.05)
        log_dispatch(r, str(tmp_path))
        files = list(tmp_path.glob("*.jsonl"))
        data = json.loads(files[0].read_text().strip())
        assert data["task_name"] == "t"
        assert data["cost_usd"] == 0.05


class TestLoadHistory:
    """Rondo-REQ-104 req 004: queryable history."""

    def test_load_returns_records(self, tmp_path):
        r = DispatchRecord(round_name="r", task_name="t", model="sonnet", status="done")
        log_dispatch(r, str(tmp_path))
        records = load_history(str(tmp_path))
        assert len(records) == 1
        assert records[0]["task_name"] == "t"

    def test_load_empty_dir(self, tmp_path):
        records = load_history(str(tmp_path))
        assert records == []


class TestQueryHistory:
    """Rondo-REQ-104 req 004: filter by model, status."""

    def test_query_by_model(self, tmp_path):
        for model in ["sonnet", "opus", "sonnet"]:
            log_dispatch(DispatchRecord(
                round_name="r", task_name=f"t-{model}", model=model, status="done",
            ), str(tmp_path))
        records = load_history(str(tmp_path))
        opus_only = query_history(records, model="opus")
        assert len(opus_only) == 1

    def test_query_by_status(self, tmp_path):
        for status in ["done", "error", "done"]:
            log_dispatch(DispatchRecord(
                round_name="r", task_name=f"t-{status}", model="sonnet", status=status,
            ), str(tmp_path))
        records = load_history(str(tmp_path))
        errors = query_history(records, status="error")
        assert len(errors) == 1

    def test_query_no_filter_returns_all(self, tmp_path):
        for i in range(3):
            log_dispatch(DispatchRecord(
                round_name="r", task_name=f"t{i}", model="sonnet", status="done",
            ), str(tmp_path))
        records = load_history(str(tmp_path))
        assert len(query_history(records)) == 3


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b2c3
