# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: the ollama adapter has NO reliability primitives.

VER-001 verification matrix — holistic-review finding #6b (cursor-review lens),
quality-checklist item 12. Pins the OBSERVABLE reliability contract that the
imminent shared-HTTP-dispatch refactor (checklist item 11) MUST satisfy.

THE GAP in src/rondo/adapters/ollama.py OllamaAdapter.dispatch() (pinned here,
NOT fixed here): a bare urllib urlopen with none of the three primitives every
other adapter has (gemini, chat_completions, anthropic_api):

    - NO circuit breaker  — a dead/hung local Ollama keeps getting hammered.
    - NO retry_http        — a transient blip is a hard failure, not a retry.
    - NO empty-response gate (REQ-109 req 070) — an empty body returns "done".

Local Ollama hangs and dies like any server; the breaker and retry semantics
apply even when cost is $0. These tests assert the contract by the same seams
the other adapter tests use (monkeypatch get_circuit_breaker + retry_http in the
module under test), discoverable in chat_completions.py.

THE CONTRACT (observable behavior, mirrors chat_completions.py):
  - Breaker OPEN for "ollama": dispatch returns status error / ERR_PROVIDER_DOWN
    with a message mentioning the breaker/cooldown, WITHOUT firing any HTTP.
  - Transient calls route THROUGH retry_http (not a bare urlopen).
  - A network failure records a breaker failure (record_failure called).
  - An empty response body ("response": "") returns ERR_EMPTY_RESPONSE.
  - Success rail: status done, auth_mode "local", cost zero (free, passes today).

Tests 1-4 MUST FAIL against current code — none of the machinery exists in
ollama.py yet (retry_http / get_circuit_breaker aren't even imported there, so
they are monkeypatched with raising=False and asserted to be USED). Test 5 (the
success rail) passes today. Hermetic — no live HTTP, no live Ollama.
"""

from __future__ import annotations

import urllib.error
from typing import Any

import pytest

import rondo.adapters.ollama as ol
from rondo.adapters.ollama import OllamaAdapter
from rondo.engine import ERR_EMPTY_RESPONSE, ERR_PROVIDER_DOWN


class _FakeBreaker:
    """Injectable circuit breaker — records calls so the test can assert usage."""

    def __init__(self, *, open_: bool) -> None:
        self._open = open_
        self.failures: list[str] = []
        self.successes: list[str] = []

    def is_open(self, provider: str) -> bool:  # noqa: ARG002
        return self._open

    def record_failure(self, provider: str) -> None:
        self.failures.append(provider)

    def record_success(self, provider: str) -> None:
        self.successes.append(provider)


class _FakeResp:
    """Minimal urlopen context-manager stand-in returning a canned body."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _const_urlopen(payload: dict[str, Any]) -> Any:
    """A fake urlopen that ignores its request and returns `payload` as JSON."""
    import json  # -- local import keeps the helper self-contained

    body = json.dumps(payload).encode("utf-8")

    def _fake(*_args: Any, **_kwargs: Any) -> _FakeResp:
        return _FakeResp(body)

    return _fake


def _inject_breaker(monkeypatch: pytest.MonkeyPatch, breaker: _FakeBreaker) -> None:
    """Wire the fake breaker via the live seam (RONDO-381 refactor harness re-point).

    Authored before the refactor landed, this anticipated the seam in the
    ollama module namespace; the shared machinery actually lives in
    rondo.adapters.http_skeleton. Patch target updated — the ASSERTIONS
    (the observable reliability contract) are unchanged.
    """
    import rondo.adapters.http_skeleton as skel  # noqa: PLC0415

    monkeypatch.setattr(skel, "get_circuit_breaker", lambda: breaker)
    monkeypatch.setattr(ol, "get_circuit_breaker", lambda: breaker, raising=False)


