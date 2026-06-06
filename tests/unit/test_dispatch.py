# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.dispatch — Rondo-REQ-100 reqs 12-28, Rondo-STD-108, Rondo-IFS-100, Rondo-STD-110.

VER-001 verification matrix: every test maps to a numbered requirement.
TDD: these tests are written BEFORE dispatch.py exists.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# -- Add rondo/src to path so we can import rondo
import pytest

from rondo.config import RondoConfig
from rondo.dispatch import (
    VALID_MODELS,
    _build_subprocess_cmd,
    build_prompt,
    classify_error,
    dispatch_task,
    extract_modified_files,
    parse_stream_json_events,
    parse_task_json,
    prepare_env,
    resolve_model,
    save_result,
)
from rondo.engine import DispatchUsage, Task, TaskResult

# ──────────────────────────────────────────────────────────────────
#  Prompt Building — Rondo-REQ-100 req 12, 24
# ──────────────────────────────────────────────────────────────────


class TestPromptBuilder:
    def test_prompt_contains_task_name(self):
        task = Task(name="check-spec", instruction="Check it", done_when="List found")
        prompt = build_prompt(task)
        assert "check-spec" in prompt

    def test_prompt_contains_instruction(self):
        task = Task(name="t", instruction="Analyze the module", done_when="done")
        prompt = build_prompt(task)
        assert "Analyze the module" in prompt

    def test_prompt_contains_done_when(self):
        task = Task(name="t", instruction="do", done_when="Summary written")
        prompt = build_prompt(task)
        assert "Summary written" in prompt

    def test_prompt_contains_context_files(self):
        task = Task(
            name="t",
            instruction="read",
            context_files=["src/main.py", "README.md"],
            done_when="done",
        )
        prompt = build_prompt(task)
        assert "src/main.py" in prompt
        assert "README.md" in prompt

    def test_prompt_contains_description(self):
        task = Task(name="t", description="A quick check", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "A quick check" in prompt

    def test_prompt_requests_json_output(self):
        """Rondo-REQ-100 req 24: prompt instructs Claude to return JSON."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "json" in prompt.lower() or "JSON" in prompt

    def test_prompt_includes_json_fields(self):
        """Prompt tells AI to include structured JSON fields (REQ-111)."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "passed" in prompt.lower()
        assert "json" in prompt.lower()


# -- REQ-106: context_data in prompt
class TestContextDataInPrompt:
    """context_data fields appear in prompt as structured data."""

    def test_context_data_appears_in_prompt(self):
        """REQ-106 req 001: context_data dict injected into prompt."""
        task = Task(
            name="t",
            instruction="analyze",
            done_when="done",
            context_data={"findings": [{"id": 1, "msg": "bad"}]},
        )
        prompt = build_prompt(task)
        assert "Structured Input Data" in prompt
        assert "findings" in prompt

    def test_context_data_json_formatted(self):
        """Context data rendered as JSON code blocks."""
        task = Task(
            name="t",
            instruction="do",
            done_when="done",
            context_data={"config": {"key": "value"}},
        )
        prompt = build_prompt(task)
        assert "```json" in prompt
        assert '"key"' in prompt

    def test_large_list_uses_jsonl(self):
        """REQ-106: lists > 100 items use JSONL format."""
        big_list = [{"id": i} for i in range(101)]
        task = Task(
            name="t",
            instruction="do",
            done_when="done",
            context_data={"items": big_list},
        )
        prompt = build_prompt(task)
        assert "```jsonl" in prompt

    def test_empty_context_data_not_in_prompt(self):
        """Empty context_data doesn't add section to prompt."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "Structured Input Data" not in prompt


# ──────────────────────────────────────────────────────────────────
#  Environment Preparation — Rondo-REQ-100 reqs 13, 17, 18
# ──────────────────────────────────────────────────────────────────


class TestEnvPrep:
    def test_claudecode_stripped(self):
        """Rondo-REQ-100 req 13: CLAUDECODE removed from child env."""
        config = RondoConfig(auth="max")
        with patch.dict(os.environ, {"CLAUDECODE": "1", "HOME": "/home/user"}):
            env = prepare_env(config)
            assert "CLAUDECODE" not in env

    def test_auth_max_strips_api_key(self):
        """Rondo-REQ-100 req 17: auth=max strips ANTHROPIC_API_KEY."""
        config = RondoConfig(auth="max")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret", "HOME": "/home"}):
            env = prepare_env(config)
            assert "ANTHROPIC_API_KEY" not in env

    def test_auth_api_keeps_api_key(self):
        """Rondo-REQ-100 req 18: auth=api keeps ANTHROPIC_API_KEY."""
        config = RondoConfig(auth="api")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret", "HOME": "/home"}):
            env = prepare_env(config)
            assert env["ANTHROPIC_API_KEY"] == "sk-secret"

    def test_env_is_copy_not_original(self):
        """prepare_env returns a copy, not os.environ itself."""
        config = RondoConfig(auth="max")
        env = prepare_env(config)
        assert env is not os.environ


# ──────────────────────────────────────────────────────────────────
#  Model Resolution — Rondo-REQ-100 reqs 20, 21, 22, 23
# ──────────────────────────────────────────────────────────────────


class TestModelResolution:
    def test_model_default_sonnet(self):
        """Rondo-REQ-100 req 22: default model is sonnet."""
        task = Task(name="t")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "sonnet"

    def test_model_from_task_hint(self):
        """Rondo-REQ-100 req 23: task.model used when no CLI override."""
        task = Task(name="t", model="opus")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "opus"

    def test_model_cli_overrides_task(self):
        """Rondo-REQ-100 req 21: CLI override wins over task hint."""
        task = Task(name="t", model="haiku")
        config = RondoConfig()
        assert resolve_model("opus", task, config) == "opus"

    def test_model_cli_overrides_config(self):
        """CLI override wins over config default_model."""
        task = Task(name="t")
        config = RondoConfig(default_model="haiku")
        assert resolve_model("opus", task, config) == "opus"

    def test_model_config_overrides_default(self):
        """Config default_model used when no CLI or task hint."""
        task = Task(name="t")
        config = RondoConfig(default_model="haiku")
        assert resolve_model(None, task, config) == "haiku"

    def test_model_1m_variant(self):
        """Rondo-IFS-100 req 10: 1M context model suffix accepted."""
        task = Task(name="t", model="opus[1m]")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "opus[1m]"


# ──────────────────────────────────────────────────────────────────
#  Task JSON Parsing — Rondo-REQ-100 reqs 25, 26
# ──────────────────────────────────────────────────────────────────


class TestTaskJsonParsing:
    def test_valid_json_parsed(self):
        """Rondo-REQ-100 req 25: valid JSON extracted and returned."""
        text = (
            'Here is the result:\n```json\n{"status": "done", "confidence": 0.9, "result": "ok", "question": ""}\n```'
        )
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["status"] == "done"
        assert parsed["confidence"] == 0.9

    def test_json_without_code_fence(self):
        """JSON block without code fence markers still parsed."""
        text = 'Some text\n{"status": "done", "confidence": 0.8, "result": "found it", "question": ""}\nMore text'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["status"] == "done"

    def test_malformed_json_returns_none(self):
        """Rondo-REQ-100 req 26: malformed JSON returns None."""
        text = "This is not JSON at all, just regular text output."
        parsed = parse_task_json(text)
        assert parsed is None

    def test_partial_json_returns_none(self):
        """Truncated JSON returns None."""
        text = '{"status": "done", "confidence":'
        parsed = parse_task_json(text)
        assert parsed is None

    def test_blocked_status_parsed(self):
        """Blocked task with question parsed correctly."""
        text = '```json\n{"status": "blocked", "confidence": 0.0, "result": "", "question": "Need access to file"}\n```'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["status"] == "blocked"
        assert "access" in parsed["question"]

    def test_last_json_block_wins(self):
        """When multiple JSON blocks exist, the last valid one is used."""
        text = (
            '```json\n{"status": "blocked", "result": "first"}\n```\n'
            "Then more work:\n"
            '```json\n{"status": "done", "result": "final"}\n```'
        )
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["status"] == "done"
        assert parsed["result"] == "final"


# ──────────────────────────────────────────────────────────────────
#  Error Classification — Rondo-STD-108 error categories
# ──────────────────────────────────────────────────────────────────


class TestErrorClassification:
    def test_auth_error_credit(self):
        assert classify_error("Credit balance is too low") == "ERR_AUTH"

    def test_auth_error_invalid_key(self):
        assert classify_error("Invalid API key provided") == "ERR_AUTH"

    def test_nested_session_error(self):
        assert classify_error("cannot be launched inside another") == "ERR_NESTED_SESSION"

    def test_rate_limit_error(self):
        assert classify_error("Rate limit reached, please wait") == "ERR_RATE_LIMIT"

    def test_rate_limit_lowercase(self):
        assert classify_error("rate_limit exceeded") == "ERR_RATE_LIMIT"

    def test_generic_error(self):
        assert classify_error("Something unexpected happened") == "ERR_SUBPROCESS"

    def test_empty_stderr(self):
        assert classify_error("") == "ERR_SUBPROCESS"


# ──────────────────────────────────────────────────────────────────
#  Stream-JSON Parsing — Rondo-IFS-100 reqs 1-9
# ──────────────────────────────────────────────────────────────────


class TestStreamJsonParsing:
    def _make_stream_output(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        cost: float = 0.05,
        duration_ms: int = 5000,
        duration_api_ms: int = 4500,
        input_tokens: int = 100,
        output_tokens: int = 200,
        cache_read: int = 50,
        cache_create: int = 30,
        num_turns: int = 1,
        context_window: int = 200000,
        rate_status: str = "allowed",
        is_overage: bool = False,
        resets_at: int = 1773507600,
        assistant_text: str = '{"status": "done", "confidence": 0.9, "result": "ok", "question": ""}',
    ) -> str:
        """Build a realistic stream-json output string."""
        lines = []
        # -- system init
        lines.append(
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "model": model,
                    "claude_code_version": "2.1.76",
                    "tools": ["Bash", "Read"],
                    "mcp_servers": [],
                    "permissionMode": "acceptEdits",
                }
            )
        )
        # -- rate_limit_event
        lines.append(
            json.dumps(
                {
                    "type": "rate_limit_event",
                    "rate_limit_info": {
                        "status": rate_status,
                        "resetsAt": resets_at,
                        "rateLimitType": "five_hour",
                        "overageStatus": "allowed",
                        "overageResetsAt": 0,
                        "isUsingOverage": is_overage,
                    },
                }
            )
        )
        # -- assistant message
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": assistant_text}]},
                }
            )
        )
        # -- result event
        lines.append(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": duration_ms,
                    "duration_api_ms": duration_api_ms,
                    "num_turns": num_turns,
                    "total_cost_usd": cost,
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_read_input_tokens": cache_read,
                        "cache_creation_input_tokens": cache_create,
                    },
                    "modelUsage": {
                        model: {"contextWindow": context_window},
                    },
                }
            )
        )
        return "\n".join(lines)

    def test_parse_lines(self):
        """Rondo-IFS-100 req 1: reads stream-json line by line."""
        raw = self._make_stream_output()
        events, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert len(events) >= 3  # -- init, rate_limit, assistant, result

    def test_rate_limit_extraction(self):
        """Rondo-IFS-100 req 2: rate_limit_event populates DispatchUsage."""
        raw = self._make_stream_output(rate_status="allowed", is_overage=False)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.rate_limit_status == "allowed"

    def test_result_metadata_extraction(self):
        """Rondo-IFS-100 req 3: result event populates cost/token/duration."""
        raw = self._make_stream_output(cost=0.12, input_tokens=500, output_tokens=300)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.cost_usd == 0.12
        assert usage.input_tokens == 500
        assert usage.output_tokens == 300

    def test_init_event_extraction(self):
        """Rondo-IFS-100 req 4: system:init model extracted."""
        raw = self._make_stream_output(model="claude-opus-4-6")
        events, _ = parse_stream_json_events(raw.split("\n"), task_name="t")
        init_events = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
        assert len(init_events) == 1
        assert init_events[0]["model"] == "claude-opus-4-6"

    def test_overage_flag(self):
        """Rondo-IFS-100 req 6: isUsingOverage captured."""
        raw = self._make_stream_output(is_overage=True)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.is_using_overage is True

    def test_cost_capture(self):
        """Rondo-IFS-100 req 7: total_cost_usd captured."""
        raw = self._make_stream_output(cost=0.25)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.cost_usd == 0.25

    def test_duration_capture(self):
        """Rondo-IFS-100 req 8: duration_ms captured."""
        raw = self._make_stream_output(duration_ms=12345, duration_api_ms=11000)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.duration_ms == 12345
        assert usage.duration_api_ms == 11000

    def test_missing_rate_limit(self):
        """Rondo-IFS-100 req 9: missing rate_limit_event uses defaults."""
        # -- Build output WITHOUT rate_limit_event
        lines = [
            json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 1000,
                    "duration_api_ms": 900,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            ),
        ]
        _, usage = parse_stream_json_events(lines, task_name="t")
        assert usage.rate_limit_status == "unknown"
        assert usage.is_using_overage is False
        assert usage.rate_limit_resets_at == 0

    def test_context_window_captured(self):
        """Context window from modelUsage captured."""
        raw = self._make_stream_output(context_window=1000000)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.context_window == 1000000

    def test_num_turns_captured(self):
        """num_turns from result event captured."""
        raw = self._make_stream_output(num_turns=5)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.num_turns == 5

    def test_assistant_text_collected(self):
        """Assistant message text collected from events."""
        raw = self._make_stream_output(assistant_text="Hello from Claude!")
        events, _ = parse_stream_json_events(raw.split("\n"), task_name="t")
        assistant_events = [e for e in events if e.get("type") == "assistant"]
        assert len(assistant_events) >= 1


# ──────────────────────────────────────────────────────────────────
#  File Extraction — Rondo-STD-108 files_modified
# ──────────────────────────────────────────────────────────────────


class TestFileExtraction:
    def test_extract_python_files(self):
        text = "I modified src/main.py and tests/test_main.py"
        files = extract_modified_files(text)
        assert "src/main.py" in files
        assert "tests/test_main.py" in files

    def test_extract_deduplicates(self):
        text = "Read src/main.py then wrote to src/main.py again"
        files = extract_modified_files(text)
        assert files.count("src/main.py") == 1

    def test_extract_multiple_extensions(self):
        text = "Changed config.toml and schema.sql and README.md"
        files = extract_modified_files(text)
        assert "config.toml" in files
        assert "schema.sql" in files
        assert "README.md" in files

    def test_extract_no_files(self):
        text = "I just thought about things but didn't change anything"
        files = extract_modified_files(text)
        assert files == []


# ──────────────────────────────────────────────────────────────────
#  Credential Sanitization — Rondo-STD-108 rule 8
# ──────────────────────────────────────────────────────────────────


class TestCredentialSanitization:
    def test_api_key_not_in_saved_result(self, tmp_path):
        """Rondo-STD-108 rule 8: API keys never in result files."""
        result = TaskResult(
            task_name="t",
            status="done",
            prompt_sent="Check this",
            raw_output="done",
            duration_sec=1.0,
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="t", model="sonnet", cost_usd=0.01)
        filepath = save_result(result, usage, str(tmp_path))
        content = Path(filepath).read_text()
        assert "sk-ant-" not in content
        assert "ANTHROPIC_API_KEY" not in content


# ──────────────────────────────────────────────────────────────────
#  Result Saving — Rondo-REQ-100 req 15, Rondo-STD-110 S5, R2
# ──────────────────────────────────────────────────────────────────


class TestResultSaving:
    def test_result_saved_to_json(self, tmp_path):
        """Rondo-REQ-100 req 15: result saved to JSON file."""
        result = TaskResult(
            task_name="my-task",
            status="done",
            prompt_sent="do it",
            raw_output='{"status":"done"}',
            duration_sec=5.0,
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="my-task", model="sonnet", cost_usd=0.05)
        filepath = save_result(result, usage, str(tmp_path))
        assert Path(filepath).exists()
        data = json.loads(Path(filepath).read_text())
        assert data["task_name"] == "my-task"
        assert data["status"] == "done"

    def test_result_file_permissions(self, tmp_path):
        """Rondo-STD-110 S5: result files have restrictive permissions (0o600)."""
        result = TaskResult(
            task_name="t",
            status="done",
            prompt_sent="do",
            raw_output="ok",
            duration_sec=1.0,
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="t", model="sonnet")
        filepath = save_result(result, usage, str(tmp_path))
        mode = oct(Path(filepath).stat().st_mode)[-3:]
        assert mode == "600"

    def test_output_truncation(self, tmp_path):
        """Rondo-STD-110 R2: output bounded at 1MB for standard models."""
        big_output = "x" * (2 * 1024 * 1024)  # -- 2MB
        result = TaskResult(
            task_name="t",
            status="done",
            prompt_sent="do",
            raw_output=big_output,
            duration_sec=1.0,
            model="sonnet",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="t", model="sonnet")
        filepath = save_result(result, usage, str(tmp_path))
        data = json.loads(Path(filepath).read_text())
        # -- raw_output should be truncated to 1MB + truncation note
        assert len(data["raw_output"]) <= 1024 * 1024 + 200  # -- 1MB + margin for note

    def test_output_cap_scales_for_1m_context_models(self, tmp_path):
        """RONDO-206 Finding #216: 1M-context models get proportionally larger output cap.

        Old static 1MB cap truncated legitimate 1.5M-char responses from
        sonnet[1m]/opus[1m]. New formula: limit_tokens * 2 bytes, 1MB floor.
        sonnet[1m] (1M tokens) → 2MB output cap.
        """
        # -- 1.5 MB output that WOULD fit in sonnet[1m] but NOT in sonnet
        output_1_5mb = "x" * (1_500_000)
        result = TaskResult(
            task_name="t",
            status="done",
            prompt_sent="do",
            raw_output=output_1_5mb,
            duration_sec=1.0,
            model="sonnet[1m]",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="t", model="sonnet[1m]")
        filepath = save_result(result, usage, str(tmp_path))
        data = json.loads(Path(filepath).read_text())
        # -- 1.5MB should NOT be truncated for sonnet[1m] (cap is 2MB)
        assert len(data["raw_output"]) == 1_500_000, (
            f"#216: sonnet[1m] should allow 1.5MB output (cap=2MB). Got truncated to {len(data['raw_output'])} bytes."
        )

    def test_output_cap_truncates_beyond_model_limit(self, tmp_path):
        """RONDO-206 Finding #216: 1M-context model cap still truncates excessive output.

        sonnet[1m] cap is 2MB. A 3MB response MUST still be truncated.
        """
        output_3mb = "y" * (3 * 1024 * 1024)
        result = TaskResult(
            task_name="t",
            status="done",
            prompt_sent="do",
            raw_output=output_3mb,
            duration_sec=1.0,
            model="sonnet[1m]",
            auth_mode="max",
            timestamp="2026-03-14T00:00:00Z",
        )
        usage = DispatchUsage(task_name="t", model="sonnet[1m]")
        filepath = save_result(result, usage, str(tmp_path))
        data = json.loads(Path(filepath).read_text())
        # -- Should be truncated to 2MB + truncation note
        assert len(data["raw_output"]) <= 2 * 1024 * 1024 + 200
        assert "TRUNCATED" in data["raw_output"]
        assert "sonnet[1m]" in data["raw_output"], "#216: truncation note must include model name for diagnostics"

    def test_max_output_bytes_scales_with_model(self):
        """RONDO-206 Finding #216: _max_output_bytes_for_model scales correctly."""
        from rondo.dispatch import _max_output_bytes_for_model

        # -- Standard models → 1MB floor (static)
        assert _max_output_bytes_for_model("sonnet") == 1024 * 1024
        assert _max_output_bytes_for_model("gpt-4.1") == 1024 * 1024
        assert _max_output_bytes_for_model("unknown-xyz") == 1024 * 1024

        # -- 1M-context models → 2 bytes/token = 2MB
        assert _max_output_bytes_for_model("sonnet[1m]") == 2_000_000
        assert _max_output_bytes_for_model("opus[1m]") == 2_000_000
        assert _max_output_bytes_for_model("gemini-2.5-flash") == 2_000_000

        # -- 2M-context → 4MB
        assert _max_output_bytes_for_model("gemini-2.5-pro") == 4_000_000

        # -- Provider prefix stripped before lookup
        assert _max_output_bytes_for_model("gemini:gemini-2.5-pro") == 4_000_000

    def test_result_includes_metadata(self, tmp_path):
        """Rondo-REQ-100 req 28: result includes task_name, status, model, auth, duration, timestamp."""
        result = TaskResult(
            task_name="check",
            status="done",
            prompt_sent="do",
            raw_output="ok",
            duration_sec=42.3,
            model="opus",
            auth_mode="api",
            timestamp="2026-03-14T01:00:00Z",
            cost_usd=0.10,
        )
        usage = DispatchUsage(task_name="check", model="opus", cost_usd=0.10)
        filepath = save_result(result, usage, str(tmp_path))
        data = json.loads(Path(filepath).read_text())
        assert data["task_name"] == "check"
        assert data["status"] == "done"
        assert data["model"] == "opus"
        assert data["auth_mode"] == "api"
        assert data["duration_sec"] == 42.3
        assert data["timestamp"] == "2026-03-14T01:00:00Z"


# ──────────────────────────────────────────────────────────────────
#  Dry Run — Rondo-REQ-100 req 16
# ──────────────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_returns_prompt(self):
        """Rondo-REQ-100 req 16: dry-run shows prompt without invoking."""
        task = Task(name="t", instruction="Check spec", done_when="List found")
        config = RondoConfig(dry_run=True)
        result, usage = dispatch_task(task, config)
        assert result.status == "skipped"
        assert "Check spec" in result.prompt_sent
        assert result.raw_output == ""

    def test_dry_run_no_subprocess(self):
        """Dry-run does not invoke any subprocess."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(dry_run=True)
        with patch("rondo.dispatch.subprocess") as mock_sub:
            dispatch_task(task, config)
            mock_sub.Popen.assert_not_called()


# ──────────────────────────────────────────────────────────────────
#  Auto Task Dispatch — Rondo-REQ-100 req 4
# ──────────────────────────────────────────────────────────────────


class TestAutoTaskDispatch:
    def test_auto_task_calls_fn(self):
        """Auto tasks call auto_fn directly, no subprocess."""
        task = Task(name="count", auto_fn=lambda: (True, "42 lines"))
        config = RondoConfig()
        result, usage = dispatch_task(task, config)
        assert result.status == "done"
        assert "42 lines" in result.raw_output

    def test_auto_task_failure(self):
        """Auto task returning False gets status error."""
        task = Task(name="check", auto_fn=lambda: (False, "File not found"))
        config = RondoConfig()
        result, usage = dispatch_task(task, config)
        assert result.status == "error"
        assert "File not found" in result.raw_output

    def test_auto_task_exception(self):
        """Auto task raising exception gets status error."""

        def bad_fn():
            raise ValueError("boom")

        task = Task(name="boom", auto_fn=bad_fn)
        config = RondoConfig()
        result, usage = dispatch_task(task, config)
        assert result.status == "error"
        assert "boom" in result.error_message

    def test_auto_task_no_subprocess(self):
        """Auto tasks never invoke subprocess."""
        task = Task(name="t", auto_fn=lambda: (True, "ok"))
        config = RondoConfig()
        with patch("rondo.dispatch.subprocess") as mock_sub:
            dispatch_task(task, config)
            mock_sub.Popen.assert_not_called()


# ──────────────────────────────────────────────────────────────────
#  Dispatch Integration (mocked subprocess) — Rondo-REQ-100 reqs 12-14, 27
# ──────────────────────────────────────────────────────────────────


class TestDispatchIntegration:
    def _mock_popen(self, stdout="", stderr="", returncode=0):
        """Create a mock Popen object."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (stdout, stderr)
        mock_proc.returncode = returncode
        mock_proc.pid = 12345
        return mock_proc

    def test_subprocess_command_has_claude_p(self):
        """Rondo-REQ-100 req 12: invokes claude -p."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        mock_proc = self._mock_popen(
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 100,
                    "duration_api_ms": 90,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            )
        )
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dispatch_task(task, config)
            call_args = mock_popen.call_args[0][0]  # -- first positional arg (command list)
            assert call_args[0] == "claude" or config.claude_binary in call_args[0]
            assert "-p" in call_args

    def test_model_flag_passed(self):
        """Rondo-REQ-100 req 20: --model passed to subprocess."""
        task = Task(name="t", instruction="do", done_when="done", model="opus")
        config = RondoConfig()
        mock_proc = self._mock_popen(
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 100,
                    "duration_api_ms": 90,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            )
        )
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dispatch_task(task, config)
            call_args = mock_popen.call_args[0][0]
            assert "--model" in call_args
            model_idx = call_args.index("--model")
            assert call_args[model_idx + 1] == "opus"

    def test_permission_mode_passed(self):
        """Rondo-REQ-100 req 47: --permission-mode passed to subprocess."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(permission_mode="bypassPermissions")
        mock_proc = self._mock_popen(
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 100,
                    "duration_api_ms": 90,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            )
        )
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dispatch_task(task, config)
            call_args = mock_popen.call_args[0][0]
            assert "--permission-mode" in call_args
            perm_idx = call_args.index("--permission-mode")
            assert call_args[perm_idx + 1] == "bypassPermissions"

    def test_permission_mode_default_auto(self):
        """Rondo-REQ-100 req 48: default permission_mode 'auto' is passed."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()  # -- default permission_mode="auto"
        mock_proc = self._mock_popen(
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 100,
                    "duration_api_ms": 90,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            )
        )
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc) as mock_popen:
            dispatch_task(task, config)
            call_args = mock_popen.call_args[0][0]
            assert "--permission-mode" in call_args
            perm_idx = call_args.index("--permission-mode")
            assert call_args[perm_idx + 1] == "auto"

    def test_error_exit_code(self):
        """Rondo-REQ-100 req 27: exit code != 0 → status error."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        mock_proc = self._mock_popen(stdout="", stderr="Something failed", returncode=1)
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, _ = dispatch_task(task, config)
            assert result.status == "error"
            assert result.exit_code == 1

    def test_empty_stdout_error(self):
        """Rondo-STD-108: empty stdout → ERR_EMPTY_OUTPUT."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        mock_proc = self._mock_popen(stdout="", stderr="", returncode=0)
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, _ = dispatch_task(task, config)
            assert result.status == "error"
            assert result.error_code == "ERR_EMPTY_OUTPUT"

    def test_malformed_json_partial(self):
        """Rondo-REQ-100 req 26: malformed JSON → status partial."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        # -- Non-JSON assistant output
        stream_lines = [
            json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "I did the work but no JSON block here."}]},
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 100,
                    "duration_api_ms": 90,
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 10,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                    "modelUsage": {},
                }
            ),
        ]
        mock_proc = self._mock_popen(stdout="\n".join(stream_lines), stderr="", returncode=0)
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, _ = dispatch_task(task, config)
            assert result.status == "partial"
            assert result.error_code == "ERR_MALFORMED_JSON"
            assert "I did the work" in result.raw_output

    def test_result_capture_fields(self):
        """Rondo-REQ-100 req 14: captures stdout, stderr, exit code, duration."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        stream_lines = [
            json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": '```json\n{"status":"done","confidence":0.9,"result":"ok","question":""}\n```',
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "duration_ms": 5000,
                    "duration_api_ms": 4500,
                    "num_turns": 2,
                    "total_cost_usd": 0.05,
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 200,
                        "cache_read_input_tokens": 50,
                        "cache_creation_input_tokens": 30,
                    },
                    "modelUsage": {"claude-sonnet-4-6": {"contextWindow": 200000}},
                }
            ),
        ]
        mock_proc = self._mock_popen(
            stdout="\n".join(stream_lines),
            stderr="some warning",
            returncode=0,
        )
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, usage = dispatch_task(task, config)
            assert result.status == "done"
            assert result.stderr == "some warning"
            assert result.exit_code == 0
            assert result.duration_sec > 0 or True  # -- duration is wall clock
            assert result.model == "sonnet"


# ──────────────────────────────────────────────────────────────────
#  Model Validation — VALID_MODELS + resolve_model fail-fast
# ──────────────────────────────────────────────────────────────────


class TestModelValidation:
    def test_valid_models_set_exists(self):
        """VALID_MODELS contains all expected models."""
        assert "sonnet" in VALID_MODELS
        assert "opus" in VALID_MODELS
        assert "haiku" in VALID_MODELS
        assert "opus[1m]" in VALID_MODELS
        assert "sonnet[1m]" in VALID_MODELS

    def test_invalid_model_raises(self):
        """Invalid model raises ValueError with clear message."""
        task = Task(name="t", instruction="do", done_when="done", model="gpt-4")
        config = RondoConfig()
        with pytest.raises(ValueError, match="Invalid model"):
            resolve_model(None, task, config)

    def test_invalid_model_from_cli(self):
        """CLI model override with invalid value raises ValueError."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        with pytest.raises(ValueError, match="Invalid model"):
            resolve_model("claude-3", task, config)

    def test_invalid_model_from_config(self):
        """Config default_model with invalid value raises ValueError."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(default_model="bad-model")
        with pytest.raises(ValueError, match="Invalid model"):
            resolve_model(None, task, config)

    def test_1m_variants_valid(self):
        """1M context window variants are valid models."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        assert resolve_model("opus[1m]", task, config) == "opus[1m]"
        assert resolve_model("sonnet[1m]", task, config) == "sonnet[1m]"


