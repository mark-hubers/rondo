# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo provider adapters — REQ-109: multi-LLM dispatch.

Abstract interface + concrete adapters for different AI providers.
Adding a new provider = implement one adapter class. No other code changes.

Import direction:
    providers.py → imports engine (TaskResult only)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from rondo.engine import TaskResult

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 001: Abstract base class
# -- ──────────────────────────────────────────────────────────────


class ProviderAdapter(ABC):
    """Abstract provider adapter — REQ-109 req 001.

    Every provider implements: dispatch, health, models.
    All return TaskResult (req 004: model-agnostic output).
    """

    name: str = "base"

    @abstractmethod
    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to provider, return TaskResult."""

    @abstractmethod
    def health(self) -> bool:
        """Check if provider is reachable."""

    @abstractmethod
    def models(self) -> list[str]:
        """List available models from this provider."""


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 D6: Claude uses dispatch_task() directly.
# --  get_provider() returns None for Claude models.
# --  Callers check: if provider is not None → use adapter.dispatch()
# --                 else → use dispatch_task() (proven path, 1178 tests)
# --  Phase 2 will extract Claude transport into a real adapter.
# -- ──────────────────────────────────────────────────────────────


# -- REQ-109 req 030: OllamaAdapter moved to adapters/ollama.py (Session 94)
# -- Re-exported via top-level import for backward compatibility


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 012: Model → provider routing
# -- ──────────────────────────────────────────────────────────────

# -- Known model prefixes for routing
_CLAUDE_MODELS = {"sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"}
_OLLAMA_PREFIXES = {"llama", "qwen", "mistral", "phi", "gemma", "codellama", "deepseek"}

# -- Singleton adapter (lazy to avoid circular import)
_ollama_adapter: ProviderAdapter | None = None


def get_ollama_adapter() -> ProviderAdapter:
    """Public accessor for OllamaAdapter singleton — avoids _private import."""
    global _ollama_adapter  # noqa: PLW0603
    if _ollama_adapter is None:
        from rondo.adapters.ollama import OllamaAdapter

        _ollama_adapter = OllamaAdapter()
    return _ollama_adapter


def parse_model(model: str) -> tuple[str, str]:
    """Parse provider:model format — REQ-100 req 409.

    Returns (provider_name, model_name):
        "" + "sonnet"          → Claude
        "" + ""                → current session (inline plan)
        "local" + "llama3.1:8b" → Ollama
        "gemini" + "flash"     → future Gemini adapter
    """
    if not model:
        return "", ""
    # -- Check for provider prefix (local:model, gemini:model, etc.)
    # -- Split on first : when preceded by a known provider name
    for prefix in ("local", "gemini", "openai", "anthropic"):
        if model.startswith(f"{prefix}:"):
            return prefix, model[len(prefix) + 1 :]
    # -- No prefix → Claude model name or legacy Ollama name
    return "", model


def _get_chat_completions_adapter(provider_name: str, model_name: str) -> ProviderAdapter:
    """Create a ChatCompletionsAdapter for the given provider — lazy import."""
    from rondo.adapters.chat_completions import ChatCompletionsAdapter

    # -- Provider config: base URLs for known providers
    provider_urls = {
        "openai": "https://api.openai.com/v1",
        "grok": "https://api.x.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
    }
    base_url = provider_urls.get(provider_name, "https://api.openai.com/v1")

    # -- Try Keychain for API key
    api_key = ""
    try:
        import subprocess

        result = subprocess.run(
            ["security", "find-generic-password", "-s", f"ace2-{provider_name}", "-w"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            api_key = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # -- Fallback to env var
    if not api_key:
        import os

        env_names = {
            "openai": "OPENAI_API_KEY",
            "grok": "XAI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }
        api_key = os.environ.get(env_names.get(provider_name, ""), "")

    return ChatCompletionsAdapter(
        provider_name=provider_name,
        base_url=base_url,
        api_key=api_key,
        default_model=model_name or "gpt-4.1",
    )


def _get_anthropic_adapter(model_name: str) -> ProviderAdapter:
    """Create an AnthropicAPIAdapter — lazy import."""
    from rondo.adapters.anthropic_api import AnthropicAPIAdapter

    api_key = ""
    try:
        import subprocess

        result = subprocess.run(
            ["security", "find-generic-password", "-s", "ace2-anthropic", "-w"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            api_key = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if not api_key:
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    return AnthropicAPIAdapter(api_key=api_key, default_model=model_name or "claude-sonnet-4-6")


def _get_gemini_adapter(model_name: str) -> ProviderAdapter:
    """Create a GeminiAdapter — lazy import."""
    from rondo.adapters.gemini import GeminiAdapter

    api_key = ""
    try:
        import subprocess

        result = subprocess.run(
            ["security", "find-generic-password", "-s", "ace2-gemini", "-w"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            api_key = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if not api_key:
        import os

        api_key = os.environ.get("GEMINI_API_KEY", "")

    return GeminiAdapter(api_key=api_key, default_model=model_name or "gemini-2.5-flash")


def get_provider(model: str) -> ProviderAdapter | None:
    """Route model name to provider adapter — REQ-109 req 012, REQ-100 req 409.

    Returns None for Claude models (callers use dispatch_task directly).
    Returns OllamaAdapter for local models (callers use adapter.dispatch).
    Returns None as default for unknown models (Claude, backward compat).

    Supports provider:model prefix (local:llama3.1:8b) and legacy prefix matching.
    """
    # -- New: provider prefix routing (REQ-100 req 409)
    provider_name, model_name = parse_model(model)
    if provider_name == "local":
        return get_ollama_adapter()
    if provider_name in ("openai", "grok", "mistral"):
        return _get_chat_completions_adapter(provider_name, model_name)
    if provider_name == "gemini":
        return _get_gemini_adapter(model_name)
    if provider_name == "anthropic":
        return _get_anthropic_adapter(model_name)

    # -- Claude models
    if model_name in _CLAUDE_MODELS or not model_name:
        return None

    # -- Legacy: Ollama prefix matching (backward compat)
    import re

    model_base = re.sub(r"[\d.:]+.*$", "", model_name.split("-")[0].lower())
    if model_base in _OLLAMA_PREFIXES:
        return get_ollama_adapter()

    # -- Default: Claude (backward compat)
    return None


# -- ──────────────────────────────────────────────────────────────
# --  Task type → model recommendation — REQ-109 D9, req 028
# -- ──────────────────────────────────────────────────────────────

# -- Default model map (used when no TOML config overrides)
_DEFAULT_TASK_MODELS: dict[str, str] = {
    "code-review": "qwen2.5-coder:7b",
    "code-fix": "qwen2.5-coder:7b",
    "code-generate": "qwen2.5-coder:7b",
    "reasoning": "deepseek-r1:8b",
    "math": "deepseek-r1:8b",
    "logic": "deepseek-r1:8b",
    "classify": "llama3.1:8b",
    "scan": "llama3.1:8b",
    "filter": "llama3.1:8b",
    "structured-json": "phi4:14b",
    "extract": "phi4:14b",
    "summarize": "gemma3:12b",
    "general": "qwen2.5:32b",
    "research": "qwen2.5:32b",
    "analysis": "qwen2.5:32b",
}

# -- Config-loaded overrides (populated by load_task_models)
_task_model_overrides: dict[str, str] = {}


def load_task_models(config_path: str = "") -> dict[str, str]:
    """Load task→model map from TOML config — REQ-109 req 028.

    COALESCE: config file → defaults. Config wins for any key it specifies.
    Reads [routing.task_models] section from ~/.rondo/config.toml or given path.
    """
    global _task_model_overrides  # noqa: PLW0603
    import tomllib
    from pathlib import Path

    path = Path(config_path) if config_path else Path.home() / ".rondo" / "config.toml"
    if path.is_file():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            routing = data.get("routing", {})
            overrides = routing.get("task_models", {})
            if isinstance(overrides, dict):
                _task_model_overrides = {k: str(v) for k, v in overrides.items()}
        except (tomllib.TOMLDecodeError, OSError):
            pass

    # -- Return merged: overrides win over defaults
    merged = {**_DEFAULT_TASK_MODELS, **_task_model_overrides}
    return merged


def recommend_model(task_type: str) -> str:
    """Recommend the best model for a task type — REQ-109 req 028.

    COALESCE: config override → default map → 'sonnet' fallback.
    Config is loaded from ~/.rondo/config.toml [routing.task_models].
    """
    key = task_type.lower()
    # -- Check overrides first, then defaults, then Claude fallback
    if key in _task_model_overrides:
        return _task_model_overrides[key]
    return _DEFAULT_TASK_MODELS.get(key, "sonnet")


# -- sig: mgh-6201.cd.bd955f.a109.b10901
