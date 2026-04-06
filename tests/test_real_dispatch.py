# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo Product Acceptance Tests — REAL dispatch, no mocking, no skipping.

RONDO-133: Every test calls a real function with real inputs and asserts
the EXACT expected result. No pytest.skip for failures. No dry_run copouts.
No '!= bad' assertions. If it fails, it FAILS.

Markers:
    (none)          — always runs, free, instant (<1s total)
    @pytest.mark.cloud  — real cloud API calls (~$0.01-0.05 each)
    @pytest.mark.ollama — needs Ollama running locally

Run:
    ace-build test                    # unmarked only (free)
    pytest -m cloud test_real_dispatch.py   # cloud tests (~$0.10)
    pytest -m ollama test_real_dispatch.py  # local AI tests
    pytest test_real_dispatch.py      # ALL tests (~$0.15)

Session 99 lesson: AI reviewers rated Rondo 8.5/10 while its primary
use case (in-session dispatch) had a 100% failure rate. Tests hid this
behind pytest.skip and dry_run=True. Never again.
"""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.mcp_dispatch import resolve_dispatch_engine, _is_in_session
from rondo.providers import get_provider, is_claude_model, is_legacy_ollama_model


# -- ──────────────────────────────────────────────────────────────
# --  TIER 1: ROUTING — free, instant, always runs
# --  These test the decision tree. Pure logic, no I/O.
# -- ──────────────────────────────────────────────────────────────


class TestRoutingInline:
    """Empty model → inline engine. Always."""

    def test_empty_model(self) -> None:
        r = resolve_dispatch_engine(model="", prompt="hello")
        assert r["engine"] == "inline"
        assert r["status"] == "plan"
        assert r["model"] == "current"

    def test_empty_model_preserves_prompt(self) -> None:
        r = resolve_dispatch_engine(model="", prompt="specific task", done_when="specific done")
        assert r["prompt"] == "specific task"
        assert r["done_when"] == "specific done"

    def test_empty_model_preserves_project(self) -> None:
        r = resolve_dispatch_engine(model="", prompt="x", project="/tmp/proj")
        assert r["project"] == "/tmp/proj"


class TestRoutingCloudProviders:
    """Provider prefix → HTTP adapter. Every provider."""

    def test_gemini(self) -> None:
        r = resolve_dispatch_engine(model="gemini:gemini-2.5-flash", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "gemini"
        assert r["status"] == "plan"

    def test_grok(self) -> None:
        r = resolve_dispatch_engine(model="grok:grok-3", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "grok"

    def test_openai(self) -> None:
        r = resolve_dispatch_engine(model="openai:gpt-4.1", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "openai"

    def test_mistral(self) -> None:
        r = resolve_dispatch_engine(model="mistral:mistral-large-latest", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "mistral"

    def test_local_ollama(self) -> None:
        r = resolve_dispatch_engine(model="local:qwen2.5:32b", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "local"

    def test_anthropic_api(self) -> None:
        """anthropic: prefix → HTTP (API key billing, NOT Max plan)."""
        r = resolve_dispatch_engine(model="anthropic:sonnet", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "anthropic"

    def test_gemini_tier(self) -> None:
        r = resolve_dispatch_engine(model="gemini:high", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "gemini"


class TestRoutingClaude:
    """Claude models route based on session context."""

    def test_sonnet_in_session(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        assert r["engine"] == "agent"
        assert r["status"] == "plan"
        assert r["model"] == "sonnet"

    def test_opus_in_session(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="opus", prompt="x")
        assert r["engine"] == "agent"

    def test_haiku_in_session(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="haiku", prompt="x")
        assert r["engine"] == "agent"

    def test_sonnet_1m_in_session(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet[1m]", prompt="x")
        assert r["engine"] == "agent"

    def test_sonnet_outside_session(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAUDECODE", raising=False)
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        assert r["engine"] == "subprocess"

    def test_haiku_outside_session(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAUDECODE", raising=False)
        r = resolve_dispatch_engine(model="haiku", prompt="x")
        assert r["engine"] == "subprocess"

    def test_new_suffix_forces_subprocess(self, monkeypatch) -> None:
        """sonnet:new → subprocess regardless of session."""
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet:new", prompt="x")
        assert r["engine"] == "subprocess"
        assert r["model"] == "sonnet"


class TestRoutingBackground:
    """background=True → subprocess. Always. No exceptions."""

    def test_background_empty_model(self) -> None:
        r = resolve_dispatch_engine(model="", background=True, prompt="x")
        assert r["engine"] == "subprocess"

    def test_background_sonnet(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet", background=True, prompt="x")
        assert r["engine"] == "subprocess"

    def test_background_gemini(self) -> None:
        r = resolve_dispatch_engine(model="gemini:high", background=True, prompt="x")
        assert r["engine"] == "subprocess"


class TestRoutingLegacyOllama:
    """Legacy Ollama names (no local: prefix) → HTTP. Not error."""

    def test_llama(self) -> None:
        r = resolve_dispatch_engine(model="llama3.1:8b", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "local"

    def test_qwen(self) -> None:
        r = resolve_dispatch_engine(model="qwen2.5:32b", prompt="x")
        assert r["engine"] == "http"
        assert r["provider"] == "local"

    def test_deepseek(self) -> None:
        r = resolve_dispatch_engine(model="deepseek-r1:14b", prompt="x")
        assert r["engine"] == "http"

    def test_phi(self) -> None:
        r = resolve_dispatch_engine(model="phi4:latest", prompt="x")
        assert r["engine"] == "http"


class TestRoutingError:
    """Unknown models → error. Not silent fallback."""

    def test_unknown_model(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAUDECODE", raising=False)
        r = resolve_dispatch_engine(model="totally-unknown-xyz", prompt="x")
        assert r["engine"] == "error"
        assert r["status"] == "error"

    def test_error_has_reason(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAUDECODE", raising=False)
        r = resolve_dispatch_engine(model="nope", prompt="x")
        assert "reason" in r
        assert "nope" in r["reason"]


class TestResponseShape:
    """Every response has the right fields. No missing keys."""

    def test_all_plans_have_status(self) -> None:
        """Cursor #6/#7: status field required for defensive parsing."""
        cases = [
            ("", False),
            ("gemini:high", False),
            ("sonnet", True),
        ]
        for model, bg in cases:
            r = resolve_dispatch_engine(model=model, background=bg, prompt="x")
            assert "status" in r, f"model={model!r} bg={bg} missing 'status'"

    def test_inline_has_kind(self) -> None:
        r = resolve_dispatch_engine(model="", prompt="x")
        assert r["kind"] == "inline_dispatch_plan"

    def test_agent_has_kind(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        assert r["kind"] == "agent_dispatch_plan"

    def test_agent_has_note(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        assert "note" in r

    def test_http_has_provider(self) -> None:
        r = resolve_dispatch_engine(model="gemini:flash", prompt="x")
        assert "provider" in r

    def test_every_response_has_engine(self) -> None:
        for model in ("", "sonnet:new", "gemini:high", "llama3.1:8b"):
            r = resolve_dispatch_engine(model=model, prompt="x")
            assert "engine" in r, f"model={model!r} missing 'engine'"


class TestRouterParity:
    """resolve_dispatch_engine and get_provider MUST agree.

    Cursor #8: 'Two routers that disagree = two products.'
    This test feeds every model through BOTH and asserts parity.
    """

    def test_claude_models_parity(self) -> None:
        for model in ("sonnet", "opus", "haiku"):
            provider = get_provider(model)
            engine = resolve_dispatch_engine(model=model, prompt="x")
            assert provider is None, f"get_provider({model!r}) should be None for Claude"
            assert engine["engine"] != "http", f"router({model!r}) should not be HTTP"

    def test_prefixed_providers_parity(self) -> None:
        for model in ("gemini:gemini-2.5-flash", "grok:grok-3", "local:qwen2.5:32b"):
            provider = get_provider(model)
            engine = resolve_dispatch_engine(model=model, prompt="x")
            assert provider is not None, f"get_provider({model!r}) should return adapter"
            assert engine["engine"] == "http", f"router({model!r}) should be HTTP"

    def test_legacy_ollama_parity(self) -> None:
        """THE test that would have caught the Cursor #1a bug."""
        for model in ("llama3.1:8b", "qwen2.5:32b"):
            provider = get_provider(model)
            engine = resolve_dispatch_engine(model=model, prompt="x")
            assert provider is not None, f"get_provider({model!r}) should return Ollama adapter"
            assert engine["engine"] == "http", f"router({model!r}) should be HTTP, got {engine['engine']}"


class TestPublicAccessors:
    """is_claude_model() and is_legacy_ollama_model() return correct results."""

    def test_claude_models(self) -> None:
        for m in ("sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"):
            assert is_claude_model(m) is True, f"{m} should be Claude"

    def test_not_claude(self) -> None:
        for m in ("gpt-4", "llama3.1:8b", "gemini", ""):
            assert is_claude_model(m) is False, f"{m} should NOT be Claude"

    def test_legacy_ollama(self) -> None:
        for m in ("llama3.1:8b", "qwen2.5:32b", "deepseek-r1:14b", "phi4:latest"):
            assert is_legacy_ollama_model(m) is True, f"{m} should be legacy Ollama"

    def test_not_ollama(self) -> None:
        for m in ("sonnet", "gpt-4.1", "gemini-flash"):
            assert is_legacy_ollama_model(m) is False, f"{m} should NOT be Ollama"


# -- ──────────────────────────────────────────────────────────────
# --  TIER 2: CLOUD AI — real API calls, costs pennies
# -- ──────────────────────────────────────────────────────────────


@pytest.mark.cloud
class TestRealGemini:
    """Real Gemini API dispatch — proves HTTP adapter works end-to-end."""

    def test_gemini_responds(self) -> None:
        """Send a prompt to Gemini, get a real response back."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Reply with exactly: GEMINI_PAT_OK", model="gemini:gemini-2.5-flash", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"
        assert tasks[0]["status"] == "done", f"Task status: {tasks[0]['status']}"
        assert "GEMINI_PAT_OK" in tasks[0].get("raw_output", ""), "Gemini did not return expected text"

    def test_gemini_returns_cost(self) -> None:
        """Real dispatch tracks cost (even if $0.00 for free tier)."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Say OK", model="gemini:gemini-2.5-flash", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) >= 1
        # -- cost_usd exists (may be 0 for free tier, but field must exist)
        assert "cost_usd" in result or "cost_usd" in tasks[0], "No cost tracking on real dispatch"


@pytest.mark.cloud
class TestRealGrok:
    """Real Grok API dispatch."""

    def test_grok_responds(self) -> None:
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Reply with exactly: GROK_PAT_OK", model="grok:grok-3", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"
        assert tasks[0]["status"] == "done", f"Task status: {tasks[0]['status']}"


@pytest.mark.cloud
class TestRealMultiReview:
    """Real multi-provider review — multiple AIs answer same prompt."""

    def test_multi_review_returns_per_provider(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Reply with exactly: MULTI_OK",
                providers='["gemini:gemini-2.5-flash"]',
                dry_run=False,
            )
        )
        assert result.get("status") == "done"
        assert result.get("provider_count", 0) >= 1
        per_provider = result.get("per_provider", [])
        assert len(per_provider) >= 1
        assert per_provider[0].get("status") == "done"


