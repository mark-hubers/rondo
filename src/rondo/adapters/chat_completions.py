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

from rondo.engine import ERR_AUTH, ERR_EMPTY_RESPONSE, ERR_PROVIDER, ERR_PROVIDER_DOWN, ERR_RATE_LIMIT, TaskResult
from rondo.provider_base import ProviderAdapter

logger = logging.getLogger(__name__)


# -- RONDO-202 (Finding #221): per-model cost table (USD per 1M tokens)
# -- Source: provider pricing pages as of 2026-04. Update when prices change.
# -- Tuple = (input_cost_per_1m, output_cost_per_1m)
_COST_TABLE: dict[str, tuple[float, float]] = {
    # -- OpenAI
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # -- Grok (xAI)
    "grok-3": (2.00, 10.00),
    "grok-3-mini": (0.30, 0.50),
    # -- Mistral
    "mistral-large-latest": (2.00, 6.00),
    "mistral-small-latest": (0.20, 0.60),
}
# -- Conservative default for unknown models (avoids silent zero-cost)
_DEFAULT_COST = (1.00, 3.00)


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute real cost in USD from token counts using per-model pricing.

    RONDO-202 (Finding #221): replaces hardcoded cost_usd=0.0 with real math.
    Unknown models get _DEFAULT_COST so budget caps still fire.
    """
    input_rate, output_rate = _COST_TABLE.get(model, _DEFAULT_COST)
    return (input_tokens / 1_000_000.0) * input_rate + (output_tokens / 1_000_000.0) * output_rate


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
        max_tokens: int = 8192,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        # -- RONDO-209 #247: default bumped from provider-dependent (~2K-4K)
        # -- to 8K so deep reviews aren't truncated mid-sentence. Budget cap
        # -- still enforces cost limits via compute_cost_usd on actual usage.
        self.max_tokens = max_tokens
        self.name = provider_name

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt via Chat Completions API, return TaskResult.

        RONDO-145 (Finding #211): wraps HTTP call in retry_http() with
        exponential backoff. Circuit breaker trips after 5 failures.
        """
        import urllib.error
        import urllib.request

        from rondo.retry import get_circuit_breaker, retry_http

        task_name = kwargs.get("task_name", f"{self.provider_name}-{model}")
        use_model = model or self.default_model
        start = time.monotonic()

        if not self.api_key:
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_AUTH,
                error_message=f"No API key for {self.provider_name}",
                model=use_model,
                duration_sec=0.0,
            )

        # -- RONDO-145: circuit breaker check
        breaker = get_circuit_breaker()
        if breaker.is_open(self.provider_name):
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER_DOWN,
                error_message=f"{self.provider_name} circuit breaker OPEN — cooldown active",
                model=use_model,
                duration_sec=0.0,
            )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": use_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,  # -- #247: bumped default to 8K
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "rondo/0.7",
        }

        def _do_request() -> dict:
            """Inner request — called by retry_http."""
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        try:
            # -- RONDO-145: retry on transient errors (5xx, 429, network)
            result = retry_http(_do_request, provider_name=self.provider_name)
            breaker.record_success(self.provider_name)
            duration = time.monotonic() - start

            # -- Extract response text
            choices = result.get("choices", [])
            text = choices[0]["message"]["content"] if choices else ""

            # -- REQ-109 req 070: empty response = error
            if not text:
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code=ERR_EMPTY_RESPONSE,
                    error_message=f"{self.provider_name} returned empty response body",
                    model=use_model,
                    duration_sec=duration,
                )

            # -- RONDO-202 (Finding #221): extract real token usage + compute cost
            usage = result.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
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

                invalidate_key(self.provider_name)
            elif exc.code == 429:
                error_code = ERR_RATE_LIMIT
                # -- RONDO-145: record transient failure for circuit breaker
                breaker.record_failure(self.provider_name)
            elif exc.code >= 500:
                error_code = ERR_PROVIDER_DOWN
                # -- RONDO-145: record server error for circuit breaker
                breaker.record_failure(self.provider_name)
            else:
                error_code = ERR_PROVIDER
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
            # -- RONDO-145: network/transient failures count against breaker
            breaker.record_failure(self.provider_name)
            return TaskResult(
                task_name=task_name,
                status="error",
                error_code=ERR_PROVIDER,
                error_message=f"{self.provider_name} error: {exc}",
                model=use_model,
                duration_sec=duration,
            )

    def health(self) -> bool:
        """Check if API endpoint is reachable — REQ-109 req 071.

        GET /v1/models for all providers. If /models returns non-5xx HTTP
        error (404 for Grok, 401 for bad key), the provider is still
        reachable — the network path works. Only 5xx or network errors
        mean "down".
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
