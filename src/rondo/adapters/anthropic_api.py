# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Anthropic API adapter — Claude via Messages API (not subprocess).

REQ-109 req 030. Direct HTTP to Anthropic's API.
This is for API-key dispatch (not Max plan claude -p subprocess).
Based on ai_review.py call_claude (proven pattern).

Key differences from Chat Completions:
- Auth: x-api-key header (not Bearer)
- Required: anthropic-version header
- Payload: messages array (system prompt supported via separate field if needed)
- Response: content[0].text (not choices[0].message.content)

Health strategy (REQ-109 req 073):
    HEAD request to base_url/messages — returns 405 (Method Not Allowed)
    which proves API is reachable. Key-present-only is NOT sufficient
    per REQ-109 req 072. Any non-timeout response = healthy.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from rondo.engine import ERR_AUTH, ERR_EMPTY_RESPONSE, ERR_PROVIDER, ERR_PROVIDER_DOWN, ERR_RATE_LIMIT, TaskResult
from rondo.provider_base import ProviderAdapter
from rondo.retry import get_circuit_breaker, retry_http

logger = logging.getLogger(__name__)


class AnthropicAPIAdapter(ProviderAdapter):
    """Anthropic API adapter — Claude dispatch via Messages API."""

    name: str = "anthropic"

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "claude-sonnet-4-6",
        temperature: float = 0.2,
        max_tokens: int = 8192,  # -- RONDO-209 #247: bumped from 4096
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Anthropic Messages API, return TaskResult.

        RONDO-204 (Finding #234): wraps HTTP call in retry_http + circuit breaker
        for consistency with ChatCompletionsAdapter + Gemini.
        """
        task_name = kwargs.get("task_name", f"anthropic-{model}")
        use_model = model or self.default_model
        start = time.monotonic()

        if not self.api_key:
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_AUTH,
                error_message="No API key for Anthropic",
                model=use_model,
                duration_sec=0.0,
            )

        # -- RONDO-204: circuit breaker check
        breaker = get_circuit_breaker()
        if breaker.is_open("anthropic"):
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER_DOWN,
                error_message="anthropic circuit breaker OPEN — cooldown active",
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
            "User-Agent": "rondo/0.7",
        }

        def _do_request() -> dict:
            """Inner HTTP call — wrapped by retry_http."""
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        try:
            result = retry_http(_do_request, provider_name="anthropic")
            breaker.record_success("anthropic")
            duration = time.monotonic() - start

            # -- Extract text from Anthropic's response format
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # -- REQ-109 req 070: empty response = error
            if not text:
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code=ERR_EMPTY_RESPONSE,
                    error_message="Anthropic returned empty response body",
                    model=use_model,
                    duration_sec=duration,
                )

            # -- RONDO-214 C-1: compute real cost from token counts (was 0.0)
            from rondo.adapters.chat_completions import compute_cost_usd  # pylint: disable=import-outside-toplevel

            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost = compute_cost_usd(use_model, input_tokens, output_tokens)

            return TaskResult(
                task_name=task_name,
                status="done",
                raw_output=text,
                model=use_model,
                duration_sec=duration,
                auth_mode="api",
                cost_usd=cost,
            )
        except urllib.error.HTTPError as exc:
            # -- REQ-109 req 068: distinct error codes by HTTP status
            duration = time.monotonic() - start
            if exc.code in (401, 403):
                error_code = ERR_AUTH
                # -- REQ-109 req 069: invalidate cached key on auth failure
                from rondo.adapters.auth import invalidate_key  # pylint: disable=import-outside-toplevel

                invalidate_key("anthropic")
            elif exc.code == 429:
                error_code = ERR_RATE_LIMIT
                breaker.record_failure("anthropic")
            elif exc.code >= 500:
                error_code = ERR_PROVIDER_DOWN
                breaker.record_failure("anthropic")
            else:
                error_code = ERR_PROVIDER
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=error_code,
                error_message=f"Anthropic HTTP {exc.code}: {exc.reason}",
                model=use_model,
                duration_sec=duration,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            duration = time.monotonic() - start
            breaker.record_failure("anthropic")
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER,
                error_message=f"Anthropic error: {exc}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if Anthropic API is reachable — REQ-109 req 072.

        HEAD to /v1/messages — any non-timeout response (even 405) proves
        the API is up and network path is clear. Key-only is insufficient.
        """
        if not self.api_key:
            return False
        try:
            req = urllib.request.Request(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "User-Agent": "rondo/0.6",
                },
                method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                return resp.status < 500
        except urllib.error.HTTPError as exc:
            # -- 405 Method Not Allowed = API is reachable (HEAD not supported)
            # -- 401/403 = reachable but bad key — still "up"
            return exc.code < 500
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """Available Claude models via API."""
        return ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]


# -- sig: mgh-6201.cd.bd955f.a109.d03004