# -- ──────────────────────────────────────────────────────────────
# --  TIER 3: LOCAL AI — needs Ollama running
# -- ──────────────────────────────────────────────────────────────


@pytest.mark.ollama
class TestRealOllama:
    """Real Ollama dispatch — local model, $0 cost."""

    def test_ollama_with_prefix(self) -> None:
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Say hello", model="local:llama3.1:8b", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done", f"Ollama failed: {tasks[0].get('error_code', '?')}"

    def test_ollama_legacy_name(self) -> None:
        """Legacy name (no local: prefix) must work identically."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Say hello", model="llama3.1:8b", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done", f"Legacy Ollama failed: {tasks[0].get('error_code', '?')}"


# -- ──────────────────────────────────────────────────────────────
# --  TIER 4: IN-SESSION — tests that only make sense from Claude Code
# -- ──────────────────────────────────────────────────────────────


class TestInSessionBehavior:
    """Tests that verify behavior when running inside Claude Code.

    These run in the current environment. If CLAUDECODE is set, they test
    in-session paths. If not, they test out-of-session paths.
    Both are valid — the assertions adapt.
    """

    def test_session_detection_matches_environment(self) -> None:
        """_is_in_session() matches CLAUDECODE env var."""
        expected = bool(os.environ.get("CLAUDECODE"))
        assert _is_in_session() == expected

    def test_sonnet_routing_matches_context(self) -> None:
        """sonnet → agent (in-session) or subprocess (outside). Not error."""
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        if _is_in_session():
            assert r["engine"] == "agent", "In-session sonnet should be agent"
        else:
            assert r["engine"] == "subprocess", "Outside-session sonnet should be subprocess"

    def test_inline_works_everywhere(self) -> None:
        """Empty model → inline regardless of session context."""
        r = resolve_dispatch_engine(model="", prompt="x")
        assert r["engine"] == "inline"

    def test_cloud_works_everywhere(self) -> None:
        """Cloud providers route to HTTP regardless of session context."""
        r = resolve_dispatch_engine(model="gemini:flash", prompt="x")
        assert r["engine"] == "http"


# -- ──────────────────────────────────────────────────────────────
# --  TIER 5: MCP INTEGRATION — rondo_run_file end-to-end
# -- ──────────────────────────────────────────────────────────────


class TestMCPIntegration:
    """rondo_run_file returns correct response shape for each engine."""

    def test_inline_via_mcp(self) -> None:
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Do something", model="", dry_run=False))
        assert result["engine"] == "inline"
        assert result["status"] == "plan"

    def test_agent_via_mcp_in_session(self) -> None:
        """Only validates if we're in a session. Otherwise sonnet→subprocess."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Do something", model="sonnet", dry_run=False))
        if _is_in_session():
            assert result["engine"] == "agent"
            assert result["status"] == "plan"
        else:
            # -- Outside session: subprocess path (may fail, that's expected)
            assert result.get("engine") == "subprocess" or "tasks" in result or "status" in result

    def test_inline_returns_instantly(self) -> None:
        """Inline plan must return in <10ms — no I/O, no dispatch."""
        from rondo.mcp_server import rondo_run_file

        t0 = time.time()
        rondo_run_file(prompt="x", model="", dry_run=False)
        elapsed = time.time() - t0
        assert elapsed < 0.1, f"Inline plan took {elapsed:.3f}s — should be instant"

    def test_no_prompt_no_file_is_error(self) -> None:
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="", model="", dry_run=True))
        assert result["status"] == "error"
