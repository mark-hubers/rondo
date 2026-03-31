# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo provider adapters — REQ-109: multi-LLM dispatch.

Abstract interface + concrete adapters for different AI providers.
Adding a new provider = implement one adapter class. No other code changes.

Import direction:
    providers.py → imports engine (TaskResult only)
"""

from __future__ import annotations

import json
import logging
import time
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
# --  REQ-109 req 002: Claude CLI adapter (existing dispatch path)
# -- ──────────────────────────────────────────────────────────────


class ClaudeCLIAdapter(ProviderAdapter):
    """Claude Code CLI adapter — dispatches via 'claude -p' subprocess.

    This is the original Rondo dispatch path, now wrapped as an adapter.
    """

    name: str = "claude"

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Dispatch via claude -p (delegates to existing dispatch.py)."""
        ## -- Delegate to existing dispatch pipeline
        return TaskResult(
            task_name=kwargs.get("task_name", "claude-dispatch"),
            status="error",
            error_message="Use dispatch_task() directly for Claude CLI — adapter is for routing only",
        )

    def health(self) -> bool:
        """Check if claude binary is on PATH."""
        import shutil

        return shutil.which("claude") is not None

    def models(self) -> list[str]:
        """Claude Code supported models."""
        return ["sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"]


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 002: Ollama adapter (local LLM, no API key)
# -- ──────────────────────────────────────────────────────────────


class OllamaAdapter(ProviderAdapter):
    """Ollama adapter — dispatches to local Ollama server.

    No API key needed. Ollama must be running at endpoint.
    """

    name: str = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434") -> None:
        self.endpoint = endpoint

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Ollama API, return TaskResult."""
        import urllib.error
        import urllib.request

        task_name = kwargs.get("task_name", f"ollama-{model}")
        start = time.monotonic()

        try:
            data = json.dumps(
                {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                f"{self.endpoint}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:  # nosec B310
                result = json.loads(resp.read().decode("utf-8"))

            duration = time.monotonic() - start
            return TaskResult(
                task_name=task_name,
                status="done",
                raw_output=result.get("response", ""),
                model=model,
                duration_sec=duration,
                auth_mode="local",
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            duration = time.monotonic() - start
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_PROVIDER",
                error_message=f"Ollama error: {exc}",
                model=model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if Ollama is running."""
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=5) as resp:  # nosec B310
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List models available in local Ollama."""
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=5) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 012: Model → provider routing
# -- ──────────────────────────────────────────────────────────────

## -- Known model prefixes for routing
_CLAUDE_MODELS = {"sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"}
_OLLAMA_PREFIXES = {"llama", "qwen", "mistral", "phi", "gemma", "codellama", "deepseek"}

## -- Singleton adapters
_claude_adapter = ClaudeCLIAdapter()
_ollama_adapter = OllamaAdapter()


def get_provider(model: str) -> ProviderAdapter:
    """Route model name to the correct provider adapter — REQ-109 req 012.

    Returns Claude adapter as default for unknown models (backward compat).
    """
    if model in _CLAUDE_MODELS:
        return _claude_adapter

    ## -- Check Ollama prefixes: strip version (llama3.2→llama), tag (qwen:7b→qwen)
    import re

    model_base = re.sub(r"[\d.:]+.*$", "", model.split("-")[0].lower())
    if model_base in _OLLAMA_PREFIXES:
        return _ollama_adapter

    ## -- Default: Claude (backward compat)
    return _claude_adapter


# -- ──────────────────────────────────────────────────────────────
# --  Task type → model recommendation
# -- ──────────────────────────────────────────────────────────────

## -- Best model per task type (local-first, Claude as fallback)
_TASK_MODEL_MAP: dict[str, str] = {
    "code-review": "qwen2.5-coder:7b",
    "code-fix": "qwen2.5-coder:7b",
    "code-generate": "qwen2.5-coder:7b",
    "reasoning": "deepseek-r1:8b",
    "math": "deepseek-r1:8b",
    "logic": "deepseek-r1:8b",
    "classify": "llama3.1:8b",
    "scan": "llama3.1:8b",
    "filter": "llama3.1:8b",
    "structured-json": "phi4:14b",
    "extract": "phi4:14b",
    "summarize": "gemma3:12b",
    "general": "qwen2.5:32b",
    "research": "qwen2.5:32b",
    "analysis": "qwen2.5:32b",
}


def recommend_model(task_type: str) -> str:
    """Recommend the best model for a task type — REQ-109.

    Returns local model name for known types, 'sonnet' (Claude) for unknown.
    """
    return _TASK_MODEL_MAP.get(task_type.lower(), "sonnet")


# -- sig: mgh-6201.cd.bd955f.a109.b10901
