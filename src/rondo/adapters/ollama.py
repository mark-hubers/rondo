# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Ollama adapter — local LLM dispatch via HTTP API.

REQ-109 req 002. No API key needed. Ollama must be running.
Moved from providers.py to adapters/ per REQ-109 req 030 (Session 94).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from rondo.engine import TaskResult
from rondo.providers import ProviderAdapter

logger = logging.getLogger(__name__)


class OllamaAdapter(ProviderAdapter):
    """Ollama adapter — dispatches to local Ollama server.

    No API key needed. Ollama must be running at endpoint.
    """

    name: str = "ollama"

    def __init__(self, endpoint: str = "") -> None:
        import os

        self.endpoint = endpoint or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

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


# -- sig: mgh-6201.cd.bd955f.a109.d03002
