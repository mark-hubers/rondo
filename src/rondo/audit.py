# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch audit trail — permanent record of every dispatch.

Rondo-STD-113: Dispatch Audit Trail.

Event model (append-only, event-sourcing pattern):
    Each dispatch produces TWO JSONL records, correlated by dispatch_id:
    1. INTENT record — written BEFORE subprocess launches (phase 1)
    2. OUTCOME record — appended AFTER subprocess completes (phase 2)

    Records are NEVER modified or deleted (STD-113 req 010). The two
    records form a pair: if only INTENT exists with no OUTCOME, the
    dispatch crashed or timed out — detectable in post-mortem.

    This is intentional append-only design, NOT a split-brain bug.
    Consumers correlate by dispatch_id to reconstruct the full picture.

Prompt/result files stored alongside JSONL, scrubbed via STD-114.

Import direction:
    audit.py → imports sanitize (STD-114 scrubbing before storage)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rondo.sanitize import sanitize_text

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Configuration — STD-113 req 008
# -- ──────────────────────────────────────────────────────────────


def _default_audit_dir() -> str:
    """Resolve audit dir: RONDO_TEST_DIR (test isolation) → ~/.rondo/audit."""
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return str(Path(test_dir) / "audit")
    return "~/.rondo/audit"


@dataclass
class AuditConfig:
    """Audit trail configuration — STD-113 req 008."""

    audit_dir: str = ""  # -- resolved in __post_init__
    enabled: bool = True
    prompt_storage: bool = True
    result_storage: bool = True
    audit_retention_days: int = 0  # -- 0 = keep forever

    def __post_init__(self) -> None:
        """COALESCE: explicit dir → RONDO_TEST_DIR → ~/.rondo/audit."""
        if not self.audit_dir:
            object.__setattr__(self, "audit_dir", _default_audit_dir())


# -- ──────────────────────────────────────────────────────────────
# --  Audit record — STD-113 req 003
# -- ──────────────────────────────────────────────────────────────


