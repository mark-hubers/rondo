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

        assert get_provider("llama3.2").name == "ollama"
        assert get_provider("qwen2.5").name == "ollama"

    def test_unknown_model_returns_claude(self) -> None:
        """Unknown models default to Claude (backward compat)."""
        from rondo.providers import get_provider

        assert get_provider("unknown-model-xyz").name == "claude"


# -- sig: mgh-6201.cd.bd955f.a109.c10901
