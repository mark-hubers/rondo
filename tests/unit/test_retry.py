# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.retry — HTTP retry/backoff + Retry-After honoring.

VER-001 verification matrix: transient-retry contract.

RONDO-347 (found LIVE): a real 80-vote cloud panel lost 9 mistral votes to
HTTP 429. retry_http DID retry, but ignored the server's `Retry-After`
header — it slept a fixed 0.5/1/2s and gave up while mistral was asking for
much longer. The fix: honor Retry-After (capped), so we wait exactly as long
as the provider tells us. These tests pin both the new behavior AND the
unmocked real-HTTPError shape the parser depends on.
"""

from __future__ import annotations

import email.message
import urllib.error

import pytest

from rondo.retry import RetryConfig, _retry_after_sec, is_transient_http_error, retry_http


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    """Build a real urllib HTTPError, optionally carrying a Retry-After header."""
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(url="https://x", code=code, msg="boom", hdrs=hdrs, fp=None)


class TestRetryAfterParsing:
    """_retry_after_sec reads the header off a REAL HTTPError (unmocked seam)."""

    def test_reads_integer_seconds(self) -> None:
        assert _retry_after_sec(_http_error(429, "30")) == 30.0

    def test_absent_header_is_none(self) -> None:
        assert _retry_after_sec(_http_error(429)) is None

    def test_garbage_header_is_none(self) -> None:
        assert _retry_after_sec(_http_error(429, "soon-ish")) is None

    def test_non_httperror_is_none(self) -> None:
        assert _retry_after_sec(TimeoutError("net")) is None


class TestRetryHonorsRetryAfter:
    """retry_http waits what the server asks on 429 — the RONDO-347 fix."""

    def test_honors_retry_after_over_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, "5")
            return "ok"

        assert retry_http(fn, provider_name="mistral") == "ok"
        assert slept and slept[0] >= 5.0, f"expected >=5s wait from Retry-After, got {slept}"

    def test_retry_after_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, "99999")
            return "ok"

        retry_http(fn, provider_name="mistral")
        assert slept[0] <= 60.0, f"a hostile Retry-After must be capped, slept {slept[0]}"

    def test_no_header_uses_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429)
            return "ok"

        retry_http(fn, provider_name="mistral", config=RetryConfig(jitter=False))
        assert slept and slept[0] < 5.0, f"no header → exponential backoff, got {slept}"

    def test_non_transient_fails_without_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr("rondo.retry.time.sleep", slept.append)

        def fn() -> str:
            raise _http_error(400)

        with pytest.raises(urllib.error.HTTPError):
            retry_http(fn, provider_name="mistral")
        assert not slept, "4xx (non-429) must fail immediately, no sleep"

    def test_429_is_transient(self) -> None:
        assert is_transient_http_error(_http_error(429))


# -- sig: mgh-6201.cd.bd955f.87bf.fe3485
