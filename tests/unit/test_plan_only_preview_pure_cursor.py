# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-7: plan_only previews are PURE.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved). Transcription note (documented, not silent): the author's
rail asserted the literal string "OUTCOME" in the JSONL — the OUTCOME record's
status field is the literal "advisory" (the word OUTCOME never appears in
records); re-pointed to assert "advisory"; the author's model="dummy-model" guess
trips ERR_INVALID_INPUT before routing (making test (a) pass vacuously) —
re-pointed to model="" like the existing advisory judges. Assertions
otherwise untouched.

THE BUG (re-score finding #7, review-20260610-184904.md): plan_only=True is
the documented pure PREVIEW ("return plan payload without execution"), yet
since RONDO-394 every advisory return — previews included — wrote 4 audit
artifacts and minted a dispatch_id. A preview must have ZERO side effects;
the estimate budget gate still applies (a side-effect-free refusal is useful).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from rondo.mcp_dispatch import rondo_run_file


def test_plan_only_inline_no_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(a) plan_only inline preview: no dispatch_id, no audit records, no prompt files.

    MUST FAIL on today's code (audit fires for every advisory return).
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt_text = f"test-inline-{uuid.uuid4()}"

    result = json.loads(rondo_run_file(prompt=prompt_text, model="", execution="inline", plan_only=True, _session=None))

    assert "dispatch_id" not in result, "preview must not mint a dispatch_id"

    audit_dir = tmp_path / "audit"
    if audit_dir.exists():
        jsonl_files = list(audit_dir.glob("*.jsonl"))
        prompt_files = list(audit_dir.glob("*.prompt.txt"))
        assert not jsonl_files, f"expected no JSONL records, found {jsonl_files}"
        assert not prompt_files, f"expected no prompt files, found {prompt_files}"


def test_plan_only_agent_sonnet_no_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(b) plan_only agent preview: zero side effects. MUST FAIL on today's code."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt_text = f"test-agent-{uuid.uuid4()}"

    result = json.loads(
        rondo_run_file(prompt=prompt_text, model="sonnet", execution="agent", plan_only=True, _session=None)
    )

    assert "dispatch_id" not in result, "preview must not mint a dispatch_id"

    audit_dir = tmp_path / "audit"
    if audit_dir.exists():
        jsonl_files = list(audit_dir.glob("*.jsonl"))
        prompt_files = list(audit_dir.glob("*.prompt.txt"))
        assert not jsonl_files, f"expected no JSONL records, found {jsonl_files}"
        assert not prompt_files, f"expected no prompt files, found {prompt_files}"


def test_plan_only_budget_gate_applies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(c) The estimate budget gate still applies to previews (side-effect-free refusal)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt_text = f"test-budget-{uuid.uuid4()}"

    result = json.loads(
        rondo_run_file(
            prompt=prompt_text,
            model="sonnet",
            execution="agent",
            plan_only=True,
            max_budget=0.000001,
            _session=None,
        )
    )

    assert result.get("status") == "error", "expected the budget gate to refuse the preview"
    assert "budget" in json.dumps(result).lower(), "expected 'budget' in the refusal envelope"


def test_default_path_has_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """(d) Rail: the default (non-preview) advisory path keeps its audit trail."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    prompt_text = f"test-default-{uuid.uuid4()}"

    result = json.loads(rondo_run_file(prompt=prompt_text, model="", execution="inline", _session=None))

    assert "dispatch_id" in result, "default execution must mint a dispatch_id"

    audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
    assert audit_file.exists(), "audit JSONL must exist for default execution"

    lines = [line for line in audit_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 2, f"expected exactly 2 audit lines (INTENT + advisory OUTCOME), got {len(lines)}"

    text_content = audit_file.read_text()
    assert "INTENT" in text_content, "audit log missing the INTENT record"
    # -- re-point: the OUTCOME record's literal status is "advisory"
    assert "advisory" in text_content, "audit log missing the advisory OUTCOME record"


# -- sig: mgh-6201.cd.bd955f.6d79.d2c50c
