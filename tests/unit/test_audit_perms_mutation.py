# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation kill-tests for audit.py file/dir PERMISSIONS — security-critical.

VER-001: Product acceptance / audit artifact permission contract (STD-110 r012).

WHY: a mutation sweep (bin/mutate, 2026-06-12) showed audit.py at 47/133 — a
weak spot. Among the survivors were the OCTAL PERMISSION constants: the audit
DIRECTORY mode (0o700) and the rotation ARCHIVE file mode (0o600). The existing
perms test pins the live-JSONL/atomic_write FILE modes but NOT the directory
mode or the archive — so a mutant widening the audit dir to 0o777 (world-readable
audit records — every dispatched prompt, every secret-bearing payload) would pass.

This is a security pin: audit artifacts hold sensitive dispatch data and MUST be
owner-only. Modes verified live before asserting. (This is one cluster of a
larger audit.py mutation backlog — see the session report.)
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from rondo.audit import AuditConfig, AuditTrail, resolve_audit_dir


@pytest.fixture
def _trail(tmp_path: Path, monkeypatch) -> AuditTrail:
    """An AuditTrail rooted in a throwaway dir (RONDO_TEST_DIR), no auto-reconcile."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    return AuditTrail(config=AuditConfig(), auto_reconcile=False)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_audit_dir_is_owner_only(_trail: AuditTrail) -> None:
    """The audit directory is 0o700 — no group/other access (kills the L329/564 dir-mode 0o700)."""
    _trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
    audit_dir = resolve_audit_dir()
    mode = _mode(audit_dir)
    # -- a 0o777/0o755 mutant would set group/other bits; owner-only means those are clear
    assert mode & 0o077 == 0, f"audit dir {audit_dir} is not owner-only: {oct(mode)}"
    assert mode & 0o700 == 0o700  # -- owner still has full access


def test_rotated_archive_dir_and_file_are_owner_only(_trail: AuditTrail) -> None:
    """Rotation's archive dir is 0o700 and the archive file is 0o600 (kills L585 dir + L591 file)."""
    _trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")
    archived = _trail.rotate()
    assert archived >= 1, "expected at least one record to be archived"

    archive_dir = resolve_audit_dir() / "archive"
    assert archive_dir.exists(), "rotation did not create the archive dir"
    assert _mode(archive_dir) & 0o077 == 0, "archive dir is not owner-only"

    archive_files = list(archive_dir.glob("*.jsonl"))
    assert archive_files, "rotation did not write an archive file"
    for f in archive_files:
        mode = _mode(f)
        # -- archive holds the same sensitive records as the live JSONL -> must be 0o600
        assert mode & 0o077 == 0, f"archive file {f} is not owner-only: {oct(mode)}"
        assert mode & 0o600 == 0o600


# -- sig: mgh-6201.cd.bd955f.a445.3dfa73
