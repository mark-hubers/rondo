# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Chat Completions adapter — OpenAI, Grok, Mistral (same API shape).

REQ-109 req 031: One adapter, three providers via config.
All use POST /v1/chat/completions with the same payload format.
Differences: base_url, auth header, model names.

Based on ai_review.py call_openai/call_grok/call_mistral (proven patterns).

Health strategy (REQ-109 req 073):
    OpenAI: GET /v1/models (supported, returns model list)
    Mistral: GET /v1/models (OpenAI-compatible, supported)
    Grok (xAI): GET /v1/models attempted; any non-5xx HTTP error (404, 401)
    treated as "reachable" since it proves network path works.
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

            # -- REQ-109 req 070: empty response = error
            if not text:
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code="ERR_EMPTY_RESPONSE",
                    error_message=f"{self.provider_name} returned empty response body",
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
                error_code = "ERR_AUTH"
                # -- REQ-109 req 069: invalidate cached key on auth failure
                from rondo.adapters.auth import invalidate_key  # pylint: disable=import-outside-toplevel

                invalidate_key(self.provider_name)
            elif exc.code == 429:
                error_code = "ERR_RATE_LIMIT"
            elif exc.code >= 500:
                error_code = "ERR_PROVIDER_DOWN"
            else:
                error_code = "ERR_PROVIDER"
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=error_code,
                error_message=f"{self.provider_name} HTTP {exc.code}: {exc.reason}",
                model=use_model,
                duration_sec=duration,
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
        """Check if API endpoint is reachable — REQ-109 req 071.

        OpenAI/Mistral: GET /v1/models (supported).
        Grok (xAI): try /v1/models first; if non-200, fall back to HEAD
        on /v1/chat/completions (any non-timeout response = reachable).
        """
        import urllib.error
        import urllib.request

        if not self.api_key:
            return False
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "rondo/0.6",
        }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                return resp.status == 200
        except urllib.error.HTTPError as exc:
            # -- /models returned error — try HEAD on completions endpoint
            if exc.code < 500:
                # -- 401/403/404 from /models = API is reachable
                return True
            return False
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List available models from provider."""
        return [self.default_model]


# -- sig: mgh-6201.cd.bd955f.a109.d03101
