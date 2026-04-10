# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.smart_return — structured JSON output control.

REQ-111 reqs 420-443.
VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json

from rondo.smart_return import build_return_prompt, validate_return_json


class TestBuildReturnPrompt:
    """REQ-111 reqs 420-425: return prompt construction."""

    def test_default_prompt_has_required_fields(self) -> None:
        """Default prompt mentions all standard fields."""
        prompt = build_return_prompt()
        assert "passed" in prompt
        assert "confidence" in prompt
        assert "result" in prompt
        assert "issues" in prompt
        assert "suggestions" in prompt
        assert "metadata" in prompt
        assert "_meta" in prompt

    def test_custom_schema_overrides_everything(self) -> None:
        """Req 423: --return overrides defaults."""
        prompt = build_return_prompt(custom_schema='{"answer": "str"}')
        assert "answer" in prompt
        assert "RESPONSE FORMAT" in prompt
        assert "_meta" not in prompt  # -- custom overrides defaults

    def test_field_name_added_to_defaults(self) -> None:
        """Req 422: --field adds named field alongside defaults."""
        prompt = build_return_prompt(field_name="bugs")
        assert "bugs" in prompt
        assert "passed" in prompt  # -- defaults still present

    def test_coalesce_custom_wins_over_field(self) -> None:
        """Req 424: custom_schema takes precedence over field_name."""
        prompt = build_return_prompt(
            field_name="bugs",
            custom_schema='{"only_this": "str"}',
        )
        assert "only_this" in prompt
        assert "bugs" not in prompt

    def test_provider_specific_template(self) -> None:
        """Req 430: provider-specific templates used when available."""
        gemini_prompt = build_return_prompt(provider="gemini:flash")
        default_prompt = build_return_prompt(provider="unknown_provider")
        # -- Gemini uses example-based format
        assert gemini_prompt != default_prompt

    def test_grok_template(self) -> None:
        """Grok gets 'JSON API' framing."""
        prompt = build_return_prompt(provider="grok:grok-3")
        assert "JSON API" in prompt

    def test_local_template_simpler(self) -> None:
        """Req 433: local/ollama gets simpler template."""
        prompt = build_return_prompt(provider="local:llama")
        assert len(prompt) < len(build_return_prompt())  # -- shorter

    def test_empty_string_for_unknown_provider(self) -> None:
        """Unknown provider falls back to default template."""
        prompt = build_return_prompt(provider="newprovider:model")
        assert "passed" in prompt
        assert "confidence" in prompt


class TestValidateReturnJSON:
    """REQ-111 reqs 440-443: response validation + auto-rating."""

    def test_valid_complete_json(self) -> None:
        """Valid JSON with all fields returns _json_valid=True, _fields_complete=True."""
        response = json.dumps(
            {
                "passed": True,
                "confidence": 0.95,
                "result": "all good",
                "issues": [],
                "suggestions": ["add tests"],
                "metadata": {"language": "python"},
            }
        )
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["_fields_complete"] is True
        assert data["passed"] is True
        assert data["confidence"] == 0.95

    def test_partial_fields_still_valid(self) -> None:
        """JSON with 4+ standard fields counts as complete."""
        response = json.dumps(
            {
                "passed": False,
                "confidence": 0.8,
                "result": "found bugs",
                "issues": ["bug1"],
            }
        )
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["_fields_complete"] is True  # -- 4 of 6

    def test_too_few_fields_incomplete(self) -> None:
        """JSON with <4 standard fields is _fields_complete=False."""
        response = json.dumps({"passed": True, "result": "ok"})
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["_fields_complete"] is False  # -- only 2 of 6

    def test_json_in_markdown_extracted(self) -> None:
        """Req 442: JSON embedded in text is extracted via brace matching."""
        response = 'Here is my analysis:\n{"passed": true, "confidence": 0.9, "result": "ok", "issues": []}\nEnd.'
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["passed"] is True

    def test_invalid_json_graceful_degradation(self) -> None:
        """Req 443: completely invalid response returns parse_error dict."""
        response = "This is just plain text with no JSON at all."
        data = validate_return_json(response)
        assert data["_json_valid"] is False
        assert data["_fields_complete"] is False
        assert data["_parse_error"] is True
        assert data["passed"] is None
        assert "plain text" in data["result"]

    def test_empty_response(self) -> None:
        """Empty response returns graceful degradation."""
        data = validate_return_json("")
        assert data["_json_valid"] is False
        assert data["_parse_error"] is True

    def test_nested_json_extraction(self) -> None:
        """Nested braces don't confuse the extractor."""
        response = (
            'Answer: {"passed": false, "result": "found {brackets} in code", "confidence": 0.7, "issues": ["nested"]}'
        )
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["passed"] is False

    def test_result_truncated_at_5000(self) -> None:
        """Graceful degradation truncates long raw text."""
        long_text = "x" * 10000
        data = validate_return_json(long_text)
        assert len(data["result"]) == 5000


