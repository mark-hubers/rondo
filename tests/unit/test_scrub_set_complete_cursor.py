# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-2: the COMPLETE scrub set + archive perms.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved — a different AI authored, Claude implements). Transcription
notes, documented not silent: (1) the author's returned fixture constant came
back as "[REDACTED:aws_access_key]" because rondo's OWN sanitize pipeline
scrubbed the canonical fake key inside the dispatch result — live proof of the
machinery; restored to the intended AKIAIOSFODNN7EXAMPLE. (2) unit-level
sanitize_task_result calls pass config=None (the config param is the SANITIZE
config, not RondoConfig — harness re-point, assertions untouched).

THE BUG (re-score finding #2 + #8, review-20260610-184904.md): sanitize scrubs
only prompt_sent/raw_output/stderr/parsed_result — error_message, context_data,
command_sent reach spool/history RAW (STD-114 r006 MUST); the rotated audit
archive is born at umask (STD-110 r012).
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

import pytest

from rondo.audit import AuditConfig, AuditTrail
from rondo.config import RondoConfig
from rondo.dispatch import finalize_dispatch
from rondo.engine import DispatchUsage, TaskResult
from rondo.sanitize import sanitize_task_result

# -- the gitleaks-allowlisted canonical fake (AWS docs example key)
_AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"  # noqa: S105 -- fake; used to assert redaction


def test_sanitize_scrubs_error_message() -> None:
    """error_message is in the scrub set: secret gone, [REDACTED marker present."""
    result = TaskResult(
        task_name="test_err",
        status="error",
        raw_output="",
        model="gemini-2.5-flash",
        error_message=f"Failed with token {_AWS_EXAMPLE_KEY}",
    )
    sanitized, _ = sanitize_task_result(result, config=None)

    assert sanitized.error_message is not None
    assert _AWS_EXAMPLE_KEY not in sanitized.error_message
    assert "[REDACTED" in sanitized.error_message


def test_sanitize_scrubs_context_and_command() -> None:
    """context_data is scrubbed recursively; command_sent list elements too."""
    result = TaskResult(
        task_name="test_ctx",
        status="done",
        raw_output="",
        model="gemini-2.5-flash",
        command_sent=["curl", "-H", f"Authorization: Bearer {_AWS_EXAMPLE_KEY}"],
        context_data={"nested": {"token": _AWS_EXAMPLE_KEY}},
    )
    sanitized, _ = sanitize_task_result(result, config=None)

    command_str = str(sanitized.command_sent)
    assert _AWS_EXAMPLE_KEY not in command_str
    assert "[REDACTED" in command_str

    context_str = str(sanitized.context_data)
    assert _AWS_EXAMPLE_KEY not in context_str
    assert "[REDACTED" in context_str


def test_store_level_no_leak_in_spool_or_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Finalize must not leak the secret to ANY store file (quarantine excluded)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    config = RondoConfig(
        audit_dir=str(tmp_path / "audit"),
        results_dir=str(tmp_path / "results"),
        spool_enabled=True,
    )
    result = TaskResult(
        task_name="test_store",
        status="error",
        raw_output="",
        model="gemini-2.5-flash",
        error_message=f"Error: {_AWS_EXAMPLE_KEY}",
        context_data={"key": _AWS_EXAMPLE_KEY},
    )
    usage = DispatchUsage(task_name="test_store", model="gemini-2.5-flash")

    finalize_dispatch(result, usage, config, None, None)

    leaks: list[Path] = []
    for root, dirs, files in os.walk(tmp_path):
        if "quarantine" in dirs:
            dirs.remove("quarantine")
        for file in files:
            file_path = Path(root) / file
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if _AWS_EXAMPLE_KEY in content:
                leaks.append(file_path)

    assert not leaks, f"secret leaked to disk outside quarantine: {leaks}"


def test_audit_archive_rotation_permissions(tmp_path: Path) -> None:
    """The rotated archive JSONL is born 0o600 even under umask 0."""
    if os.name != "posix":
        pytest.skip("POSIX-only permission test")

    cfg = AuditConfig(audit_dir=str(tmp_path / "audit"), max_jsonl_bytes=200)
    trail = AuditTrail(config=cfg, auto_reconcile=False)

    old_umask = os.umask(0)
    try:
        for _ in range(10):
            trail.record_intent(task_name="t", round_name="r", model="m", prompt="p" * 50)

        archive_dir = tmp_path / "audit" / "archive"
        assert archive_dir.exists(), "archive directory not created (rotation never fired)"

        archive_files = list(archive_dir.glob("*.jsonl"))
        assert archive_files, "no archive files created"

        for archive_file in archive_files:
            mode = archive_file.stat().st_mode
            assert mode & 0o777 == 0o600, f"{archive_file} has mode {oct(mode)}, expected 0o600"
    finally:
        os.umask(old_umask)


def test_rails_raw_output_scrubbing_unchanged() -> None:
    """Rail: raw_output scrubbing behaves exactly as before."""
    result = TaskResult(
        task_name="test_raw",
        status="done",
        raw_output=f"Output: {_AWS_EXAMPLE_KEY}",
        model="gemini-2.5-flash",
    )
    sanitized, _ = sanitize_task_result(result, config=None)

    assert _AWS_EXAMPLE_KEY not in sanitized.raw_output
    assert "[REDACTED" in sanitized.raw_output


def test_rails_clean_task_result_unchanged() -> None:
    """Rail: a clean TaskResult passes through with zero redaction markers."""
    result = TaskResult(
        task_name="test_clean",
        status="done",
        raw_output="Clean output",
        model="gemini-2.5-flash",
        error_message="No errors",
        command_sent=["echo", "hello"],
        context_data={"info": "safe"},
    )
    sanitized, _ = sanitize_task_result(result, config=None)

    sanitized_str = str(asdict(sanitized))
    assert "[REDACTED" not in sanitized_str
    assert sanitized.raw_output == "Clean output"
    assert sanitized.error_message == "No errors"


# -- sig: mgh-6201.cd.bd955f.f2c5.c75336
