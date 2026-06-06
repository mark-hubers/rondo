# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""E2E cloud tests for rondo_multi_review bare provider names — RONDO-288.

VER-001: Product acceptance / unit test coverage.

Real dispatch against live provider APIs using bare names like ["gemini", "grok"].
Regression guard for RONDO-287: bare names used to produce "gemini:gemini" /
"grok:grok" which caused HTTP 404 / 400 from the real APIs.

Marked @pytest.mark.cloud — skipped by default (costs $0.01-$0.05 per run).
Run explicitly: pytest -m cloud rondo/tests/integration/test_multi_review_bare_names_cloud.py

These tests exist to catch:
    - Provider API drift (model deprecations, endpoint changes)
    - Adapter payload format regressions
    - The RONDO-287 class of bug at the REAL dispatch layer
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.cloud
class TestMultiReviewBareNamesLive:
    """Real dispatch with bare provider names — the exact AIP failure mode.

    The AIP session failure was: rondo_multi_review(providers=["gemini", "grok", "openai"])
    which produced "gemini:gemini" (HTTP 404) and "grok:grok" (HTTP 400).
    """

    def test_bare_gemini_grok_mistral_all_dispatch(self) -> None:
        """All 3 bare names resolve and dispatch successfully (no 404/400)."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt='Respond with exactly one word: "ok"',
                providers='["gemini", "grok", "mistral"]',
                tier="high",
            )
        )
        assert result["status"] in ("done", "partial"), f"unexpected status: {result['status']}"
        assert result["provider_count"] == 3

        ## Each provider must have resolved to a non-mangled form
        providers = [p["provider"] for p in result["per_provider"]]
        assert "gemini:gemini-2.5-pro" in providers
        assert "grok:grok-3" in providers
        assert "mistral:mistral-large-latest" in providers

        ## RONDO-287 regression guard — mangled forms MUST NOT appear
        assert "gemini:gemini" not in providers, "RONDO-287 regression: bare name mangled"
        assert "grok:grok" not in providers, "RONDO-287 regression: bare name mangled"

    def test_bare_gemini_tier_high_dispatches_to_pro(self) -> None:
        """tier='high' routes bare 'gemini' to gemini-2.5-pro (best_model)."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt='Respond with exactly one word: "ok"',
                providers='["gemini"]',
                tier="high",
            )
        )
        per_provider = result["per_provider"]
        assert len(per_provider) == 1
        assert per_provider[0]["provider"] == "gemini:gemini-2.5-pro"
        ## Must have either done (success) OR an error_code — NOT empty/stuck
        assert per_provider[0]["status"] in ("done", "error", "partial")

    def test_bare_grok_tier_default_dispatches(self) -> None:
        """tier='default' routes bare 'grok' to grok-3 (default_model)."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt='Respond with exactly one word: "ok"',
                providers='["grok"]',
                tier="default",
            )
        )
        per_provider = result["per_provider"]
        assert per_provider[0]["provider"] == "grok:grok-3"
        assert per_provider[0]["status"] in ("done", "error", "partial")

    def test_no_404_on_bare_gemini(self) -> None:
        """RONDO-287 specific regression: bare 'gemini' must NOT return HTTP 404."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt='Respond with exactly one word: "ok"',
                providers='["gemini"]',
                tier="high",
            )
        )
        p = result["per_provider"][0]
        ## If provider was down, error_code should be ERR_PROVIDER_DOWN not a 404 crash
        error_msg = p.get("error_message", "") or ""
        assert "HTTP 404" not in error_msg, f"RONDO-287 regression: bare 'gemini' produced 404: {error_msg[:200]}"

    def test_no_400_on_bare_grok(self) -> None:
        """RONDO-287 specific regression: bare 'grok' must NOT return HTTP 400."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt='Respond with exactly one word: "ok"',
                providers='["grok"]',
                tier="high",
            )
        )
        p = result["per_provider"][0]
        error_msg = p.get("error_message", "") or ""
        assert "HTTP 400" not in error_msg, f"RONDO-287 regression: bare 'grok' produced 400: {error_msg[:200]}"


# -- sig: mgh-6201.cd.bd955f.36eb.a5f136