def test_breaker_open_returns_provider_down_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaker OPEN must short-circuit to ERR_PROVIDER_DOWN with NO HTTP fired.

    FAILS today: ollama.py never consults a breaker, so the bare urlopen fires
    and trips the AssertionError guard below.
    """
    _inject_breaker(monkeypatch, _FakeBreaker(open_=True))

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("dispatch fired HTTP while the breaker was OPEN")

    monkeypatch.setattr(ol.urllib.request, "urlopen", _boom)

    tr = OllamaAdapter().dispatch(prompt="hi", model="llama3")

    assert tr.status == "error"
    assert tr.error_code == ERR_PROVIDER_DOWN
    msg = (tr.error_message or "").lower()
    assert "breaker" in msg or "cooldown" in msg or "open" in msg


def test_dispatch_routes_through_retry_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP call must be wrapped in retry_http, not called bare.

    FAILS today: retry_http is monkeypatched (raising=False) but ollama.py never
    invokes it, so `used` stays False.
    """
    _inject_breaker(monkeypatch, _FakeBreaker(open_=False))
    used = {"called": False}

    def _fake_retry_http(fn: Any, *_args: Any, **_kwargs: Any) -> Any:
        used["called"] = True
        return fn()

    import rondo.adapters.http_skeleton as skel  # noqa: PLC0415

    monkeypatch.setattr(skel, "retry_http", _fake_retry_http)  # -- live seam (RONDO-381)
    monkeypatch.setattr(ol, "retry_http", _fake_retry_http, raising=False)
    monkeypatch.setattr(ol.urllib.request, "urlopen", _const_urlopen({"response": "hi"}))

    tr = OllamaAdapter().dispatch(prompt="hi", model="llama3")

    assert used["called"], "dispatch must route the HTTP call through retry_http, never urlopen bare"
    assert tr.status == "done"


def test_network_failure_records_breaker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A network failure must be recorded against the ollama breaker.

    FAILS today: no breaker exists, so record_failure is never called.
    """
    breaker = _FakeBreaker(open_=False)
    _inject_breaker(monkeypatch, breaker)

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.URLError("connection refused")

    # -- cover both rails: the live skeleton seam AND a bare urlopen fallback.
    import rondo.adapters.http_skeleton as skel  # noqa: PLC0415

    monkeypatch.setattr(skel, "retry_http", _raise)  # -- live seam (RONDO-381)
    monkeypatch.setattr(ol, "retry_http", _raise, raising=False)
    monkeypatch.setattr(ol.urllib.request, "urlopen", _raise)

    tr = OllamaAdapter().dispatch(prompt="hi", model="llama3")

    assert tr.status == "error"
    assert "ollama" in breaker.failures, "a network failure must record a breaker failure for 'ollama'"


def test_empty_response_body_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty response body must return ERR_EMPTY_RESPONSE (REQ-109 req 070).

    FAILS today: ollama.py returns status "done" with an empty raw_output.
    """
    _inject_breaker(monkeypatch, _FakeBreaker(open_=False))
    monkeypatch.setattr(ol, "retry_http", lambda fn, *a, **k: fn(), raising=False)  # noqa: ARG005
    monkeypatch.setattr(ol.urllib.request, "urlopen", _const_urlopen({"response": ""}))

    tr = OllamaAdapter().dispatch(prompt="hi", model="llama3")

    assert tr.status == "error"
    assert tr.error_code == ERR_EMPTY_RESPONSE


def test_success_rail_done_local_zero_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rail: a normal response stays done, auth_mode local, cost zero (free).

    PASSES today — the success path already returns this shape; this pins it so
    the refactor doesn't regress the happy path.
    """
    _inject_breaker(monkeypatch, _FakeBreaker(open_=False))
    monkeypatch.setattr(ol, "retry_http", lambda fn, *a, **k: fn(), raising=False)  # noqa: ARG005
    monkeypatch.setattr(ol.urllib.request, "urlopen", _const_urlopen({"response": "the answer"}))

    tr = OllamaAdapter().dispatch(prompt="hi", model="llama3")

    assert tr.status == "done"
    assert tr.raw_output == "the answer"
    assert tr.auth_mode == "local"
    assert not tr.cost_usd, "local Ollama dispatch is free — cost must be zero/None"


# -- sig: mgh-6201.cd.bd955f.045a.77eec4
