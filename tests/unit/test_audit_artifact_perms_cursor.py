# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""ROAD-TO-8 item 8.3 regression: audit artifacts MUST be born 0o600 (STD-110 r012).

VER-001 verification matrix: audit/result artifact birth-permission contract.

Re-score finding R3 (reports/cursor-reviews/review-20260610-164750.md) flagged that
audit + result artifacts are NOT born locked-down — they hit disk at the process
umask (typically 0o644/0o666) and are either left wide (atomic_write, audit JSONL)
or only narrowed AFTER the full payload already sat readable (save_result's
write-then-chmod window). spool.py:165's mkstemp pattern is the model: files BORN
0o600, never chmod-after-write.

The contract these tests pin (the worst-case umask 0o000 reveals it):
    (a) atomic_write — the final file is 0o600 AND no instant during the write
        exposes wider perms (the temp itself is born 0o600).
    (b) the audit JSONL — when created by the first append, is 0o600.
    (c) save_result — its file is born 0o600, with NO write-then-chmod window;
        a no-op chmod monkeypatch proves the mode does not DEPEND on a post-write
        chmod (born right, not narrowed-after).
    (d) POSIX-only — perm assertions skip on non-posix.
    (e) behavior preserved — atomic_write stays atomic (os.replace + tmp cleanup),
        append still appends, save_result content unchanged.

Expected against TODAY's code: tests 1, 2, 3 FAIL (born at umask), test 4 FAILS on
the mechanism pin (relies on post-write chmod), tests 5, 6 PASS (behavior holds).
"""

import json
import os
import stat
from pathlib import Path

import pytest

import rondo.audit as audit_mod
from rondo.audit import AuditConfig, AuditTrail, atomic_write
from rondo.dispatch import save_result
from rondo.engine import DispatchUsage, TaskResult

# -- (d) the birth-permission claims are POSIX mode bits; Windows has no umask
# -- semantics worth asserting here, so the perm tests skip cleanly there.
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file-mode birth contract")

_PERM_MASK = 0o777


def _mode(path: Path) -> int:
    """Return the permission bits (& 0o777) of a path's current stat."""
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def permissive_umask() -> "object":
    """Set a fully permissive umask (0o000) for the test, always restored.

    Under umask 0 a umask-dependent open yields 0o666/0o644, which KILLS any
    born-at-umask implementation; a born-0o600 writer (mkstemp / os.open with
    mode 0o600) yields 0o600 regardless of umask, so it survives.
    """
    old = os.umask(0o000)
    try:
        yield
    finally:
        os.umask(old)


# -- ──────────────────────────────────────────────────────────────
# --  1. atomic_write — final file born 0o600 (MUST FAIL today)
# -- ──────────────────────────────────────────────────────────────


@posix_only
def test_atomic_write_file_born_0600(tmp_path: Path, permissive_umask: object) -> None:
    """Under umask 0, atomic_write's final file is 0o600, not the umask default."""
    # -- today: tmp_path.write_text births 0o666 and os.replace carries it across.
    target = tmp_path / "artifact.txt"
    atomic_write(target, "prompt-payload")
    assert _mode(target) == 0o600, oct(_mode(target))


# -- ──────────────────────────────────────────────────────────────
# --  2. atomic_write — the TEMP is never wider than 0o600 (MUST FAIL today)
# -- ──────────────────────────────────────────────────────────────