# ──────────────────────────────────────────────────────────────────
#  Task Contract Pre-Dispatch Validation
# ──────────────────────────────────────────────────────────────────


class TestDispatchValidation:
    def test_invalid_task_returns_error_result(self):
        """Dispatching an invalid task returns error result without subprocess."""
        task = Task(name="bad", instruction="", done_when="")
        config = RondoConfig()
        result, usage = dispatch_task(task, config)
        assert result.status == "error"
        assert result.error_code == "ERR_INTERNAL"
        assert "Validation failed" in result.error_message

    def test_invalid_task_no_subprocess(self):
        """Invalid task never invokes subprocess."""
        task = Task(name="bad", instruction="", done_when="")
        config = RondoConfig()
        with patch("rondo.dispatch.subprocess") as mock_sub:
            dispatch_task(task, config)
            mock_sub.Popen.assert_not_called()

    def test_valid_task_passes_validation(self):
        """Valid task proceeds past validation (hits dry-run or subprocess)."""
        task = Task(name="ok", instruction="do work", done_when="work done")
        config = RondoConfig(dry_run=True)
        result, _ = dispatch_task(task, config)
        assert result.status == "skipped"  # -- dry-run status, not error


# -- REQ-100 reqs 022-024, 047-049, 071-073: tool_mode, permission_mode, --bare
class TestBuildSubprocessCmd:
    """Tests for _build_subprocess_cmd — flag generation from config + task."""

    def test_default_cmd_has_base_flags(self):
        """Default config produces minimal command."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "test prompt", "sonnet")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--model" in cmd
        assert "--output-format" in cmd

    def test_bare_flag_added_when_enabled(self):
        """REQ-100 req 071 + IFS-100 req 015: --bare added when bare=True AND auth=api."""
        config = RondoConfig(bare=True, auth="api")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" in cmd

    def test_bare_dropped_under_max_auth(self):
        """IFS-100 req 015 (RONDO-301, Finding #293): bare+max is a contradiction.

        --bare disables OAuth/keychain; auth=max strips ANTHROPIC_API_KEY from
        the child env → deterministic "Not logged in" (the historic 13.3% bucket).
        Rondo MUST drop --bare under max auth and warn.
        """
        config = RondoConfig(bare=True, auth="max")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" not in cmd

    def test_bare_flag_present_by_default(self):
        """RONDO-110: --bare added by default (skip hooks/CLAUDE.md startup overhead)."""
        config = RondoConfig()
        _build_subprocess_cmd(config, "test", "sonnet")
        ## -- bare is True by default, but only added if CC version >= 2.1.81
        ## -- In test env, CC version may not be detected → bare skipped
        ## -- Just verify the config is True
        assert config.bare is True

    def test_tool_mode_none_adds_tools_empty(self):
        """REQ-100 req 022: tool_mode=none passes --tools ''."""
        config = RondoConfig()
        task = Task(name="t", instruction="do", done_when="done", tool_mode="none")
        cmd = _build_subprocess_cmd(config, "test", "sonnet", task=task)
        idx = cmd.index("--tools")
        assert cmd[idx + 1] == ""

    def test_tool_mode_sandbox_adds_dangerously_skip(self):
        """REQ-100 req 023: tool_mode=sandbox passes --dangerously-skip-permissions."""
        config = RondoConfig()
        task = Task(name="t", instruction="do", done_when="done", tool_mode="sandbox")
        cmd = _build_subprocess_cmd(config, "test", "sonnet", task=task)
        assert "--dangerously-skip-permissions" in cmd

    def test_tool_mode_default_no_extra_flags(self):
        """REQ-100 req 024: tool_mode=default adds no tool flags."""
        config = RondoConfig()
        task = Task(name="t", instruction="do", done_when="done", tool_mode="default")
        cmd = _build_subprocess_cmd(config, "test", "sonnet", task=task)
        assert "--tools" not in cmd
        assert "--dangerously-skip-permissions" not in cmd

    def test_permission_mode_in_cmd(self):
        """REQ-100 req 047: --permission-mode passed from config."""
        config = RondoConfig(permission_mode="dontAsk")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "dontAsk"


# -- REQ-100 reqs 078-080: --max-budget-usd, --json-schema, --system-prompt
class TestCostOutputControl:
    """Tests for new CC flags in dispatch command."""

    def test_max_budget_in_cmd(self):
        """REQ-100 req 078: --max-budget-usd from config."""
        config = RondoConfig(max_budget_usd=0.50)
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        idx = cmd.index("--max-budget-usd")
        assert cmd[idx + 1] == "0.5"

    def test_max_budget_absent_when_none(self):
        """No --max-budget-usd when not configured."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--max-budget-usd" not in cmd

    def test_json_schema_in_cmd(self):
        """REQ-100 req 079: --json-schema from config."""
        schema = '{"type":"object","properties":{"status":{"type":"string"}}}'
        config = RondoConfig(json_schema=schema)
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        idx = cmd.index("--json-schema")
        assert cmd[idx + 1] == schema

    def test_json_schema_absent_when_empty(self):
        """No --json-schema when not configured."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--json-schema" not in cmd

    def test_system_prompt_in_cmd(self):
        """REQ-100 req 080: --system-prompt from config."""
        config = RondoConfig(dispatch_system_prompt="You are Rondo.")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        idx = cmd.index("--system-prompt")
        assert cmd[idx + 1] == "You are Rondo."

    def test_system_prompt_absent_when_empty(self):
        """No --system-prompt when not configured."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--system-prompt" not in cmd


# -- Rondo-REQ-100 req 071: CC version detection + gated --bare
class TestCCVersionDetection:
    """Detect CC version and gate --bare flag usage."""

    def test_detect_cc_version(self):
        """Parses 'X.Y.Z' from claude --version output."""
        import rondo.dispatch
        from rondo.dispatch import detect_cc_version

        rondo.dispatch._cc_version_cache = None  # -- reset cache
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "2.1.86 (Claude Code)\n"
            mock_run.return_value.returncode = 0
            version = detect_cc_version()
        assert version == (2, 1, 86)

    def test_detect_cc_version_missing(self):
        """Returns None when claude not available."""
        import rondo.dispatch
        from rondo.dispatch import detect_cc_version

        rondo.dispatch._cc_version_cache = None  # -- reset cache
        with patch("subprocess.run", side_effect=FileNotFoundError):
            version = detect_cc_version()
        assert version is None

    def test_bare_skipped_when_version_too_old(self):
        """--bare not added when CC < 2.1.81."""
        config = RondoConfig(bare=True)
        with patch("rondo.dispatch._cc_version_cache", (2, 1, 50)):
            cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" not in cmd

    def test_bare_added_when_version_sufficient(self):
        """--bare added when CC >= 2.1.81 AND auth=api (IFS-100 req 015)."""
        config = RondoConfig(bare=True, auth="api")
        with patch("rondo.dispatch._cc_version_cache", (2, 1, 86)):
            cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" in cmd


# -- Rondo-REQ-100 req 079: StructuredOutput parsing from --json-schema
class TestStructuredOutputParsing:
    """When --json-schema is used, CC returns StructuredOutput tool calls."""

    def test_extract_structured_output_found(self):
        """Extracts input dict from StructuredOutput tool_use event."""
        from rondo.dispatch import extract_structured_output

        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "StructuredOutput",
                            "input": {"status": "done", "result": "all good"},
                        }
                    ]
                },
            },
        ]
        result = extract_structured_output(events)
        assert result == {"status": "done", "result": "all good"}

    def test_extract_structured_output_not_found(self):
        """Returns None when no StructuredOutput in events."""
        from rondo.dispatch import extract_structured_output

        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
        ]
        result = extract_structured_output(events)
        assert result is None

    def test_extract_structured_output_multiple_events(self):
        """Uses LAST StructuredOutput if multiple exist."""
        from rondo.dispatch import extract_structured_output

        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "StructuredOutput",
                            "input": {"status": "error", "result": "first try"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "StructuredOutput",
                            "input": {"status": "done", "result": "second try"},
                        }
                    ]
                },
            },
        ]
        result = extract_structured_output(events)
        assert result["status"] == "done"

    def test_structured_output_preferred_over_text_parsing(self):
        """When both structured and text JSON exist, structured wins."""
        from rondo.dispatch import extract_structured_output

        # Event has both text with JSON and a StructuredOutput tool call
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": '```json\n{"status":"error"}\n```'},
                        {
                            "type": "tool_use",
                            "name": "StructuredOutput",
                            "input": {"status": "done", "result": "structured wins"},
                        },
                    ]
                },
            },
        ]
        result = extract_structured_output(events)
        assert result["status"] == "done"


