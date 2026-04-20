# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Gemini adapter — Google Gemini generateContent API.

REQ-109 req 030. Unique API shape (not Chat Completions).
Based on ai_review.py call_gemini (proven pattern, Session 86).

Key differences from Chat Completions:
- Auth: API key in URL query param (?key=), not Bearer header
- Payload: systemInstruction + contents, not messages array
- Response: candidates[0].content.parts[0].text, not choices[0].message.content

Health strategy (REQ-109 req 073):
    GET /v1beta/models?key=KEY — Gemini exposes a models endpoint.
    Returns 200 with model list if reachable and key valid.
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


class GeminiAdapter(ProviderAdapter):
    """Gemini adapter — dispatches to Google Gemini generateContent API."""

    name: str = "gemini"

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "gemini-2.5-flash",
        temperature: float = 0.2,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        max_output_tokens: int = 8192,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")
        # -- RONDO-209 #247: default bumped so deep reviews aren't truncated
        self.max_output_tokens = max_output_tokens

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Gemini generateContent API, return TaskResult.

        RONDO-204 (Finding #234): wraps HTTP call in retry_http + circuit breaker
        for consistency with ChatCompletionsAdapter.
        """
        task_name = kwargs.get("task_name", f"gemini-{model}")
        use_model = model or self.default_model
        start = time.monotonic()

        if not self.api_key:
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_AUTH,
                error_message="No API key for Gemini",
                model=use_model,
                duration_sec=0.0,
            )

        # -- RONDO-204: circuit breaker check
        breaker = get_circuit_breaker()
        if breaker.is_open("gemini"):
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER_DOWN,
                error_message="gemini circuit breaker OPEN — cooldown active",
                model=use_model,
                duration_sec=0.0,
            )

        # -- Gemini API: key in URL, not header
        url = f"{self.base_url}/models/{use_model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,  # -- #247
            },
        }

        def _do_request() -> dict:
            """Inner HTTP call — wrapped by retry_http."""
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "rondo/0.7",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        try:
            result = retry_http(_do_request, provider_name="gemini")
            breaker.record_success("gemini")
            duration = time.monotonic() - start

            # -- Extract response text (Gemini's unique structure)
            try:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                text = ""

            # -- REQ-109 req 070: empty response = error
            if not text:
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code=ERR_EMPTY_RESPONSE,
                    error_message="Gemini returned empty response body",
                    model=use_model,
                    duration_sec=duration,
                )

            # -- RONDO-214 C-1: compute real cost from token counts (was 0.0)
            from rondo.adapters.chat_completions import compute_cost_usd  # pylint: disable=import-outside-toplevel

            usage = result.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)
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

                invalidate_key("gemini")
            elif exc.code == 429:
                error_code = ERR_RATE_LIMIT
                breaker.record_failure("gemini")
            elif exc.code >= 500:
                error_code = ERR_PROVIDER_DOWN
                breaker.record_failure("gemini")
            else:
                error_code = ERR_PROVIDER
            # -- RONDO-287 (Finding #270): include response body snippet on 4xx/5xx.
            # -- Gemini's 404 "model not found" body has the real cause; without it
            # -- the error is just "HTTP 404: Not Found" which is useless for debug.
            # -- RONDO-216 C4: also redact API key from body (Gemini key is in URL).
            body_snippet = ""
            try:
                body_bytes = exc.read() or b""
                body_snippet = body_bytes.decode("utf-8", errors="replace")[:500]
                if self.api_key and self.api_key in body_snippet:
                    body_snippet = body_snippet.replace(self.api_key, "[REDACTED]")
            except (OSError, AttributeError):
                body_snippet = ""
            err_msg = f"Gemini HTTP {exc.code}: {exc.reason}"
            if body_snippet:
                err_msg = f"{err_msg} | body: {body_snippet}"
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=error_code,
                error_message=err_msg,
                model=use_model,
                duration_sec=duration,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            duration = time.monotonic() - start
            breaker.record_failure("gemini")
            # -- RONDO-216 C4 (Cursor finding): redact API key from exception text.
            # -- URLError/OSError can include the full URL with ?key=SECRET.
            err_text = str(exc)
            if self.api_key and self.api_key in err_text:
                err_text = err_text.replace(self.api_key, "[REDACTED]")
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER,
                error_message=f"Gemini error: {err_text}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if Gemini API is reachable."""
        if not self.api_key:
            return False
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "rondo/0.6"})
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List available Gemini models."""
        return [self.default_model]


# -- sig: mgh-6201.cd.bd955f.a109.d03003
