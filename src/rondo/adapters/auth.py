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
import threading
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

## -- RONDO-142 (Finding #209): tenant-scoped cache + thread safety
## -- Cache key: (provider, tenant) — prevents cross-tenant credential bleed
## -- Lock: prevents race conditions across workers
_KEY_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_KEY_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SEC = 300  # 5 minutes (REQ-109 req 040)


def _get_tenant() -> str:
    """RONDO-142: derive tenant scope from env var.

    Defaults to RONDO_TENANT env var, falls back to USER, then 'default'.
    Tenant scoping prevents one user's API key from being served to another
    user's request through the shared cache.
    """
    return os.environ.get("RONDO_TENANT") or os.environ.get("USER") or "default"


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

    RONDO-142 (Finding #209): cache is now tenant-scoped + thread-safe.
    Cache key is (provider, tenant) — one user's key never served to
    another user's request. Lock prevents race conditions across workers.
    """
    tenant = _get_tenant()
    cache_key = (provider, tenant)

    # -- Check cache first (under lock for thread safety)
    with _KEY_CACHE_LOCK:
        if cache_key in _KEY_CACHE:
            cached_key, cached_at = _KEY_CACHE[cache_key]
            if time.monotonic() - cached_at < _CACHE_TTL_SEC:
                return cached_key

    # -- Walk the chain (outside lock — backend calls can block)
    for backend in _DEFAULT_CHAIN:
        key = backend.get_key(provider)
        if key:
            with _KEY_CACHE_LOCK:
                _KEY_CACHE[cache_key] = (key, time.monotonic())
            return key

    return ""


def invalidate_key(provider: str) -> None:
    """Clear cached key for provider+tenant (e.g., after auth error).

    RONDO-142: only invalidates the current tenant's cached key.
    Other tenants' caches are untouched.
    """
    tenant = _get_tenant()
    with _KEY_CACHE_LOCK:
        _KEY_CACHE.pop((provider, tenant), None)


def invalidate_all_keys() -> None:
    """Clear ALL cached keys across all tenants. RONDO-142: for testing only."""
    with _KEY_CACHE_LOCK:
        _KEY_CACHE.clear()


# -- sig: mgh-6201.cd.bd955f.a109.d03540