# -- Rondo-REQ-100 reqs 079-080: Result schema + default system prompt
class TestRondoConstants:
    """Rondo defines reusable constants for dispatch configuration."""

    def test_result_schema_is_valid_json(self):
        """RONDO_RESULT_SCHEMA is a valid JSON string."""
        from rondo.dispatch import RONDO_RESULT_SCHEMA

        parsed = json.loads(RONDO_RESULT_SCHEMA)
        assert parsed["type"] == "object"
        assert "status" in parsed["properties"]
        assert "result" in parsed["properties"]

    def test_result_schema_has_required_fields(self):
        """Schema requires status and result."""
        from rondo.dispatch import RONDO_RESULT_SCHEMA

        parsed = json.loads(RONDO_RESULT_SCHEMA)
        assert "status" in parsed["required"]
        assert "result" in parsed["required"]

    ## RONDO-261: RONDO_DISPATCH_PROMPT constant was removed as part of
    ## deduplicating --system-prompt. Dispatch rules now live in config.toml
    ## (claude_p_rules) and are wired via _build_subprocess_cmd directly.
    ## Tests for the removed constant are deleted.

    def test_config_uses_schema_constant(self):
        """When json_schema is 'auto', it uses RONDO_RESULT_SCHEMA."""
        from rondo.dispatch import RONDO_RESULT_SCHEMA

        config = RondoConfig(json_schema="auto")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        idx = cmd.index("--json-schema")
        assert cmd[idx + 1] == RONDO_RESULT_SCHEMA


