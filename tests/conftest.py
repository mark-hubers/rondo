# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared test fixtures for Rondo test suite."""

import sys
from pathlib import Path

import pytest

# -- Add rondo/src to sys.path so ALL tests can import rondo
# -- This replaces the per-file sys.path.insert() in individual test files
_SRC_DIR = str(Path(__file__).parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture(autouse=True)
def _clean_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate test environment — no writes to real ~/.rondo/.

    Tests run inside Claude Code which sets CLAUDECODE.
    Preflight would abort every CLI test without this.
    RONDO_TEST_DIR redirects audit+spool to tmp (Session 93 — RONDO-28).
    """
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    # -- Clear preflight cache between tests (RONDO-60)
    from rondo.preflight import _preflight_cache

    _preflight_cache.clear()

    # -- Clear config + provider caches between tests (Session 97)
    from rondo.config import reset_rondo_config

    reset_rondo_config()

    import rondo.providers as _p

    _p._providers_config.clear()
    _p._providers_loaded = False
    _p._task_model_overrides.clear()
    _p._task_models_loaded = False


# -- sig: mgh-6201.cd.bd955f.e4a1.conf01
