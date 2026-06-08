# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for config-driven read-timeouts — RONDO-318 (REQ-109 req 212).

5-10 minutes is NORMAL for max-effort thinking on long tasks — a fixed
timeout is always wrong for someone. COALESCE: per-dispatch → config
[timeouts] per (model-class, effort) → built-in defaults.

VER-001 verification matrix: read-timeout COALESCE per model-class/effort.
"""

from __future__ import annotations

from rondo.adapters.timeouts import DEFAULT_TIMEOUTS, resolve_read_timeout


class TestBuiltInDefaults:
    """req 212 defaults: classic 120; thinking low/med/high 600; xhigh/max 900."""

    def test_classic_default(self) -> None:
        assert resolve_read_timeout(thinking=False, effort="", timeouts_cfg={}) == 120

    def test_thinking_high_default(self) -> None:
        assert resolve_read_timeout(thinking=True, effort="high", timeouts_cfg={}) == 600

    def test_thinking_max_default(self) -> None:
        assert resolve_read_timeout(thinking=True, effort="max", timeouts_cfg={}) == 900

    def test_thinking_xhigh_default(self) -> None:
        assert resolve_read_timeout(thinking=True, effort="xhigh", timeouts_cfg={}) == 900

    def test_unknown_effort_gets_thinking_floor(self) -> None:
        """An unrecognized effort on a thinking model is never given 120s."""
        assert resolve_read_timeout(thinking=True, effort="experimental", timeouts_cfg={}) == 600

    def test_defaults_table_locked(self) -> None:
        assert DEFAULT_TIMEOUTS["classic"] == 120
        assert DEFAULT_TIMEOUTS["thinking_max"] == 900


class TestConfigOverride:
    """[timeouts] in config.toml overrides defaults per (class, effort)."""

    def test_config_overrides_thinking_max(self) -> None:
        cfg = {"thinking_max": 1800}
        assert resolve_read_timeout(thinking=True, effort="max", timeouts_cfg=cfg) == 1800

    def test_config_overrides_classic(self) -> None:
        assert resolve_read_timeout(thinking=False, effort="", timeouts_cfg={"classic": 60}) == 60

    def test_partial_config_falls_through(self) -> None:
        """A config that only sets one key leaves the others at defaults."""
        cfg = {"thinking_max": 1800}
        assert resolve_read_timeout(thinking=True, effort="high", timeouts_cfg=cfg) == 600

    def test_malformed_value_ignored(self) -> None:
        """'fast' is not a timeout — fall through to the default, never crash."""
        cfg = {"thinking_high": "fast"}
        assert resolve_read_timeout(thinking=True, effort="high", timeouts_cfg=cfg) == 600

    def test_nonpositive_value_ignored(self) -> None:
        assert resolve_read_timeout(thinking=False, effort="", timeouts_cfg={"classic": 0}) == 120


class TestPerDispatchWins:
    """Per-dispatch beats config beats defaults — manual always wins."""

    def test_per_dispatch_beats_config(self) -> None:
        cfg = {"thinking_max": 1800}
        assert resolve_read_timeout(thinking=True, effort="max", per_dispatch=300, timeouts_cfg=cfg) == 300

    def test_per_dispatch_zero_ignored(self) -> None:
        assert resolve_read_timeout(thinking=False, effort="", per_dispatch=0, timeouts_cfg={}) == 120


class TestAdapterWiring:
    """The anthropic adapter resolves its read timeout through this chain."""

    def test_adapter_read_timeout_method(self) -> None:
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="sk-test-not-real")  # noqa: S106
        assert adapter.read_timeout_for("claude-sonnet-4-6", "", timeouts_cfg={}) == 120
        assert adapter.read_timeout_for("claude-opus-4-8", "max", timeouts_cfg={}) == 900
        assert adapter.read_timeout_for("claude-opus-4-8", "max", timeouts_cfg={"thinking_max": 1200}) == 1200


class TestAdaptersWireTheTimeout:
    """ChatCompletions + Gemini adapters resolve the read timeout — RONDO-355.

    They hardcoded 120s. Found LIVE via USH: gpt-5.5 and gemini blew it on a
    long prompt while fast mistral squeaked under. The resolver (RONDO-318)
    existed but only anthropic_api was wired.
    """

    def test_chat_completions_defaults_patient_not_120(self) -> None:
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="x")
        assert adapter._read_timeout("gpt-5.5") >= 600, "chat adapter still hardcodes a short timeout"

    def test_chat_completions_per_dispatch_override_wins(self) -> None:
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="x")
        assert adapter._read_timeout("gpt-5.5", read_timeout=42) == 42

    def test_gemini_defaults_patient_not_120(self) -> None:
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="x")
        assert adapter._read_timeout("gemini-2.5-pro") >= 600, "gemini adapter still hardcodes a short timeout"

    def test_gemini_per_dispatch_override_wins(self) -> None:
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="x")
        assert adapter._read_timeout("gemini-2.5-pro", read_timeout=30) == 30


# -- sig: mgh-6201.cd.bd955f.5a1f.fb1779
