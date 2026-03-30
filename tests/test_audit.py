# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.audit — Rondo-STD-113 dispatch audit trail.

VER-001 verification matrix: two-phase audit recording, JSONL storage,
prompt/result file preservation, credential scrubbing, immutability.
"""

import hashlib
import json
import time
from pathlib import Path

import pytest

from rondo.audit import (
    AuditConfig,
    AuditRecord,
    AuditTrail,
)


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 001 — Audit record BEFORE dispatch (intent)
# -- ──────────────────────────────────────────────────────────────


class TestPhaseOneIntent:
    """STD-113 req 001: audit record created before subprocess launches."""

    def test_record_intent_creates_record(self, tmp_path):
        """Phase 1 writes an INTENT record."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="review_code",
            round_name="spec_review",
            model="claude-sonnet-4-6",
            prompt="Review this code for bugs",
        )
        assert record.dispatch_id != ""
        assert record.status == "INTENT"
        assert record.task_name == "review_code"

    def test_intent_has_dispatch_id(self, tmp_path):
        """Intent record gets a unique dispatch_id."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        r1 = trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p1")
        r2 = trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p2")
        assert r1.dispatch_id != r2.dispatch_id

    def test_intent_has_prompt_hash(self, tmp_path):
        """Intent record includes SHA-256 hash of prompt."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        prompt = "Review this code"
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt=prompt)
        expected_hash = hashlib.sha256(prompt.encode()).hexdigest()
        assert record.prompt_hash == f"sha256:{expected_hash}"

    def test_intent_has_timestamp(self, tmp_path):
        """Intent record has dispatched_at timestamp."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        assert record.dispatched_at != ""

    def test_intent_written_to_jsonl(self, tmp_path):
        """Intent record appended to JSONL file immediately."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        assert jsonl_file.exists()
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["status"] == "INTENT"


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 002 — Audit record updated AFTER dispatch
# -- ──────────────────────────────────────────────────────────────


class TestPhaseTwoComplete:
    """STD-113 req 002: audit record updated after dispatch completes."""

    def test_record_outcome_updates_status(self, tmp_path):
        """Phase 2 updates record to COMPLETE."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            cost_usd=0.042,
            duration_sec=12.5,
            raw_output="Result here",
            input_tokens=1000,
            output_tokens=500,
        )
        # -- Read back from JSONL
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        # -- Should have 2 lines: intent + complete
        assert len(lines) == 2
        complete = json.loads(lines[1])
        assert complete["status"] == "done"
        assert complete["cost_usd"] == 0.042

    def test_outcome_has_completed_at(self, tmp_path):
        """Phase 2 record has completed_at timestamp."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
        )
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        complete = json.loads(lines[1])
        assert complete["completed_at"] != ""


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 003 — Audit record schema
# -- ──────────────────────────────────────────────────────────────


class TestAuditRecordSchema:
    """STD-113 req 003: audit record contains required fields."""

    def test_record_has_all_required_fields(self, tmp_path):
        """AuditRecord has all mandatory fields from spec."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        required = [
            "dispatch_id", "task_name", "model", "prompt_hash",
            "dispatched_at", "status",
        ]
        for field_name in required:
            assert getattr(record, field_name) is not None, f"Missing field: {field_name}"

    def test_record_serializes_to_dict(self, tmp_path):
        """AuditRecord can be converted to JSON-serializable dict."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        data = record.to_dict()
        # -- Should be JSON-serializable
        json_str = json.dumps(data)
        assert "dispatch_id" in json_str


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 004 — Prompt stored in separate file
# -- ──────────────────────────────────────────────────────────────


class TestPromptStorage:
    """STD-113 req 004: full prompt text stored in audit/{id}.prompt.txt."""

    def test_prompt_file_created(self, tmp_path):
        """Prompt text saved to separate file."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="t", round_name="r", model="m",
            prompt="Review this code for security issues",
        )
        prompt_file = tmp_path / f"{record.dispatch_id}.prompt.txt"
        assert prompt_file.exists()
        assert "Review this code" in prompt_file.read_text(encoding="utf-8")

    def test_prompt_file_referenced_in_record(self, tmp_path):
        """Record's prompt_file field points to the saved file."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        assert record.prompt_file.endswith(".prompt.txt")


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 005 — Result stored in separate file
# -- ──────────────────────────────────────────────────────────────


