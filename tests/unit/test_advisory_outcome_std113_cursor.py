# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-4: advisory OUTCOMEs vs STD-113.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved — a different AI authored, Claude implements; transcribed
verbatim from the dispatch).

THE BUG (re-score finding #4, review-20260610-184904.md): STD-113 req 021
(MUST) — every non-done OUTCOME persists error_message; the issued-advisory
OUTCOME passes "". And §8 still claims "two states: INTENT and COMPLETE"
while code emits done/error/blocked/skipped/stuck/advisory/refused. Both
sides get fixed: code passes a real delegation note; the spec's state
vocabulary is amended (spec-honesty, like item 8.9).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from rondo.audit import AuditConfig, AuditTrail
from rondo.mcp_dispatch import rondo_run_file


def test_advisory_outcome_has_error_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(a) Issued advisory OUTCOME has a NON-EMPTY error_message (req 021). MUST FAIL today."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt = f"test_advisory_{uuid.uuid4().hex}"

    result_str = rondo_run_file(prompt=prompt, model="", execution="inline", dry_run=False, _session=object())
    plan = json.loads(result_str)
    dispatch_id = plan.get("dispatch_id")

    audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
    records = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]

    advisory_records = [r for r in records if r.get("dispatch_id") == dispatch_id and r.get("status") == "advisory"]
    assert len(advisory_records) == 1, "expected exactly one advisory outcome record"

    record = advisory_records[0]
    assert "error_message" in record
    assert record["error_message"] != "", "error_message must be non-empty for advisory status per spec req 021"


def test_refused_outcome_has_error_message_and_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(b) Refused OUTCOME has non-empty error_message AND error_code ERR_BUDGET_EXCEEDED."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt = f"test_refused_{uuid.uuid4().hex}"

    result_str = rondo_run_file(
        prompt=prompt,
        model="sonnet",
        execution="agent",
        dry_run=False,
        _session=object(),
        max_budget=0.000001,
    )
    result = json.loads(result_str)
    assert result.get("status") == "error", "expected error envelope for refused plan"

    audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
    records = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]

    refused_records = [r for r in records if r.get("status") == "refused"]
    assert len(refused_records) >= 1, "expected at least one refused outcome record"

    record = refused_records[-1]
    assert "error_message" in record
    assert record["error_message"] != "", "error_message must be non-empty for refused status"
    assert record.get("error_code") == "ERR_BUDGET_EXCEEDED"


def test_spec_amendment_states() -> None:
    """(c) SPEC PIN: STD-113 mentions advisory AND refused; 'two states' gone. MUST FAIL today."""
    spec_path = Path(__file__).resolve().parents[2] / "specs" / "Rondo-STD-113-dispatch-audit-trail.md"
    content = spec_path.read_text(encoding="utf-8").lower()

    assert "advisory" in content, "spec must mention the 'advisory' state"
    assert "refused" in content, "spec must mention the 'refused' state"
    assert "two states" not in content, "spec must not contain the outdated phrase 'two states'"


def test_done_outcome_permits_empty_error_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(d) Rail: a done OUTCOME still permits empty error_message."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))

    audit_trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    dispatch_id = f"test_done_{uuid.uuid4().hex}"

    audit_trail.record_outcome(dispatch_id=dispatch_id, status="done", exit_code=0, error_message="")

    audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
    records = [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]

    done_records = [r for r in records if r.get("dispatch_id") == dispatch_id and r.get("status") == "done"]
    assert len(done_records) == 1

    record = done_records[0]
    assert record.get("error_message") == "", "done status should permit empty error_message"


def test_reconcile_stuck_intents_zero_after_advisory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(e) Rail: reconcile finds 0 stuck right after an advisory dispatch (INTENT paired)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt = f"test_reconcile_{uuid.uuid4().hex}"

    rondo_run_file(prompt=prompt, model="", execution="inline", dry_run=False, _session=object())

    audit_trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    stuck_count = audit_trail.reconcile_stuck_intents(stuck_after_sec=0)

    assert stuck_count == 0, "expected 0 stuck intents after a completed advisory dispatch"


# -- sig: mgh-6201.cd.bd955f.3290.1535e5
