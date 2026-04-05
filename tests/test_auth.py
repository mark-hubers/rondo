# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.adapters.auth — REQ-109 reqs 035-040 KeyBackend interface.

VER-001 verification matrix: pluggable key backends, auto chain, caching.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from rondo.adapters.auth import (
    _KEY_CACHE,
    EnvBackend,
    KeyBackend,
    KeychainBackend,
    OnePasswordBackend,
    invalidate_key,
    load_api_key,
)

# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 036: KeyBackend interface
# -- ──────────────────────────────────────────────────────────────


class TestKeyBackendInterface:
    """REQ-109 req 036: abstract base with get_key method."""

    def test_keybackend_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            KeyBackend()  # type: ignore[abstract]

    def test_env_backend_is_keybackend(self) -> None:
        assert isinstance(EnvBackend(), KeyBackend)

    def test_keychain_backend_is_keybackend(self) -> None:
        assert isinstance(KeychainBackend(), KeyBackend)

    def test_onepassword_backend_is_keybackend(self) -> None:
        assert isinstance(OnePasswordBackend(), KeyBackend)


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 035: EnvBackend — env var lookup
# -- ──────────────────────────────────────────────────────────────


class TestEnvBackend:
    """REQ-109 req 035: env var is first in precedence chain."""

    def test_returns_env_var_when_set(self) -> None:
        backend = EnvBackend()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-123"}):
            assert backend.get_key("openai") == "sk-test-123"

    def test_returns_empty_when_not_set(self) -> None:
        backend = EnvBackend()
        with patch.dict("os.environ", {}, clear=True):
            assert backend.get_key("openai") == ""

    def test_returns_empty_for_unknown_provider(self) -> None:
        backend = EnvBackend()
        assert backend.get_key("unknown_provider") == ""

    def test_gemini_env_var(self) -> None:
        backend = EnvBackend()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "gem-key"}):
            assert backend.get_key("gemini") == "gem-key"

    def test_anthropic_env_var(self) -> None:
        backend = EnvBackend()
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-key"}):
            assert backend.get_key("anthropic") == "ant-key"

    def test_grok_env_var(self) -> None:
        backend = EnvBackend()
        with patch.dict("os.environ", {"XAI_API_KEY": "xai-key"}):
            assert backend.get_key("grok") == "xai-key"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 006: KeychainBackend — macOS Keychain
# -- ──────────────────────────────────────────────────────────────


class TestKeychainBackend:
    """REQ-109 req 006: keys from macOS Keychain via security command."""

    def test_returns_key_on_success(self) -> None:
        backend = KeychainBackend()
        mock_result = type("R", (), {"returncode": 0, "stdout": "my-secret-key\n"})()
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = backend.get_key("openai")
            assert result == "my-secret-key"
            args = mock_run.call_args[0][0]
            assert "ace.ai-key.openai" in args

    def test_returns_empty_on_failure(self) -> None:
        backend = KeychainBackend()
        mock_result = type("R", (), {"returncode": 44, "stdout": ""})()
        with patch("subprocess.run", return_value=mock_result):
            assert backend.get_key("openai") == ""

    def test_returns_empty_on_timeout(self) -> None:
        import subprocess as sp

        backend = KeychainBackend()
        with patch("subprocess.run", side_effect=sp.TimeoutExpired("security", 5)):
            assert backend.get_key("openai") == ""

    def test_returns_empty_when_security_missing(self) -> None:
        backend = KeychainBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert backend.get_key("openai") == ""


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 038: OnePasswordBackend — 1Password CLI
# -- ──────────────────────────────────────────────────────────────


class TestOnePasswordBackend:
    """REQ-109 req 038: keys from 1Password via op read."""

    def test_returns_key_on_success(self) -> None:
        backend = OnePasswordBackend(vault="AI Keys")
        mock_result = type("R", (), {"returncode": 0, "stdout": "op-secret\n"})()
        with patch("shutil.which", return_value="/usr/local/bin/op"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                result = backend.get_key("openai")
                assert result == "op-secret"
                args = mock_run.call_args[0][0]
                assert "op://AI Keys/openai/password" in args

    def test_returns_empty_when_op_not_installed(self) -> None:
        backend = OnePasswordBackend()
        backend._available = None
        with patch("shutil.which", return_value=None):
            assert backend.get_key("openai") == ""

    def test_returns_empty_on_op_failure(self) -> None:
        backend = OnePasswordBackend()
        mock_result = type("R", (), {"returncode": 1, "stdout": ""})()
        with patch("shutil.which", return_value="/usr/local/bin/op"):
            with patch("subprocess.run", return_value=mock_result):
                assert backend.get_key("openai") == ""

    def test_custom_vault_name(self) -> None:
        backend = OnePasswordBackend(vault="Work Keys")
        mock_result = type("R", (), {"returncode": 0, "stdout": "key\n"})()
        with patch("shutil.which", return_value="/usr/local/bin/op"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                backend.get_key("gemini")
                args = mock_run.call_args[0][0]
                assert "op://Work Keys/gemini/password" in args


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 037: Auto chain — env → keychain → 1password
# -- ──────────────────────────────────────────────────────────────


class TestAutoChain:
    """REQ-109 req 037: first non-empty value wins."""

    def setup_method(self) -> None:
        _KEY_CACHE.clear()

    def test_env_wins_over_keychain(self) -> None:
        _KEY_CACHE.clear()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            result = load_api_key("openai")
            assert result == "env-key"

    def test_keychain_used_when_no_env(self) -> None:
        _KEY_CACHE.clear()
        mock_result = type("R", (), {"returncode": 0, "stdout": "kc-key\n"})()
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", return_value=mock_result):
                result = load_api_key("openai")
                assert result == "kc-key"

    def test_returns_empty_when_all_fail(self) -> None:
        _KEY_CACHE.clear()
        mock_result = type("R", (), {"returncode": 44, "stdout": ""})()
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", return_value=mock_result):
                with patch("shutil.which", return_value=None):
                    assert load_api_key("openai") == ""


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 040: Cache with 5-minute TTL
# -- ──────────────────────────────────────────────────────────────


class TestCaching:
    """REQ-109 req 040: per-process cache with TTL + invalidation."""

    def setup_method(self) -> None:
        _KEY_CACHE.clear()

    def test_second_call_uses_cache(self) -> None:
        _KEY_CACHE.clear()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "cached-key"}):
            load_api_key("openai")
        ## Env var gone — should still return cached
        with patch.dict("os.environ", {}, clear=True):
            assert load_api_key("openai") == "cached-key"

    def test_invalidate_clears_cache(self) -> None:
        _KEY_CACHE.clear()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "old-key"}):
            load_api_key("openai")
        invalidate_key("openai")
        assert "openai" not in _KEY_CACHE

    def test_invalidate_nonexistent_is_safe(self) -> None:
        _KEY_CACHE.clear()
        invalidate_key("nonexistent")  ## Should not raise


# -- sig: mgh-6201.cd.bd955f.33a5.3551c3
