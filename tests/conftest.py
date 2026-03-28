# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared test fixtures for Rondo test suite."""

import os

import pytest


@pytest.fixture(autouse=True)
def _clean_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip CLAUDECODE from test environment.

    Tests run inside Claude Code which sets CLAUDECODE.
    Preflight would abort every CLI test without this.
    """
    monkeypatch.delenv("CLAUDECODE", raising=False)


# -- sig: mgh-6201.cd.bd955f.e4a1.conf01