class TestResultStorage:
    """STD-113 req 005: full result stored in audit/{id}.result.json."""

    def test_result_file_created_on_outcome(self, tmp_path):
        """Result JSON saved when outcome recorded."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            raw_output="AI said: hello world",
        )
        result_file = tmp_path / f"{record.dispatch_id}.result.json"
        assert result_file.exists()
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert data["raw_output"] == "AI said: hello world"


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 006 — Files modified tracking
# -- ──────────────────────────────────────────────────────────────


class TestFilesModified:
    """STD-113 req 006: files modified stored in audit record."""

    def test_files_modified_in_outcome(self, tmp_path):
        """Files list included in outcome record."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            files_modified=["src/main.py", "tests/test_main.py"],
        )
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        complete = json.loads(lines[1])
        assert "src/main.py" in complete["files_modified"]


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 007 — JSONL storage (append-only)
# -- ──────────────────────────────────────────────────────────────


class TestJsonlStorage:
    """STD-113 req 007: audit records in rondo_audit.jsonl, append-only."""

    def test_multiple_records_appended(self, tmp_path):
        """Multiple dispatches all append to same JSONL file."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p1")
        trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p2")
        trail.record_intent(task_name="t3", round_name="r", model="m", prompt="p3")
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_each_line_is_valid_json(self, tmp_path):
        """Every line in JSONL is parseable JSON."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p1")
        trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p2")
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
            data = json.loads(line)
            assert "dispatch_id" in data


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 008 — Audit dir configurable
# -- ──────────────────────────────────────────────────────────────


class TestAuditDir:
    """STD-113 req 008: audit dir is configurable."""

    def test_custom_audit_dir(self, tmp_path):
        """Audit files go to configured directory."""
        custom_dir = tmp_path / "custom_audit"
        trail = AuditTrail(config=AuditConfig(audit_dir=str(custom_dir)))
        trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        assert (custom_dir / "rondo_audit.jsonl").exists()

    def test_audit_dir_created_if_missing(self, tmp_path):
        """Audit dir auto-created if it doesn't exist."""
        new_dir = tmp_path / "new" / "nested" / "audit"
        trail = AuditTrail(config=AuditConfig(audit_dir=str(new_dir)))
        trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        assert new_dir.exists()


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 009 — Credential scrubbing before writing
# -- ──────────────────────────────────────────────────────────────


class TestCredentialScrubbing:
    """STD-113 req 009: scrub secrets via STD-114 before writing audit files."""

    def test_prompt_file_scrubbed(self, tmp_path):
        """Prompt text is scrubbed before writing to file."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="t", round_name="r", model="m",
            prompt="Use api_key = 'sk-real-secret-key-12345' to auth",
        )
        prompt_file = tmp_path / f"{record.dispatch_id}.prompt.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "sk-real-secret-key-12345" not in content
        assert "[REDACTED:" in content

    def test_result_file_scrubbed(self, tmp_path):
        """Result output is scrubbed before writing to file."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            raw_output="Found password = 'super_secret_value' in config",
        )
        result_file = tmp_path / f"{record.dispatch_id}.result.json"
        content = result_file.read_text(encoding="utf-8")
        assert "super_secret_value" not in content


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 010 — Append-only immutability
# -- ──────────────────────────────────────────────────────────────


class TestImmutability:
    """STD-113 req 010: audit records are append-only, never modified."""

    def test_outcome_appends_not_modifies(self, tmp_path):
        """Outcome adds new line, doesn't modify intent line."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")

        jsonl_file = tmp_path / "rondo_audit.jsonl"
        intent_line = jsonl_file.read_text(encoding="utf-8").strip()

        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
        )

        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        # -- Original intent line unchanged
        assert lines[0] == intent_line
        # -- New complete line appended
        assert len(lines) == 2


# -- ──────────────────────────────────────────────────────────────
# --  STD-113 req 014 — Morning report references dispatch_ids
# -- ──────────────────────────────────────────────────────────────


class TestMorningReportIds:
    """STD-113 req 014: failed dispatch IDs available for morning report."""

    def test_get_failed_dispatches(self, tmp_path):
        """Can query failed dispatches for morning report."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        r1 = trail.record_intent(task_name="ok", round_name="r", model="m", prompt="p")
        trail.record_outcome(dispatch_id=r1.dispatch_id, status="done", exit_code=0, task_name="ok")
        r2 = trail.record_intent(task_name="fail", round_name="r", model="m", prompt="p")
        trail.record_outcome(dispatch_id=r2.dispatch_id, status="error", exit_code=1, task_name="fail")

        failed = trail.get_failed_dispatches()
        assert len(failed) == 1
        assert failed[0]["task_name"] == "fail"


