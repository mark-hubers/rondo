# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Chat Completions adapter — OpenAI, Grok, Mistral (same API shape).

REQ-109 req 031: One adapter, three providers via config.
All use POST /v1/chat/completions with the same payload format.
Differences: base_url, auth header, model names.

Based on ai_review.py call_openai/call_grok/call_mistral (proven patterns).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from rondo.engine import TaskResult
from rondo.providers import ProviderAdapter

logger = logging.getLogger(__name__)


class ChatCompletionsAdapter(ProviderAdapter):
    """Chat Completions API adapter — handles OpenAI, Grok, Mistral.

    All three use the same API shape. Config provides:
    - base_url: API endpoint (https://api.openai.com/v1, etc.)
    - api_key: Bearer token for Authorization header
    - default_model: Model name for this provider
    """

    name: str = "chat_completions"

    def __init__(
        self,
        provider_name: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        default_model: str = "gpt-4.1",
        temperature: float = 0.2,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.name = provider_name

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt via Chat Completions API, return TaskResult."""
        import urllib.error
        import urllib.request

        task_name = kwargs.get("task_name", f"{self.provider_name}-{model}")
        use_model = model or self.default_model
        start = time.monotonic()

        if not self.api_key:
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_AUTH",
                error_message=f"No API key for {self.provider_name}",
                model=use_model,
                duration_sec=0.0,
            )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": use_model,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "rondo/0.6",
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                result = json.loads(resp.read().decode("utf-8"))

            duration = time.monotonic() - start

            # -- Extract response text
            choices = result.get("choices", [])
            text = choices[0]["message"]["content"] if choices else ""

            return TaskResult(
                task_name=task_name,
                status="done",
                raw_output=text,
                model=use_model,
                duration_sec=duration,
                auth_mode="api",
                cost_usd=0.0,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as exc:
            duration = time.monotonic() - start
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_PROVIDER",
                error_message=f"{self.provider_name} error: {exc}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if API endpoint is reachable (lightweight — just connect)."""
        import urllib.error
        import urllib.request

        if not self.api_key:
            return False
        try:
            # -- HEAD request to models endpoint (minimal)
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "rondo/0.6",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List available models from provider."""
        return [self.default_model]


# -- sig: mgh-6201.cd.bd955f.a109.d03101
