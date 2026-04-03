# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: MIT
"""Config-driven cloud provider validation — REQ-109 reqs 075-078.

Reads ~/.rondo/config.toml and dispatches a minimal prompt to every enabled
provider at every tier (cheap/default/best). Proves model IDs are valid
against real APIs. Also validates _DEFAULT_TASK_MODELS entries.

Run: pytest -m cloud_full -v
Cost: ~$0.10-0.50 depending on provider count + model pricing.
Never runs in normal pytest (marker excluded by default in pyproject.toml).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

## -- Minimal prompt: cheap, fast, deterministic
_PROBE_PROMPT = "Reply with exactly one word: HELLO"


# -- ──────────────────────────────────────────────────────────────
# --  Config loading
# -- ──────────────────────────────────────────────────────────────


def _load_config() -> dict:
    """Load ~/.rondo/config.toml, return empty dict if missing."""
    config_path = Path.home() / ".rondo" / "config.toml"
    if not config_path.is_file():
        return {}
    import tomllib

    with open(config_path, "rb") as f:
        return tomllib.load(f)


def _get_enabled_providers(config: dict) -> dict[str, dict]:
    """Return {name: cfg} for enabled providers."""
    providers = config.get("providers", {})
    return {name: cfg for name, cfg in providers.items() if isinstance(cfg, dict) and cfg.get("enabled", True)}


def _has_key(provider: str) -> bool:
    """Check if API key is available for provider."""
    try:
        from rondo.adapters.auth import load_api_key

        return bool(load_api_key(provider))
    except Exception:  # noqa: BLE001
        return False


def _get_adapter(provider: str, model: str) -> object | None:
    """Get adapter instance for provider with loaded key."""
    from rondo.adapters.auth import load_api_key

    key = load_api_key(provider)
    if not key:
        return None

    if provider == "gemini":
        from rondo.adapters.gemini import GeminiAdapter

        return GeminiAdapter(api_key=key)
    if provider in ("openai", "grok", "mistral"):
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        urls = {
            "openai": "https://api.openai.com/v1",
            "grok": "https://api.x.ai/v1",
            "mistral": "https://api.mistral.ai/v1",
        }
        return ChatCompletionsAdapter(
            provider_name=provider,
            base_url=urls[provider],
            api_key=key,
            default_model=model,
        )
    if provider == "anthropic":
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        return AnthropicAPIAdapter(api_key=key)
    return None


# -- ──────────────────────────────────────────────────────────────
# --  cloud_full: validate every provider + tier from config
# -- ──────────────────────────────────────────────────────────────


@pytest.mark.cloud_full
class TestConfigProviderValidation:
    """REQ-109 req 075: dispatch to every enabled provider at every tier."""

    def test_all_providers_all_tiers(self) -> None:
        """Every enabled provider × every tier → real dispatch → valid result."""
        config = _load_config()
        providers = _get_enabled_providers(config)
        if not providers:
            pytest.skip("No providers configured in ~/.rondo/config.toml")

        tiers = ["cheap_model", "default_model", "best_model"]
        results: list[dict] = []
        failures: list[str] = []

        for name, cfg in providers.items():
            if not _has_key(name):
                for tier in tiers:
                    results.append(
                        {
                            "provider": name,
                            "tier": tier,
                            "model": "-",
                            "status": "SKIP",
                            "latency": 0,
                            "error": "no key",
                        }
                    )
                continue

            for tier in tiers:
                model = cfg.get(tier, "")
                if not model:
                    results.append(
                        {
                            "provider": name,
                            "tier": tier,
                            "model": "-",
                            "status": "SKIP",
                            "latency": 0,
                            "error": "not configured",
                        }
                    )
                    continue

                adapter = _get_adapter(name, model)
                if not adapter:
                    results.append(
                        {
                            "provider": name,
                            "tier": tier,
                            "model": model,
                            "status": "SKIP",
                            "latency": 0,
                            "error": "no adapter",
                        }
                    )
                    continue

                start = time.monotonic()
                result = adapter.dispatch(prompt=_PROBE_PROMPT, model=model)
                latency = time.monotonic() - start

                if result.status == "done" and result.raw_output.strip():
                    results.append(
                        {
                            "provider": name,
                            "tier": tier,
                            "model": model,
                            "status": "PASS",
                            "latency": round(latency, 1),
                            "error": "",
                        }
                    )
                else:
                    error = result.error_message or result.error_code or "empty response"
                    results.append(
                        {
                            "provider": name,
                            "tier": tier,
                            "model": model,
                            "status": "FAIL",
                            "latency": round(latency, 1),
                            "error": error,
                        }
                    )
                    failures.append(f"{name}:{tier} ({model}) → {error}")

        ## -- REQ-109 req 076: print results table
        print("\n")
        print(f"  {'Provider':<12} {'Tier':<15} {'Model':<28} {'Status':<6} {'Latency':>8}  Error")
        print(f"  {'─' * 12} {'─' * 15} {'─' * 28} {'─' * 6} {'─' * 8}  {'─' * 30}")
        for r in results:
            print(
                f"  {r['provider']:<12} {r['tier']:<15} {r['model']:<28} {r['status']:<6} {r['latency']:>7.1f}s  {r['error']}"
            )

        assert not failures, f"{len(failures)} provider/tier failures:\n  " + "\n  ".join(failures)


@pytest.mark.cloud_full
class TestConfigHealthValidation:
    """Validate health() returns True for every enabled provider with a key."""

    def test_all_providers_health(self) -> None:
        """Every enabled provider with a key → health() returns True."""
        config = _load_config()
        providers = _get_enabled_providers(config)
        failures: list[str] = []

        for name, cfg in providers.items():
            if not _has_key(name):
                continue
            model = cfg.get("default_model", "")
            adapter = _get_adapter(name, model)
            if adapter is None:
                continue
            healthy = adapter.health()
            if not healthy:
                failures.append(f"{name}: health() returned False")

        assert not failures, "Unhealthy providers:\n  " + "\n  ".join(failures)


@pytest.mark.cloud_full
class TestDefaultTaskModelsValid:
    """REQ-109 req 077: every model in _DEFAULT_TASK_MODELS dispatches successfully."""

    def test_all_default_models_dispatch(self) -> None:
        """Every unique model ID in _DEFAULT_TASK_MODELS → real dispatch."""
        from rondo.providers import _DEFAULT_TASK_MODELS

        ## -- Get unique model strings (many tasks share the same model)
        unique_models = sorted(set(_DEFAULT_TASK_MODELS.values()))
        failures: list[str] = []
        results: list[dict] = []

        for model_str in unique_models:
            ## -- Parse provider:model
            if ":" not in model_str:
                results.append({"model": model_str, "status": "SKIP", "error": "no provider prefix (Claude)"})
                continue
            provider, model = model_str.split(":", 1)

            if not _has_key(provider):
                results.append({"model": model_str, "status": "SKIP", "error": "no key"})
                continue

            adapter = _get_adapter(provider, model)
            if not adapter:
                results.append({"model": model_str, "status": "SKIP", "error": "no adapter"})
                continue

            result = adapter.dispatch(prompt=_PROBE_PROMPT, model=model)
            if result.status == "done" and result.raw_output.strip():
                results.append({"model": model_str, "status": "PASS", "error": ""})
            else:
                error = result.error_message or result.error_code or "empty"
                results.append({"model": model_str, "status": "FAIL", "error": error})
                failures.append(f"{model_str} → {error}")

        ## -- Print results
        print("\n")
        print(f"  {'Model':<35} {'Status':<6}  Error")
        print(f"  {'─' * 35} {'─' * 6}  {'─' * 40}")
        for r in results:
            print(f"  {r['model']:<35} {r['status']:<6}  {r['error']}")

        assert not failures, f"{len(failures)} default model failures:\n  " + "\n  ".join(failures)


# -- sig: mgh-6201.cd.bd955f.a109.e2e075