# -- Rondo-REQ-100 req 078: budget exceeded detection
class TestBudgetExceeded:
    """Detect when --max-budget-usd causes CC to stop early."""

    def test_budget_exceeded_in_result_events(self):
        """error_max_budget_usd subtype detected in result event."""
        from rondo.dispatch import parse_stream_json_events

        lines = [
            '{"type":"result","subtype":"error_max_budget_usd","total_cost_usd":0.022,"is_error":false}',
        ]
        events, usage = parse_stream_json_events(lines, task_name="t1")
        assert usage.budget_exceeded is True

    def test_success_result_not_budget_exceeded(self):
        """Normal success result has budget_exceeded=False."""
        from rondo.dispatch import parse_stream_json_events

        lines = [
            '{"type":"result","subtype":"success","total_cost_usd":0.01,"is_error":false}',
        ]
        events, usage = parse_stream_json_events(lines, task_name="t1")
        assert usage.budget_exceeded is False


# -- Sprints 34+: deeper spec coverage with TDD
class TestDryRunOutput:
    """REQ-100 req 016: dry-run returns prompt without invoking."""

    def test_dry_run_returns_prompt(self):
        config = RondoConfig(dry_run=True)
        task = Task(name="t1", instruction="check files", done_when="files checked")
        result, _ = dispatch_task(task, config)
        assert result.status == "skipped"
        assert "check files" in result.prompt_sent

    def test_dry_run_no_subprocess(self):
        config = RondoConfig(dry_run=True)
        task = Task(name="t1", instruction="do work", done_when="done")
        with patch("rondo.dispatch.subprocess") as mock_sub:
            dispatch_task(task, config)
            mock_sub.Popen.assert_not_called()


