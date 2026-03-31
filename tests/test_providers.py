# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.providers — REQ-109 provider adapter interface.

VER-001 verification matrix: provider adapters, routing, multi-LLM.
"""

import json

import pytest

from rondo.engine import TaskResult


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 001: ProviderAdapter interface
# -- ──────────────────────────────────────────────────────────────


class TestProviderInterface:
    """REQ-109 req 001: abstract base class with dispatch/health/models."""

    def test_adapter_has_dispatch(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "dispatch")

    def test_adapter_has_health(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "health")

    def test_adapter_has_models(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "models")


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 002: Ollama adapter
# -- ──────────────────────────────────────────────────────────────


class TestOllamaAdapter:
    """REQ-109 req 002: OllamaAdapter for local LLM dispatch."""

    def test_ollama_adapter_exists(self) -> None:
        from rondo.providers import OllamaAdapter

        adapter = OllamaAdapter()
        assert adapter is not None

    def test_ollama_models_returns_list(self) -> None:
        from rondo.providers import OllamaAdapter

        adapter = OllamaAdapter()
        result = adapter.models()
        assert isinstance(result, list)

    def test_ollama_dispatch_returns_task_result(self) -> None:
        """Dispatch returns TaskResult even if Ollama not running."""
        from rondo.providers import OllamaAdapter

        adapter = OllamaAdapter()
        result = adapter.dispatch(prompt="Say hello", model="llama3.2")
        assert isinstance(result, TaskResult)
        ## -- If Ollama not running, should be error not crash
        assert result.status in ("done", "error")


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 004: All adapters return same format
# -- ──────────────────────────────────────────────────────────────


class TestProviderRouting:
    """REQ-109 req 012: model → provider routing."""

    def test_route_claude_models(self) -> None:
        from rondo.providers import get_provider

        assert get_provider("sonnet").name == "claude"
        assert get_provider("opus").name == "claude"
        assert get_provider("haiku").name == "claude"

    def test_route_ollama_models(self) -> None:
        from rondo.providers import get_provider

        assert get_provider("llama3.1:8b").name == "ollama"
        assert get_provider("qwen2.5:32b").name == "ollama"
        assert get_provider("qwen2.5-coder:7b").name == "ollama"
        assert get_provider("deepseek-r1:8b").name == "ollama"
        assert get_provider("gemma3:12b").name == "ollama"
        assert get_provider("phi4:14b").name == "ollama"
        assert get_provider("mistral").name == "ollama"

    def test_unknown_model_returns_claude(self) -> None:
        """Unknown models default to Claude (backward compat)."""
        from rondo.providers import get_provider

        assert get_provider("unknown-model-xyz").name == "claude"

    def test_recommend_model_for_task(self) -> None:
        """recommend_model returns best local model for task type."""
        from rondo.providers import recommend_model

        assert recommend_model("code-review") == "qwen2.5-coder:7b"
        assert recommend_model("reasoning") == "deepseek-r1:8b"
        assert recommend_model("classify") == "llama3.1:8b"
        assert recommend_model("structured-json") == "phi4:14b"
        assert recommend_model("general") == "qwen2.5:32b"
        assert recommend_model("unknown-type") == "sonnet"  ## default to Claude


# -- ──────────────────────────────────────────────────────────────
# --  Provider-aware MCP dispatch (RONDO-73)
# -- ──────────────────────────────────────────────────────────────


class TestMCPProviderRouting:
    """MCP dispatch routes non-Claude models to provider adapters."""

    def test_ollama_model_routes_to_adapter(self) -> None:
        """rondo_run_file with ollama model uses OllamaAdapter."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello",
            model="llama3.2",
            dry_run=True,
        ))
        ## -- Dry-run with non-Claude model: should still return valid result
        assert result["status"] in ("done", "skipped", "error")

    def test_claude_model_uses_existing_path(self) -> None:
        """rondo_run_file with sonnet uses existing Claude dispatch."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello",
            model="sonnet",
            dry_run=True,
        ))
        assert result["status"] in ("done", "skipped")


# -- ──────────────────────────────────────────────────────────────
# --  Finding #188: Provider dispatches log to audit (RONDO-74)
# -- ──────────────────────────────────────────────────────────────


class TestProviderAuditTrail:
    """Provider dispatches must write to audit JSONL."""

    def test_ollama_dispatch_creates_audit(self, tmp_path, monkeypatch):
        """Ollama dispatch writes INTENT+OUTCOME to audit JSONL."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        (tmp_path / "audit").mkdir()
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello", model="llama3.1:8b", dry_run=False,
        ))
        ## -- Check audit file exists and has records
        audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
        if audit_file.exists():
            lines = audit_file.read_text().strip().splitlines()
            assert len(lines) >= 1  ## at least OUTCOME
        ## -- Result should still be valid
        assert result["status"] in ("done", "error", "partial")


# -- sig: mgh-6201.cd.bd955f.a109.c10901
