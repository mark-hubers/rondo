# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for auto-tier derivation + model canary — RONDO-316 (REQ-111 604-610).

Auto-tiers derive auto_low/mid/high per provider from the registry cache so
new model generations get picked up without hand-editing config. Manual pins
ALWAYS win (req 610); derivation never crosses providers (req 609); the
canary (req 604) proves each configured tier model actually answers.

VER-001 verification matrix: auto-tier derivation, collapse ladder, canary.
"""

from __future__ import annotations

from typing import Any

import pytest

from rondo.model_registry import (
    derive_auto_tiers,
    resolve_model,
    verify_models,
)


def _cache(provider: str, models: list[str]) -> dict[str, Any]:
    return {"providers": {provider: {"models": models, "error": ""}}}


ENABLED = {"enabled": True}


class TestDeriveAutoTiers:
    """req 607: tier models derived from registry capability classes."""

    def test_three_class_provider(self) -> None:
        cache = _cache("anthropic", ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"])
        tiers = derive_auto_tiers(cache, {"anthropic": dict(ENABLED)})
        assert tiers["anthropic"]["auto_low"] == "claude-haiku-4-5"
        assert tiers["anthropic"]["auto_mid"] == "claude-sonnet-4-6"
        assert tiers["anthropic"]["auto_high"] == "claude-opus-4-8"

    def test_alias_first_rule(self) -> None:
        """req 603: prefer -latest aliases over dated IDs within a class."""
        cache = _cache("gemini", ["gemini-flash-2026-01-15", "gemini-flash-latest", "gemini-pro-latest"])
        tiers = derive_auto_tiers(cache, {"gemini": dict(ENABLED)})
        assert tiers["gemini"]["auto_mid"] == "gemini-flash-latest"
        assert tiers["gemini"]["auto_high"] == "gemini-pro-latest"

    def test_collapse_ladder_missing_low(self) -> None:
        """req 608: a provider missing a distinct low inherits mid."""
        cache = _cache("grok", ["grok-4.3"])
        tiers = derive_auto_tiers(cache, {"grok": dict(ENABLED)})
        assert tiers["grok"]["auto_low"] == "grok-4.3"
        assert tiers["grok"]["auto_mid"] == "grok-4.3"
        assert tiers["grok"]["auto_high"] == "grok-4.3"

    def test_within_provider_boundary(self) -> None:
        """req 609: derivation NEVER borrows another provider's models."""
        cache = {
            "providers": {
                "grok": {"models": ["grok-4.3"], "error": ""},
                "openai": {"models": ["gpt-5.5", "gpt-5.4-nano"], "error": ""},
            }
        }
        cfg = {"grok": dict(ENABLED), "openai": dict(ENABLED)}
        tiers = derive_auto_tiers(cache, cfg)
        for tier_model in tiers["grok"].values():
            assert "gpt" not in tier_model

    def test_non_chat_models_excluded(self) -> None:
        """Live run 2026-06-06: openai auto_high derived to text-embedding-3-large.
        Embeddings/moderation/audio/image models never enter text tiers."""
        cache = _cache(
            "openai",
            ["text-embedding-3-large", "omni-moderation-latest", "whisper-1", "gpt-5.4-nano", "gpt-5.5"],
        )
        tiers = derive_auto_tiers(cache, {"openai": dict(ENABLED)})
        assert tiers["openai"]["auto_low"] == "gpt-5.4-nano"
        assert tiers["openai"]["auto_high"] == "gpt-5.5"
        for model in tiers["openai"].values():
            assert "embedding" not in model and "moderation" not in model

    def test_disabled_provider_skipped(self) -> None:
        cache = _cache("mistral", ["mistral-large-latest"])
        assert derive_auto_tiers(cache, {"mistral": {"enabled": False}}) == {}

    def test_fetch_error_provider_skipped(self) -> None:
        """NO_CACHE provider: never derive tiers from stale/absent data."""
        cache = {"providers": {"openai": {"models": [], "error": "HTTP 500"}}}
        assert derive_auto_tiers(cache, {"openai": dict(ENABLED)}) == {}


class TestResolveModel:
    """req 610: COALESCE manual pin → auto-tier → collapse. Manual ALWAYS wins."""

    def test_manual_pin_wins(self) -> None:
        cfg = {"anthropic": {"enabled": True, "best_model": "claude-opus-4-8"}}
        auto = {"anthropic": {"auto_high": "claude-opus-9-experimental"}}
        assert resolve_model("anthropic", "best_model", cfg, auto) == "claude-opus-4-8"

    def test_auto_tier_fills_blank(self) -> None:
        cfg = {"anthropic": {"enabled": True}}
        auto = {"anthropic": {"auto_high": "claude-opus-4-8", "auto_mid": "claude-sonnet-4-6"}}
        assert resolve_model("anthropic", "best_model", cfg, auto) == "claude-opus-4-8"

    def test_no_data_returns_empty(self) -> None:
        assert resolve_model("anthropic", "best_model", {"anthropic": {"enabled": True}}, {}) == ""


class TestVerifyModels:
    """req 604: canary dispatch per configured tier — PASS/FAIL/SKIP table."""

    def _cfg(self) -> dict[str, dict[str, Any]]:
        return {
            "anthropic": {"enabled": True, "cheap_model": "claude-haiku-4-5", "best_model": "claude-opus-4-8"},
            "openai": {"enabled": False, "default_model": "gpt-5.5"},
        }

    def test_pass_fail_skip_rows(self) -> None:
        def fake_dispatch(provider: str, model: str) -> tuple[bool, str, float]:
            if "opus" in model:
                return False, "HTTP 404 model_not_found", 0.0
            return True, "", 0.001

        rows = verify_models(self._cfg(), dispatcher=fake_dispatch)
        by_model = {r["model"]: r for r in rows}
        assert by_model["claude-haiku-4-5"]["result"] == "PASS"
        assert by_model["claude-opus-4-8"]["result"] == "FAIL"
        assert "404" in by_model["claude-opus-4-8"]["note"]
        ## -- disabled provider rows are SKIP, never silently absent
        assert by_model["gpt-5.5"]["result"] == "SKIP"

    def test_dispatcher_crash_is_fail_not_crash(self) -> None:
        def boom(provider: str, model: str) -> tuple[bool, str, float]:
            raise OSError("network down")

        rows = verify_models({"anthropic": {"enabled": True, "best_model": "x"}}, dispatcher=boom)
        assert rows[0]["result"] == "FAIL"
        assert "network down" in rows[0]["note"]

    def test_total_cost_accumulates(self) -> None:
        def fake_dispatch(provider: str, model: str) -> tuple[bool, str, float]:
            return True, "", 0.002

        rows = verify_models(
            {"anthropic": {"enabled": True, "cheap_model": "a", "best_model": "b"}}, dispatcher=fake_dispatch
        )
        assert sum(r["cost_usd"] for r in rows) == pytest.approx(0.004)


class TestRegistryMode:
    """reqs 605-606: suggest is the default; auto application is gated."""

    def test_suggest_is_default(self) -> None:
        from rondo.model_registry import registry_mode

        assert registry_mode({}) == "suggest"

    def test_auto_downgrades_to_suggest_until_implemented(self) -> None:
        """req 606 auto-APPLY isn't built — 'auto' must NOT silently pretend."""
        from rondo.model_registry import registry_mode

        assert registry_mode({"registry": {"mode": "auto"}}) == "suggest"


# -- sig: mgh-6201.cd.bd955f.93a3.aa26ed
