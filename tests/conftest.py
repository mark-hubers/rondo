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


# -- RONDO-300 (Finding #292): hermetic provider config. Tests must NEVER read
# -- the live ~/.rondo/config.toml — real model tiers change (alias sweep
# -- 2026-06-05 broke 23 tests that asserted live values). This is a stable
# -- snapshot of the tier names the suite was written against. Tests that need
# -- different values inject their own via load_providers_config(toml_data).
_STABLE_PROVIDERS: dict = {
    "providers": {
        "gemini": {
            "enabled": True,
            "cheap_model": "gemini-2.5-flash-lite",
            "default_model": "gemini-2.5-flash",
            "best_model": "gemini-2.5-pro",
            "trust": "trusted",
        },
        "openai": {
            "enabled": True,
            "cheap_model": "gpt-4o-mini",
            "default_model": "gpt-4.1-mini",
            "best_model": "gpt-4.1",
            "trust": "trusted",
        },
        "grok": {
            "enabled": True,
            "cheap_model": "grok-3-mini",
            "default_model": "grok-3",
            "best_model": "grok-3",
            "trust": "untrusted",
        },
        "mistral": {
            "enabled": True,
            "cheap_model": "mistral-small-latest",
            "default_model": "mistral-medium-latest",
            "best_model": "mistral-large-latest",
            "trust": "trusted",
        },
        "anthropic": {
            "enabled": True,
            "cheap_model": "claude-haiku-4-5",
            "default_model": "claude-sonnet-4-6",
            "best_model": "claude-opus-4-6",
            "trust": "trusted",
        },
    }
}


@pytest.fixture(autouse=True)
def _clean_test_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate test environment — no writes to real ~/.rondo/.

    Tests run inside Claude Code which sets CLAUDECODE.
    Preflight would abort every CLI test without this.
    RONDO_TEST_DIR redirects audit+spool to tmp (Session 93 — RONDO-28).
    RONDO-300: providers cache pre-loaded with a STABLE fixture so no test
    silently depends on the live user config. cloud/cloud_full tests are
    exempt — their whole purpose is validating the REAL config.
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

    # -- RONDO-300: hermetic by default; live-config tests keep reality
    is_live_config_test = request.node.get_closest_marker("cloud") or request.node.get_closest_marker("cloud_full")
    if not is_live_config_test:
        _p.load_providers_config(_STABLE_PROVIDERS)


# -- sig: mgh-6201.cd.bd955f.e4a1.conf01
