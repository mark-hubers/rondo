# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-gate regression: history.py record/log/load/aggregate contracts.

VER-001 verification matrix: dispatch-history telemetry shape and math.

Quality-checklist item 16 (mutation gate): src/rondo/history.py leaks 11 of 25
mutants past tests/unit/test_history.py. Every survivor is a REAL contract gap —
the CLI cost/metrics commands consume these functions, so a regression would ship
while the suite stayed green. These tests pin the OBSERVABLE outcomes the
survivors depend on, mirroring tests/unit/test_spool_contracts_cursor.py in
spirit. They PASS against current code — their proof is RED-vs-MUTANTS: with them
landed, bin/mutate on history.py kills the listed survivors.

Survivor groups covered (A-E):
    A DispatchRecord defaults — numeric/bool zero-value record shape contract
    B log_dispatch dir handling — parents/exist_ok bools + 0o700 mode literal
    C log_dispatch + load_history round-trip — field fidelity + daily filename
    D load_history missing dir — returns [] (never None, never raises)
    E aggregate_by_model — count/success/error/cost/duration math + unknown bucket
"""

import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rondo.history import (
    DispatchRecord,
    aggregate_by_model,
    load_history,
    log_dispatch,
)

# -- ──────────────────────────────────────────────────────────────
# --  A. DispatchRecord defaults — bare-record zero-value contract
# -- ──────────────────────────────────────────────────────────────


class TestDispatchRecordDefaults:
    """A bare DispatchRecord() must expose the documented zero defaults."""

    def test_bare_record_numeric_and_bool_defaults(self) -> None:
        """input_tokens/output_tokens default to 0 and budget_exceeded to False.

        Pins the record-shape contract the cost/metrics commands read. Kills the
        int-literal mutants on the token defaults and the bool mutant on
        budget_exceeded (a flip to True would silently flag every dispatch).
        """
        record = DispatchRecord()
        assert record.input_tokens == 0
        assert record.output_tokens == 0
        assert record.budget_exceeded is False


# -- ──────────────────────────────────────────────────────────────
# --  B. log_dispatch directory handling — parents/exist_ok/mode
# -- ──────────────────────────────────────────────────────────────


class TestLogDispatchDirHandling:
    """log_dispatch must mkdir nested dirs, tolerate re-entry, and lock mode 0o700."""

    def test_twice_into_nested_missing_dir_succeeds(self, tmp_path: Path) -> None:
        """Two logs into a NESTED missing dir both succeed and append two lines.

        The first call needs parents=True (else the missing intermediate dir
        crashes); the second needs exist_ok=True (else the now-existing dir
        crashes). Flipping either bool turns one of these calls into an error.
        """
        nested = tmp_path / "a" / "b"
        log_dispatch(DispatchRecord(task_name="first"), str(nested))
        log_dispatch(DispatchRecord(task_name="second"), str(nested))

        files = list(nested.glob("history-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
    def test_created_dir_mode_is_0o700(self, tmp_path: Path) -> None:
        """The created history dir is owner-only (st_mode & 0o777) == 0o700.

        umask is zeroed so the requested mode lands verbatim — any change to the
        0o700 (448) literal then shows up directly in the leaf dir's mode.
        """
        nested = tmp_path / "a" / "b"
        old_umask = os.umask(0)
        try:
            log_dispatch(DispatchRecord(task_name="t"), str(nested))
        finally:
            os.umask(old_umask)

        mode = nested.stat().st_mode & 0o777
        assert mode == 0o700, oct(mode)


# -- ──────────────────────────────────────────────────────────────
# --  C. log_dispatch + load_history round-trip — fields + filename
# -- ──────────────────────────────────────────────────────────────


class TestRoundTrip:
    """A logged record reloads field-for-field from a daily-named JSONL file."""

    def test_logged_record_round_trips_with_daily_filename(self, tmp_path: Path) -> None:
        """Field values survive log -> load; file is history-YYYY-MM-DD.jsonl.

        Pins the asdict/json serialization fidelity and the daily filename
        format the load glob and CLI reporting depend on.
        """
        record = DispatchRecord(
            round_name="round-x",
            task_name="task-y",
            model="opus",
            status="done",
            cost_usd=0.42,
            duration_sec=3.5,
            input_tokens=123,
            output_tokens=456,
            confidence=0.9,
            error_code="",
            budget_exceeded=True,
        )
        log_dispatch(record, str(tmp_path))

        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        expected = tmp_path / f"history-{date_str}.jsonl"
        assert expected.is_file()
        assert re.fullmatch(r"history-\d{4}-\d{2}-\d{2}\.jsonl", expected.name)

        loaded = load_history(str(tmp_path))
        assert len(loaded) == 1
        got = loaded[0]
        assert got["round_name"] == "round-x"
        assert got["task_name"] == "task-y"
        assert got["model"] == "opus"
        assert got["status"] == "done"
        assert got["cost_usd"] == 0.42
        assert got["duration_sec"] == 3.5
        assert got["input_tokens"] == 123
        assert got["output_tokens"] == 456
        assert got["confidence"] == 0.9
        assert got["budget_exceeded"] is True


# -- ──────────────────────────────────────────────────────────────
# --  D. load_history missing dir — [] not None, never raises
# -- ──────────────────────────────────────────────────────────────


class TestLoadHistoryMissingDir:
    """load_history on an absent dir returns an empty list, calmly."""

    def test_missing_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """A non-existent history dir yields [] — not None, no exception.

        Pins the early-return guard: a mutant that returns None (or drops the
        guard so the glob raises) dies here.
        """
        ghost = tmp_path / "ghost"
        result = load_history(str(ghost))
        assert result == []
        assert result is not None
        assert isinstance(result, list)


# -- ──────────────────────────────────────────────────────────────
# --  E. aggregate_by_model — count/success/error/cost/duration math
# -- ──────────────────────────────────────────────────────────────


class TestAggregateByModel:
    """aggregate_by_model must count all, success only 'done', error only 'error'."""

    def test_status_buckets_costs_and_unknown_key(self) -> None:
        """count=all; success=done-only; error=error-only; partial counts neither.

        Two models carry done/error/partial rows with known costs/durations, and
        a model-less row must bucket under 'unknown'. This kills the count/cost/
        duration arithmetic mutants, the done/error status-compare mutants, and
        the get("model", "unknown") default mutant.
        """
        records = [
            {"model": "sonnet", "status": "done", "cost_usd": 0.10, "duration_sec": 1.0},
            {"model": "sonnet", "status": "error", "cost_usd": 0.20, "duration_sec": 2.0},
            {"model": "sonnet", "status": "partial", "cost_usd": 0.05, "duration_sec": 0.5},
            {"model": "opus", "status": "done", "cost_usd": 1.00, "duration_sec": 10.0},
            {"status": "done", "cost_usd": 0.01, "duration_sec": 0.1},
        ]
        agg = aggregate_by_model(records)

        # -- sonnet: 3 rows, but only done->success and error->error; partial neither.
        assert agg["sonnet"]["count"] == 3
        assert agg["sonnet"]["success"] == 1
        assert agg["sonnet"]["error"] == 1
        assert agg["sonnet"]["total_cost"] == pytest.approx(0.35)
        assert agg["sonnet"]["total_duration"] == pytest.approx(3.5)

        # -- opus: single done row.
        assert agg["opus"]["count"] == 1
        assert agg["opus"]["success"] == 1
        assert agg["opus"]["error"] == 0
        assert agg["opus"]["total_cost"] == pytest.approx(1.00)
        assert agg["opus"]["total_duration"] == pytest.approx(10.0)

        # -- model-less row buckets under the 'unknown' default key.
        assert "unknown" in agg
        assert agg["unknown"]["count"] == 1
        assert agg["unknown"]["total_cost"] == pytest.approx(0.01)


# -- sig: mgh-6201.cd.bd955f.02df.fdbfa0
