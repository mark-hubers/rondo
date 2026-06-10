# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: RONDO-334 stream-disconnect re-attempt silently doubles spend.

VER-001 verification matrix — holistic-review finding #5 (cursor-review lens),
quality-checklist item 5. Pins the contract against REQ-109 req 213 (MUST).

THE BUG in src/rondo/adapters/anthropic_api.py AnthropicAPIAdapter.dispatch()
(pinned here, NOT fixed here):

    result = retry_http(_do_request, provider_name="anthropic")
    if result.get("disconnect_error"):
        logger.warning("... one automatic re-attempt (RONDO-334)")
        second = retry_http(_do_request, provider_name="anthropic")   # <-- silent
        result = _best_of_disconnects(result, second)

When the first streaming attempt comes back with a disconnect_error, dispatch
fires a SECOND full paid attempt automatically (and retry_http itself can run up
to 5 attempts under the hood). REQ-109 req 213 (MUST): "Expensive thinking
dispatches MUST NOT be auto-retried ... One visible retry BY CHOICE, never
silent spend." A max-effort run that disconnects at ~30 min already billed its
output tokens; the silent second bills them all over again.

THE CONTRACT (test the observable behavior, not internals):
  - DEFAULT OFF (req 213 MUST): on disconnect, NO second request fires. The
    partial/disconnect envelope returns so the caller can retry BY CHOICE.
  - OPT-IN: when a gate flag (RondoConfig / adapter kwarg `stream_reattempt`,
    or the fix's chosen name) is enabled, the second attempt MAY fire, but the
    result envelope MUST SURFACE that it happened — never silently.
  - RAIL: a clean (non-disconnect) success makes exactly ONE request in both
    modes — the re-attempt path is disconnect-only.

The DEFAULT-OFF test MUST FAIL against current code (it fires the silent second
today). Every test drives the REAL dispatch() with the retry_http seam stubbed
to return queued attempt results — hermetic, no live HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest

from rondo.adapters.anthropic_api import AnthropicAPIAdapter

# -- Plausible names for the opt-in gate the fix will add. Setting every
#    candidate (raising=False, harmless if unused) keeps the ENABLED test
#    robust to whichever name the fix picks — adapter attribute OR dispatch kwarg.
_ENABLE_NAMES: tuple[str, ...] = (
    "stream_reattempt",
    "stream_re_attempt",
    "auto_reattempt",
    "stream_auto_retry",
    "reattempt_on_disconnect",
)


class _FakeBreaker:
    """Always-closed circuit breaker — keeps the test order-independent."""

    def is_open(self, provider: str) -> bool:  # noqa: ARG002
        return False

    def record_success(self, provider: str) -> None:  # noqa: ARG002
        return None

    def record_failure(self, provider: str) -> None:  # noqa: ARG002
        return None


def _disconnected(text: str) -> dict[str, Any]:
    """One _do_request result whose stream dropped mid-flight (RONDO-323 shape)."""
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "disconnected",
        "disconnect_error": "ConnectionResetError: dropped",
    }


def _ok(text: str) -> dict[str, Any]:
    """One clean _do_request result — no disconnect."""
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn",
        "disconnect_error": "",
    }


def _wire_attempts(monkeypatch: pytest.MonkeyPatch, results: list[dict[str, Any]]) -> dict[str, int]:
    """Stub the retry_http seam so each invocation = one paid attempt batch.

    Returns a mutable counter; calls["n"] is the number of paid requests dispatch
    decided to make. retry_http only retries on EXCEPTIONS, so a disconnect (which
    RETURNS) is one request per invocation — counting invocations counts spend.
    """
    import rondo.adapters.anthropic_api as api

    calls = {"n": 0}

    def fake_retry_http(fn: Any, provider_name: str = "") -> dict[str, Any]:  # noqa: ARG001
        calls["n"] += 1
        return results[min(calls["n"] - 1, len(results) - 1)]

    monkeypatch.setattr(api, "retry_http", fake_retry_http)
    monkeypatch.setattr(api, "get_circuit_breaker", lambda: _FakeBreaker())
    return calls


