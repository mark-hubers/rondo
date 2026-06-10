# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: http_skeleton success-path catch is too narrow (ROAD-TO-8 item 8.7).

VER-001 verification matrix — re-score finding R8 (cursor-review lens). Pins the
NEW contract against REQ-109 reqs 068/070; the fix lands in
src/rondo/adapters/http_skeleton.py dispatch_via_http (pinned here, NOT fixed
here).

THE HOLE (src/rondo/adapters/http_skeleton.py ~line 223): the success-path
except tuple is (URLError, OSError, JSONDecodeError, KeyError). A TypeError or
ValueError raised AFTER a successful HTTP response — token/cost math on a
malformed-but-200 usage block (usage fields as strings/None), or an
extract_text / early_result callback tripping on an unexpected shape — ESCAPES
the adapter and crashes the CALLER instead of becoming an error TaskResult. The
parallel collector swallows it; direct/sequential callers do not.

THE NEW CONTRACT:
  (a) TypeError and ValueError from the post-response pipeline (extract_text,
      early_result, empty_message, _done_result token/cost math) are caught at
      the SAME boundary and produce status="error" / error_code ERR_PROVIDER
      (same envelope as today's URLError branch), breaker.record_failure fired,
      key-redaction applied to the message.
  (b) Clean rail unchanged: well-formed responses still produce done results
      with correct metrics; the EXISTING four exception types still produce
      error results (no regression).
  (c) No NEW exception types beyond TypeError/ValueError (no bare-Exception
      creep — truly novel provider bugs should still crash loudly in dev).

Tests 1-4 MUST FAIL today (TypeError/ValueError propagate; breaker + redaction
depend on the new catch). Tests 5-6 PASS today (clean rail + existing URLError
rail) — they pin no-regression. Hermetic: the retry_http + circuit-breaker
seams in http_skeleton are stubbed; no live HTTP, no live AI.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Callable
from typing import Any

import pytest

import rondo.adapters.http_skeleton as skel
from rondo.adapters.http_skeleton import HttpDispatchPlan, dispatch_via_http
from rondo.engine import ERR_PROVIDER, TaskResult

# -- gitleaks-allowlisted canonical fake (AWS docs example key) — house rule:
# -- only the AKIAIOSFODNN7EXAMPLE family appears in tests
_API_KEY = "AKIAIOSFODNN7EXAMPLE"  # noqa: S105 -- fake; used to assert redaction


class _FakeBreaker:
    """Injectable circuit breaker — records calls so tests can assert usage."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.successes: list[str] = []

    def is_open(self, provider: str) -> bool:  # noqa: ARG002
        return False

    def record_failure(self, provider: str) -> None:
        self.failures.append(provider)

    def record_success(self, provider: str) -> None:
        self.successes.append(provider)


def _wire(monkeypatch: pytest.MonkeyPatch, breaker: _FakeBreaker) -> None:
    """Stub the http_skeleton seams: retry_http runs the request inline, breaker is ours.

    retry_http(fn, provider_name=...) is replaced with a pass-through that simply
    CALLS the plan's do_request — so a do_request that returns drives the success
    pipeline, and one that raises (URLError) propagates exactly as live retry
    would after exhausting transient retries.
    """

    def _passthrough(fn: Callable[[], dict[str, Any]], provider_name: str = "") -> dict[str, Any]:  # noqa: ARG001
        return fn()

    monkeypatch.setattr(skel, "retry_http", _passthrough)
    monkeypatch.setattr(skel, "get_circuit_breaker", lambda: breaker)


def _make_plan(
    *,
    do_request: Callable[[], dict[str, Any]] | None = None,
    extract_text: Callable[[dict[str, Any]], str] | None = None,
    extract_tokens: Callable[[dict[str, Any]], tuple[int, int]] | None = None,
    api_key: str = _API_KEY,
) -> HttpDispatchPlan:
    """Build a minimal valid HttpDispatchPlan; callers override the hook under test."""
    return HttpDispatchPlan(
        provider="testprov",
        label="TestProv",
        task_name="t1",
        model="gpt-4o-mini",
        do_request=do_request if do_request is not None else (lambda: {"ok": True}),
        extract_text=extract_text if extract_text is not None else (lambda r: "answer"),  # noqa: ARG005
        extract_tokens=extract_tokens,
        api_key=api_key,
        extra_done_metrics={"probe": "k"},
    )


def test_typeerror_in_pipeline_returns_error_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 whose post-response pipeline raises TypeError must RETURN an error result.

    MUST FAIL today: TypeError is not in the success-path except tuple, so it
    propagates out of dispatch_via_http and crashes the caller.
    """
    _wire(monkeypatch, _FakeBreaker())

    def _bad_text(_result: dict[str, Any]) -> str:
        # -- token math on a malformed-but-200 usage block: None + int
        return "x" + None  # type: ignore[operator]  # noqa: RUF100

    tr = dispatch_via_http(_make_plan(extract_text=_bad_text))

    assert isinstance(tr, TaskResult)
    assert tr.status == "error"
    assert tr.error_code == ERR_PROVIDER


def test_valueerror_in_pipeline_returns_error_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 whose post-response pipeline raises ValueError must RETURN an error result.

    MUST FAIL today: ValueError is not in the success-path except tuple, so it
    propagates instead of becoming an error TaskResult.
    """
    _wire(monkeypatch, _FakeBreaker())

    def _bad_text(_result: dict[str, Any]) -> str:
        return str(int("not-a-number"))  # -- ValueError inside a plan callback

    tr = dispatch_via_http(_make_plan(extract_text=_bad_text))

    assert isinstance(tr, TaskResult)
    assert tr.status == "error"
    assert tr.error_code == ERR_PROVIDER


def test_typeerror_path_records_breaker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The widened TypeError path must record a breaker failure for plan.provider.

    Depends on the new catch (today the exception escapes before record_failure),
    so this is expected RED until the fix lands.
    """
    breaker = _FakeBreaker()
    _wire(monkeypatch, breaker)

    def _bad_text(_result: dict[str, Any]) -> str:
        raise TypeError("boom in extract_text")

    dispatch_via_http(_make_plan(extract_text=_bad_text))

    assert "testprov" in breaker.failures, "TypeError path must record a breaker failure"


def test_typeerror_message_is_key_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the TypeError text carries the API key, the error_message must redact it.

    Depends on the new catch applying the same redaction as the URLError branch,
    so this is expected RED until the fix lands.
    """
    _wire(monkeypatch, _FakeBreaker())

    def _bad_text(_result: dict[str, Any]) -> str:
        raise TypeError(f"leaked {_API_KEY} in trace")

    tr = dispatch_via_http(_make_plan(extract_text=_bad_text))

    assert tr.status == "error"
    assert _API_KEY not in (tr.error_message or ""), "raw API key must not survive in the error message"
    assert "[REDACTED]" in (tr.error_message or "")


def test_clean_rail_still_done_with_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rail: a well-formed 200 still returns done with text + metrics + correct cost.

    PASSES today — pins the happy path so the catch-widening fix doesn't regress it.
    """
    _wire(monkeypatch, _FakeBreaker())
    tr = dispatch_via_http(
        _make_plan(
            do_request=lambda: {"usage": {"in": 1000, "out": 2000}},
            extract_text=lambda r: "the answer",  # noqa: ARG005
            extract_tokens=lambda r: (r["usage"]["in"], r["usage"]["out"]),
        )
    )

    assert tr.status == "done"
    assert tr.raw_output == "the answer"
    assert tr.metrics.get("probe") == "k"
    assert tr.cost_usd is not None and tr.cost_usd > 0.0


def test_existing_urlerror_rail_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rail: a URLError still produces the same ERR_PROVIDER error result (no regression).

    PASSES today — one of the four existing caught types; pins that the widening
    doesn't drop the established behavior.
    """
    breaker = _FakeBreaker()
    _wire(monkeypatch, breaker)

    def _raise() -> dict[str, Any]:
        raise urllib.error.URLError("connection refused")

    tr = dispatch_via_http(_make_plan(do_request=_raise))

    assert tr.status == "error"
    assert tr.error_code == ERR_PROVIDER
    assert "testprov" in breaker.failures


# -- Claude top-up (labeled, RONDO-397): pins contract clause (c) explicitly —
# -- the Cursor judge guards it implicitly; this makes over-widening a RED.
def test_novel_runtimeerror_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract (c): NO bare-Exception creep — a novel RuntimeError must still raise.

    A truly unexpected provider bug should crash loudly in dev, not be
    swallowed into an error envelope. Kills any future `except Exception`
    over-fix at this boundary.
    """
    _wire(monkeypatch, _FakeBreaker())

    def _novel(_result: dict[str, Any]) -> str:
        raise RuntimeError("novel provider bug — must crash loudly")

    with pytest.raises(RuntimeError, match="novel provider bug"):
        dispatch_via_http(_make_plan(extract_text=_novel))


# -- sig: mgh-6201.cd.bd955f.3633.a19cd4