class TestConfigTemplateLoading:
    """REQ-111 req 430: config.toml return prompt templates."""

    def test_config_template_overrides_code(self, tmp_path) -> None:
        """Config template takes precedence over hardcoded."""
        import os

        config = tmp_path / "config.toml"
        config.write_text('[return_prompts.gemini]\nprompt = "CUSTOM GEMINI TEMPLATE"\n')
        os.environ["RONDO_CONFIG"] = str(config)
        try:
            prompt = build_return_prompt(provider="gemini:flash")
            assert "CUSTOM GEMINI TEMPLATE" in prompt
        finally:
            del os.environ["RONDO_CONFIG"]

    def test_no_config_falls_through_to_code(self) -> None:
        """No config file → uses hardcoded code template."""
        import os

        os.environ["RONDO_CONFIG"] = "/nonexistent/config.toml"
        try:
            prompt = build_return_prompt(provider="gemini:flash")
            assert "passed" in prompt.lower()  # -- code template has this
        finally:
            del os.environ["RONDO_CONFIG"]

    def test_config_default_template(self, tmp_path) -> None:
        """Config [return_prompts.default] used for unknown providers."""
        import os

        config = tmp_path / "config.toml"
        config.write_text('[return_prompts]\ndefault = "USE THIS DEFAULT"\n')
        os.environ["RONDO_CONFIG"] = str(config)
        try:
            prompt = build_return_prompt(provider="newprovider:model")
            assert "USE THIS DEFAULT" in prompt
        finally:
            del os.environ["RONDO_CONFIG"]


class TestNormalizeResponse:
    """REQ-111 reqs 470-475: response normalization."""

    def test_grok_nested_meta_hoisted(self) -> None:
        """Req 474: Grok nests _meta inside metadata → hoist to top level."""
        from rondo.smart_return import normalize_response

        data = {
            "passed": True,
            "confidence": 0.95,
            "result": "answer",
            "issues": [],
            "suggestions": [],
            "metadata": {
                "topic": "security",
                "_meta": {"quality": 8, "complete": True, "limitations": "none"},
            },
        }
        normalized = normalize_response(data)
        assert "_meta" in normalized
        assert normalized["_meta"]["quality"] == 8
        assert "_meta" not in normalized["metadata"]

    def test_missing_fields_filled_with_defaults(self) -> None:
        """Req 472: missing standard fields get defaults."""
        from rondo.smart_return import normalize_response

        data = {"passed": True, "result": "answer"}
        normalized = normalize_response(data)
        assert normalized["confidence"] == 0.0
        assert normalized["issues"] == []
        assert normalized["suggestions"] == []
        assert normalized["_meta"]["quality"] == 0

    def test_extra_fields_preserved(self) -> None:
        """Req 475: provider-specific extra fields are NOT stripped."""
        from rondo.smart_return import normalize_response

        data = {"passed": True, "result": "answer", "custom_field": "kept"}
        normalized = normalize_response(data)
        assert normalized["custom_field"] == "kept"

    def test_openai_template_exists(self) -> None:
        """OpenAI has a dedicated template."""
        prompt = build_return_prompt(provider="openai:gpt-4.1")
        assert "passed" in prompt.lower()


# -- sig: mgh-6201.cd.bd955f.5ead.e35e50
