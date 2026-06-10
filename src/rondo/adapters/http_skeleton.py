# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared HTTP dispatch skeleton — RONDO-381 (cursor holistic #6, checklist 11/12).

Rondo-REQ-109 reqs 001/068/069/070: every HTTP adapter runs the SAME
reliability pipeline. Before this module, gemini / chat_completions /
anthropic_api triplicated it (~150 lines x 3) and ollama had none of it —
and the triplication bred real drift bugs: the RONDO-357 health fix landed
in one adapter and missed its twin (RONDO-375), the API-key body-snippet
redaction existed only in gemini, the Windows fcntl guard missed retry.py
(RONDO-372). One skeleton = one place to fix = no more twins BY CONSTRUCTION.

The pipeline (shared, in order):
    1. missing-key gate            -> ERR_AUTH (skipped for keyless providers)
    2. circuit-breaker-open gate   -> ERR_PROVIDER_DOWN (no HTTP fired)
    3. retry_http(do_request)      -> transient retry + Retry-After + per-provider gate
    4. post_retry hook             -> adapter-specific (anthropic disconnect re-attempt)
    5. breaker.record_success
    6. extract_text + early_result hook (anthropic disconnect branch)
    7. empty-response gate         -> ERR_EMPTY_RESPONSE (req 070)
    8. token extraction + cost     -> compute_cost_usd
    9. HTTPError triage            -> 401/403 AUTH + invalidate_key, 429 RATE + breaker,
                                      5xx DOWN + breaker, else PROVIDER; body snippet
                                      with the API key REDACTED (RONDO-216 C4 — now
                                      for EVERY adapter, was gemini-only)
   10. network/parse errors        -> breaker.record_failure + ERR_PROVIDER

What stays in each adapter: request building (URL, auth placement, payload
contract), response parsing (text + token fields), and any provider-unique
flow (anthropic streaming/re-attempt) — supplied as plan hooks.

Import direction: adapters/http_skeleton.py -> engine, retry (same layer
edges every adapter already has; provider_base stays pure).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rondo.engine import (
    ERR_AUTH,
    ERR_EMPTY_RESPONSE,
    ERR_PROVIDER,
    ERR_PROVIDER_DOWN,
    ERR_RATE_LIMIT,
    TaskResult,
)
from rondo.retry import get_circuit_breaker, retry_http

logger = logging.getLogger(__name__)


@dataclass
class HttpDispatchPlan:  # pylint: disable=too-many-instance-attributes
    """Everything provider-specific the skeleton needs for one dispatch.

    The hooks keep adapters declarative: build the request, parse the
    response, and (rarely) intercept the flow — the reliability pipeline
    itself lives in dispatch_via_http and is identical for every provider.
    """

    provider: str  # -- breaker + retry_http + invalidate_key name (lowercase)
    label: str  # -- human-facing name in error messages ("Gemini", "openai")
    task_name: str
    model: str
    do_request: Callable[[], dict[str, Any]]  # -- ONE HTTP attempt (urlopen inside)
    extract_text: Callable[[dict[str, Any]], str]
    # -- (input_tokens, output_tokens) from the raw result; None = costless (ollama)
    extract_tokens: Callable[[dict[str, Any]], tuple[int, int]] | None = None
    auth_mode: str = "api"
    api_key: str = ""  # -- used for the missing-key gate AND snippet redaction
    requires_key: bool = True
    # -- anthropic: disconnect re-attempt; returns (result, reattempted)
    post_retry: Callable[[dict[str, Any]], tuple[dict[str, Any], bool]] | None = None
    # -- anthropic: disconnect branch — may short-circuit with its own TaskResult
    early_result: Callable[[dict[str, Any], str, float, bool], TaskResult | None] | None = None
    # -- custom empty-response message (anthropic explains stop_reason)
    empty_message: Callable[[dict[str, Any]], str] | None = None
    extra_done_metrics: dict[str, Any] = field(default_factory=dict)


def _redacted_body_snippet(exc: urllib.error.HTTPError, api_key: str) -> str:
    """Read up to 500 chars of the error body, with the API key scrubbed.

    RONDO-287 #270: the body carries the real cause (bad model name, malformed
    payload). RONDO-216 C4 / RONDO-381: the key is redacted for EVERY adapter
    now — it was gemini-only (key-in-URL providers can echo it back), a
    triplication drift bug.
    """
    try:
        body = (exc.read() or b"").decode("utf-8", errors="replace")[:500]
    except (OSError, AttributeError):
        return ""
    if api_key and api_key in body:
        body = body.replace(api_key, "[REDACTED]")
    return body


