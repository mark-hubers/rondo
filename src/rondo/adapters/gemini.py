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
from typing import Any

from rondo.engine import ERR_AUTH, ERR_EMPTY_RESPONSE, ERR_PROVIDER, ERR_PROVIDER_DOWN, ERR_RATE_LIMIT, TaskResult
from rondo.providers import ProviderAdapter

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
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Gemini generateContent API, return TaskResult."""
        import urllib.error
        import urllib.request

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

        # -- Gemini API: key in URL, not header
        url = f"{self.base_url}/models/{use_model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature},
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "rondo/0.6",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                result = json.loads(resp.read().decode("utf-8"))

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

            return TaskResult(
                task_name=task_name,
                status="done",
                raw_output=text,
                model=use_model,
                duration_sec=duration,
                auth_mode="api",
                cost_usd=0.0,
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
            elif exc.code >= 500:
                error_code = ERR_PROVIDER_DOWN
            else:
                error_code = ERR_PROVIDER
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=error_code,
                error_message=f"Gemini HTTP {exc.code}: {exc.reason}",
                model=use_model,
                duration_sec=duration,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            duration = time.monotonic() - start
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER,
                error_message=f"Gemini error: {exc}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if Gemini API is reachable."""
        import urllib.error
        import urllib.request

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
