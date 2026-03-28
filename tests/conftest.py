# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared test fixtures for Rondo test suite."""

import os
import sys
from pathlib import Path

import pytest

# -- Add rondo/src to sys.path so ALL tests can import rondo
# -- This replaces the per-file sys.path.insert() in individual test files
_SRC_DIR = str(Path(__file__).parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True)
def _clean_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip CLAUDECODE from test environment.

    Tests run inside Claude Code which sets CLAUDECODE.
    Preflight would abort every CLI test without this.
    """
    monkeypatch.delenv("CLAUDECODE", raising=False)


# -- sig: mgh-6201.cd.bd955f.e4a1.conf01