def _http_error_result(plan: HttpDispatchPlan, exc: urllib.error.HTTPError, duration: float) -> TaskResult:
    """Shared HTTPError triage — REQ-109 req 068/069 (one copy, no twins)."""
    breaker = get_circuit_breaker()
    if exc.code in (401, 403):
        error_code = ERR_AUTH
        # -- REQ-109 req 069: invalidate cached key on auth failure
        from rondo.adapters.auth import invalidate_key  # pylint: disable=import-outside-toplevel

        invalidate_key(plan.provider)
    elif exc.code == 429:
        error_code = ERR_RATE_LIMIT
        breaker.record_failure(plan.provider)
    elif exc.code >= 500:
        error_code = ERR_PROVIDER_DOWN
        breaker.record_failure(plan.provider)
    else:
        error_code = ERR_PROVIDER
    err_msg = f"{plan.label} HTTP {exc.code}: {exc.reason}"
    body_snippet = _redacted_body_snippet(exc, plan.api_key)
    if body_snippet:
        err_msg = f"{err_msg} | body: {body_snippet}"
    return TaskResult(
        task_name=plan.task_name,
        status="error",
        error_code=error_code,
        error_message=err_msg,
        model=plan.model,
        duration_sec=duration,
    )


def _done_result(
    plan: HttpDispatchPlan, text: str, result: dict[str, Any], duration: float, metrics: dict[str, Any]
) -> TaskResult:
    """Build the success TaskResult: tokens -> cost -> done (req 004)."""
    cost = 0.0
    if plan.extract_tokens is not None:
        from rondo.adapters.chat_completions import compute_cost_usd  # pylint: disable=import-outside-toplevel

        input_tokens, output_tokens = plan.extract_tokens(result)
        cost = compute_cost_usd(plan.model, input_tokens, output_tokens)
    return TaskResult(
        task_name=plan.task_name,
        status="done",
        raw_output=text,
        model=plan.model,
        duration_sec=duration,
        auth_mode=plan.auth_mode,
        cost_usd=cost,
        metrics=metrics,
    )


def dispatch_via_http(plan: HttpDispatchPlan) -> TaskResult:
    """Run one provider dispatch through the shared reliability pipeline.

    See the module docstring for the 10-step pipeline. Behavior-preserving
    extraction of the previously-triplicated adapter flow (RONDO-381).
    """
    start = time.monotonic()

    if plan.requires_key and not plan.api_key:
        return TaskResult(
            task_name=plan.task_name,
            status="error",
            error_code=ERR_AUTH,
            error_message=f"No API key for {plan.label}",
            model=plan.model,
            duration_sec=0.0,
        )

    breaker = get_circuit_breaker()
    if breaker.is_open(plan.provider):
        return TaskResult(
            task_name=plan.task_name,
            status="error",
            error_code=ERR_PROVIDER_DOWN,
            error_message=f"{plan.provider} circuit breaker OPEN — cooldown active",
            model=plan.model,
            duration_sec=0.0,
        )

    try:
        result = retry_http(plan.do_request, provider_name=plan.provider)
        reattempted = False
        if plan.post_retry is not None:
            result, reattempted = plan.post_retry(result)
        breaker.record_success(plan.provider)
        duration = time.monotonic() - start

        text = plan.extract_text(result)
        if plan.early_result is not None:
            early = plan.early_result(result, text, duration, reattempted)
            if early is not None:
                return early

        if not text:
            msg = (
                plan.empty_message(result)
                if plan.empty_message is not None
                else f"{plan.label} returned empty response body"
            )
            return TaskResult(
                task_name=plan.task_name,
                status="error",
                error_code=ERR_EMPTY_RESPONSE,
                error_message=msg,
                model=plan.model,
                duration_sec=duration,
            )

        metrics = dict(plan.extra_done_metrics)
        if reattempted:
            # -- RONDO-378: an opt-in re-attempt is surfaced, never silent (r213)
            metrics["stream_reattempts"] = 1
        return _done_result(plan, text, result, duration, metrics)
    except urllib.error.HTTPError as exc:
        return _http_error_result(plan, exc, time.monotonic() - start)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        # -- network/parse failures count against the breaker (RONDO-145)
        # -- RONDO-397 (8.7): TypeError/ValueError added — token/cost math on a
        # -- malformed-but-200 usage block (or a plan callback tripping on an
        # -- unexpected shape) must become an error RESULT for every caller,
        # -- not a crash only the parallel collector survives. Deliberately NOT
        # -- a bare Exception: a truly novel provider bug should crash loudly.
        get_circuit_breaker().record_failure(plan.provider)
        # -- RONDO-216 C4: URLError/OSError text can carry the full URL with
        # -- ?key=SECRET (key-in-URL providers) — redact for EVERY adapter.
        err_text = str(exc)
        if plan.api_key and plan.api_key in err_text:
            err_text = err_text.replace(plan.api_key, "[REDACTED]")
        return TaskResult(
            task_name=plan.task_name,
            status="error",
            error_code=ERR_PROVIDER,
            error_message=f"{plan.label} error: {err_text}",
            model=plan.model,
            duration_sec=time.monotonic() - start,
        )


# -- sig: mgh-6201.cd.bd955f.91e6.77f45b
