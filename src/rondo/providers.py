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

# -- REQ-109 reqs 041-045: Provider tiers
_TIER_NAMES = {"high", "default", "low"}
_TIER_MAP = {"high": "best_model", "default": "default_model", "low": "cheap_model"}

## Cached provider config from TOML (populated by load_providers_config)
_providers_config: dict[str, dict[str, str]] = {}
_providers_loaded: bool = False


def load_providers_config(toml_data: dict | None = None) -> None:
    """Load [providers] section from TOML into tier resolution cache.

    Called at startup (CLI main, MCP server create).
    Behavior:
    - toml_data provided: merges into cache (additive, does not remove keys).
    - toml_data=None: reads ~/.rondo/config.toml ONCE (one-shot, not hot-reload).
    - Missing config file: empty config, no error — hardcoded defaults used.
    - Second call without toml_data: no-op (already loaded from file).
    """
    global _providers_config, _providers_loaded  # noqa: PLW0603
    if toml_data is not None:
        _providers_config.update(toml_data.get("providers", {}))
        _providers_loaded = True
        return
    if _providers_loaded:
        return
    ## Load from default config path
    from pathlib import Path

    config_path = Path.home() / ".rondo" / "config.toml"
    if config_path.is_file():
        import tomllib

        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        _providers_config.update(data.get("providers", {}))
    _providers_loaded = True


def resolve_tier(provider: str, tier: str) -> str:
    """Resolve provider:tier → actual model name from config.

    REQ-109 req 042: gemini:high → [providers.gemini].best_model
    REQ-109 req 043: exact model name beats tier (caller checks first).
    Returns empty string if provider/tier not configured.
    """
    provider_cfg = _providers_config.get(provider, {})
    config_key = _TIER_MAP.get(tier, "")
    if config_key:
        return provider_cfg.get(config_key, "")
    return ""


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
    """Parse provider:model format with tier resolution — REQ-100 req 409, REQ-109 reqs 041-045.

    Returns (provider_name, model_name):
        "" + "sonnet"              → Claude
        "" + ""                    → current session (inline plan)
        "local" + "llama3.1:8b"   → Ollama
        "gemini" + "flash"         → Gemini (exact model)
        "gemini" + "gemini-2.5-pro" → Gemini (tier resolved: gemini:high)

    Tier resolution (REQ-109 req 042-043):
        provider:high   → best_model from config
        provider:low    → cheap_model from config
        provider:default → default_model from config
        provider:flash  → exact model (not a tier — exact beats tier)
    """
    if not model:
        return "", ""
    # -- Check for provider prefix (local:model, gemini:model, etc.)
    # -- Split on first : when preceded by a known provider name
    for prefix in ("local", "gemini", "openai", "anthropic", "grok", "mistral"):
        if model.startswith(f"{prefix}:"):
            model_part = model[len(prefix) + 1 :]
            # -- REQ-109 req 042: check if model_part is a tier name
            if model_part in _TIER_NAMES:
                resolved = resolve_tier(prefix, model_part)
                if resolved:
                    return prefix, resolved
                # -- Tier not configured — fall through with tier as model name
                logger.warning("Tier '%s' not configured for provider '%s'", model_part, prefix)
            return prefix, model_part
    # -- No prefix → Claude model name or legacy Ollama name
    return "", model


def _get_chat_completions_adapter(provider_name: str, model_name: str) -> ProviderAdapter:
    """Create a ChatCompletionsAdapter for the given provider — lazy import."""
    from rondo.adapters.auth import load_api_key
    from rondo.adapters.chat_completions import ChatCompletionsAdapter

    provider_urls = {
        "openai": "https://api.openai.com/v1",
        "grok": "https://api.x.ai/v1",
        "mistral": "https://api.mistral.ai/v1",
    }

    return ChatCompletionsAdapter(
        provider_name=provider_name,
        base_url=provider_urls.get(provider_name, "https://api.openai.com/v1"),
        api_key=load_api_key(provider_name),
        default_model=model_name or "gpt-4.1",
    )


def _get_anthropic_adapter(model_name: str) -> ProviderAdapter:
    """Create an AnthropicAPIAdapter — lazy import."""
    from rondo.adapters.anthropic_api import AnthropicAPIAdapter
    from rondo.adapters.auth import load_api_key

    return AnthropicAPIAdapter(
        api_key=load_api_key("anthropic"),
        default_model=model_name or "claude-sonnet-4-6",
    )


def _get_gemini_adapter(model_name: str) -> ProviderAdapter:
    """Create a GeminiAdapter — lazy import."""
    from rondo.adapters.auth import load_api_key
    from rondo.adapters.gemini import GeminiAdapter

    api_key = load_api_key("gemini")

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
# -- REQ-109 D9: cloud-first — Gemini mid-tier (flash) for daily work; Mistral for security (contrarian).
# -- OpenAI is not a default here; override [routing.task_models] if you want it.
_DEFAULT_TASK_MODELS: dict[str, str] = {
    "code-review": "gemini:gemini-2.5-flash",
    "code-fix": "gemini:gemini-2.5-flash",
    "code-generate": "gemini:gemini-2.5-flash",
    "reasoning": "gemini:gemini-2.5-flash",
    "math": "gemini:gemini-2.5-flash",
    "logic": "gemini:gemini-2.5-flash",
    "classify": "llama3.1:8b",
    "scan": "llama3.1:8b",
    "filter": "llama3.1:8b",
    "structured-json": "gemini:gemini-2.5-flash",
    "extract": "gemini:gemini-2.5-flash",
    "summarize": "gemini:gemini-2.5-flash",
    "general": "gemini:gemini-2.5-flash",
    "research": "gemini:gemini-2.5-flash",
    "analysis": "gemini:gemini-2.5-flash",
    "security": "mistral:mistral-large-latest",
}

