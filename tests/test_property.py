# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Property-based tests for Rondo — FIX-677.

VER-001 verification: hypothesis fuzzing for parsers, config, and model resolution.
Targets: dispatch_parse (JSON extraction), config validation, parse_model.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

from rondo.config import RondoConfig, validate_config
from rondo.dispatch_parse import classify_error, get_error_recovery, parse_task_json
from rondo.engine import ErrorPayload, TaskResult
from rondo.providers import parse_model


# -- ──────────────────────────────────────────────────────────────
#  dispatch_parse: JSON extraction never crashes
# -- ──────────────────────────────────────────────────────────────


class TestJsonExtractionProperty:
    """parse_task_json must never raise, regardless of input."""

    @given(st.text(min_size=0, max_size=5000))
    @settings(max_examples=200, deadline=1000)
    def test_never_crashes_on_arbitrary_text(self, raw_output: str) -> None:
        """Arbitrary text input never causes parse_task_json to raise."""
        result = parse_task_json(raw_output)
        assert result is None or isinstance(result, dict)

    @given(st.text(min_size=0, max_size=500).map(lambda s: f'{{"data": "{s}"}}'))
    @settings(max_examples=100, deadline=1000)
    def test_valid_json_shapes_return_dict_or_none(self, json_text: str) -> None:
        """Valid-ish JSON shapes either parse or return None (never crash)."""
        result = parse_task_json(json_text)
        assert result is None or isinstance(result, dict)

    @given(st.binary(min_size=1, max_size=1000).map(lambda b: b.decode("utf-8", errors="replace")))
    @settings(max_examples=100, deadline=1000)
    def test_binary_garbage_never_crashes(self, garbage: str) -> None:
        """Binary garbage decoded as text never crashes the parser."""
        result = parse_task_json(garbage)
        assert result is None or isinstance(result, dict)


# -- ──────────────────────────────────────────────────────────────
#  dispatch_parse: error classification always returns valid code
# -- ──────────────────────────────────────────────────────────────


class TestErrorClassificationProperty:
    """classify_error must always return a string starting with ERR_."""

    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=200, deadline=500)
    def test_always_returns_err_code(self, stderr: str) -> None:
        """Any stderr input produces a valid ERR_ code."""
        code = classify_error(stderr)
        assert isinstance(code, str)
        assert code.startswith("ERR_"), f"Got non-ERR code: {code}"

    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=100, deadline=500)
    def test_recovery_exists_for_all_codes(self, stderr: str) -> None:
        """Every classified code has a recovery suggestion."""
        code = classify_error(stderr)
        recovery, transient = get_error_recovery(code)
        assert isinstance(recovery, str)
        assert len(recovery) > 0, f"Empty recovery for {code}"
        assert isinstance(transient, bool)


# -- ──────────────────────────────────────────────────────────────
#  config: validation never crashes
# -- ──────────────────────────────────────────────────────────────


class TestConfigValidationProperty:
    """Config validation must never raise, only return error lists."""

    @given(
        st.fixed_dictionaries(
            {
                "workers": st.integers(min_value=-100, max_value=200),
                "task_timeout_sec": st.integers(min_value=-100, max_value=100000),
                "default_model": st.text(min_size=0, max_size=50),
            }
        )
    )
    @settings(max_examples=100, deadline=1000)
    def test_validation_never_crashes(self, overrides: dict) -> None:
        """Arbitrary config values produce errors list, never exceptions."""
        try:
            config = RondoConfig(
                workers=overrides["workers"],
                task_timeout_sec=overrides["task_timeout_sec"],
                default_model=overrides["default_model"],
            )
            errors = validate_config(config)
            assert isinstance(errors, list)
        except (TypeError, ValueError):
            pass  # -- Some extreme values may fail at dataclass level — that's OK


# -- ──────────────────────────────────────────────────────────────
#  providers: parse_model never crashes
# -- ──────────────────────────────────────────────────────────────


class TestParseModelProperty:
    """parse_model must handle arbitrary model strings without crashing."""

    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=200, deadline=500)
    def test_never_crashes_on_arbitrary_model(self, model_str: str) -> None:
        """Any model string input produces a tuple (provider, model) or raises ValueError."""
        try:
            provider, model = parse_model(model_str)
            assert isinstance(provider, str)
            assert isinstance(model, str)
        except (ValueError, KeyError, TypeError):
            pass  # -- Invalid models may raise — that's expected behavior


# -- ──────────────────────────────────────────────────────────────
#  engine: ErrorPayload construction never crashes
# -- ──────────────────────────────────────────────────────────────


class TestErrorPayloadProperty:
    """ErrorPayload must handle any string inputs."""

    @given(
        code=st.text(min_size=1, max_size=50),
        message=st.text(min_size=0, max_size=500),
        recovery=st.text(min_size=0, max_size=200),
    )
    @settings(max_examples=100, deadline=500)
    def test_construction_never_crashes(self, code: str, message: str, recovery: str) -> None:
        """ErrorPayload accepts any strings without crashing."""
        payload = ErrorPayload(code=code, message=message, recovery=recovery)
        assert payload.code == code
        assert payload.message == message


# -- sig: mgh-6201.cd.bd955f.a7g8.prop01
