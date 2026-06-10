# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression tests for quality-checklist item 20: sanitize FAIL-OPEN + LOUD.

When ``sanitize_task_result`` itself raises (a bug in the sanitizer, e.g.
TypeError/AttributeError), the shared finalize path in ``rondo.dispatch``
catches it. Today that catch is *silent* (DEBUG-only, no flag, no marking)
and the UNSCRUBBED result proceeds to audit/spool/history.

Mark's ruling: keep persisting the data (golden rule — never lose data) BUT
make the failure LOUD and machine-detectable:
  (a) a -WARNING- log noting the result persisted UNSCRUBBED,
  (b) ``result.metrics["sanitize_failed"] is True``,
  (c) ``result.context_data["sanitize_error"]`` carrying the exception detail.

AMENDED by RONDO-391 (ROAD-TO-8 item 8.1, Mark 2026-06-10): persistence of the
RAW payload moved from in-band (the returned/stored result) to the QUARANTINE
store — see ``test_sanitize_quarantine_cursor.py`` for the superseding pins.
The LOUD contract (warning + flag + context marking) is unchanged and still
pinned here. Only the persist-raw assertion in test 1 was updated to the
quarantine stub; the reconciliation is documented in the RONDO-391 commit.

These tests drive ONLY the finalize path with a pre-built ``TaskResult``
(no live dispatch). Tests for (a)/(b)/(c) MUST FAIL on current code.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import logging
from unittest import mock

from rondo.config import RondoConfig
from rondo.dispatch import finalize_dispatch
from rondo.engine import DispatchUsage, TaskResult

_SANITIZE_TARGET = "rondo.dispatch.sanitize_task_result"


def _build_result() -> TaskResult:
    """Return a representative done-status TaskResult for finalize."""
    return TaskResult(
        task_name="failopen-test",
        status="done",
        raw_output="some output with a value",
        model="gemini-2.5-flash",
    )


def _build_config(tmp_path) -> RondoConfig:
    """Return a hermetic config: audit off, results under tmp (no real I/O)."""
    return RondoConfig(audit_dir="", results_dir=str(tmp_path / "results"))


def test_failopen_does_not_raise_and_persists(tmp_path) -> None:
    """(a) When the sanitizer bombs, finalize must NOT raise and must return the result.

    RONDO-391 amendment: the raw payload now persists in the QUARANTINE store
    (never-lose-data kept), so the RETURNED result carries the redaction stub —
    not the original text. The original persist-raw assertion was superseded.
    """
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    assert finalized is result, "fail-open must still return the (redacted-in-place) result"
    # -- RONDO-391: raw text lives in quarantine now; the in-band result is the stub
    assert "quarantin" in str(finalized.raw_output).lower(), "raw_output must be the quarantine redaction stub"
    assert "some output with a value" not in str(finalized.raw_output), "original text must be withheld in-band"


def test_failopen_logs_warning(tmp_path, caplog) -> None:
    """(b) A WARNING record must mention persisting unscrubbed / a sanitize failure."""
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    caplog.set_level(logging.WARNING, logger="rondo.dispatch")
    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalize_dispatch(result, usage, config, None, None)

    # -- tolerant of exact wording: any WARNING mentioning unscrubbed OR sanitize
    matches = [
        rec
        for rec in caplog.records
        if rec.levelno >= logging.WARNING and ("unscrubbed" in rec.message.lower() or "sanitize" in rec.message.lower())
    ]
    assert matches, "expected a -WARNING- log noting the result persisted UNSCRUBBED / sanitize failure"


def test_failopen_sets_metrics_flag(tmp_path) -> None:
    """(c) result.metrics["sanitize_failed"] must be True after a sanitizer crash."""
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    # -- raising-tolerant on the field NAME: .get() never KeyErrors; contract pins the key
    assert finalized.metrics.get("sanitize_failed") is True, (
        "expected machine-readable metrics['sanitize_failed'] is True on sanitize crash"
    )


def test_failopen_marks_context_data(tmp_path) -> None:
    """(c) result.context_data["sanitize_error"] must carry the exception detail (TypeError)."""
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    # -- raising-tolerant on the field NAME: .get() never KeyErrors; contract pins the key
    sanitize_error = finalized.context_data.get("sanitize_error")
    assert sanitize_error is not None, "expected context_data['sanitize_error'] marking on sanitize crash"
    assert "TypeError" in str(sanitize_error), "sanitize_error should mention the exception type"


def test_success_is_quiet_and_scrubbed_result_persists(tmp_path, caplog) -> None:
    """Rail: a normal sanitize is quiet (no warning, no flag) and the scrubbed result survives."""
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    sentinel = _build_result()
    sentinel.raw_output = "SCRUBBED-SENTINEL-7f3a"

    caplog.set_level(logging.WARNING, logger="rondo.dispatch")
    with mock.patch(_SANITIZE_TARGET, return_value=(sentinel, None)):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    assert finalized.raw_output == "SCRUBBED-SENTINEL-7f3a", "the scrubbed result must be the one persisted"

    warnings = [
        rec for rec in caplog.records if ("unscrubbed" in rec.message.lower() or "sanitize" in rec.message.lower())
    ]
    assert not warnings, "no sanitize/unscrubbed WARNING should be logged on the happy path"
    assert "sanitize_failed" not in finalized.metrics, "no sanitize_failed flag on the happy path"


# -- sig: mgh-6201.cd.bd955f.4605.904767
