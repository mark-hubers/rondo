# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.review_tiers — ai-review tier merge from config.toml.

VER-001 verification matrix: Rondo SSOT for ai-review tier models (REQ-109 reqs 064-067).
"""

from __future__ import annotations

import textwrap

import pytest


@pytest.fixture
def builtin_tiers() -> dict[str, dict[str, str]]:
    return {
        "best": {"gemini": "gemini-2.5-pro", "grok": "grok-old"},
        "standard": {"gemini": "gemini-2.5-flash", "grok": "grok-std"},
        "fast": {"gemini": "gemini-2.5-flash", "grok": "grok-fast"},
    }


def test_merge_no_config_returns_copy(tmp_path, monkeypatch: pytest.MonkeyPatch, builtin_tiers: dict) -> None:
    from rondo.review_tiers import merge_ai_review_tiers

    monkeypatch.setenv("RONDO_CONFIG_PATH", str(tmp_path / "missing.toml"))
    out = merge_ai_review_tiers(builtin_tiers)
    assert out == builtin_tiers
    assert out is not builtin_tiers
    out["best"]["gemini"] = "mutated"
    assert builtin_tiers["best"]["gemini"] == "gemini-2.5-pro"


def test_merge_overrides_from_toml(tmp_path, monkeypatch: pytest.MonkeyPatch, builtin_tiers: dict) -> None:
    from rondo.review_tiers import merge_ai_review_tiers

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            """
            [providers.gemini]
            enabled = true
            best_model = "gemini-OVERRIDE-BEST"
            default_model = "gemini-OVERRIDE-DEF"
            cheap_model = "gemini-OVERRIDE-CHEAP"

            [providers.grok]
            enabled = true
            best_model = "grok-BEST"
            default_model = "grok-DEF"
            cheap_model = "grok-CHEAP"
            """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("RONDO_CONFIG_PATH", str(cfg))
    out = merge_ai_review_tiers(builtin_tiers)
    assert out["best"]["gemini"] == "gemini-OVERRIDE-BEST"
    assert out["standard"]["gemini"] == "gemini-OVERRIDE-DEF"
    assert out["fast"]["gemini"] == "gemini-OVERRIDE-CHEAP"
    assert out["best"]["grok"] == "grok-BEST"


def test_merge_skips_disabled_provider(tmp_path, monkeypatch: pytest.MonkeyPatch, builtin_tiers: dict) -> None:
    from rondo.review_tiers import merge_ai_review_tiers

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            """
            [providers.gemini]
            enabled = false
            default_model = "should-not-apply"
            """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("RONDO_CONFIG_PATH", str(cfg))
    out = merge_ai_review_tiers(builtin_tiers)
    assert out["standard"]["gemini"] == builtin_tiers["standard"]["gemini"]


def test_merge_maps_anthropic_to_claude(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rondo.review_tiers import merge_ai_review_tiers

    builtin = {
        "best": {"claude": "claude-opus-4-6"},
        "standard": {"claude": "claude-sonnet-4-6"},
        "fast": {"claude": "claude-haiku-4-5-20251001"},
    }
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            """
            [providers.anthropic]
            enabled = true
            best_model = "claude-ANTH-BEST"
            default_model = "claude-ANTH-DEF"
            cheap_model = "claude-ANTH-CHEAP"
            """
        ).strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("RONDO_CONFIG_PATH", str(cfg))
    out = merge_ai_review_tiers(builtin)
    assert out["best"]["claude"] == "claude-ANTH-BEST"
    assert out["standard"]["claude"] == "claude-ANTH-DEF"


# -- sig: mgh-6201.cd.bd955f.b902.e53f22