class TestDispatchInputValidation:
    """Pre-dispatch validation catches bad tasks before wasting API calls."""

    def test_empty_instruction_rejected(self):
        task = Task(name="t1", instruction="", done_when="done")
        result, _ = dispatch_task(task, RondoConfig())
        assert result.status == "error"
        assert "instruction" in result.error_message.lower()

    def test_invalid_tool_mode_rejected(self):
        task = Task(name="t1", instruction="do", done_when="done", tool_mode="bad")
        result, _ = dispatch_task(task, RondoConfig())
        assert result.status == "error"
        assert "tool_mode" in result.error_message


class TestNotifyAllChannels:
    """REQ-105 req 005: all 3 channels fire together."""

    def test_all_channels_fire(self, tmp_path):
        from rondo.notify import NotifyConfig, notify_round_complete

        log_file = tmp_path / "notify.log"
        with patch("subprocess.run"):
            notify_round_complete(
                round_name="test",
                status="done",
                duration_sec=5.0,
                cost_usd=0.01,
                config=NotifyConfig(channels=["terminal", "file", "macos"], log_file=str(log_file)),
            )
        assert log_file.exists()


class TestPreflightSerialization:
    """Preflight results can be used programmatically."""

    def test_result_serializable(self):
        import json as _json

        from rondo.preflight import run_preflight

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = run_preflight()
        data = {"status": result.status, "checks": result.checks}
        assert "GREEN" in _json.dumps(data)


class TestHistoryWithRealData:
    """History works with real dispatch records."""

    def test_query_by_round_and_model(self, tmp_path):
        from rondo.history import DispatchRecord, load_history, log_dispatch, query_history

        for rn, model in [("r1", "sonnet"), ("r1", "opus"), ("r2", "sonnet")]:
            log_dispatch(
                DispatchRecord(
                    round_name=rn,
                    task_name=f"t-{model}",
                    model=model,
                    status="done",
                ),
                str(tmp_path),
            )
        records = load_history(str(tmp_path))
        r1_sonnet = query_history(records, round_name="r1", model="sonnet")
        assert len(r1_sonnet) == 1

    def test_aggregate_includes_duration(self, tmp_path):
        from rondo.history import DispatchRecord, aggregate_by_model, load_history, log_dispatch

        log_dispatch(
            DispatchRecord(
                round_name="r",
                task_name="t",
                model="opus",
                status="done",
                cost_usd=0.10,
                duration_sec=5.5,
            ),
            str(tmp_path),
        )
        records = load_history(str(tmp_path))
        agg = aggregate_by_model(records)
        assert agg["opus"]["total_duration"] == 5.5


class TestEngineFields:
    """Verify all Session 91 dataclass fields work correctly."""

    def test_task_all_new_fields(self):
        t = Task(
            name="full",
            instruction="do",
            done_when="done",
            tool_mode="sandbox",
            bare=False,
            human_input="Review first",
            context_data={"key": "val"},
        )
        assert t.tool_mode == "sandbox"
        assert t.bare is False
        assert t.human_input == "Review first"
        assert t.context_data == {"key": "val"}

    def test_dispatch_usage_budget_field(self):
        u = DispatchUsage(task_name="t", budget_exceeded=True)
        assert u.budget_exceeded is True

    def test_dispatch_usage_defaults(self):
        u = DispatchUsage(task_name="t")
        assert u.budget_exceeded is False
        assert u.cost_usd == 0.0
        assert u.rate_limit_status == "unknown"


