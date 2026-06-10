# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression tests for ROAD-TO-8 item 8.1: QUARANTINE on scrub failure.

Mark's amended ruling (2026-06-10): when ``sanitize_task_result`` raises in the
shared finalize path (``rondo.dispatch``), the never-lose-data guarantee is kept
via QUARANTINE rather than fail-open-and-persist-unscrubbed. The new contract:

  (a) ANY Exception from sanitize → the raw result is written to a locked-down
      quarantine store (``<RONDO_TEST_DIR>/quarantine/`` mirroring audit/spool;
      ~/.rondo/quarantine/ in prod), one JSON file per result, born 0o600, with
      the original payload AND the error detail.
  (b) The unscrubbed payload is WITHHELD from the normal stores (audit outcome,
      result file, spool, history). The returned ``TaskResult`` has its
      raw_output/parsed_result REPLACED by a redaction stub, carries
      ``metrics["sanitize_failed"] is True``, and a quarantine reference in
      ``context_data``.
  (c) The -WARNING- log remains and now mentions quarantine + the file.
  (d) RecursionError and re.error are caught too (the narrow ``except
      (TypeError, AttributeError)`` is widened to ``except Exception``).
  (e) Clean path: a normal sanitize is untouched by any of this.

These tests drive ONLY the finalize path with a pre-built ``TaskResult`` (no
live dispatch), reusing the harness from ``test_sanitize_failopen_loud_cursor``.
Tests 1-4 MUST FAIL on current code (no quarantine store; raw persists; a
RecursionError escapes the narrow except). Test 5 (clean rail) passes today.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest import mock

import pytest

from rondo.config import RondoConfig
from rondo.dispatch import finalize_dispatch
from rondo.engine import DispatchUsage, TaskResult

_SANITIZE_TARGET = "rondo.dispatch.sanitize_task_result"

# -- A distinctive secret-bearing payload that must NEVER reach the normal
# -- stores once sanitize fails. Unique enough to grep for unambiguously.
_SECRET_RAW = "secret-bearing-raw-OUTPUT-9d4f1a-DO-NOT-PERSIST sk-LIVE-abc123"
_SECRET_PARSED = {"api_key": "sk-LIVE-parsed-7e2b-DO-NOT-PERSIST"}


def _build_result() -> TaskResult:
    """Return a done-status TaskResult carrying secret-bearing payload."""
    return TaskResult(
        task_name="quarantine-test",
        status="done",
        raw_output=_SECRET_RAW,
        parsed_result=dict(_SECRET_PARSED),
        model="gemini-2.5-flash",
    )


def _build_config(tmp_path: Path, *, spool: bool = False) -> RondoConfig:
    """Return a hermetic config: audit off, results under tmp, spool optional."""
    return RondoConfig(
        audit_dir="",
        results_dir=str(tmp_path / "results"),
        spool_enabled=spool,
    )


def _quarantine_files(tmp_path: Path) -> list[Path]:
    """Return JSON files written to the quarantine store under tmp."""
    qdir = tmp_path / "quarantine"
    if not qdir.exists():
        return []
    return sorted(qdir.glob("*.json"))


def _context_mentions_quarantine(result: TaskResult) -> bool:
    """True if context_data keys or values reference the quarantine store."""
    blob = " ".join(str(k) for k in result.context_data) + " " + " ".join(str(v) for v in result.context_data.values())
    return "quarantine" in blob.lower()


