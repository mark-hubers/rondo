# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: gemini adapter undercounts cost for 2.5 thinking models.

VER-001 verification matrix — holistic-review finding #9 (quality checklist
item 8, cursor-review lens).

THE BUG in src/rondo/adapters/gemini.py GeminiAdapter.dispatch() (pinned here,
NOT fixed here):

    usage = result.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)
    cost = compute_cost_usd(use_model, input_tokens, output_tokens)

Gemini 2.5 models return THINKING tokens in a separate field
`thoughtsTokenCount`. Google bills those as OUTPUT tokens, but the adapter
reads only `candidatesTokenCount` — so cost_usd is undercounted on exactly the
expensive thinking runs. The budget gate (RONDO-373) is then fed low numbers
and under-enforces the cap on the very dispatches most likely to blow it.

THE CONTRACT:
  - effective_output = candidatesTokenCount + thoughtsTokenCount (when present)
  - cost_usd MUST price (promptTokenCount in, effective_output out)
  - Absent `thoughtsTokenCount` (non-thinking models) = unchanged behavior:
    output is exactly candidatesTokenCount.

The thinking test MUST FAIL against current code (it prices only 500 output
tokens, not 8500). The no-thoughts rail pins that a fix must not change
behavior when the field is absent. Every test drives the REAL GeminiAdapter
with urllib.request.urlopen patched — no live HTTP.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from rondo.adapters.chat_completions import compute_cost_usd
from rondo.adapters.gemini import GeminiAdapter

_MODEL = "gemini-2.5-pro"


def _mock_response(usage: dict[str, int]) -> MagicMock:
    """Build a urlopen context-manager stub for one Gemini 200 body.

    Mirrors the existing gemini success-path mocking in test_providers.py:
    a MagicMock that acts as its own context manager and yields a JSON body
    with a single text candidate plus the supplied usageMetadata.
    """
    body = {
        "candidates": [{"content": {"parts": [{"text": "deep answer"}]}}],
        "usageMetadata": usage,
    }
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_thinking_tokens_counted_as_output_cost() -> None:
    """ThoughtsTokenCount must be billed as output: cost prices 8500, not 500.

    Thinking-heavy realistic shape: 1000 in, 500 candidate + 8000 thoughts.
    The contract cost is compute_cost_usd(model, 1000, 8500). This FAILS on
    current code, which prices only candidatesTokenCount (500 output tokens).
    """
    adapter = GeminiAdapter(api_key="key")
    usage = {
        "promptTokenCount": 1000,
        "candidatesTokenCount": 500,
        "thoughtsTokenCount": 8000,
    }
    resp = _mock_response(usage)

    with patch("urllib.request.urlopen", return_value=resp):
        result = adapter.dispatch(prompt="think hard", model=_MODEL)

    expected_with_thoughts = compute_cost_usd(_MODEL, 1000, 8500)
    expected_without_thoughts = compute_cost_usd(_MODEL, 1000, 500)

    assert result.status == "done"
    assert result.cost_usd == expected_with_thoughts, (
        "thoughtsTokenCount (8000) must be billed as output tokens: "
        f"cost must price 8500 output ({expected_with_thoughts}), "
        f"got {result.cost_usd}"
    )
    assert result.cost_usd > expected_without_thoughts, (
        f"thinking cost must strictly exceed the same response priced without thoughts ({expected_without_thoughts})"
    )


def test_no_thoughts_field_is_unchanged_behavior() -> None:
    """Absent thoughtsTokenCount = unchanged: output is exactly 500 tokens.

    Non-thinking models omit the field. The rail pins that a fix must not add
    phantom output tokens here — cost stays compute_cost_usd(model, 1000, 500).
    """
    adapter = GeminiAdapter(api_key="key")
    usage = {"promptTokenCount": 1000, "candidatesTokenCount": 500}
    resp = _mock_response(usage)

    with patch("urllib.request.urlopen", return_value=resp):
        result = adapter.dispatch(prompt="quick answer", model=_MODEL)

    expected = compute_cost_usd(_MODEL, 1000, 500)

    assert result.status == "done"
    assert result.cost_usd == expected, (
        f"with no thoughtsTokenCount, cost must price exactly 500 output tokens ({expected}), got {result.cost_usd}"
    )


# -- sig: mgh-6201.cd.bd955f.ce72.bdb40b
