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

Thinking-default models (REQ-109 reqs 200-205, RONDO-296):
    Opus 4.8-era models use adaptive thinking. Their request contract differs
    from classic (4.6-era) models:
      - temperature/top_p/top_k are REJECTED (HTTP 400) — omitted entirely
      - thinking: {"type": "adaptive"} requested (manual budget_tokens rejected)
      - output_config: {"effort": low|medium|high|xhigh|max} controls depth
    Classic models keep the proven temperature payload (req 202).

anthropic-version (REQ-109 req 206): "2023-06-01" verified current as of
    2026-06-03 — new fields (output_config, adaptive thinking) gate on the
    MODEL, not the version date. Do not bump without re-verifying docs.
"""

from __future__ import annotations

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from fnmatch import fnmatch
from typing import Any

from rondo.engine import (
    ERR_AUTH,
    ERR_EMPTY_RESPONSE,
    ERR_PROVIDER,
    ERR_PROVIDER_DOWN,
    ERR_RATE_LIMIT,
    ERR_STREAM_DISCONNECT,
    TaskResult,
)
from rondo.provider_base import ProviderAdapter
from rondo.retry import get_circuit_breaker, retry_http

logger = logging.getLogger(__name__)

# -- REQ-109 req 200 (RONDO-296): models that use adaptive thinking (4.8-era contract).
# -- Config-overridable via constructor; these are the built-in defaults.
DEFAULT_THINKING_MODEL_PATTERNS: tuple[str, ...] = ("claude-opus-4-8", "claude-*-4-8")

# -- REQ-109 req 214 (RONDO-310): with streaming, the watchdog is per-EVENT
# -- silence, not total duration — a model may think 30 minutes safely as
# -- long as SSE events keep flowing. 120s of true silence = dead connection.
STREAM_EVENT_WATCHDOG_SEC = 120


def consume_sse_stream(lines: Any) -> dict[str, Any]:
    """Consume an Anthropic SSE stream into the non-streaming result shape.

    REQ-109 req 214 (RONDO-310). Accumulates text deltas (thinking deltas are
    metadata, not output), captures usage tokens and stop_reason. Returning
    the SAME shape as the non-streaming API means zero downstream changes.
    """
    text_parts: list[str] = []
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    stop_reason: str | None = None
    disconnect_error = ""
    try:
        for raw in lines:
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            etype = event.get("type", "")
            if etype == "message_start":
                usage["input_tokens"] = event.get("message", {}).get("usage", {}).get("input_tokens", 0)
            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
            elif etype == "message_delta":
                stop_reason = event.get("delta", {}).get("stop_reason") or stop_reason
                out = event.get("usage", {}).get("output_tokens")
                if out:
                    usage["output_tokens"] = out
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        # -- REQ-109 req 215 (RONDO-323): a dropped connection must never
        # -- evaporate accumulated content. Real incident 2026-06-05: a
        # -- max-effort stream died at ~1802s (~30-min ceiling suspected)
        # -- and lost everything. Return the partials; dispatch classifies
        # -- ERR_STREAM_DISCONNECT (transient) with raw_output preserved.
        disconnect_error = f"{type(exc).__name__}: {exc}"
        stop_reason = "disconnected"
        logger.warning("-WARNING- SSE stream disconnected after %d delta(s): %s", len(text_parts), disconnect_error)
    return {
        "content": [{"type": "text", "text": "".join(text_parts)}],
        "usage": usage,
        "stop_reason": stop_reason,
        "disconnect_error": disconnect_error,
    }


def _best_of_disconnects(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Pick the better of two stream results — RONDO-334 (SOP-106).

    A clean second attempt always wins. If BOTH disconnected, keep whichever
    accumulated MORE text — 20 minutes of partial thinking beats 2.
    """
    if not second.get("disconnect_error"):
        return second

    def _text(result: dict[str, Any]) -> str:
        return "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")

    return first if len(_text(first)) >= len(_text(second)) else second


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
        effort: str = "high",  # -- REQ-109 req 205: adapter-level effort default
        thinking_models: list[str] | None = None,  # -- REQ-109 req 200: pattern override
        stream_reattempt: bool = False,  # -- RONDO-378: opt-in disconnect re-attempt (r213)
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        self.effort = effort
        # -- RONDO-378 (REQ-109 r213 MUST "never silent spend"): the RONDO-334
        # -- automatic disconnect re-attempt is now OPT-IN, default OFF. The
        # -- deliberate retry belongs to the caller (rondo retry) by choice.
        self.stream_reattempt = stream_reattempt
        self.thinking_models: list[str] = (
            list(thinking_models) if thinking_models is not None else list(DEFAULT_THINKING_MODEL_PATTERNS)
        )

    def is_thinking_model(self, model: str) -> bool:
        """Classify a model as thinking-default — REQ-109 req 200 (RONDO-296).

        Thinking-default models (Opus 4.8 era) reject temperature/top_p/top_k
        and use adaptive thinking + output_config.effort. fnmatch patterns so
        config can say "claude-*-4-8" once instead of listing every variant.
        """
        return any(fnmatch(model, pattern) for pattern in self.thinking_models)

    def read_timeout_for(
        self, model: str, effort: str, *, per_dispatch: Any = None, timeouts_cfg: dict[str, Any] | None = None
    ) -> int:
        """Resolve this dispatch's HTTP read-timeout — REQ-109 req 212.

        COALESCE: per-dispatch → config [timeouts] → built-in defaults.
        `timeouts_cfg` is injectable for hermetic tests.
        """
        from rondo.adapters.timeouts import resolve_read_timeout  # pylint: disable=import-outside-toplevel

        return resolve_read_timeout(
            thinking=self.is_thinking_model(model),
            effort=effort,
            per_dispatch=per_dispatch,
            timeouts_cfg=timeouts_cfg,
        )

    def _maybe_reattempt(self, result: dict[str, Any], do_request: Any, opt_in: bool) -> tuple[dict[str, Any], bool]:
        """Disconnect handling: opt-in re-attempt or honest no-retry — RONDO-378.

        REQ-109 r213 (MUST): "One visible retry BY CHOICE, never silent spend."
        Default (opt_in False) returns the partial untouched — the caller
        retries deliberately via `rondo retry`. Opt-in fires ONE extra attempt
        (RONDO-334 semantics: keep whichever partial accumulated more) and the
        caller surfaces it in the result envelope. Returns (result, reattempted).
        """
        if not result.get("disconnect_error"):
            return result, False
        if not opt_in:
            logger.warning(
                "-WARNING- stream disconnected — NOT re-attempting (REQ-109 r213: "
                "opt in via stream_reattempt=True, or retry by choice with rondo retry)"
            )
            return result, False
        logger.warning("-WARNING- stream disconnected — opt-in re-attempt firing (RONDO-334/378)")
        second = retry_http(do_request, provider_name="anthropic")
        return _best_of_disconnects(result, second), True

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

        # -- REQ-109 req 212 (RONDO-318): read-timeout is config-driven.
        # -- COALESCE: per-dispatch timeout_sec → [timeouts] config → defaults
        # -- (classic 120s; thinking ≤high 600s; xhigh/max 900s — req 211).
        http_timeout = self.read_timeout_for(
            use_model, str(kwargs.get("effort") or self.effort or ""), per_dispatch=kwargs.get("timeout_sec")
        )
        url = f"{self.base_url}/messages"
        payload: dict[str, Any] = {
            "model": use_model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        if self.is_thinking_model(use_model):
            # -- REQ-109 reqs 201/203/204 (RONDO-296): thinking-default contract.
            # -- temperature/top_p/top_k are REJECTED by 4.8-era models (HTTP 400
            # -- "temperature may only be set to 1 when thinking is enabled") — omit.
            # -- Adaptive thinking only; manual budget_tokens is also rejected.
            # -- Effort COALESCE (req 205): per-dispatch → adapter default → "high".
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": kwargs.get("effort") or self.effort or "high"}
            # -- REQ-109 req 210 (RONDO-308 learn-by-use #2): adaptive thinking
            # -- tokens COUNT AGAINST max_tokens. At max effort on a long task an
            # -- 8K cap can be consumed entirely by thinking → empty body
            # -- (ERR_EMPTY_RESPONSE, real incident 2026-06-05). Floor 32K.
            effort_val = str(payload["output_config"]["effort"])
            floor = 64000 if effort_val in ("xhigh", "max") else 32000
            payload["max_tokens"] = max(self.max_tokens, floor)
            # -- REQ-109 req 214 (RONDO-310): thinking models STREAM. With SSE
            # -- the timeout becomes per-EVENT silence (the STD-108 watchdog
            # -- idiom) — arbitrary thinking time is safe; 3 real max-effort
            # -- failures proved non-streaming cannot tell thinking from hung.
            payload["stream"] = True
        else:
            # -- REQ-109 req 202: classic (4.6-era) models keep the proven payload
            payload["temperature"] = self.temperature
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "rondo/0.7",
        }

        def _do_request() -> dict:
            """Inner HTTP call — wrapped by retry_http.

            Streaming (req 214): urllib's timeout applies per socket READ, so
            iterating SSE lines gives a per-event watchdog for free — the
            connection may live for 30+ minutes as long as events keep flowing.
            """
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            if payload.get("stream"):
                with urllib.request.urlopen(req, timeout=STREAM_EVENT_WATCHDOG_SEC) as resp:  # nosec B310
                    return consume_sse_stream(resp)
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        try:
            result = retry_http(_do_request, provider_name="anthropic")
            # -- RONDO-334: retry_http only retries on EXCEPTIONS; a mid-stream
            # -- disconnect RETURNS (RONDO-323 preserves the partial). RONDO-378:
            # -- the re-attempt is OPT-IN (REQ-109 r213 — never silent spend).
            result, reattempted = self._maybe_reattempt(
                result, _do_request, bool(kwargs.get("stream_reattempt", self.stream_reattempt))
            )
            breaker.record_success("anthropic")
            duration = time.monotonic() - start

            # -- Extract text from Anthropic's response format
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # -- REQ-109 req 215 (RONDO-323): mid-stream disconnect — partial
            # -- content PRESERVED in raw_output, classified transient so the
            # -- retry path can re-dispatch. Checked BEFORE the empty-response
            # -- gate: a zero-text disconnect is a disconnect, not "empty".
            if result.get("disconnect_error"):
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code=ERR_STREAM_DISCONNECT,
                    error_message=(
                        f"SSE stream disconnected after {duration:.0f}s with "
                        f"{len(text)} chars accumulated ({result['disconnect_error']}) — "
                        f"partial output preserved; ~30-min connection ceiling suspected "
                        f"for very long thinking runs (REQ-109 req 215)"
                        + (" — after one opt-in re-attempt (RONDO-378)" if reattempted else "")
                    ),
                    raw_output=text,
                    model=use_model,
                    duration_sec=duration,
                    auth_mode="api",
                    metrics={"stream_reattempts": 1} if reattempted else {},
                )

            # -- REQ-109 req 070: empty response = error
            if not text:
                return TaskResult(
                    task_name=task_name,
                    status="error",
                    error_code=ERR_EMPTY_RESPONSE,
                    error_message=(
                        f"Anthropic returned empty response body "
                        f"(stop_reason={result.get('stop_reason')!r} — if 'max_tokens', "
                        f"thinking consumed the output budget; consider streaming, REQ-109 Q1)"
                    ),
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
                # -- RONDO-378: an opt-in re-attempt is surfaced, never silent (r213)
                metrics={"stream_reattempts": 1} if reattempted else {},
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
            # -- STD-108 reqs 011-014 (RONDO-296): include response body snippet.
            # -- Port of RONDO-287 (Finding #270) pattern from gemini/chat_completions —
            # -- this was the ONE adapter missing it. The 400 body names the exact
            # -- cause (e.g. "temperature may only be set to 1 when thinking is
            # -- enabled"); without it diagnosis is archaeology. Best-effort: a
            # -- failed read falls back to the status line (req 014).
            body_snippet = ""
            try:
                body_bytes = exc.read() or b""
                body_snippet = body_bytes.decode("utf-8", errors="replace")[:500]
                if self.api_key and self.api_key in body_snippet:
                    body_snippet = body_snippet.replace(self.api_key, "[REDACTED]")
            except (OSError, AttributeError):
                body_snippet = ""
            err_msg = f"Anthropic HTTP {exc.code}: {exc.reason}"
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
            # -- RONDO-375 (cursor holistic #4): mirror the RONDO-357 contract —
            # -- a dead/invalid KEY (401/403) is NOT healthy; green health over
            # -- broken auth is dishonest (next dispatch dies ERR_AUTH). An
            # -- endpoint quirk (405 on HEAD, 404, 429) is still reachable with
            # -- a good key. This adapter was the missed copy-paste twin.
            if exc.code in (401, 403):
                return False
            return exc.code < 500
        except (urllib.error.URLError, OSError):
            return False

    def models(self) -> list[str]:
        """Available Claude models via API — REQ-109 req 207: include active generation.

        A list that omits the routed best_model (4-8) misleads health/benchmark
        tooling into thinking the active model is unavailable.
        """
        return ["claude-opus-4-8", "claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]


# -- sig: mgh-6201.cd.bd955f.94f4.2b7492