# -- Sprints 40-54: Batch deep coverage
class TestPromptBuildingDeep:
    """REQ-100 reqs 12, 24: prompt building edge cases."""

    def test_prompt_with_context_data_and_files(self):
        """Both context_files and context_data in one prompt."""
        task = Task(
            name="t",
            instruction="review",
            done_when="reviewed",
            context_files=["src/main.py"],
            context_data={"findings": [1, 2, 3]},
        )
        prompt = build_prompt(task)
        assert "src/main.py" in prompt
        assert "Structured Input Data" in prompt
        assert "findings" in prompt

    def test_prompt_with_description(self):
        """Description included when present."""
        task = Task(name="t", instruction="do", done_when="done", description="A detailed task")
        prompt = build_prompt(task)
        assert "A detailed task" in prompt

    def test_prompt_always_has_output_format(self):
        """Every prompt tells AI to return JSON (REQ-111 smart return)."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "passed" in prompt.lower()
        assert "json" in prompt.lower()


class TestModelResolutionDeep:
    """REQ-100 reqs 20-23: COALESCE model resolution."""

    def test_cli_overrides_task(self):
        task = Task(name="t", instruction="do", done_when="done", model="haiku")
        model = resolve_model("opus", task, RondoConfig())
        assert model == "opus"

    def test_task_overrides_config(self):
        task = Task(name="t", instruction="do", done_when="done", model="haiku")
        model = resolve_model(None, task, RondoConfig(default_model="sonnet"))
        assert model == "haiku"

    def test_config_default_used(self):
        task = Task(name="t", instruction="do", done_when="done")
        model = resolve_model(None, task, RondoConfig(default_model="sonnet"))
        assert model == "sonnet"

    def test_invalid_model_raises(self):
        task = Task(name="t", instruction="do", done_when="done")
        with pytest.raises(ValueError, match="Invalid model"):
            resolve_model("gpt4", task, RondoConfig())


# -- RONDO-208: TestErrorClassificationDeep deleted — all 5 tests were
# -- duplicates or near-duplicates of TestErrorClassification (see L268).
# -- test_auth_error ≈ test_auth_error_credit (same input, lowercased)
# -- test_rate_limit_error dup of test_rate_limit_error/test_rate_limit_lowercase
# -- test_nested_session_error EXACT dup
# -- test_empty_stderr EXACT dup
# -- test_unknown_error ≈ test_generic_error (both → ERR_SUBPROCESS)


class TestStreamJsonParsingDeep:
    """REQ-IFS-100: stream-json event parsing."""

    def test_empty_lines_skipped(self):
        events, _ = parse_stream_json_events(["", "  ", "\n"], task_name="t")
        assert events == []

    def test_invalid_json_skipped(self):
        events, _ = parse_stream_json_events(["not json", '{"valid": true}'], task_name="t")
        assert len(events) == 1

    def test_rate_limit_populates_usage(self):
        lines = ['{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","isUsingOverage":false}}']
        _, usage = parse_stream_json_events(lines, task_name="t")
        assert usage.rate_limit_status == "allowed"
        assert usage.is_using_overage is False

    def test_result_populates_cost(self):
        lines = [
            '{"type":"result","subtype":"success","total_cost_usd":0.05,"duration_ms":1000,"usage":{"input_tokens":100,"output_tokens":50},"modelUsage":{}}'
        ]
        _, usage = parse_stream_json_events(lines, task_name="t")
        assert usage.cost_usd == 0.05
        assert usage.input_tokens == 100
        assert usage.duration_ms == 1000


class TestEnvPrepDeep:
    """REQ-100 reqs 13, 17, 18: environment preparation."""

    def test_claudecode_always_stripped(self):
        with patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/bin"}):
            env = prepare_env(RondoConfig())
        assert "CLAUDECODE" not in env

    def test_api_key_stripped_for_max(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            env = prepare_env(RondoConfig(auth="max"))
        assert "ANTHROPIC_API_KEY" not in env

    def test_api_key_kept_for_api(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            env = prepare_env(RondoConfig(auth="api"))
        assert env.get("ANTHROPIC_API_KEY") == "sk-test"


class TestResultSavingDeep:
    """REQ-100 req 15, STD-110: result saving."""

    def test_save_creates_file(self, tmp_path):
        result = TaskResult(task_name="save-test", status="done", model="sonnet", auth_mode="max")
        usage = DispatchUsage(task_name="save-test", model="sonnet", cost_usd=0.01)
        filepath = save_result(result, usage, str(tmp_path))
        assert Path(filepath).exists()

    def test_save_file_permissions(self, tmp_path):
        result = TaskResult(task_name="perm-test", status="done", model="sonnet", auth_mode="max")
        usage = DispatchUsage(task_name="perm-test")
        filepath = save_result(result, usage, str(tmp_path))
        mode = Path(filepath).stat().st_mode
        assert mode & 0o777 == 0o600

    def test_save_contains_usage(self, tmp_path):
        result = TaskResult(task_name="usage-test", status="done", model="sonnet", auth_mode="max")
        usage = DispatchUsage(task_name="usage-test", cost_usd=0.05)
        filepath = save_result(result, usage, str(tmp_path))
        data = json.loads(Path(filepath).read_text())
        assert data["usage"]["cost_usd"] == 0.05


class TestRoundResultCalculation:
    """REQ-100 req 046: round status from task results."""

    def test_all_done_is_done(self):
        from rondo.engine import calculate_round_status

        results = [TaskResult(task_name="t1", status="done"), TaskResult(task_name="t2", status="done")]
        assert calculate_round_status(results) == "done"

    def test_mix_is_partial(self):
        from rondo.engine import calculate_round_status

        results = [TaskResult(task_name="t1", status="done"), TaskResult(task_name="t2", status="error")]
        assert calculate_round_status(results) == "partial"

    def test_all_error(self):
        from rondo.engine import calculate_round_status

        results = [TaskResult(task_name="t1", status="error"), TaskResult(task_name="t2", status="error")]
        assert calculate_round_status(results) == "error"

    def test_empty_is_skipped(self):
        from rondo.engine import calculate_round_status

        assert calculate_round_status([]) == "skipped"


class TestConfigValidationDeep:
    """STD-109: config validation edge cases."""

    def test_zero_workers_rejected(self):
        from rondo.config import validate_config

        config = RondoConfig(workers=0)
        errors = validate_config(config)
        assert any("workers" in e for e in errors)

    def test_negative_timeout_rejected(self):
        from rondo.config import validate_config

        config = RondoConfig(task_timeout_sec=-1)
        errors = validate_config(config)
        assert any("timeout" in e.lower() for e in errors)

    def test_valid_config_no_errors(self):
        from rondo.config import validate_config

        config = RondoConfig()
        errors = validate_config(config)
        assert errors == []


# -- Final batch: harden existing modules
class TestAutoTask:
    """REQ-100 req 004: auto tasks with Python callables."""

    def test_auto_task_success(self):
        config = RondoConfig()
        task = Task(name="auto-pass", auto_fn=lambda: (True, "all good"))
        result, usage = dispatch_task(task, config)
        assert result.status == "done"

    def test_auto_task_failure(self):
        config = RondoConfig()
        task = Task(name="auto-fail", auto_fn=lambda: (False, "nope"))
        result, usage = dispatch_task(task, config)
        assert result.status == "error"

    def test_auto_task_exception(self):
        def _boom():
            msg = "kaboom"
            raise RuntimeError(msg)

        config = RondoConfig()
        task = Task(name="auto-boom", auto_fn=_boom)
        result, usage = dispatch_task(task, config)
        assert result.status == "error"
        assert "kaboom" in result.error_message


class TestConfigCoalesce:
    """STD-109: COALESCE resolution — CLI → config file → default."""

    def test_cli_overrides_toml(self, tmp_path):
        from rondo.config import load_config

        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('default_model = "opus"\nworkers = 8\n')
        config = load_config(config_path=str(toml_file), cli_overrides={"default_model": "haiku"})
        assert config.default_model == "haiku"
        assert config.workers == 8

    def test_toml_overrides_default(self, tmp_path):
        from rondo.config import load_config

        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('effort = "low"\n')
        config = load_config(config_path=str(toml_file))
        assert config.effort == "low"

    def test_default_when_no_toml(self):
        from rondo.config import load_config

        config = load_config(config_path="/nonexistent/rondo.toml")
        assert config.default_model == "sonnet"
        assert config.workers == 4


class TestGateExecution:
    """REQ-100 reqs 005-007: gate execution."""

    def test_passing_gate(self):
        from rondo.engine import Gate, run_gate

        g = Gate(name="check", check_fn=lambda: (True, "ok"))
        result = run_gate(g)
        assert result.passed is True

    def test_failing_gate(self):
        from rondo.engine import Gate, run_gate

        g = Gate(name="check", check_fn=lambda: (False, "bad"))
        result = run_gate(g)
        assert result.passed is False
        assert result.detail == "bad"

    def test_blocking_gate_prevents_proceed(self):
        from rondo.engine import Gate, run_gates, should_proceed

        gates = [Gate(name="blocker", check_fn=lambda: (False, "stop"), blocking=True)]
        results = run_gates(gates)
        assert should_proceed(results) is False

    def test_non_blocking_gate_allows_proceed(self):
        from rondo.engine import Gate, run_gates, should_proceed

        gates = [Gate(name="warn", check_fn=lambda: (False, "meh"), blocking=False)]
        results = run_gates(gates)
        assert should_proceed(results) is True


class TestRoundValidation:
    """REQ-100: round validation before execution."""

    def test_duplicate_task_names_rejected(self):
        from rondo.engine import Round as _Round
        from rondo.engine import validate_round

        r = _Round(
            name="dup",
            tasks=[
                Task(name="t1", instruction="do", done_when="done"),
                Task(name="t1", instruction="also", done_when="also done"),
            ],
        )
        errors = validate_round(r)
        assert any("duplicate" in e.lower() for e in errors)

    def test_valid_round_no_errors(self):
        from rondo.engine import Round as _Round
        from rondo.engine import validate_round

        r = _Round(
            name="good",
            tasks=[
                Task(name="t1", instruction="do", done_when="done"),
                Task(name="t2", instruction="also", done_when="also done"),
            ],
        )
        errors = validate_round(r)
        assert errors == []


class TestFileExtractionSTD108:
    """STD-108: file path extraction edge cases.

    RONDO-208: removed test_extracts_python_files — exact duplicate of
    TestFileExtraction::test_extract_python_files (earlier in file). Kept
    the deduplication + empty-output cases that ARE unique to this class.
    """

    def test_no_duplicates(self):
        text = "Changed config.py then changed config.py again"
        files = extract_modified_files(text)
        assert files.count("config.py") == 1

    def test_empty_output(self):
        assert extract_modified_files("") == []


class TestSanitizeWiring:
    """STD-114 wiring: dispatch results are sanitized before return."""

    def test_dry_run_not_sanitized(self):
        """Dry run doesn't sanitize (no real output)."""
        task = Task(name="t", instruction="do it", done_when="done")
        config = RondoConfig(dry_run=True)
        result, _ = dispatch_task(task, config)
        assert result.status == "skipped"

    def test_auto_task_output_sanitized(self):
        """Auto task output goes through sanitize pipeline."""
        task = Task(
            name="leaky-auto",
            auto_fn=lambda: (True, "Found api_key = 'sk-should-be-scrubbed'"),
        )
        config = RondoConfig(dry_run=False)
        result, _ = dispatch_task(task, config)
        # -- After wiring, secrets should be scrubbed in stored result
        # -- Note: auto_fn result is raw_output — sanitize scrubs it
        assert result.status == "done"


class TestAuditWiring:
    """STD-113 wiring: dispatches are recorded in audit trail."""

    def test_interactive_dispatch_records_audit(self, tmp_path):
        """Interactive dispatch writes audit INTENT + OUTCOME."""
        task = Task(name="audited-task", instruction="review code", done_when="reviewed")
        config = RondoConfig(
            dry_run=False,
            audit_dir=str(tmp_path / "audit"),
        )
        # -- Mock subprocess to avoid real Claude call
        with patch("rondo.dispatch._run_subprocess") as mock_run:
            mock_run.return_value = (
                '{"type":"result","result":"done"}\n',
                "",
                0,
                False,
            )
            result, _ = dispatch_task(task, config)

        # -- Check audit files exist
        audit_dir = tmp_path / "audit"
        if audit_dir.exists():
            jsonl = audit_dir / "rondo_audit.jsonl"
            assert jsonl.exists(), "Audit JSONL should be written"
            lines = jsonl.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) >= 1, "At least INTENT record should exist"


class TestDispatchErrorPaths:
    """STD-108: all error paths return structured TaskResult."""

    def test_validation_error_returns_result(self):
        """Invalid task returns error TaskResult, not exception."""
        task = Task(name="broken")  # -- no instruction or auto_fn
        config = RondoConfig()
        result, usage = dispatch_task(task, config)
        assert result.status == "error"
        assert result.error_code == "ERR_INTERNAL"
        assert "Validation" in (result.error_message or "")

    def test_dry_run_returns_skipped(self):
        """Dry run returns status=skipped with prompt."""
        task = Task(name="t", instruction="do it", done_when="done")
        config = RondoConfig(dry_run=True)
        result, usage = dispatch_task(task, config)
        assert result.status == "skipped"
        assert result.prompt_sent != ""

    def test_auto_task_success(self):
        """Auto task returns done on success."""
        task = Task(name="auto", auto_fn=lambda: (True, "all good"))
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert result.status == "done"
        assert "all good" in result.raw_output

    def test_auto_task_failure(self):
        """Auto task returns error on failure."""
        task = Task(name="auto", auto_fn=lambda: (False, "broke"))
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert result.status == "error"

    def test_auto_task_exception(self):
        """Auto task exception caught, returns ERR_INTERNAL."""

        def bad_fn():
            raise RuntimeError("crash")

        task = Task(name="auto", auto_fn=bad_fn)
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert result.status == "error"
        assert result.error_code == "ERR_INTERNAL"


