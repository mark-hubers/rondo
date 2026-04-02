# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Anthropic API adapter — Claude via Messages API (not subprocess).

REQ-109 req 030. Direct HTTP to Anthropic's API.
This is for API-key dispatch (not Max plan claude -p subprocess).
Based on ai_review.py call_claude (proven pattern).

Key differences from Chat Completions:
- Auth: x-api-key header (not Bearer)
- Required: anthropic-version header
- Payload: system field + messages (not messages-only)
- Response: content[0].text (not choices[0].message.content)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from rondo.engine import TaskResult
from rondo.providers import ProviderAdapter

logger = logging.getLogger(__name__)


class AnthropicAPIAdapter(ProviderAdapter):
    """Anthropic API adapter — Claude dispatch via Messages API."""

    name: str = "anthropic"

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "claude-sonnet-4-6",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Anthropic Messages API, return TaskResult."""
        import urllib.error
        import urllib.request

        task_name = kwargs.get("task_name", f"anthropic-{model}")
        use_model = model or self.default_model
        start = time.monotonic()

        if not self.api_key:
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_AUTH",
                error_message="No API key for Anthropic",
                model=use_model,
                duration_sec=0.0,
            )

        url = f"{self.base_url}/messages"
        payload = {
            "model": use_model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
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

            # -- Extract text from Anthropic's response format
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            return TaskResult(
                task_name=task_name,
                status="done",
                raw_output=text,
                model=use_model,
                duration_sec=duration,
                auth_mode="api",
                cost_usd=0.0,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            duration = time.monotonic() - start
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code="ERR_PROVIDER",
                error_message=f"Anthropic error: {exc}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if Anthropic API is reachable."""
        if not self.api_key:
            return False
        return True  # -- No lightweight health endpoint; key presence is enough

    def models(self) -> list[str]:
        """Available Claude models via API."""
        return ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]


# -- sig: mgh-6201.cd.bd955f.a109.d03004
