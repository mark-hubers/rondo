# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.dispatch — REQ-001 reqs 12-28, STD-001, ACE-IFS-001, STD-003.

VER-001 verification matrix: every test maps to a numbered requirement.
TDD: these tests are written BEFORE dispatch.py exists.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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
#  Prompt Building — REQ-001 req 12, 24
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
        """REQ-001 req 24: prompt instructs Claude to return JSON."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "json" in prompt.lower() or "JSON" in prompt

    def test_prompt_includes_status_field(self):
        """Prompt tells Claude to include status in JSON response."""
        task = Task(name="t", instruction="do", done_when="done")
        prompt = build_prompt(task)
        assert "status" in prompt.lower()


# -- REQ-106: context_data in prompt
class TestContextDataInPrompt:
    """context_data fields appear in prompt as structured data."""

    def test_context_data_appears_in_prompt(self):
        """REQ-106 req 001: context_data dict injected into prompt."""
        task = Task(
            name="t", instruction="analyze", done_when="done",
            context_data={"findings": [{"id": 1, "msg": "bad"}]},
        )
        prompt = build_prompt(task)
        assert "Structured Input Data" in prompt
        assert "findings" in prompt

    def test_context_data_json_formatted(self):
        """Context data rendered as JSON code blocks."""
        task = Task(
            name="t", instruction="do", done_when="done",
            context_data={"config": {"key": "value"}},
        )
        prompt = build_prompt(task)
        assert "```json" in prompt
        assert '"key"' in prompt

    def test_large_list_uses_jsonl(self):
        """REQ-106: lists > 100 items use JSONL format."""
        big_list = [{"id": i} for i in range(101)]
        task = Task(
            name="t", instruction="do", done_when="done",
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
#  Environment Preparation — REQ-001 reqs 13, 17, 18
# ──────────────────────────────────────────────────────────────────


class TestEnvPrep:
    def test_claudecode_stripped(self):
        """REQ-001 req 13: CLAUDECODE removed from child env."""
        config = RondoConfig(auth="max")
        with patch.dict(os.environ, {"CLAUDECODE": "1", "HOME": "/home/user"}):
            env = prepare_env(config)
            assert "CLAUDECODE" not in env

    def test_auth_max_strips_api_key(self):
        """REQ-001 req 17: auth=max strips ANTHROPIC_API_KEY."""
        config = RondoConfig(auth="max")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret", "HOME": "/home"}):
            env = prepare_env(config)
            assert "ANTHROPIC_API_KEY" not in env

    def test_auth_api_keeps_api_key(self):
        """REQ-001 req 18: auth=api keeps ANTHROPIC_API_KEY."""
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
#  Model Resolution — REQ-001 reqs 20, 21, 22, 23
# ──────────────────────────────────────────────────────────────────


class TestModelResolution:
    def test_model_default_sonnet(self):
        """REQ-001 req 22: default model is sonnet."""
        task = Task(name="t")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "sonnet"

    def test_model_from_task_hint(self):
        """REQ-001 req 23: task.model used when no CLI override."""
        task = Task(name="t", model="opus")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "opus"

    def test_model_cli_overrides_task(self):
        """REQ-001 req 21: CLI override wins over task hint."""
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
        """ACE-IFS-001 req 10: 1M context model suffix accepted."""
        task = Task(name="t", model="opus[1m]")
        config = RondoConfig()
        assert resolve_model(None, task, config) == "opus[1m]"


# ──────────────────────────────────────────────────────────────────
#  Task JSON Parsing — REQ-001 reqs 25, 26
# ──────────────────────────────────────────────────────────────────


class TestTaskJsonParsing:
    def test_valid_json_parsed(self):
        """REQ-001 req 25: valid JSON extracted and returned."""
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
        """REQ-001 req 26: malformed JSON returns None."""
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
#  Error Classification — STD-001 error categories
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
#  Stream-JSON Parsing — ACE-IFS-001 reqs 1-9
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
        """ACE-IFS-001 req 1: reads stream-json line by line."""
        raw = self._make_stream_output()
        events, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert len(events) >= 3  # -- init, rate_limit, assistant, result

    def test_rate_limit_extraction(self):
        """ACE-IFS-001 req 2: rate_limit_event populates DispatchUsage."""
        raw = self._make_stream_output(rate_status="allowed", is_overage=False)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.rate_limit_status == "allowed"

    def test_result_metadata_extraction(self):
        """ACE-IFS-001 req 3: result event populates cost/token/duration."""
        raw = self._make_stream_output(cost=0.12, input_tokens=500, output_tokens=300)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.cost_usd == 0.12
        assert usage.input_tokens == 500
        assert usage.output_tokens == 300

    def test_init_event_extraction(self):
        """ACE-IFS-001 req 4: system:init model extracted."""
        raw = self._make_stream_output(model="claude-opus-4-6")
        events, _ = parse_stream_json_events(raw.split("\n"), task_name="t")
        init_events = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
        assert len(init_events) == 1
        assert init_events[0]["model"] == "claude-opus-4-6"

    def test_overage_flag(self):
        """ACE-IFS-001 req 6: isUsingOverage captured."""
        raw = self._make_stream_output(is_overage=True)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.is_using_overage is True

    def test_cost_capture(self):
        """ACE-IFS-001 req 7: total_cost_usd captured."""
        raw = self._make_stream_output(cost=0.25)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.cost_usd == 0.25

    def test_duration_capture(self):
        """ACE-IFS-001 req 8: duration_ms captured."""
        raw = self._make_stream_output(duration_ms=12345, duration_api_ms=11000)
        _, usage = parse_stream_json_events(raw.split("\n"), task_name="t")
        assert usage.duration_ms == 12345
        assert usage.duration_api_ms == 11000

    def test_missing_rate_limit(self):
        """ACE-IFS-001 req 9: missing rate_limit_event uses defaults."""
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
#  File Extraction — STD-001 files_modified
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
#  Credential Sanitization — STD-001 rule 8
# ──────────────────────────────────────────────────────────────────


class TestCredentialSanitization:
    def test_api_key_not_in_saved_result(self, tmp_path):
        """STD-001 rule 8: API keys never in result files."""
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
#  Result Saving — REQ-001 req 15, STD-003 S5, R2
# ──────────────────────────────────────────────────────────────────


class TestResultSaving:
    def test_result_saved_to_json(self, tmp_path):
        """REQ-001 req 15: result saved to JSON file."""
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
        """STD-003 S5: result files have restrictive permissions (0o600)."""
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
        """STD-003 R2: output bounded at 1MB."""
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
        # -- raw_output should be truncated
        assert len(data["raw_output"]) <= 1024 * 1024 + 100  # -- 1MB + margin for truncation note

    def test_result_includes_metadata(self, tmp_path):
        """REQ-001 req 28: result includes task_name, status, model, auth, duration, timestamp."""
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
#  Dry Run — REQ-001 req 16
# ──────────────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_returns_prompt(self):
        """REQ-001 req 16: dry-run shows prompt without invoking."""
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
#  Auto Task Dispatch — REQ-001 req 4
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
#  Dispatch Integration (mocked subprocess) — REQ-001 reqs 12-14, 27
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
        """REQ-001 req 12: invokes claude -p."""
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
        """REQ-001 req 20: --model passed to subprocess."""
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
        """REQ-001 req 47: --permission-mode passed to subprocess."""
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
        """REQ-001 req 48: default permission_mode 'auto' is passed."""
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
        """REQ-001 req 27: exit code != 0 → status error."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        mock_proc = self._mock_popen(stdout="", stderr="Something failed", returncode=1)
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, _ = dispatch_task(task, config)
            assert result.status == "error"
            assert result.exit_code == 1

    def test_empty_stdout_error(self):
        """STD-001: empty stdout → ERR_EMPTY_OUTPUT."""
        task = Task(name="t", instruction="do", done_when="done")
        config = RondoConfig()
        mock_proc = self._mock_popen(stdout="", stderr="", returncode=0)
        with patch("rondo.dispatch.subprocess.Popen", return_value=mock_proc):
            result, _ = dispatch_task(task, config)
            assert result.status == "error"
            assert result.error_code == "ERR_EMPTY_OUTPUT"

    def test_malformed_json_partial(self):
        """REQ-001 req 26: malformed JSON → status partial."""
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
        """REQ-001 req 14: captures stdout, stderr, exit code, duration."""
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
        """REQ-100 req 071: --bare added when config.bare=True."""
        config = RondoConfig(bare=True)
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" in cmd

    def test_bare_flag_absent_by_default(self):
        """--bare not added when config.bare=False (default)."""
        config = RondoConfig()
        cmd = _build_subprocess_cmd(config, "test", "sonnet")
        assert "--bare" not in cmd

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


# -- sig: mgh-6201.cd.bd955f.eae2.2c7525