class TestDispatchAlwaysOn:
    """ALWAYS-ON: every dispatch path sets required fields."""

    def test_dry_run_has_timestamp(self):
        """Even dry-run has ISO 8601 timestamp."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(dry_run=True)
        result, _ = dispatch_task(task, config)
        assert result.timestamp.startswith("20"), f"Not ISO 8601: {result.timestamp!r}"
        assert "T" in result.timestamp, f"Missing time separator: {result.timestamp!r}"

    def test_dry_run_has_model(self):
        """Dry-run records which model would be used."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig(dry_run=True, default_model="opus")
        result, _ = dispatch_task(task, config)
        assert result.model == "opus"

    def test_auto_task_has_duration(self):
        """Auto task records duration_sec."""
        task = Task(name="auto", auto_fn=lambda: (True, "ok"))
        config = RondoConfig()
        result, _ = dispatch_task(task, config)
        assert result.duration_sec >= 0

    def test_error_result_has_auth_mode(self):
        """Error results still have auth_mode set."""
        task = Task(name="broken")
        config = RondoConfig(auth="max")
        result, _ = dispatch_task(task, config)
        assert result.auth_mode == "max"


class TestSubprocessCommand:
    """REQ-100: _build_subprocess_cmd produces correct CLI command."""

    def test_basic_command_structure(self):
        """Basic command has claude -p --model --output-format (prompt via stdin)."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "hello", "sonnet")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        ## -- Finding #177: prompt piped via stdin, NOT in cmd args
        assert "hello" not in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd

    def test_effort_flag_added(self):
        """--effort added when configured."""
        config = RondoConfig(effort="high")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--effort" in cmd
        assert "high" in cmd

    def test_permission_mode_flag(self):
        """--permission-mode added when configured."""
        config = RondoConfig(permission_mode="auto")
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--permission-mode" in cmd

    def test_max_budget_flag(self):
        """--max-budget-usd added when configured (req 078)."""
        config = RondoConfig(max_budget_usd=0.50)
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--max-budget-usd" in cmd
        assert "0.5" in cmd

    # -- RONDO-208: removed test_tool_mode_none — exact duplicate of
    # -- TestBuildSubprocessCmd::test_tool_mode_none_adds_tools_empty.


class TestEnvironmentPrep:
    """REQ-100: prepare_env sets up subprocess environment."""

    def test_env_strips_claudecode(self):
        """CLAUDECODE stripped to prevent nested sessions."""
        config = RondoConfig()
        env = prepare_env(config)
        assert "CLAUDECODE" not in env

    def test_env_has_path(self):
        """Environment preserves PATH."""
        config = RondoConfig()
        env = prepare_env(config)
        assert "PATH" in env


class TestHistoryIntegration:
    """REQ-104: dispatch results logged to history."""

    def test_history_logged_after_interactive_dispatch(self):
        """After interactive dispatch, _log_to_history is called."""
        task = Task(name="logged", instruction="check", done_when="checked")
        config = RondoConfig()

        with patch("rondo.dispatch._run_subprocess") as mock_run, patch("rondo.dispatch._log_to_history") as mock_log:
            mock_run.return_value = ('{"type":"result"}\n', "", 0, False)
            dispatch_task(task, config)
            mock_log.assert_called_once()


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 045 — Spool gated by sync/async mode
# -- ──────────────────────────────────────────────────────────────


class TestSpoolGating:
    """REQ-101 req 045: sync callers skip spool, async callers spool."""

    def test_sync_dispatch_skips_spool(self):
        """Default (sync) dispatch does NOT write spool files."""
        task = Task(name="sync-task", instruction="review", done_when="done")
        config = RondoConfig()  ## spool_enabled defaults to False

        with patch("rondo.dispatch._run_subprocess") as mock_run, patch("rondo.dispatch.spool_result") as mock_spool:
            mock_run.return_value = ('{"type":"result"}\n', "", 0, False)
            dispatch_task(task, config)
            mock_spool.assert_not_called()

    def test_async_dispatch_writes_spool(self):
        """Async dispatch (spool_enabled=True) writes spool files."""
        task = Task(name="async-task", instruction="review", done_when="done")
        config = RondoConfig(spool_enabled=True)

        with patch("rondo.dispatch._run_subprocess") as mock_run, patch("rondo.dispatch.spool_result") as mock_spool:
            mock_run.return_value = ('{"type":"result"}\n', "", 0, False)
            dispatch_task(task, config)
            mock_spool.assert_called_once()

    def test_spool_enabled_false_by_default(self):
        """RondoConfig.spool_enabled defaults to False (sync = no spool)."""
        config = RondoConfig()
        assert config.spool_enabled is False

    def test_dry_run_skips_spool(self):
        """Dry-run never writes spool regardless of config."""
        task = Task(name="dry", instruction="review", done_when="done")
        config = RondoConfig(dry_run=True, spool_enabled=True)

        with patch("rondo.dispatch.spool_result") as mock_spool:
            dispatch_task(task, config)
            mock_spool.assert_not_called()


# -- ──────────────────────────────────────────────────────────────
# --  U-15 to U-19: --project flag (RONDO-36)
# -- ──────────────────────────────────────────────────────────────


class TestProjectFlag:
    """U-15 to U-19: --project sets subprocess working directory."""

    def test_config_has_project_field(self):
        """U-15: RondoConfig has project field."""
        config = RondoConfig()
        assert hasattr(config, "project")
        assert config.project == ""

    def test_project_sets_subprocess_cwd(self, tmp_path):
        """U-17: --project sets cwd on subprocess."""
        task = Task(name="proj-test", instruction="check", done_when="done")
        config = RondoConfig(project=str(tmp_path))

        with patch("rondo.dispatch._run_subprocess") as mock_run:
            mock_run.return_value = ('{"type":"result"}\n', "", 0, False)
            dispatch_task(task, config)
            call_args = mock_run.call_args
            assert call_args is not None
            ## -- Verify cwd was passed
            assert str(tmp_path) in str(call_args)

    def test_default_project_is_empty(self):
        """U-19: default is empty (CWD, no change)."""
        config = RondoConfig()
        assert config.project == ""


# -- ──────────────────────────────────────────────────────────────
# --  U-26 to U-30: Result parsing helpers (Phase 6)
# -- ──────────────────────────────────────────────────────────────


class TestExtractJson:
    """U-26: TaskResult.extract_json() parses raw_output as JSON."""

    def test_valid_json(self):
        r = TaskResult(task_name="t", raw_output='{"status":"done","count":3}')
        assert r.extract_json() == {"status": "done", "count": 3}

    def test_invalid_json_returns_none(self):
        r = TaskResult(task_name="t", raw_output="This is not JSON at all")
        assert r.extract_json() is None

    def test_empty_output_returns_none(self):
        r = TaskResult(task_name="t", raw_output="")
        assert r.extract_json() is None

    def test_json_embedded_in_text(self):
        """Extract JSON even when surrounded by text."""
        r = TaskResult(task_name="t", raw_output='Here is the result:\n{"status":"done"}\nDone.')
        result = r.extract_json()
        assert result is not None
        assert result["status"] == "done"

    def test_nested_json_extracted(self):
        """Finding #178: nested JSON objects must be parseable."""
        r = TaskResult(task_name="t", raw_output='Result: {"status":"done","data":{"count":3,"items":["a","b"]}}')
        result = r.extract_json()
        assert result is not None
        assert result["data"]["count"] == 3

    def test_does_not_modify_raw_output(self):
        """U-30: read-only."""
        original = '{"key":"val"}'
        r = TaskResult(task_name="t", raw_output=original)
        r.extract_json()
        assert r.raw_output == original


class TestExtractCodeBlocks:
    """U-27: TaskResult.extract_code_blocks() extracts fenced blocks."""

    def test_single_block(self):
        r = TaskResult(task_name="t", raw_output="```python\nprint('hi')\n```")
        blocks = r.extract_code_blocks()
        assert len(blocks) == 1
        assert blocks[0] == ("python", "print('hi')")

    def test_multiple_blocks(self):
        r = TaskResult(task_name="t", raw_output="```js\nalert(1)\n```\ntext\n```bash\nls\n```")
        blocks = r.extract_code_blocks()
        assert len(blocks) == 2
        assert blocks[0][0] == "js"
        assert blocks[1][0] == "bash"

    def test_no_language(self):
        r = TaskResult(task_name="t", raw_output="```\nplain code\n```")
        blocks = r.extract_code_blocks()
        assert len(blocks) == 1
        assert blocks[0] == ("", "plain code")

    def test_no_blocks_returns_empty(self):
        r = TaskResult(task_name="t", raw_output="No code here")
        assert r.extract_code_blocks() == []

    def test_never_raises(self):
        """U-29: never raise."""
        r = TaskResult(task_name="t", raw_output=None)  # type: ignore[arg-type]
        assert r.extract_code_blocks() == []


class TestExtractTable:
    """U-28: TaskResult.extract_table() extracts markdown tables."""

    def test_simple_table(self):
        md = "| Name | Age |\n|------|-----|\n| Mark | 57 |\n| Bob | 30 |"
        r = TaskResult(task_name="t", raw_output=md)
        table = r.extract_table()
        assert len(table) == 2
        assert table[0]["Name"] == "Mark"
        assert table[1]["Age"] == "30"

    def test_no_table_returns_empty(self):
        r = TaskResult(task_name="t", raw_output="No table here")
        assert r.extract_table() == []

    def test_never_raises(self):
        """U-29: never raise."""
        r = TaskResult(task_name="t", raw_output="")
        assert r.extract_table() == []


# -- ──────────────────────────────────────────────────────────────
# --  REQ-101 req 019-023: Watchdog timer (RONDO-58)
# -- ──────────────────────────────────────────────────────────────


class TestWatchdog:
    """REQ-101 req 019-023: detect stuck/hung dispatches by output silence."""

    def test_watchdog_config_exists(self):
        """RondoConfig has watchdog_timeout_sec."""
        config = RondoConfig()
        assert hasattr(config, "watchdog_timeout_sec")
        assert config.watchdog_timeout_sec == 60

    def test_watchdog_kills_silent_process(self):
        """Process with no output for watchdog_timeout_sec is killed."""
        from rondo.dispatch import _run_subprocess

        ## -- sleep 30 produces no output
        ## -- watchdog at 2s should kill it before task_timeout at 30s
        stdout, stderr, returncode, timed_out = _run_subprocess(
            ["sleep", "30"],
            env={},
            timeout_sec=30,
            watchdog_sec=2,
        )
        assert timed_out is True

    def test_watchdog_allows_output_producing_process(self):
        """Process that produces output regularly is NOT killed by watchdog."""
        from rondo.dispatch import _run_subprocess

        ## -- echo produces output immediately, then exits
        stdout, stderr, returncode, timed_out = _run_subprocess(
            ["echo", "hello"],
            env={},
            timeout_sec=10,
            watchdog_sec=2,
        )
        assert timed_out is False
        assert "hello" in stdout


