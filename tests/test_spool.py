# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.spool — Rondo-REQ-101 result spool (mailbox pattern).

VER-001 verification matrix: spool write, TTL cleanup, CLI commands.
"""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
        """req 051: spool dir auto-created on first write."""
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


# -- sig: mgh-6201.cd.bd955f.f1a4.95a4b5