def test_typeerror_quarantines_and_withholds_raw(tmp_path, caplog, monkeypatch) -> None:
    """TypeError from sanitize → raw quarantined (0o600 file w/ payload+error), stub returned, flag, ref, WARNING."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    caplog.set_level(logging.WARNING, logger="rondo.dispatch")
    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    # -- (a) quarantine file exists with the ORIGINAL raw_output + the error
    files = _quarantine_files(tmp_path)
    assert files, "expected a quarantine JSON file under <RONDO_TEST_DIR>/quarantine/"
    payload = files[0].read_text(encoding="utf-8")
    assert _SECRET_RAW in payload, "quarantine file must preserve the original raw_output (never-lose-data)"
    assert "TypeError" in payload, "quarantine file must record the sanitize error detail"

    # -- (b) returned result is REDACTED: original secret absent, stub present
    assert _SECRET_RAW not in str(finalized.raw_output), "unscrubbed secret must be withheld from the returned result"
    assert "quarantin" in str(finalized.raw_output).lower(), "raw_output should be a quarantine redaction stub"
    assert finalized.metrics.get("sanitize_failed") is True, "metrics['sanitize_failed'] must be True"
    assert _context_mentions_quarantine(finalized), "context_data must carry a quarantine reference (path or id)"

    # -- (c) the -WARNING- log mentions quarantine
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING and "quarantine" in r.message.lower()]
    assert warnings, "expected a -WARNING- log mentioning quarantine"


def test_recursionerror_is_caught_and_quarantined(tmp_path, monkeypatch) -> None:
    """RecursionError from sanitize must NOT escape finalize — it quarantines identically (kills narrow except)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    with mock.patch(_SANITIZE_TARGET, side_effect=RecursionError("too deep")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    files = _quarantine_files(tmp_path)
    assert files, "RecursionError must be caught and the raw result quarantined (not crash finalize)"
    payload = files[0].read_text(encoding="utf-8")
    assert _SECRET_RAW in payload, "quarantine file must preserve the original raw_output"
    assert "RecursionError" in payload, "quarantine file must record the RecursionError detail"
    assert _SECRET_RAW not in str(finalized.raw_output), "unscrubbed secret must be withheld from the returned result"
    assert finalized.metrics.get("sanitize_failed") is True, "metrics['sanitize_failed'] must be True"


def test_unscrubbed_raw_is_withheld_from_spool(tmp_path, monkeypatch) -> None:
    """Withholding proof: with spool enabled, no spool file may contain the original unscrubbed raw text."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path, spool=True)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalize_dispatch(result, usage, config, None, None)

    # -- sanity: it WAS quarantined (so the secret lives in exactly one place)
    assert _quarantine_files(tmp_path), "expected the raw result to be quarantined"

    # -- the spool store (the finalize path's own write) must not leak the secret
    spool_dir = tmp_path / "spool"
    leaked = [
        f
        for f in spool_dir.rglob("*")
        if f.is_file() and (_SECRET_RAW in f.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not leaked, f"spool must NOT contain the unscrubbed raw payload, found in: {leaked}"


def test_quarantine_file_is_mode_0600(tmp_path, monkeypatch) -> None:
    """POSIX: the quarantine file is born with restrictive perms (mode & 0o777 == 0o600)."""
    if os.name != "posix":
        pytest.skip("POSIX file-mode assertion")
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalize_dispatch(result, usage, config, None, None)

    files = _quarantine_files(tmp_path)
    assert files, "expected a quarantine JSON file to inspect perms on"
    mode = files[0].stat().st_mode & 0o777
    assert mode == 0o600, f"quarantine file must be 0o600, got {oct(mode)}"


def test_clean_path_creates_no_quarantine(tmp_path, caplog, monkeypatch) -> None:
    """Clean rail: a successful sanitize creates no quarantine dir/file, no stub, no flag, no warning."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path, spool=True)

    scrubbed = _build_result()
    scrubbed.raw_output = "SCRUBBED-SENTINEL-7f3a"
    scrubbed.parsed_result = {"api_key": "[REDACTED]"}

    caplog.set_level(logging.WARNING, logger="rondo.dispatch")
    with mock.patch(_SANITIZE_TARGET, return_value=(scrubbed, None)):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    assert not (tmp_path / "quarantine").exists(), "clean path must NOT create a quarantine store"
    assert finalized.raw_output == "SCRUBBED-SENTINEL-7f3a", "the scrubbed result must be the one returned"
    assert "sanitize_failed" not in finalized.metrics, "no sanitize_failed flag on the happy path"
    assert not _context_mentions_quarantine(finalized), "no quarantine reference on the happy path"
    warnings = [r for r in caplog.records if "quarantine" in r.message.lower() or "sanitize" in r.message.lower()]
    assert not warnings, "no quarantine/sanitize WARNING should be logged on the happy path"


# -- Claude top-ups (labeled, RONDO-399): pins for mid-point review findings
# -- #1 and #2 (reports/cursor-reviews/midpoint-review-20260610-road-to-8.md).


def test_prompt_sent_is_redacted_too(tmp_path, monkeypatch) -> None:
    """Mid-point #1 (HIGH): prompt_sent is in sanitize's scrub set — it must be stubbed.

    The original redaction stubbed raw_output/parsed_result/stderr but left
    prompt_sent raw, so a secret in the PROMPT reached spool/history/envelope
    on the fail path (re-opening STD-104 r023). Every field sanitize scrubs
    must be redacted on scrub failure.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    result.prompt_sent = f"prompt with secret {_SECRET_RAW}"
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path, spool=True)

    with mock.patch(_SANITIZE_TARGET, side_effect=TypeError("boom")):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    assert _SECRET_RAW not in str(finalized.prompt_sent), "prompt_sent must be redacted on scrub failure"
    assert "quarantin" in str(finalized.prompt_sent).lower(), "prompt_sent should carry the quarantine stub"
    # -- the quarantine store still preserves the original (never-lose-data)
    files = _quarantine_files(tmp_path)
    assert files and _SECRET_RAW in files[0].read_text(encoding="utf-8")
    # -- and the spool write (asdict includes prompt_sent) must not leak it
    spool_dir = tmp_path / "spool"
    leaked = [
        f
        for f in spool_dir.rglob("*")
        if f.is_file() and _SECRET_RAW in f.read_text(encoding="utf-8", errors="replace")
    ]
    assert not leaked, f"spool must not contain the raw prompt, found in: {leaked}"


def test_redaction_survives_quarantine_write_recursionerror(tmp_path, monkeypatch) -> None:
    """Mid-point #2 (MED): a RecursionError in the quarantine WRITE must not defeat redaction.

    The same deeply-nested structure that crashed sanitize recurses again in
    json.dump inside the quarantine writer; the old narrow write-except let it
    escape BEFORE the redaction lines ran — finalize crashed with the result
    still raw. Redaction must win even when the quarantine write itself dies.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    result = _build_result()
    usage = DispatchUsage(task_name=result.task_name, model=result.model)
    config = _build_config(tmp_path)

    def _recursing_dump(*_args: object, **_kwargs: object) -> None:
        raise RecursionError("maximum recursion depth exceeded in json.dump")

    with (
        mock.patch(_SANITIZE_TARGET, side_effect=RecursionError("too deep")),
        mock.patch("rondo.dispatch.json.dump", _recursing_dump),
    ):
        finalized, _usage = finalize_dispatch(result, usage, config, None, None)

    assert _SECRET_RAW not in str(finalized.raw_output), "redaction must run even when the quarantine write fails"
    assert finalized.metrics.get("sanitize_failed") is True
    assert finalized.context_data.get("quarantine_file") == "", "failed write must record an empty quarantine ref"


# -- sig: mgh-6201.cd.bd955f.4d4e.c45c7f
