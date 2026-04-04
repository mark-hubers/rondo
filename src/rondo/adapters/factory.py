# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Adapter factory — single construction point for all provider adapters.

DRY: replaces 4+ duplicate `if provider == "gemini": GeminiAdapter(...)` blocks.
Imports: factory.py → adapters + auth + config. Does NOT import providers.py.

Usage:
    from rondo.adapters.factory import get_adapter

    adapter = get_adapter("gemini", "gemini-2.5-flash")
    if adapter:
        result = adapter.dispatch(prompt="...", model="gemini-2.5-flash")
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

## -- Provider → base URL mapping (hardcoded defaults, config override in phase 2)
_PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
}


def get_adapter(provider: str, model: str = "") -> object | None:
    """Return a configured adapter instance for the given provider.

    Loads API key from auth chain (env → keychain → 1password).
    Returns None if no key available or unknown provider.

    Args:
        provider: Provider name (gemini, openai, grok, mistral, anthropic, local).
        model: Default model for the adapter.

    Returns:
        Configured adapter instance, or None.
    """
    from rondo.adapters.auth import load_api_key  # pylint: disable=import-outside-toplevel

    if provider == "local":
        from rondo.adapters.ollama import OllamaAdapter  # pylint: disable=import-outside-toplevel

        return OllamaAdapter()

    key = load_api_key(provider)
    if not key:
        logger.debug("No API key for provider '%s'", provider)
        return None

    if provider == "gemini":
        from rondo.adapters.gemini import GeminiAdapter  # pylint: disable=import-outside-toplevel

        return GeminiAdapter(api_key=key, default_model=model or "gemini-2.5-flash")

    if provider in ("openai", "grok", "mistral"):
        from rondo.adapters.chat_completions import ChatCompletionsAdapter  # pylint: disable=import-outside-toplevel

        base_url = _PROVIDER_URLS.get(provider, "")
        if not base_url:
            logger.warning("No base_url for provider '%s'", provider)
            return None
        return ChatCompletionsAdapter(
            provider_name=provider,
            base_url=base_url,
            api_key=key,
            default_model=model,
        )

    if provider == "anthropic":
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter  # pylint: disable=import-outside-toplevel

        return AnthropicAPIAdapter(api_key=key, default_model=model or "claude-sonnet-4-6")

    logger.debug("Unknown provider: '%s'", provider)
    return None


# -- sig: mgh-6201.cd.bd955f.a109.fac001