@posix_only
def test_atomic_write_tmp_never_wider(
    tmp_path: Path, permissive_umask: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp file handed to os.replace is already 0o600 — no wide-perm window.

    Capturing the temp's mode at the instant of the rename (then performing the
    real replace) proves the payload was never readable by group/other, not even
    transiently. Today the temp is born at umask (0o666) -> this fails.
    """
    target = tmp_path / "windowed.txt"
    real_replace = audit_mod.os.replace
    captured: dict[str, int] = {}

    def spy_replace(src: str, dst: str) -> None:
        captured["tmp_mode"] = _mode(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr(audit_mod.os, "replace", spy_replace)
    atomic_write(target, "secret-in-flight")

    assert "tmp_mode" in captured, "os.replace was never called — atomicity lost"
    assert captured["tmp_mode"] == 0o600, oct(captured["tmp_mode"])


# -- ──────────────────────────────────────────────────────────────
# --  3. audit JSONL — created 0o600 on first append (MUST FAIL today)
# -- ──────────────────────────────────────────────────────────────


@posix_only
def test_audit_jsonl_created_0600(tmp_path: Path, permissive_umask: object) -> None:
    """The audit JSONL, born on the first record_intent append, is 0o600."""
    # -- explicit audit_dir (not RONDO_TEST_DIR) so the path is fully ours.
    audit_dir = tmp_path / "audit"
    trail = AuditTrail(config=AuditConfig(audit_dir=str(audit_dir)), auto_reconcile=False)
    trail.record_intent(task_name="t", round_name="r", model="m", prompt="p")

    jsonl = audit_dir / "rondo_audit.jsonl"
    assert jsonl.exists(), "first append did not create the JSONL"
    # -- today: open("a") births the file at umask (0o666) -> this fails.
    assert _mode(jsonl) == 0o600, oct(_mode(jsonl))


# -- ──────────────────────────────────────────────────────────────
# --  4. save_result — born 0o600, NOT narrowed-after (MUST FAIL today)
# -- ──────────────────────────────────────────────────────────────


@posix_only
def test_save_result_born_0600_no_window(
    tmp_path: Path, permissive_umask: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save_result's file is 0o600 by BIRTH — it must not depend on a post-write chmod.

    Mechanism pin: Path.chmod is monkeypatched to a recording NO-OP. A born-0o600
    writer (mkstemp / os.open) is 0o600 regardless of chmod; today's code
    (write_text then chmod 0o600) births 0o666 under umask 0 and, with chmod
    neutralised, STAYS 0o666 -> this fails. Pinning the mechanism (not just the
    final mode) is required precisely because a real chmod would mask the birth.
    """
    chmod_calls: list[tuple[str, int]] = []
    real_chmod = Path.chmod

    def recording_noop_chmod(self: Path, mode: int, *args: object, **kwargs: object) -> None:
        chmod_calls.append((str(self), mode))
        # -- deliberately do NOT apply: this neutralises any narrow-after-write.

    monkeypatch.setattr(Path, "chmod", recording_noop_chmod)

    result = TaskResult(task_name="cursor-perm-task", status="done", raw_output="payload-bytes")
    out = save_result(result, DispatchUsage(), str(tmp_path))

    # -- keep `real_chmod` referenced so the unused-binding lint stays quiet while
    # -- documenting that we swapped the genuine implementation out on purpose.
    assert real_chmod is not recording_noop_chmod
    out_path = Path(out)
    assert out_path.is_file()
    assert _mode(out_path) == 0o600, (oct(_mode(out_path)), chmod_calls)


# -- ──────────────────────────────────────────────────────────────
# --  5. atomic_write — still atomic + correct (MUST PASS today)
# -- ──────────────────────────────────────────────────────────────


def test_atomic_write_still_atomic_and_correct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Content round-trips, no temp is left behind, and a failed write is rolled back."""
    target = tmp_path / "doc.txt"

    # -- happy path: exact round-trip and zero leftover temp files.
    atomic_write(target, "new-content")
    assert target.read_text(encoding="utf-8") == "new-content"
    assert list(tmp_path.glob("*.tmp")) == [], "a temp file leaked after success"

    # -- failure path: os.replace raises mid-write -> old content survives, no leak.
    target.write_text("old-content", encoding="utf-8")

    def boom(_src: str, _dst: str) -> None:
        raise OSError("forced replace failure")

    monkeypatch.setattr(audit_mod.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write(target, "doomed-content")

    assert target.read_text(encoding="utf-8") == "old-content"
    assert list(tmp_path.glob("*.tmp")) == [], "a temp file leaked after failure"


# -- ──────────────────────────────────────────────────────────────
# --  6. audit JSONL — still appends (MUST PASS today)
# -- ──────────────────────────────────────────────────────────────


def test_append_jsonl_still_appends(tmp_path: Path) -> None:
    """Two recorded intents produce exactly two parseable JSONL lines (append, not clobber)."""
    audit_dir = tmp_path / "audit"
    trail = AuditTrail(config=AuditConfig(audit_dir=str(audit_dir)), auto_reconcile=False)
    trail.record_intent(task_name="t1", round_name="r", model="m", prompt="p1")
    trail.record_intent(task_name="t2", round_name="r", model="m", prompt="p2")

    jsonl = audit_dir / "rondo_audit.jsonl"
    lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    records = [json.loads(ln) for ln in lines]
    assert [r["task_name"] for r in records] == ["t1", "t2"]


# -- sig: mgh-6201.cd.bd955f.7882.602bab
