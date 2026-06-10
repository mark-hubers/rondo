# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: AuditTrail.rotate MUST degrade — never crash on no-fcntl.

VER-001 verification matrix — RONDO-372 audit rotation (cursor holistic review,
spec STD-110 req 019). The THIRD twin of the unguarded-fcntl class pinned in
test_reconcile_degradation_cursor.py (audit reconcile) and
test_breaker_save_degradation_cursor.py (CircuitBreaker._save_state).

THE BUG (observable failures this file pins):
    src/rondo/audit.py rotate() did an UNGUARDED `import fcntl` BEFORE its try
    block. rotate() is called by _maybe_rotate() on EVERY append once the jsonl
    grows past config.max_jsonl_bytes — so on Windows (no fcntl module), once the
    size threshold trips, EVERY audit record write crashes with ImportError. The
    audit trail is the permanent forensic record; making it blow up on the write
    path the moment it gets big is the worst possible failure mode. STD-110 req
    019 (MUST): where flock is unavailable (NFS/Windows) the code SHALL fall back
    to single-writer mode and emit a WARNING — never crash.

These tests assert the OBSERVABLE guarantee — appends past the threshold survive
with no ImportError escaping AND rotation actually HAPPENS in single-writer mode
(an archive file appears and the live jsonl shrinks), plus a direct rotate() on a
populated trail returns the archived line count (>0) and clears the live jsonl —
NOT any internal method name or branch shape, so any correct fix (an ImportError
guard mirroring _append_jsonl's `except (ImportError, OSError)`, or a guarded
import + single-writer fallback) satisfies them.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rondo.audit import AuditConfig, AuditTrail

# -- Block `import fcntl` exactly like a platform without the module: None in
#    sys.modules makes `import fcntl` raise ImportError (CPython import protocol).
_NO_FCNTL = {"fcntl": None}

# -- Live (un-rotated) audit log filename — STD-113.
_JSONL_NAME = "rondo_audit.jsonl"


def _trail(audit_dir: str, max_jsonl_bytes: int) -> AuditTrail:
    """Build an AuditTrail with auto_reconcile off and a chosen rotation cap."""
    return AuditTrail(
        config=AuditConfig(audit_dir=audit_dir, max_jsonl_bytes=max_jsonl_bytes),
        auto_reconcile=False,
    )


def _record_many(trail: AuditTrail, count: int) -> None:
    """Append `count` INTENT records — each append first calls _maybe_rotate()."""
    for i in range(count):
        trail.record_intent(task_name=f"t{i}", round_name="r", model="m", prompt="p")


def _archive_files(audit_dir: str) -> list[Path]:
    """Return the .jsonl archive files rotate() produces (the rotation-ran signal)."""
    archive_dir = Path(audit_dir) / "archive"
    if not archive_dir.exists():
        return []
    return sorted(archive_dir.glob("*.jsonl"))


def _live_jsonl_size(audit_dir: str) -> int:
    """Size of the live jsonl in bytes (0 if absent)."""
    live = Path(audit_dir) / _JSONL_NAME
    return live.stat().st_size if live.exists() else 0


def test_append_past_threshold_survives_when_fcntl_unimportable(tmp_path) -> None:
    """No fcntl (Windows) must NOT crash auto-rotation — appends survive + rotate.

    Block `import fcntl`, then write enough records through a TINY
    max_jsonl_bytes that _maybe_rotate() fires rotate() on the append path. On
    the buggy code the unguarded `import fcntl` in rotate() raises ImportError
    straight out of record_intent the moment the jsonl crosses the threshold. A
    correct fix degrades to single-writer mode: (a) no ImportError escapes the
    writes, and (b) rotation OBSERVABLY happened — an archive .jsonl file exists
    (the rotated records landed) and the live jsonl is smaller than the total
    written (it was emptied and only the post-rotation tail remains).
    """
    audit_dir = str(tmp_path)
    record_count = 8
    with patch.dict(sys.modules, _NO_FCNTL):
        try:
            trail = _trail(audit_dir, max_jsonl_bytes=200)
            _record_many(trail, record_count)
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"audit append crashed when fcntl is unavailable: {exc!r} — rotation on "
                f"the append path must fall back to single-writer mode (STD-110 req 019), "
                f"not propagate"
            )

    archives = _archive_files(audit_dir)
    assert archives, (
        "rotation never ran in single-writer fallback: no archive .jsonl file was "
        f"created after {record_count} appends past a 200-byte cap (STD-110 req 019 — "
        "degrade and rotate, never crash or silently skip)"
    )
    archived_bytes = sum(f.stat().st_size for f in archives)
    assert archived_bytes > 0, "archive file exists but is empty — no records were actually rotated out"
    assert _live_jsonl_size(audit_dir) < archived_bytes, (
        "live jsonl did not shrink: rotation must move the bulk of records into the "
        "archive and leave only the post-rotation tail live"
    )


def test_rotate_called_directly_archives_and_clears_when_fcntl_unimportable(tmp_path) -> None:
    """No-fcntl world: a direct rotate() must archive the lines and empty the jsonl.

    Populate a trail with a roomy cap (so the writes themselves don't auto-rotate),
    then call rotate() directly under no fcntl. On the buggy code the unguarded
    import raises ImportError out of rotate(); a correct fix degrades to
    single-writer mode and still does the work: returns the archived line count
    (>0) and removes/empties the live jsonl (STD-113 req 010 archive semantics
    preserved even without the cross-process flock).
    """
    audit_dir = str(tmp_path)
    record_count = 4
    with patch.dict(sys.modules, _NO_FCNTL):
        # -- huge cap → the appends never trip _maybe_rotate; rotate() is explicit
        trail = _trail(audit_dir, max_jsonl_bytes=10 * 1024 * 1024)
        _record_many(trail, record_count)
        try:
            archived = trail.rotate()
        except ImportError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"rotate() crashed when fcntl is unavailable: {exc!r} — it must fall "
                f"back to single-writer mode (STD-110 req 019), not propagate"
            )

    assert archived == record_count, (
        f"rotate() did not archive in single-writer fallback: expected {record_count} "
        f"lines archived, got {archived} (STD-110 req 019 — degrade, never crash)"
    )
    assert _live_jsonl_size(audit_dir) == 0, (
        "live jsonl must be gone/empty after a direct rotate(): rotation archives the "
        "content then unlinks the live log (STD-113 req 010)"
    )
    archives = _archive_files(audit_dir)
    assert archives, "rotate() reported success but produced no archive .jsonl file"


# -- sig: mgh-6201.cd.bd955f.b926.117423
