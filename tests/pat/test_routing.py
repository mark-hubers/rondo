# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dispatch router — decision-tree tests, pure logic, no I/O.

Split from test_real_dispatch.py in RONDO-207 to reduce file size to
best-practice range (200-500 lines per test file). Original monster was
2227 lines with 133 tests across 24 classes — this file is a focused slice.

Markers:
    (none)          — always runs, free, instant
    @pytest.mark.cloud  — real cloud API calls
    @pytest.mark.ollama — needs Ollama running locally

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import sys

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.mcp_dispatch import resolve_dispatch_engine
from rondo.providers import get_provider, is_claude_model, is_legacy_ollama_model


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


# -- sig: mgh-dfca.86.231680.02fd.0a0ebe