# -- REQ-109 reqs 021-023: multi-provider defaults — Gemini + Grok + Mistral (no OpenAI in defaults).
# -- Single-model tasks are "mid" (flash); use provider:high / rondo_cloud tier=high for Opus-like depth.
_DEFAULT_MULTI_REVIEW: dict[str, list[str]] = {
    "code-review": ["gemini:gemini-2.5-flash", "grok:grok-3"],
    "security": ["gemini:gemini-2.5-flash", "grok:grok-3", "mistral:mistral-large-latest"],
    "analysis": ["gemini:gemini-2.5-flash", "grok:grok-3"],
    "research": ["gemini:gemini-2.5-flash", "grok:grok-3"],
    # -- Deep cognitive pair — gemini-2.5-pro ≈ doc shorthand "gemini:pro"; mistral large = third-body perspective
    "reasoning": ["gemini:gemini-2.5-pro", "mistral:mistral-large-latest"],
}

# -- Config-loaded multi-review overrides
_multi_review_overrides: dict[str, list[str]] = {}

# -- Config-loaded overrides (populated by load_task_models)
_task_model_overrides: dict[str, str] = {}


_task_models_loaded: bool = False


def load_task_models(config_path: str = "") -> dict[str, str]:
    """Load task→model map from TOML config — REQ-109 req 028.

    COALESCE: config file → defaults. Config wins for any key it specifies.
    Reads [routing.task_models] section from ~/.rondo/config.toml or given path.
    Called at startup (CLI, MCP) and idempotent.
    """
    global _task_model_overrides, _task_models_loaded  # noqa: PLW0603
    if _task_models_loaded and not config_path:
        merged = {**_DEFAULT_TASK_MODELS, **_task_model_overrides}
        return merged
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
            # -- REQ-109 reqs 021-023: multi-review provider lists
            multi = routing.get("multi_review", {})
            if isinstance(multi, dict):
                for k, v in multi.items():
                    if isinstance(v, list):
                        _multi_review_overrides[k] = [str(x) for x in v]
        except (tomllib.TOMLDecodeError, OSError):
            pass

    _task_models_loaded = True
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


def recommend_review_providers(task_type: str, count: int = 2) -> list[str]:
    """Recommend multiple cloud providers for review tasks — REQ-109 reqs 021-023.

    Returns up to `count` provider:model strings for multi-AI review.
    COALESCE: config [routing.multi_review] → defaults → single recommend_model fallback.

    Args:
        task_type: Task category (code-review, security, analysis, etc.).
        count:     Max providers to return (default 2, more if requested).

    Returns:
        List of provider:model strings, e.g. ['gemini:gemini-2.5-flash', 'grok:grok-3'].
    """
    key = task_type.lower()
    # -- Config overrides win (req 024: manual override always wins)
    if key in _multi_review_overrides:
        return _multi_review_overrides[key][:count]
    # -- Default multi-review list
    if key in _DEFAULT_MULTI_REVIEW:
        return _DEFAULT_MULTI_REVIEW[key][:count]
    # -- Fallback: single model recommendation as a list
    return [recommend_model(key)]


# -- ──────────────────────────────────────────────────────────────
# --  Fallback chain — REQ-109 reqs 015, 016, 019
# -- ──────────────────────────────────────────────────────────────


def _get_fallback_provider(provider_name: str) -> str | None:
    """Return configured fallback provider name, or None if not set.

    REQ-109 req 015: reads [providers.<name>] fallback from config.toml.
    """
    try:
        import tomllib
        from pathlib import Path

        path = Path.home() / ".rondo" / "config.toml"
        if not path.is_file():
            return None
        with open(path, "rb") as f:
            data = tomllib.load(f)
        provider_cfg = data.get("providers", {}).get(provider_name, {})
        fallback = provider_cfg.get("fallback", "")
        return str(fallback) if fallback else None
    except (OSError, KeyError, TypeError):
        return None


def get_provider_with_fallback(model: str) -> tuple[object | None, str]:
    """Route to provider adapter with health check + fallback — REQ-109 reqs 015, 016, 019.

    Checks if primary provider is healthy. If down, uses configured fallback.
    REQ-109 req 016: NEVER falls back to Claude interactive (returns None).

    Args:
        model: Provider:model string (e.g. 'gemini:gemini-2.5-flash', 'grok:grok-3').

    Returns:
        (adapter, model_string) — adapter is None if no healthy provider found.
    """
    from rondo.adapters.health import is_provider_healthy  # pylint: disable=import-outside-toplevel

    provider_name, model_name = parse_model(model)

    # -- No provider prefix → Claude path, not handled here
    if not provider_name:
        return get_provider(model), model

    # -- Check primary provider health
    if is_provider_healthy(provider_name):
        adapter = get_provider(model)
        return adapter, model

    # -- REQ-109 req 019: log WARNING, try fallback
    logger.warning("Provider '%s' is unhealthy — trying fallback", provider_name)

    fallback_name = _get_fallback_provider(provider_name)
    if fallback_name:
        fallback_model = f"{fallback_name}:{model_name}" if model_name else fallback_name
        if is_provider_healthy(fallback_name):
            adapter = get_provider(fallback_model)
            logger.info("Using fallback provider '%s' for '%s'", fallback_name, provider_name)
            return adapter, fallback_model

    # -- REQ-109 req 016: no fallback available — return None (NOT Claude interactive)
    logger.warning("No healthy fallback for provider '%s' — dispatch aborted", provider_name)
    return None, ""


# -- sig: mgh-6201.cd.bd955f.a109.b10901
