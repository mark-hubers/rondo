# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.spool — Rondo-REQ-101 result spool (mailbox pattern).

VER-001 verification matrix: spool write, TTL cleanup, CLI commands.
"""

import json
import os
import time

import pytest

from rondo.spool import (
    SpoolConfig,
    SpoolManager,
    spool_result,
)

# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 042 — Spool directory
# -- ──────────────────────────────────────────────────────────────


class TestSpoolDirectory:
    """REQ-101 req 042: spool directory for result files."""

    def test_spool_dir_configurable(self, tmp_path):
        """Spool path is configurable."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "custom")))
        assert "custom" in str(spool.spool_dir)

    def test_req051_auto_create(self, tmp_path):
        """Req 051: spool dir auto-created on first write."""
        spool_dir = tmp_path / "new" / "spool"
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(spool_dir)))
        spool.write_result(task_name="test", result={"status": "done"})
        assert spool_dir.exists()


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 043 — Write result JSON to spool
# -- ──────────────────────────────────────────────────────────────


class TestSpoolWrite:
    """REQ-101 req 043: write result JSON to spool directory."""

    def test_write_creates_file(self, tmp_path):
        """Writing result creates a JSON file."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="review", result={"status": "done", "output": "looks good"})
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "done"

    def test_filename_format(self, tmp_path):
        """Filename is {ISO-timestamp}-{task_name}.json."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="code-review", result={"status": "done"})
        assert "code-review" in path.name
        assert path.suffix == ".json"

    def test_multiple_results(self, tmp_path):
        """Multiple results create separate files."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done"})
        spool.write_result(task_name="t2", result={"status": "error"})
        spool.write_result(task_name="t3", result={"status": "done"})
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 3


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 046 — TTL cleanup
# -- ──────────────────────────────────────────────────────────────


class TestSpoolTTL:
    """REQ-101 req 046: TTL-based auto-cleanup."""

    def test_expired_files_cleaned(self, tmp_path):
        """Files older than TTL are removed on clean."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path), ttl_days=1))
        # -- Create an old file
        old_file = tmp_path / "2026-01-01T000000-old-task.json"
        old_file.write_text('{"status":"done"}', encoding="utf-8")
        # -- Set mtime to 10 days ago
        old_time = time.time() - (10 * 86400)
        os.utime(old_file, (old_time, old_time))
        # -- Clean
        removed = spool.clean_expired()
        assert removed == 1
        assert not old_file.exists()

    def test_fresh_files_kept(self, tmp_path):
        """Files newer than TTL are kept."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path), ttl_days=7))
        path = spool.write_result(task_name="fresh", result={"status": "done"})
        removed = spool.clean_expired()
        assert removed == 0
        assert path.exists()

    def test_clean_all(self, tmp_path):
        """--all flag removes everything."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done"})
        spool.write_result(task_name="t2", result={"status": "done"})
        removed = spool.clean_all()
        assert removed == 2
        assert len(list(tmp_path.glob("*.json"))) == 0


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 047 — List pending files
# -- ──────────────────────────────────────────────────────────────


class TestSpoolList:
    """REQ-101 req 047: list pending spool files."""

    def test_list_returns_entries(self, tmp_path):
        """List shows all pending files."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done"})
        spool.write_result(task_name="t2", result={"status": "error"})
        entries = spool.list_pending()
        assert len(entries) == 2

    def test_list_sorted_newest_first(self, tmp_path):
        """List sorted newest first."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="first", result={"status": "done"})
        time.sleep(0.01)  # -- ensure different mtime
        spool.write_result(task_name="second", result={"status": "done"})
        entries = spool.list_pending()
        assert "second" in entries[0]["filename"]

    def test_list_empty_spool(self, tmp_path):
        """Empty spool returns empty list."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        entries = spool.list_pending()
        assert entries == []


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 049 — Export since date
# -- ──────────────────────────────────────────────────────────────


class TestSpoolExport:
    """REQ-101 req 049: export spool files since date."""

    def test_export_returns_json_array(self, tmp_path):
        """Export returns list of result dicts."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done", "val": 1})
        spool.write_result(task_name="t2", result={"status": "error", "val": 2})
        exported = spool.export_since("2026-01-01")
        assert len(exported) == 2
        assert all(isinstance(e, dict) for e in exported)


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 052 — Failure resilience
# -- ──────────────────────────────────────────────────────────────


class TestSpoolResilience:
    """REQ-101 req 052: spool failure is non-fatal."""

    def test_write_to_readonly_dir_doesnt_crash(self, tmp_path):
        """Writing to unwritable dir logs warning, doesn't crash."""
        bad_dir = tmp_path / "readonly"
        bad_dir.mkdir()
        bad_dir.chmod(0o444)
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(bad_dir)))
        # -- Should not raise — returns None on failure
        path = spool.write_result(task_name="t", result={"status": "done"})
        assert path is None
        # -- Restore permissions for cleanup
        bad_dir.chmod(0o755)


# -- ──────────────────────────────────────────────────────────────
# --  Convenience function
# -- ──────────────────────────────────────────────────────────────


