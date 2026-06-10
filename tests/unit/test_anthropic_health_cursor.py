# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: anthropic_api.health() reports a dead key as healthy.

VER-001 verification matrix — holistic-review finding #4 (cursor-review lens).

THE BUG in src/rondo/adapters/anthropic_api.py AnthropicAPIAdapter.health()
(pinned here, NOT fixed here):

    except urllib.error.HTTPError as exc:
        # -- 401/403 = reachable but bad key — still "up"
        return exc.code < 500

An expired/revoked Anthropic API key returns 401/403, which `exc.code < 500`
treats as healthy — so `rondo doctor` shows GREEN over broken auth, then the
next real dispatch dies ERR_AUTH. RONDO-357 already fixed this exact dishonesty
in chat_completions.py (401/403 -> unhealthy; other 4xx like 404/405/429 ->
still reachable). The anthropic adapter is the missed twin — copy-paste drift.

THE CONTRACT (mirrors the chat_completions RONDO-357 behavior):
  - HTTPError 401 / 403 -> health() returns False  (bad key = NOT healthy)
  - HTTPError 404 / 405 / 429 -> True              (reachable; do-not-overcorrect)
  - HTTPError 5xx -> False                          (provider down)
  - URLError / OSError -> False                     (network down)

The 401 and 403 rows MUST FAIL against current code (it returns True today);
the 404/405 rows pin the rail that a fix must not overcorrect into. Every test
drives the REAL AnthropicAPIAdapter.health() with urlopen patched — no live HTTP.
"""

import urllib.error
from unittest.mock import patch

import pytest

from rondo.adapters.anthropic_api import AnthropicAPIAdapter

# -- (status_code, reason, expected_health) rows of the RONDO-357 contract,
#    ported to the anthropic adapter. 401/403 are the bug being pinned.
_HTTP_CONTRACT: list[tuple[int, str, bool]] = [
    (401, "Unauthorized", False),
    (403, "Forbidden", False),
    (404, "Not Found", True),
    (405, "Method Not Allowed", True),
    (429, "Too Many Requests", True),
    (500, "Internal Server Error", False),
    (503, "Service Unavailable", False),
]


def _http_error(code: int, reason: str) -> urllib.error.HTTPError:
    """Build an HTTPError the way urllib raises it from a HEAD response."""
    return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", code, reason, {}, None)


@pytest.mark.parametrize(("code", "reason", "expected"), _HTTP_CONTRACT)
def test_anthropic_health_http_status_contract(code: int, reason: str, expected: bool) -> None:
    """health() classifies each HTTP status per the RONDO-357 contract.

    401/403 (dead key) -> False is the regression: current code returns True,
    so those two rows fail today. 404/405/429 -> True is the do-not-overcorrect
    rail; 5xx -> False is provider-down. urlopen is patched — no live HTTP.
    """
    adapter = AnthropicAPIAdapter(api_key="dead-or-live-key")
    exc = _http_error(code, reason)
    with patch("urllib.request.urlopen", side_effect=exc):
        result = adapter.health()
    assert result is expected, (
        f"HTTP {code} ({reason}) must report health()={expected}, got {result} "
        f"(finding #4: 401/403 dead key shows GREEN in rondo doctor today)"
    )


def test_anthropic_health_401_dead_key_is_unhealthy() -> None:
    """A revoked/expired key (401) must report UNHEALTHY — MUST FAIL today.

    This is the headline regression: `exc.code < 500` returns True for 401, so
    rondo doctor reports the provider GREEN while the very next dispatch dies
    ERR_AUTH. Dishonest for a tool whose health bar is a reliability scoreboard.
    """
    adapter = AnthropicAPIAdapter(api_key="revoked-key")
    with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
        assert adapter.health() is False, "401 (dead key) must report unhealthy (finding #4)"


def test_anthropic_health_403_forbidden_is_unhealthy() -> None:
    """A forbidden key (403) must report UNHEALTHY — MUST FAIL today.

    403 is the twin of 401: bad/disabled credentials, not a reachable endpoint
    quirk. Current `exc.code < 500` wrongly treats it as up.
    """
    adapter = AnthropicAPIAdapter(api_key="forbidden-key")
    with patch("urllib.request.urlopen", side_effect=_http_error(403, "Forbidden")):
        assert adapter.health() is False, "403 (bad key) must report unhealthy (finding #4)"


def test_anthropic_health_405_is_still_reachable() -> None:
    """405 from a HEAD with a GOOD key proves reachability — the rail stays True.

    The adapter's health strategy expects 405 (Method Not Allowed) from HEAD on
    /messages. A fix for 401/403 must NOT overcorrect this reachable signal.
    """
    adapter = AnthropicAPIAdapter(api_key="good-key")
    with patch("urllib.request.urlopen", side_effect=_http_error(405, "Method Not Allowed")):
        assert adapter.health() is True, "405 (HEAD not allowed) is still reachable — do not overcorrect"


def test_anthropic_health_404_is_still_reachable() -> None:
    """404 (endpoint quirk) with a good key is still reachable — rail stays True.

    Mirrors the chat_completions Grok 404 rail: a 4xx that is not auth must not
    be downgraded to unhealthy when a fix narrows the True window to 401/403.
    """
    adapter = AnthropicAPIAdapter(api_key="good-key")
    with patch("urllib.request.urlopen", side_effect=_http_error(404, "Not Found")):
        assert adapter.health() is True, "404 endpoint quirk with a good key is still reachable"


def test_anthropic_health_url_error_is_down() -> None:
    """A network failure (URLError) must report UNHEALTHY — no route, no green.

    This already passes today (URLError is its own except branch); pinned here so
    the network-down rail can never silently regress alongside a 401/403 fix.
    """
    adapter = AnthropicAPIAdapter(api_key="good-key")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route to host")):
        assert adapter.health() is False, "network down (URLError) must report unhealthy"


def test_anthropic_health_os_error_is_down() -> None:
    """A raw OSError (socket/DNS) must report UNHEALTHY — no live HTTP.

    OSError is the base of URLError but pinned explicitly: a connection reset or
    DNS failure surfacing as OSError must never read as healthy.
    """
    adapter = AnthropicAPIAdapter(api_key="good-key")
    with patch("urllib.request.urlopen", side_effect=OSError("connection reset by peer")):
        assert adapter.health() is False, "socket/DNS failure (OSError) must report unhealthy"


def test_anthropic_health_no_key_is_unhealthy() -> None:
    """No API key short-circuits to UNHEALTHY before any HTTP is attempted.

    Guards the key-present precondition: with no key, health() returns False and
    urlopen is never called (asserted via a patch that would raise if reached).
    """
    adapter = AnthropicAPIAdapter(api_key="")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("urlopen must not be called when no API key is set")

    with patch("urllib.request.urlopen", side_effect=_boom):
        assert adapter.health() is False, "missing key must report unhealthy without any HTTP call"


# -- sig: mgh-6201.cd.bd955f.7118.052806
