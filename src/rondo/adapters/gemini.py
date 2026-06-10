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
import urllib.error
import urllib.request
from typing import Any

from rondo.engine import TaskResult
from rondo.provider_base import ProviderAdapter

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

    def _read_timeout(self, model: str, **kwargs: Any) -> int:
        """Resolve this dispatch's HTTP read-timeout — RONDO-355 / REQ-109 req 212.

        Was a hardcoded 120s that killed gemini-pro on long prompts (USH, live).
        Patient by default; COALESCE: per-dispatch `read_timeout` → config
        [timeouts] → built-in thinking default.
        """
        from rondo.adapters.timeouts import resolve_read_timeout  # pylint: disable=import-outside-toplevel

        return resolve_read_timeout(
            thinking=True,
            effort=str(kwargs.get("effort", "high")),
            per_dispatch=kwargs.get("read_timeout"),
        )

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to Gemini generateContent API, return TaskResult.

        RONDO-204 (Finding #234): wraps HTTP call in retry_http + circuit breaker
        for consistency with ChatCompletionsAdapter.
        """
        from rondo.adapters.http_skeleton import (  # pylint: disable=import-outside-toplevel
            HttpDispatchPlan,
            dispatch_via_http,
        )

        task_name = kwargs.get("task_name", f"gemini-{model}")
        use_model = model or self.default_model

        # -- Gemini API: key in URL, not header (the skeleton REDACTS it from
        # -- any error-body snippet — RONDO-216 C4, now shared by all adapters)
        url = f"{self.base_url}/models/{use_model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,  # -- #247
            },
        }

        # -- RONDO-355: resolve read timeout (was hardcoded 120 — killed
        # -- gemini-pro on long prompts live via USH). Patient default.
        read_to = self._read_timeout(use_model, **kwargs)

        def _do_request() -> dict:
            """Inner HTTP call — wrapped by retry_http (via the skeleton)."""
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "rondo/0.7",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=read_to) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        def _extract_text(result: dict) -> str:
            # -- Gemini's unique nesting; absent path = empty (req 070 gate)
            try:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return ""

        def _extract_tokens(result: dict) -> tuple[int, int]:
            usage = result.get("usageMetadata", {})
            # -- RONDO-380 (cursor holistic #9): Gemini 2.5 bills THINKING tokens
            # -- as output but reports them in a separate thoughtsTokenCount —
            # -- excluding them undercounted cost on exactly the expensive
            # -- thinking runs and fed the budget gate (RONDO-373) low numbers.
            return (
                usage.get("promptTokenCount", 0),
                usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
            )

        return dispatch_via_http(
            HttpDispatchPlan(
                provider="gemini",
                label="Gemini",
                task_name=task_name,
                model=use_model,
                do_request=_do_request,
                extract_text=_extract_text,
                extract_tokens=_extract_tokens,
                api_key=self.api_key,
            )
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


# -- sig: mgh-6201.cd.bd955f.f3f3.0d860f
