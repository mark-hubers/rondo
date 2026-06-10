# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Chat Completions adapter — OpenAI, Grok, Mistral (same API shape).

REQ-109 req 031: One adapter, three providers via config.
All use POST /v1/chat/completions with the same payload format.
Differences: base_url, auth header, model names.

Based on ai_review.py call_openai/call_grok/call_mistral (proven patterns).

Health strategy (REQ-109 req 073, RONDO-357):
    OpenAI: GET /v1/models (supported, returns model list)
    Mistral: GET /v1/models (OpenAI-compatible, supported)
    Grok (xAI): GET /v1/models attempted; a 404 endpoint quirk with a GOOD key
    is "reachable" (network path works). But 401/403 = a DEAD key = UNHEALTHY
    (a green signal over broken auth is dishonest; 5xx/network = down too).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from fnmatch import fnmatch
from typing import Any

from rondo.engine import TaskResult
from rondo.provider_base import ProviderAdapter

logger = logging.getLogger(__name__)

# -- REQ-109 req 209 (RONDO-297): reasoning-class models reject max_tokens
# -- (require max_completion_tokens) and reject temperature. OpenAI naming
# -- only — grok/mistral names never match. Config-overridable via constructor.
DEFAULT_REASONING_MODEL_PATTERNS: tuple[str, ...] = ("gpt-5*", "o1*", "o3*", "o4*", "o5*")


# -- RONDO-202 (Finding #221): per-model cost table (USD per 1M tokens)
# -- Source: provider pricing pages as of 2026-04. Update when prices change.
# -- Tuple = (input_cost_per_1m, output_cost_per_1m)
_COST_TABLE: dict[str, tuple[float, float]] = {
    # -- (input_rate, output_rate) per 1M tokens
    # -- OpenAI
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # -- Grok (xAI)
    "grok-3": (2.00, 10.00),
    "grok-3-mini": (0.30, 0.50),
    # -- Mistral
    "mistral-large-latest": (2.00, 6.00),
    "mistral-medium-latest": (0.40, 1.00),
    "mistral-small-latest": (0.20, 0.60),
    # -- Gemini (RONDO-214 C-1: was hardcoded 0.0 in gemini.py)
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-flash-lite": (0.01, 0.04),
    # -- Anthropic (RONDO-214 C-1: was hardcoded 0.0 in anthropic_api.py)
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
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
        reasoning_models: list[str] | None = None,  # -- REQ-109 req 209: pattern override
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
        self.reasoning_models: list[str] = (
            list(reasoning_models) if reasoning_models is not None else list(DEFAULT_REASONING_MODEL_PATTERNS)
        )

    def is_reasoning_model(self, model: str) -> bool:
        """Classify a model as reasoning-class — REQ-109 req 209 (RONDO-297).

        Reasoning-class ChatCompletions models (gpt-5*/o*-series) require
        max_completion_tokens (max_tokens rejected, HTTP 400) and reject
        temperature. fnmatch patterns, constructor-overridable.
        """
        return any(fnmatch(model, pattern) for pattern in self.reasoning_models)

    def _read_timeout(self, model: str, **kwargs: Any) -> int:
        """Resolve this dispatch's HTTP read-timeout — RONDO-355 / REQ-109 req 212.

        Was a hardcoded 120s that killed slow models (gpt-5.5/gemini) on long
        prompts. Defaults PATIENT (a long ceiling is safe — fast models still
        return in seconds; a short ceiling is the bug). COALESCE: per-dispatch
        `read_timeout` kwarg → config [timeouts] → built-in thinking default.
        """
        from rondo.adapters.timeouts import resolve_read_timeout  # pylint: disable=import-outside-toplevel

        return resolve_read_timeout(
            thinking=True,
            effort=str(kwargs.get("effort", "high")),
            per_dispatch=kwargs.get("read_timeout"),
        )

    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt via Chat Completions API, return TaskResult.

        RONDO-381: reliability pipeline (key gate, breaker, retry_http, empty
        gate, cost, HTTPError triage with redacted body) lives in the shared
        http_skeleton — this adapter supplies only its request + parsing.
        """
        from rondo.adapters.http_skeleton import (  # pylint: disable=import-outside-toplevel
            HttpDispatchPlan,
            dispatch_via_http,
        )

        task_name = kwargs.get("task_name", f"{self.provider_name}-{model}")
        use_model = model or self.default_model

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        if self.is_reasoning_model(use_model):
            # -- REQ-109 req 209 (RONDO-297): gpt-5*/o*-series contract.
            # -- max_tokens is REJECTED ("Use 'max_completion_tokens' instead",
            # -- HTTP 400, live gpt-5.5 canary 2026-06-05); temperature rejected too.
            payload["max_completion_tokens"] = self.max_tokens
        else:
            # -- classic (gpt-4.x era / grok / mistral) keeps the proven payload
            payload["temperature"] = self.temperature
            payload["max_tokens"] = self.max_tokens  # -- #247: bumped default to 8K
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "rondo/0.7",
        }

        # -- RONDO-355: resolve the read timeout (was hardcoded 120 — killed
        # -- gpt-5.5/gemini on long prompts live via USH while fast mistral
        # -- squeaked under). Patient by default; config/per-dispatch override.
        read_to = self._read_timeout(use_model, **kwargs)

        def _do_request() -> dict:
            """Inner request — called by retry_http (via the skeleton)."""
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=read_to) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        def _extract_text(result: dict[str, Any]) -> str:
            choices = result.get("choices", [])
            return choices[0]["message"]["content"] if choices else ""

        def _extract_tokens(result: dict[str, Any]) -> tuple[int, int]:
            # -- RONDO-202 #221: real token usage (completion_tokens already
            # -- includes reasoning tokens on OpenAI-compatible APIs)
            usage = result.get("usage", {}) or {}
            return int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)

        return dispatch_via_http(
            HttpDispatchPlan(
                provider=self.provider_name,
                label=self.provider_name,
                task_name=task_name,
                model=use_model,
                do_request=_do_request,
                extract_text=_extract_text,
                extract_tokens=_extract_tokens,
                api_key=self.api_key,
            )
        )

    def health(self) -> bool:
        """Check if API endpoint is reachable — REQ-109 req 071.

        GET /v1/models for all providers. If /models returns non-5xx HTTP
        error (404 for Grok, 401 for bad key), the provider is still
        reachable — the network path works. Only 5xx or network errors
        mean "down".
        """
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
            # -- RONDO-357: a dead/invalid KEY (401/403) is NOT healthy — green
            # -- health over broken auth is dishonest (next dispatch dies
            # -- ERR_AUTH). But an endpoint quirk (e.g. Grok 404s on /models
            # -- with a GOOD key) is still reachable. Split the two.
            if exc.code in (401, 403):
                return False
            if exc.code < 500:
                # -- other 4xx (404 endpoint quirk) = API reachable, key fine
                return True
            return False
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """List available models from provider."""
        return [self.default_model]


# -- sig: mgh-6201.cd.bd955f.7c49.e79b4a
