# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unit tests for `_normalize_provider_model` — RONDO-288.

VER-001: Product acceptance / unit test coverage.

Root cause of RONDO-287 (Finding #270) was ZERO direct tests for this
function. A private function with a "bare provider name" branch was never
exercised by any test, so a rule-ordering bug lived in main for months:
bare names like "gemini" matched the 'if "gemini" in lower' heuristic
BEFORE the _PROVIDER_PREFIXES check, producing "gemini:gemini" instead of
"gemini:gemini-2.5-pro" -> HTTP 404 Not Found from the Gemini API.

These tests cover:
    1. Bare provider names resolve via `tier` to best/default/cheap models.
    2. Explicit `provider:model` strings pass through unchanged.
    3. Bare model names route via heuristic (gpt-4.1 -> openai:gpt-4.1, etc).
    4. Claude shorthand stays as shorthand (subprocess dispatch path).
    5. Empty/None inputs return empty string.
    6. Unknown provider names return raw (no mangling).
"""

from __future__ import annotations

import pytest

from rondo.mcp_compose import _normalize_provider_model


class TestBareProviderNames:
    """Bare names ("gemini", "grok") MUST resolve via tier — RONDO-287 bug."""

    def test_bare_gemini_tier_high_resolves_to_best_model(self) -> None:
        assert _normalize_provider_model("gemini", tier="high") == "gemini:gemini-2.5-pro"

    def test_bare_gemini_tier_default_resolves_to_default_model(self) -> None:
        assert _normalize_provider_model("gemini", tier="default") == "gemini:gemini-2.5-flash"

    def test_bare_grok_tier_high_resolves(self) -> None:
        assert _normalize_provider_model("grok", tier="high") == "grok:grok-3"

    def test_bare_grok_tier_default_resolves(self) -> None:
        assert _normalize_provider_model("grok", tier="default") == "grok:grok-3"

    def test_bare_openai_tier_high_resolves_to_best_model(self) -> None:
        assert _normalize_provider_model("openai", tier="high") == "openai:gpt-4.1"

    def test_bare_openai_tier_default_resolves(self) -> None:
        assert _normalize_provider_model("openai", tier="default") == "openai:gpt-4.1-mini"

    def test_bare_mistral_tier_high_resolves_to_large(self) -> None:
        assert _normalize_provider_model("mistral", tier="high") == "mistral:mistral-large-latest"

    def test_bare_mistral_tier_default_resolves(self) -> None:
        assert _normalize_provider_model("mistral", tier="default") == "mistral:mistral-medium-latest"

    def test_bare_anthropic_tier_high_resolves(self) -> None:
        ## claude-opus-4-6 OR claude-opus-4-7 depending on config
        result = _normalize_provider_model("anthropic", tier="high")
        assert result.startswith("anthropic:claude-")

    def test_bare_local_falls_back_to_ollama_default(self) -> None:
        ## 'local' is special — if no default_model in config, falls back hardcoded
        result = _normalize_provider_model("local", tier="default")
        assert result.startswith("local:")

    def test_unknown_tier_falls_back_to_default_model(self) -> None:
        ## Invalid tier should use default_model, not break
        assert _normalize_provider_model("gemini", tier="bogus") == "gemini:gemini-2.5-flash"


class TestExplicitProviderModels:
    """provider:model strings pass through unchanged."""

    def test_explicit_gemini_pro_unchanged(self) -> None:
        assert _normalize_provider_model("gemini:gemini-2.5-pro") == "gemini:gemini-2.5-pro"

    def test_explicit_gemini_flash_unchanged(self) -> None:
        assert _normalize_provider_model("gemini:gemini-2.5-flash") == "gemini:gemini-2.5-flash"

    def test_explicit_grok_unchanged(self) -> None:
        assert _normalize_provider_model("grok:grok-3") == "grok:grok-3"

    def test_explicit_openai_unchanged(self) -> None:
        assert _normalize_provider_model("openai:gpt-4.1") == "openai:gpt-4.1"

    def test_explicit_mistral_unchanged(self) -> None:
        assert _normalize_provider_model("mistral:mistral-large-latest") == "mistral:mistral-large-latest"

    def test_explicit_local_unchanged(self) -> None:
        assert _normalize_provider_model("local:qwen2.5:32b") == "local:qwen2.5:32b"

    def test_tier_ignored_when_explicit(self) -> None:
        ## Passing tier when user gave explicit model should NOT override
        assert _normalize_provider_model("gemini:gemini-2.5-flash", tier="high") == "gemini:gemini-2.5-flash"


class TestHeuristicFallbacks:
    """Bare model names (no provider prefix) route via prefix heuristics."""

    def test_gpt_prefix_routes_to_openai(self) -> None:
        assert _normalize_provider_model("gpt-4.1") == "openai:gpt-4.1"

    def test_o1_prefix_routes_to_openai(self) -> None:
        assert _normalize_provider_model("o1-preview") == "openai:o1-preview"

    def test_o3_prefix_routes_to_openai(self) -> None:
        assert _normalize_provider_model("o3-mini") == "openai:o3-mini"

    def test_grok_model_with_version_routes_to_grok(self) -> None:
        ## Bare name "grok-beta" (not just "grok") — heuristic branch
        assert _normalize_provider_model("grok-beta") == "grok:grok-beta"

    def test_mistral_bare_model_hits_legacy_ollama(self) -> None:
        ## QUIRK: "mistral" is in _OLLAMA_PREFIXES (local model namespace),
        ## so bare "mistral-large-latest" routes to local:, NOT mistral:.
        ## To hit the real Mistral API, use explicit "mistral:mistral-large-latest"
        ## or the bare provider name "mistral" (which goes through _PROVIDER_PREFIXES
        ## check FIRST since RONDO-287).
        assert _normalize_provider_model("mistral-large-latest") == "local:mistral-large-latest"

    def test_codestral_prefix_routes_to_mistral(self) -> None:
        ## "codestral" is NOT in _OLLAMA_PREFIXES, so heuristic routes to mistral.
        assert _normalize_provider_model("codestral-latest") == "mistral:codestral-latest"

    def test_claude_prefix_routes_to_anthropic(self) -> None:
        assert _normalize_provider_model("claude-opus-4-7") == "anthropic:claude-opus-4-7"

    def test_gemini_model_with_version_routes_to_gemini(self) -> None:
        ## Bare name "gemini-1.5-flash" (version, not just "gemini") — heuristic
        assert _normalize_provider_model("gemini-1.5-flash") == "gemini:gemini-1.5-flash"


class TestClaudeShorthand:
    """Claude shorthand (sonnet/opus/haiku) stays as-is for subprocess dispatch."""

    def test_sonnet_stays_shorthand(self) -> None:
        assert _normalize_provider_model("sonnet") == "sonnet"

    def test_opus_stays_shorthand(self) -> None:
        assert _normalize_provider_model("opus") == "opus"

    def test_haiku_stays_shorthand(self) -> None:
        assert _normalize_provider_model("haiku") == "haiku"

    def test_sonnet_1m_stays_shorthand(self) -> None:
        assert _normalize_provider_model("sonnet[1m]") == "sonnet[1m]"

    def test_opus_1m_stays_shorthand(self) -> None:
        assert _normalize_provider_model("opus[1m]") == "opus[1m]"


class TestEdgeCases:
    """Empty, None, whitespace, unknown inputs."""

    def test_empty_string_returns_empty(self) -> None:
        assert _normalize_provider_model("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert _normalize_provider_model("   ") == ""

    def test_whitespace_trimmed(self) -> None:
        ## Leading/trailing whitespace should be stripped before matching
        assert _normalize_provider_model("  gemini  ", tier="high") == "gemini:gemini-2.5-pro"

    def test_unknown_provider_name_returns_raw(self) -> None:
        ## Not a known provider, not a known model prefix, not Claude shorthand
        assert _normalize_provider_model("unknown-xyz") == "unknown-xyz"

    def test_none_input_returns_empty(self) -> None:
        ## None should be treated same as empty string (no crash)
        assert _normalize_provider_model(None) == ""  # type: ignore[arg-type]


class TestRuleOrderingRegression:
    """RONDO-287 regression: bare names MUST NOT match prefix heuristics.

    If these break, the core bug is back. Guards against future refactors
    accidentally re-ordering the rules.
    """

    def test_bare_gemini_does_not_become_gemini_gemini(self) -> None:
        result = _normalize_provider_model("gemini", tier="default")
        assert result != "gemini:gemini", f"RONDO-287 regression: got {result!r}"
        assert ":" in result
        ## Ensure we resolved to an actual model, not the provider name
        _, model = result.split(":", 1)
        assert model != "gemini"

    def test_bare_grok_does_not_become_grok_grok(self) -> None:
        result = _normalize_provider_model("grok", tier="default")
        assert result != "grok:grok", f"RONDO-287 regression: got {result!r}"
        _, model = result.split(":", 1)
        assert model != "grok"

    @pytest.mark.parametrize("provider", ["gemini", "grok", "openai", "mistral", "anthropic"])
    def test_bare_provider_never_produces_provider_as_model(self, provider: str) -> None:
        """Any bare provider name MUST resolve to a real model, not itself."""
        result = _normalize_provider_model(provider, tier="high")
        assert result.startswith(f"{provider}:"), f"Provider prefix lost: {result!r}"
        _, model = result.split(":", 1)
        assert model != provider, f"Bare name {provider!r} mangled into {result!r}"


# -- sig: mgh-6201.cd.bd955f.b699.296e60
