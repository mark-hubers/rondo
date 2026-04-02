# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""API key loading — shared by all provider adapters.

REQ-109 req 034: Keychain-first, env var fallback.
Matches ai_review.py key loading pattern (same Keychain service names).
Per CORE-STD-008: keys in macOS Keychain only, never in files or git.

Keychain service: ace.ai-key.{provider} (set via ai-keys.py)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# -- Provider → env var name mapping (matches ai_review.py)
_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
}


def load_api_key(provider: str) -> str:
    """Load API key: env var first, then macOS Keychain.

    Matches ai_review.py's _load_key_from_keychain pattern so both tools
    use the same keys stored via ai-keys.py.
    """
    # -- Check env var first
    env_var = _ENV_MAP.get(provider, "")
    if env_var:
        val = os.environ.get(env_var, "")
        if val:
            return val

    # -- Fall back to Keychain (same service name as ai-keys.py)
    try:
        import subprocess

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
        pass

    return ""


# -- sig: mgh-6201.cd.bd955f.a109.d03401
