# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""API key loading — pluggable backend with auto-fallback chain.

REQ-109 reqs 035-040: KeyBackend interface with 3 implementations.
Precedence (auto mode): env var → macOS Keychain → 1Password CLI.
First non-empty value wins. Keys never cached longer than 5 minutes.

Keychain service: ace.ai-key.{provider} (set via ai-keys.py)
1Password: op://AI Keys/{provider}/password (if configured)
Per CORE-STD-008: keys in macOS Keychain only, never in files or git.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

## -- Provider → env var name mapping (matches ai_review.py)
_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
}

## -- Per-process cache: provider → (key, timestamp)
_KEY_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SEC = 300  # 5 minutes (REQ-109 req 040)


# ═══════════════════════════════════════════════════════════════
# KeyBackend interface (REQ-109 req 036)
# ═══════════════════════════════════════════════════════════════


class KeyBackend(ABC):
    """Abstract base for key retrieval backends."""

    @abstractmethod
    def get_key(self, provider: str) -> str:
        """Retrieve API key for a provider. Returns empty string if not found."""


class EnvBackend(KeyBackend):
    """Load keys from environment variables."""

    def get_key(self, provider: str) -> str:
        """Check env var for provider key."""
        env_var = _ENV_MAP.get(provider, "")
        if env_var:
            return os.environ.get(env_var, "")
        return ""


class KeychainBackend(KeyBackend):
    """Load keys from macOS Keychain via security command."""

    def get_key(self, provider: str) -> str:
        """Query macOS Keychain for ace.ai-key.{provider}."""
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    f"ace.ai-key.{provider}",
                    "-a",
                    "markhubers",
                    "-w",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("Keychain lookup failed for %s", provider)
        return ""


class OnePasswordBackend(KeyBackend):
    """Load keys from 1Password CLI (op read).

    Requires: op binary on PATH + authenticated session.
    REQ-109 req 038: use op read "op://vault/item/password".
    """

    def __init__(self, vault: str = "AI Keys") -> None:
        self.vault = vault
        self._available: bool | None = None

    def _is_available(self) -> bool:
        """Check if op CLI is installed and authenticated."""
        if self._available is not None:
            return self._available
        self._available = shutil.which("op") is not None
        return self._available

    def get_key(self, provider: str) -> str:
        """Read key from 1Password vault."""
        if not self._is_available():
            return ""
        try:
            result = subprocess.run(
                ["op", "read", f"op://{self.vault}/{provider}/password"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("1Password lookup failed for %s", provider)
        return ""


# ═══════════════════════════════════════════════════════════════
# Auto chain (REQ-109 req 037)
# ═══════════════════════════════════════════════════════════════

## Default backend chain: env → keychain → 1password
_DEFAULT_CHAIN: list[KeyBackend] = [
    EnvBackend(),
    KeychainBackend(),
    OnePasswordBackend(),
]


def load_api_key(provider: str) -> str:
    """Load API key using backend chain: env → Keychain → 1Password.

    REQ-109 req 035: first non-empty value wins.
    REQ-109 req 040: cached per-process with 5-minute TTL.
    Cache invalidated if key fails (caller should call invalidate_key).
    """
    ## Check cache first
    if provider in _KEY_CACHE:
        cached_key, cached_at = _KEY_CACHE[provider]
        if time.monotonic() - cached_at < _CACHE_TTL_SEC:
            return cached_key

    ## Walk the chain
    for backend in _DEFAULT_CHAIN:
        key = backend.get_key(provider)
        if key:
            _KEY_CACHE[provider] = (key, time.monotonic())
            return key

    return ""


def invalidate_key(provider: str) -> None:
    """Clear cached key for provider (e.g., after auth error)."""
    _KEY_CACHE.pop(provider, None)


# -- sig: mgh-6201.cd.bd955f.a109.d03540