def _enable_reattempt(monkeypatch: pytest.MonkeyPatch, adapter: AnthropicAPIAdapter) -> dict[str, Any]:
    """Turn the opt-in gate ON across every plausible name; return matching kwargs.

    The fix is not present yet, so we set adapter attributes (raising=False) AND
    return kwargs for whichever surface the fix chose — both are harmless no-ops
    for the names the fix ignores.
    """
    for attr in _ENABLE_NAMES:
        monkeypatch.setattr(adapter, attr, True, raising=False)
    return {name: True for name in _ENABLE_NAMES}


def _surfaced_reattempt(tr: Any) -> bool:
    """True if the result envelope visibly reports the re-attempt happened.

    Tolerant: accepts any natural surfacing the fix might choose — a truthy
    `reattempt*` key in metrics/context_data/parsed_result, a new boolean field
    on the result, or a human-readable warning in the message/output text.
    """
    for blob in (tr.metrics, tr.context_data, tr.parsed_result or {}):
        if isinstance(blob, dict):
            for key, val in blob.items():
                if "reattempt" in str(key).lower() or "re_attempt" in str(key).lower():
                    if val:
                        return True
    for attr in ("reattempted", "stream_reattempted", "reattempt", "retried"):
        if getattr(tr, attr, False):
            return True
    text = " ".join(s for s in (tr.error_message or "", tr.raw_output or "", tr.stderr or "") if s).lower()
    return any(marker in text for marker in ("reattempt", "re-attempt", "second attempt"))


def test_disconnect_default_off_fires_only_one_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-109 r213 MUST: a disconnect must NOT silently fire a second paid attempt.

    The default (no opt-in flag) must make EXACTLY ONE request. Current code fires
    the automatic second, so this assertion FAILS today — the regression pin.
    """
    calls = _wire_attempts(monkeypatch, [_disconnected("half a partial"), _disconnected("tiny")])
    tr = AnthropicAPIAdapter(api_key="sk-test-not-real").dispatch(prompt="p", model="claude-opus-4-8")  # noqa: S106
    assert calls["n"] == 1, "default-off disconnect must not auto-fire a second paid attempt (silent spend)"
    assert tr.status == "error"
    assert tr.error_code == "ERR_STREAM_DISCONNECT"
    assert tr.raw_output == "half a partial"


def test_disconnect_enabled_fires_second_and_surfaces_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the opt-in gate is ON, the second attempt may fire AND must be surfaced.

    Two requests are allowed here (count == 2) but the envelope must visibly report
    the re-attempt — never silent. Current code re-attempts but surfaces nothing, so
    the surfacing assertion FAILS today.
    """
    calls = _wire_attempts(monkeypatch, [_disconnected("partial"), _ok("full answer")])
    adapter = AnthropicAPIAdapter(api_key="sk-test-not-real")  # noqa: S106
    enable_kwargs = _enable_reattempt(monkeypatch, adapter)
    tr = adapter.dispatch(prompt="p", model="claude-opus-4-8", **enable_kwargs)
    assert calls["n"] == 2, "opt-in re-attempt should fire exactly the one extra paid attempt"
    assert _surfaced_reattempt(tr), "an opt-in re-attempt MUST be surfaced in the result envelope, never silent"


def test_clean_success_makes_one_request_in_both_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rail: a non-disconnect success makes exactly ONE request, gate off or on.

    The re-attempt path is disconnect-only; a clean result never triggers it.
    """
    calls_off = _wire_attempts(monkeypatch, [_ok("first try")])
    tr_off = AnthropicAPIAdapter(api_key="sk-test-not-real").dispatch(prompt="p", model="claude-opus-4-8")  # noqa: S106
    assert calls_off["n"] == 1
    assert tr_off.status == "done"

    calls_on = _wire_attempts(monkeypatch, [_ok("first try")])
    adapter = AnthropicAPIAdapter(api_key="sk-test-not-real")  # noqa: S106
    enable_kwargs = _enable_reattempt(monkeypatch, adapter)
    tr_on = adapter.dispatch(prompt="p", model="claude-opus-4-8", **enable_kwargs)
    assert calls_on["n"] == 1, "a clean success must never trigger the re-attempt path, even when enabled"
    assert tr_on.status == "done"


# -- sig: mgh-6201.cd.bd955f.b655.7df84b