@dataclass
class AuditRecord:
    """One dispatch audit record — STD-113 req 003.

    Phase 1 (INTENT): dispatch_id, task_name, model, prompt_hash, dispatched_at.
    Phase 2 (COMPLETE): status, exit_code, cost_usd, duration_sec, completed_at.
    """

    # -- identity
    dispatch_id: str = ""
    task_name: str = ""
    round_name: str = ""
    model: str = ""

    # -- prompt tracking
    prompt_hash: str = ""
    prompt_file: str = ""

    # -- result tracking
    result_file: str = ""
    status: str = "INTENT"
    exit_code: int | None = None
    error_code: str | None = None

    # -- cost and timing
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_sec: float = 0.0

    # -- file tracking
    files_modified: list[str] = field(default_factory=list)

    # -- timestamps
    dispatched_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict — STD-113 req 007."""
        return {
            "dispatch_id": self.dispatch_id,
            "task_name": self.task_name,
            "round_name": self.round_name,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "prompt_file": self.prompt_file,
            "result_file": self.result_file,
            "status": self.status,
            "exit_code": self.exit_code,
            "error_code": self.error_code,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_sec": self.duration_sec,
            "files_modified": self.files_modified,
            "dispatched_at": self.dispatched_at,
            "completed_at": self.completed_at,
        }


# -- ──────────────────────────────────────────────────────────────
# --  Audit trail — main interface
# -- ──────────────────────────────────────────────────────────────


def _generate_dispatch_id() -> str:
    """Generate a unique dispatch ID — STD-113 req 003."""
    return f"dsp_{uuid.uuid4().hex[:16]}"


def _hash_prompt(prompt: str) -> str:
    """SHA-256 hash of prompt text — STD-113 req 003."""
    return f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()}"


class AuditTrail:
    """Two-phase dispatch audit trail — STD-113.

    Phase 1: record_intent() — called BEFORE dispatch.
    Phase 2: record_outcome() — called AFTER dispatch completes.
    """

    def __init__(self, *, config: AuditConfig | None = None) -> None:
        self.config = config or AuditConfig()
        self._audit_dir = Path(self.config.audit_dir).expanduser()
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self._audit_dir / "rondo_audit.jsonl"
        self._intent_times: dict[str, str] = {}  # -- dispatch_id → dispatched_at

    def record_intent(
        self,
        *,
        task_name: str,
        round_name: str,
        model: str,
        prompt: str,
    ) -> AuditRecord:
        """Phase 1: record dispatch intent BEFORE subprocess — STD-113 req 001.

        Creates audit record, saves prompt file, appends to JSONL.
        """
        dispatch_id = _generate_dispatch_id()
        prompt_file = f"{dispatch_id}.prompt.txt"

        record = AuditRecord(
            dispatch_id=dispatch_id,
            task_name=task_name,
            round_name=round_name,
            model=model,
            prompt_hash=_hash_prompt(prompt),
            prompt_file=prompt_file,
            status="INTENT",
            dispatched_at=datetime.now(UTC).isoformat(),
        )

        # -- STD-113 req 004: save prompt to file
        # -- STD-113 req 009: scrub secrets before writing
        if self.config.prompt_storage:
            scrubbed = sanitize_text(prompt)
            prompt_path = self._audit_dir / prompt_file
            prompt_path.write_text(scrubbed.sanitized_text, encoding="utf-8")

        # -- STD-113 req 007: append to JSONL (req 010: append-only)
        self._append_jsonl(record)

        # -- Finding #162: store dispatched_at for OUTCOME propagation
        self._intent_times[dispatch_id] = record.dispatched_at

        logger.info("Audit INTENT: %s task=%s model=%s", dispatch_id, task_name, model)
        return record

    def record_outcome(
        self,
        *,
        dispatch_id: str,
        status: str,
        exit_code: int = 0,
        error_code: str | None = None,
        cost_usd: float = 0.0,
        duration_sec: float = 0.0,
        raw_output: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        files_modified: list[str] | None = None,
        task_name: str = "",
        round_name: str = "",
        model: str = "",
    ) -> None:
        """Phase 2: record dispatch outcome AFTER subprocess — STD-113 req 002.

        Appends outcome record to JSONL, saves result file.
        """
        result_file = f"{dispatch_id}.result.json"

        outcome = AuditRecord(
            dispatch_id=dispatch_id,
            task_name=task_name,
            round_name=round_name,
            model=model,
            status=status,
            exit_code=exit_code,
            error_code=error_code,
            cost_usd=cost_usd,
            duration_sec=duration_sec,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            result_file=result_file,
            files_modified=files_modified or [],
            dispatched_at=self._intent_times.get(dispatch_id, ""),
            completed_at=datetime.now(UTC).isoformat(),
        )

        # -- STD-113 req 005: save result to file
        # -- STD-113 req 009: scrub secrets before writing
        if self.config.result_storage and raw_output:
            scrubbed = sanitize_text(raw_output)
            result_data = {
                "dispatch_id": dispatch_id,
                "status": status,
                "raw_output": scrubbed.sanitized_text,
                "secrets_scrubbed": scrubbed.secrets_found,
            }
            result_path = self._audit_dir / result_file
            result_path.write_text(
                json.dumps(result_data, indent=2),
                encoding="utf-8",
            )

        # -- STD-113 req 007 + 010: append outcome (never modify intent)
        self._append_jsonl(outcome)

        logger.info(
            "Audit OUTCOME: %s status=%s cost=$%.4f",
            dispatch_id,
            status,
            cost_usd,
        )

    def get_failed_dispatches(self) -> list[dict[str, Any]]:
        """Get failed dispatches for morning report — STD-113 req 014."""
        failed: list[dict[str, Any]] = []
        if not self._jsonl_path.exists():
            return failed
        for line in self._jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("status") in ("error", "blocked", "timeout"):
                failed.append(data)
        return failed

    def rotate(self) -> int:
        """Archive current JSONL to archive/YYYY-MM.jsonl — RONDO-29.

        Returns number of lines archived (0 if nothing to rotate).
        """
        if not self._jsonl_path.exists():
            return 0
        content = self._jsonl_path.read_text(encoding="utf-8").strip()
        if not content:
            self._jsonl_path.unlink()
            return 0
        line_count = len(content.splitlines())
        archive_dir = self._audit_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m")
        archive_path = archive_dir / f"{timestamp}.jsonl"
        ## -- Append if archive already exists (multiple rotations in same month)
        with archive_path.open("a", encoding="utf-8") as f:
            f.write(content + "\n")
        self._jsonl_path.unlink()
        logger.info("Rotated %d audit records to %s", line_count, archive_path)
        return line_count

    def reset(self) -> int:
        """Clear all audit data (JSONL + prompt/result files) — RONDO-29.

        Returns number of files removed.
        """
        removed = 0
        if self._jsonl_path.exists():
            self._jsonl_path.unlink()
            removed += 1
        for pattern in ("*.prompt.txt", "*.result.json"):
            for f in self._audit_dir.glob(pattern):
                f.unlink()
                removed += 1
        return removed

    def _append_jsonl(self, record: AuditRecord) -> None:
        """Append record to JSONL file — STD-113 reqs 007, 010."""
        with self._jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")


# -- sig: mgh-6201.cd.bd955f.f1a2.93a2b4