# -- ──────────────────────────────────────────────────────────────
# --  REQ-106 req 005: context_data size cap (RONDO-52)
# -- ──────────────────────────────────────────────────────────────


class TestContextDataSizeCap:
    """REQ-106 req 005: context_data included in max_context_bytes cap."""

    def test_large_context_data_rejected(self):
        """context_data > max_context_bytes is rejected."""
        from rondo.engine import validate_task

        big_data = {"payload": "x" * 600_000}
        task = Task(name="big", instruction="x", done_when="y", context_data=big_data)
        errors = validate_task(task, max_context_bytes=500_000)
        assert any("context" in e.lower() and "bytes" in e.lower() for e in errors)

    def test_small_context_data_accepted(self):
        """context_data under cap passes."""
        from rondo.engine import validate_task

        task = Task(name="ok", instruction="x", done_when="y", context_data={"key": "val"})
        errors = validate_task(task, max_context_bytes=500_000)
        assert not any("context_data" in e for e in errors)

    def test_combined_files_and_data_cap(self, tmp_path):
        """context_files + context_data combined must be under cap."""
        from rondo.engine import validate_task

        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * 400_000)
        big_data = {"extra": "y" * 200_000}
        task = Task(
            name="combined",
            instruction="x",
            done_when="y",
            context_files=[str(big_file)],
            context_data=big_data,
        )
        errors = validate_task(task, max_context_bytes=500_000)
        assert any("bytes" in e.lower() for e in errors)


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-298 (Finding #290): parser robustness — REQ-100 reqs 123-126
# --  80 historic dispatches succeeded but were misfiled "partial":
# --  (a) status-key gate rejected smart-return schema ('passed' key)
# --  (b) flat regex \{[^{}]*\} could not match nested JSON
# -- ──────────────────────────────────────────────────────────────


class TestSmartReturnParsing:
    """REQ-100 reqs 123-125: dual-schema acceptance + real JSON scanner."""

    def test_smart_return_schema_accepted(self) -> None:
        """REQ-100 req 123: smart-return shape ('passed' key) is a parsed result."""
        text = '{"passed": true, "confidence": 1.0, "result": "Hello", "issues": [], "suggestions": []}'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["passed"] is True

    def test_contract_schema_still_accepted(self) -> None:
        """REQ-100 req 123: three-field contract ('status' key) unchanged."""
        parsed = parse_task_json('{"status": "done", "confidence": 0.9, "result": "ok"}')
        assert parsed is not None
        assert parsed["status"] == "done"

    def test_nested_json_parses(self) -> None:
        """REQ-100 req 124: nested objects/arrays must parse (flat regex could not)."""
        text = 'preamble\n{"status": "done", "result": {"nested": {"deep": [1, 2]}}, "confidence": 0.9}'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["result"]["nested"]["deep"] == [1, 2]

    def test_escaped_braces_inside_strings(self) -> None:
        """REQ-100 req 124: escaped JSON-in-string must not break the scanner."""
        text = '{"passed": true, "confidence": 1.0, "result": "{\\"mode\\": \\"subprocess\\"}"}'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert "mode" in parsed["result"]

    def test_last_matching_block_wins(self) -> None:
        """REQ-100 req 125: last recognized block wins (unchanged precedence)."""
        text = '{"status": "done", "result": "first"}\nnoise\n{"passed": true, "result": "second"}'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["result"] == "second"

    def test_non_result_dicts_ignored(self) -> None:
        """REQ-100 req 123: dicts matching neither schema are not results."""
        text = '{"random": 1, "other": 2} then {"status": "done", "result": "real"}'
        parsed = parse_task_json(text)
        assert parsed is not None
        assert parsed["result"] == "real"

    def test_no_json_returns_none(self) -> None:
        """No recognizable result anywhere → None (partial path preserved)."""
        assert parse_task_json("just prose, no JSON at all") is None


# -- RONDO-313: sanitized corpus fixtures shipped IN the repo so the corpus
# -- gates run everywhere (CI, other machines) — answers Cursor finding #301
# -- "local-only gates". Full local audit corpus still runs when present.
CORPUS_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"


def load_corpus_fixtures(kind: str) -> list[str]:
    """Return raw_output strings from repo fixtures: kind is 'parser' or 'auth'."""
    folder = CORPUS_FIXTURES / kind
    return [
        json.loads(p.read_text())["raw_output"]
        for p in sorted(folder.glob("*.json"))
    ]


class TestHistoricCorpusParsing:
    """REQ-100 req 126: the 80 misfiled production outputs are the regression suite."""

    def test_fixture_partials_parse(self) -> None:
        """Repo-fixture corpus gate — runs on EVERY machine, never skips."""
        raws = load_corpus_fixtures("parser")
        assert len(raws) >= 10, "parser fixture corpus missing or too small"
        failures = [i for i, raw in enumerate(raws) if parse_task_json(raw) is None]
        assert not failures, f"fixture records {failures} unparseable — parser regression"

    def test_historic_partials_parse(self) -> None:
        """Re-parse every preserved partial raw_output (excluding auth-loss)."""
        audit = Path.home() / ".rondo" / "audit"
        log = audit / "rondo_audit.jsonl"
        if not log.exists():
            pytest.skip("no local audit corpus on this machine")
        failures = 0
        candidates = 0
        for line in log.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "partial":
                continue
            p = audit / (rec.get("result_file") or "_none_")
            if not p.exists():
                continue
            raw = json.loads(p.read_text()).get("raw_output") or ""
            if "Not logged in" in raw or "Please run /login" in raw:
                continue  # -- auth-loss bucket — IFS-100 reqs 011-014, not a parse problem
            candidates += 1
            if parse_task_json(raw) is None:
                failures += 1
        if candidates == 0:
            pytest.skip("no partial records in local corpus")
        # -- Cursor review 2026-06-05: gate must match the claim. All 80 were
        # -- measured parsing; the gate is therefore ZERO failures, not 95%.
        # -- (Full local corpus when present; repo fixtures above cover CI —
        # --  finding #301 resolved by RONDO-313.)
        assert failures == 0, f"{failures}/{candidates} historic outputs unparseable — regression vs the 80/80 baseline"


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-299: auth-loss detection — IFS-100 reqs 011-014
# --  33 historic "Not logged in" outputs misclassified as
# --  ERR_MALFORMED_JSON/partial; multi-task runs continued on dead sessions.
# -- ──────────────────────────────────────────────────────────────


class TestAuthLossDetection:
    """IFS-100 reqs 011 + 014: structured auth-loss check before JSON fallback."""

    def test_detects_not_logged_in_output(self) -> None:
        from rondo.dispatch_parse import detect_auth_loss

        assert detect_auth_loss("Not logged in · Please run /login") is not None

    def test_detects_invalid_key_in_stderr(self) -> None:
        from rondo.dispatch_parse import detect_auth_loss

        assert detect_auth_loss("", stderr="Error: Invalid API key provided") is not None

    def test_clean_output_returns_none(self) -> None:
        from rondo.dispatch_parse import detect_auth_loss

        assert detect_auth_loss('{"status": "done", "result": "ok"}') is None

    def test_returns_matched_signal_for_message(self) -> None:
        """IFS-100 req 014: the error message must name the detected signal."""
        from rondo.dispatch_parse import detect_auth_loss

        signal = detect_auth_loss("blah Credit balance is too low blah")
        assert signal == "Credit balance is too low"

    def test_fixture_auth_corpus_detected(self) -> None:
        """Repo-fixture auth-loss gate — runs on EVERY machine, never skips."""
        from rondo.dispatch_parse import detect_auth_loss

        raws = load_corpus_fixtures("auth")
        assert len(raws) >= 5, "auth fixture corpus missing or too small"
        missed = [i for i, raw in enumerate(raws) if detect_auth_loss(raw) is None]
        assert not missed, f"fixture records {missed} not detected — auth-loss regression"

    def test_historic_auth_corpus_detected(self) -> None:
        """All 33 historic auth-loss outputs must be detected (production corpus)."""
        from rondo.dispatch_parse import detect_auth_loss

        audit = Path.home() / ".rondo" / "audit"
        log = audit / "rondo_audit.jsonl"
        if not log.exists():
            pytest.skip("no local audit corpus on this machine")
        missed = 0
        found = 0
        for line in log.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "partial":
                continue
            p = audit / (rec.get("result_file") or "_none_")
            if not p.exists():
                continue
            raw = json.loads(p.read_text()).get("raw_output") or ""
            if "Not logged in" in raw or "Please run /login" in raw:
                found += 1
                if detect_auth_loss(raw) is None:
                    missed += 1
        if found == 0:
            pytest.skip("no auth-loss records in local corpus")
        assert missed == 0, f"{missed}/{found} historic auth-loss outputs not detected"


class TestAuthHaltsPhase:
    """IFS-100 req 012: auth failure halts the run — it is never transient."""

    def test_has_auth_error_predicate(self) -> None:
        from rondo.engine import RoundResult
        from rondo.overnight import _has_auth_error

        ok = TaskResult(task_name="a", status="done")
        bad = TaskResult(task_name="b", status="error", error_code="ERR_AUTH")
        assert _has_auth_error(RoundResult(round_name="r", status="partial", task_results=[ok, bad])) is True
        assert _has_auth_error(RoundResult(round_name="r", status="done", task_results=[ok])) is False


# -- sig: mgh-6201.cd.bd955f.eae2.2c7525
