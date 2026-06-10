# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Spool missing-dir contracts — RONDO-384 residue (Claude-authored top-up).

VER-001 verification matrix: spool empty-state contract.

The Cursor-authored test_spool_contracts_cursor.py killed 32 of spool's 36
surviving mutants; these two pin the last REAL pair — the missing-dir early
returns. CLI spool commands call these directly: a None where 0/[] is promised
would crash the front door. (The one remaining survivor after this file,
json indent=2, is a cosmetic equivalent mutant — skipped deliberately.)
"""

from __future__ import annotations

from pathlib import Path

from rondo.spool import SpoolConfig, SpoolManager


def _absent_dir_manager(tmp_path: Path) -> SpoolManager:
    """A SpoolManager pointed at a directory that does not exist."""
    return SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "never-created")))


def test_clean_all_missing_dir_returns_zero(tmp_path: Path) -> None:
    """clean_all on an absent spool dir returns 0 — never None, never raises."""
    assert _absent_dir_manager(tmp_path).clean_all() == 0


def test_consume_all_missing_dir_returns_empty_list(tmp_path: Path) -> None:
    """consume_all on an absent spool dir returns [] — never None, never raises."""
    assert _absent_dir_manager(tmp_path).consume_all() == []


# -- sig: mgh-6201.cd.bd955f.ac3b.76c45c