# -- ──────────────────────────────────────────────────────────────
# --  Edge cases
# -- ──────────────────────────────────────────────────────────────


class TestAuditEdgeCases:
    """Edge cases for audit trail."""

    def test_crash_leaves_intent(self, tmp_path):
        """If outcome never recorded, intent still exists for post-mortem."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="crashed", round_name="r", model="m", prompt="p")
        # -- No outcome recorded (simulating crash)
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["status"] == "INTENT"
        assert data["task_name"] == "crashed"

    def test_outcome_for_unknown_id_still_writes(self, tmp_path):
        """Outcome for unknown dispatch_id appends (doesn't crash)."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_outcome(
            dispatch_id="unknown-id",
            status="error",
            exit_code=1,
        )
        jsonl_file = tmp_path / "rondo_audit.jsonl"
        assert jsonl_file.exists()

    def test_empty_prompt(self, tmp_path):
        """Empty prompt doesn't crash."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="")
        assert record.prompt_hash.startswith("sha256:")

    def test_unicode_in_prompt(self, tmp_path):
        """Unicode prompt stored correctly."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="t", round_name="r", model="m",
            prompt="レビュー: このコードをチェック",
        )
        prompt_file = tmp_path / f"{record.dispatch_id}.prompt.txt"
        assert "レビュー" in prompt_file.read_text(encoding="utf-8")

    def test_large_output_stored(self, tmp_path):
        """Large output (>10KB) stored without truncation."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        large_output = "x" * 50_000
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            raw_output=large_output,
        )
        result_file = tmp_path / f"{record.dispatch_id}.result.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert len(data["raw_output"]) == 50_000


# -- ──────────────────────────────────────────────────────────────
# --  Audit rotation and reset (RONDO-29)
# -- ──────────────────────────────────────────────────────────────


class TestAuditRotate:
    """Audit rotation: archive by month, clean current."""

    def test_rotate_moves_to_archive(self, tmp_path):
        """Rotate moves current JSONL to archive/YYYY-MM.jsonl."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p")
        trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p")
        assert (tmp_path / "rondo_audit.jsonl").exists()
        count = trail.rotate()
        assert count > 0
        assert not (tmp_path / "rondo_audit.jsonl").exists()
        archives = list((tmp_path / "archive").glob("*.jsonl"))
        assert len(archives) == 1

    def test_rotate_empty_is_noop(self, tmp_path):
        """Rotate with no audit file returns 0."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        count = trail.rotate()
        assert count == 0

    def test_rotate_preserves_data(self, tmp_path):
        """Archived file has same content as original."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="check", round_name="r", model="m", prompt="p")
        original = (tmp_path / "rondo_audit.jsonl").read_text()
        trail.rotate()
        archives = list((tmp_path / "archive").glob("*.jsonl"))
        assert archives[0].read_text() == original


class TestAuditReset:
    """Audit reset: clear all data."""

    def test_reset_clears_jsonl(self, tmp_path):
        """Reset removes audit JSONL."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        assert (tmp_path / "rondo_audit.jsonl").exists()
        count = trail.reset()
        assert count > 0
        assert not (tmp_path / "rondo_audit.jsonl").exists()

    def test_reset_clears_prompt_result_files(self, tmp_path):
        """Reset removes .prompt.txt and .result.json files."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done", exit_code=0, raw_output="ok",
        )
        trail.reset()
        assert len(list(tmp_path.glob("*.prompt.txt"))) == 0
        assert len(list(tmp_path.glob("*.result.json"))) == 0

    def test_reset_empty_is_zero(self, tmp_path):
        """Reset with no data returns 0."""
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        count = trail.reset()
        assert count == 0


# -- sig: mgh-6201.cd.bd955f.f1a2.93a2b3