class TestSpoolResultFunction:
    """spool_result() convenience function."""

    def test_spool_result_writes(self, tmp_path):
        """spool_result() writes to configured dir."""
        path = spool_result(
            task_name="quick",
            result={"status": "done"},
            spool_dir=str(tmp_path),
        )
        assert path is not None
        assert path.exists()


class TestSpoolConsume:
    """REQ-101 req 044: consumers read and delete spool files (mailbox)."""

    def test_consume_returns_results(self, tmp_path):
        """Consume reads all pending results."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done", "output": "ok"})
        spool.write_result(task_name="t2", result={"status": "error", "output": "fail"})
        consumed = spool.consume_all()
        assert len(consumed) == 2
        assert all(isinstance(c, dict) for c in consumed)

    def test_consume_deletes_files(self, tmp_path):
        """After consume, spool is empty."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="t1", result={"status": "done"})
        spool.write_result(task_name="t2", result={"status": "done"})
        spool.consume_all()
        remaining = list(tmp_path.glob("*.json"))
        assert len(remaining) == 0

    def test_consume_empty_spool(self, tmp_path):
        """Empty spool returns empty list."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        consumed = spool.consume_all()
        assert consumed == []

    def test_consume_preserves_data(self, tmp_path):
        """Consumed data matches what was written."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="review", result={"status": "done", "score": 0.95})
        consumed = spool.consume_all()
        assert consumed[0]["status"] == "done"
        assert consumed[0]["score"] == 0.95

    def test_consume_one_by_filename(self, tmp_path):
        """Consume a specific file by name."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="target", result={"status": "done"})
        spool.write_result(task_name="other", result={"status": "done"})
        consumed = spool.consume_file(path.name)
        assert consumed is not None
        assert consumed["status"] == "done"
        # -- Only target consumed, other remains
        remaining = list(tmp_path.glob("*.json"))
        assert len(remaining) == 1

    def test_consume_file_rejects_path_traversal(self, tmp_path):
        """Malicious filename must not escape spool dir (finding #161)."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        spool.write_result(task_name="safe", result={"status": "done"})
        assert spool.consume_file("../../../etc/passwd") is None
        assert spool.consume_file("subdir/file.json") is None
        # -- Legitimate basename still works
        names = [p.name for p in tmp_path.glob("*.json")]
        assert len(names) == 1
        assert spool.consume_file(names[0]) is not None

    def test_write_sanitizes_task_name(self, tmp_path):
        """Backslashes, .., and separators do not create paths outside spool."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(
            task_name=r"..\..\windows\evil",
            result={"status": "done"},
        )
        assert path is not None
        assert path.parent.resolve() == tmp_path.resolve()
        assert ".." not in path.name


class TestSpoolMorningReport:
    """REQ-101: spool feeds into morning report."""

    def test_overnight_results_consumable(self, tmp_path):
        """Overnight results written to spool can be consumed next morning."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        # -- Simulate overnight writing results
        spool.write_result(
            task_name="overnight-done",
            result={
                "status": "done",
                "total_cost_usd": 0.42,
                "duration_sec": 3600,
                "phase_count": 3,
            },
        )
        # -- Morning: consume and check
        consumed = spool.consume_all()
        assert len(consumed) == 1
        assert consumed[0]["total_cost_usd"] == 0.42
        assert consumed[0]["phase_count"] == 3

    def test_multiple_overnight_runs(self, tmp_path):
        """Multiple overnight runs accumulate in spool."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        for i in range(3):
            spool.write_result(
                task_name=f"overnight-run-{i}",
                result={"status": "done", "run": i, "cost": 0.1 * (i + 1)},
            )
        consumed = spool.consume_all()
        assert len(consumed) == 3
        total_cost = sum(c["cost"] for c in consumed)
        assert total_cost == pytest.approx(0.6)


# -- ──────────────────────────────────────────────────────────────
# --  STD-107 req 006: File permissions (RONDO-55)
# -- ──────────────────────────────────────────────────────────────


class TestSpoolPermissions:
    """STD-107 req 006: spool directory 700, spool files owner-only."""

    def test_spool_dir_created_700(self, tmp_path):
        """New spool dir has owner-only permissions."""
        spool_dir = tmp_path / "new-spool"
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(spool_dir)))
        spool.write_result(task_name="t", result={"status": "done"})
        mode = spool_dir.stat().st_mode & 0o777
        assert mode == 0o700, f"Expected 700, got {oct(mode)}"

    def test_spool_files_600(self, tmp_path):
        """Spool files have owner-only read/write."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="t", result={"status": "done"})
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 600, got {oct(mode)}"


# -- ──────────────────────────────────────────────────────────────
# --  STD-107 req 004: Input validation (RONDO-55)
# -- ──────────────────────────────────────────────────────────────


class TestSpoolInputValidation:
    """STD-107 req 004+009: validate spool input before writing."""

    def test_rejects_non_dict_result(self, tmp_path):
        """Spool rejects non-dict results."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="t", result="not a dict")  # type: ignore[arg-type]
        assert path is None

    def test_rejects_empty_task_name(self, tmp_path):
        """Spool rejects empty task name."""
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        path = spool.write_result(task_name="", result={"status": "done"})
        assert path is None


# -- sig: mgh-6201.cd.bd955f.f1a4.95a4b5
