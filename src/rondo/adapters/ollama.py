# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Ollama adapter — local LLM dispatch via HTTP API.

REQ-109 req 002. No API key needed. Ollama must be running.
Moved from providers.py to adapters/ per REQ-109 req 030 (Session 94).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from rondo.engine import TaskResult
from rondo.provider_base import ProviderAdapter

logger = logging.getLogger(__name__)


class OllamaAdapter(ProviderAdapter):
    """Ollama adapter — dispatches to local Ollama server.

    No API key needed. Ollama must be running at endpoint.
    """

    name: str = "ollama"

    def __init__(self, endpoint: str = "") -> None:
        self.endpoint = endpoint or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Ollama API, return TaskResult.

        RONDO-381 (cursor holistic #6b, checklist item 12): ollama was the lone
        HTTP adapter with NO reliability primitives — bare urlopen, no
        retry_http, no circuit breaker, no empty-response gate. Local servers
        hang and die like any other; only the COST is special ($0). Now wired
        through the same shared skeleton as every cloud adapter.
        """
        from rondo.adapters.http_skeleton import (  # pylint: disable=import-outside-toplevel
            HttpDispatchPlan,
            dispatch_via_http,
        )

        task_name = kwargs.get("task_name", f"ollama-{model}")

        def _do_request() -> dict:
            """Inner HTTP call — wrapped by retry_http (via the skeleton)."""
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
                return json.loads(resp.read().decode("utf-8"))

        return dispatch_via_http(
            HttpDispatchPlan(
                provider="ollama",
                label="Ollama",
                task_name=task_name,
                model=model,
                do_request=_do_request,
                extract_text=lambda result: result.get("response", ""),
                extract_tokens=None,  # -- local = $0; no cost computation
                auth_mode="local",
                requires_key=False,  # -- Ollama has no API key
            )
        )

    def health(self) -> bool:
        """Check if Ollama is running."""
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=5) as resp:  # nosec B310
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List models available in local Ollama."""
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=5) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []


# -- sig: mgh-6201.cd.bd955f.455b.695d79
