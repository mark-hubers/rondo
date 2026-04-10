# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.hooks — dispatch hook execution pipeline.

REQ-100-addendum-dispatch-hooks reqs 100-114.
VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import pytest

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Task, TaskResult
from rondo.hooks import HookError, run_post_dispatch_hooks, run_pre_dispatch_hooks


class TestPreDispatchHooks:
    """REQ-100-addendum reqs 100-105: pre-dispatch hook execution."""

    def test_no_hooks_returns_prompt_unchanged(self) -> None:
        """No hooks → prompt passes through unmodified."""
        task = Task(name="t1", instruction="hello")
        prompt, trace = run_pre_dispatch_hooks("hello world", task, RondoConfig())
        assert prompt == "hello world"
        assert trace == []

    def test_single_hook_transforms_prompt(self) -> None:
        """Single callable hook modifies the prompt."""
        def upper_hook(prompt, _task, _config):
            return prompt.upper()

        task = Task(name="t1", instruction="hi", pre_dispatch=[upper_hook])
        prompt, trace = run_pre_dispatch_hooks("hello", task, RondoConfig())
        assert prompt == "HELLO"
        assert len(trace) == 1
        assert trace[0]["status"] == "ok"
        assert trace[0]["hook"] == "upper_hook"

    def test_hooks_chain_in_order(self) -> None:
        """Req 101: hooks chain — output of N is input to N+1."""
        def add_prefix(prompt, _task, _config):
            return f"PREFIX:{prompt}"

        def add_suffix(prompt, _task, _config):
            return f"{prompt}:SUFFIX"

        task = Task(name="t1", instruction="hi", pre_dispatch=[add_prefix, add_suffix])
        prompt, trace = run_pre_dispatch_hooks("data", task, RondoConfig())
        assert prompt == "PREFIX:data:SUFFIX"
        assert len(trace) == 2

    def test_hook_error_raises_hook_error(self) -> None:
        """Req 102: hook exception → HookError with hook name."""
        def bad_hook(_prompt, _task, _config):
            raise ValueError("intentional failure")

        task = Task(name="t1", instruction="hi", pre_dispatch=[bad_hook])
        with pytest.raises(HookError, match="bad_hook"):
            run_pre_dispatch_hooks("hello", task, RondoConfig())

    def test_hook_error_includes_trace(self) -> None:
        """Req 103: even on error, trace includes the failed hook."""
        def ok_hook(prompt, _task, _config):
            return prompt

        def bad_hook(_prompt, _task, _config):
            raise TypeError("boom")

        task = Task(name="t1", instruction="hi", pre_dispatch=[ok_hook, bad_hook])
        with pytest.raises(HookError):
            run_pre_dispatch_hooks("hello", task, RondoConfig())

    def test_hook_must_return_string(self) -> None:
        """Req 100: hook returning non-str raises TypeError."""
        def bad_return(_prompt, _task, _config):
            return 42

        task = Task(name="t1", instruction="hi", pre_dispatch=[bad_return])
        with pytest.raises(HookError, match="must return str"):
            run_pre_dispatch_hooks("hello", task, RondoConfig())

    def test_shell_hook_transforms_prompt(self) -> None:
        """Req 104: shell hook (string starting with '!') runs command."""
        task = Task(name="t1", instruction="hi", pre_dispatch=["!tr a-z A-Z"])
        prompt, trace = run_pre_dispatch_hooks("hello", task, RondoConfig())
        assert prompt.strip() == "HELLO"
        assert trace[0]["status"] == "ok"

    def test_shell_hook_error_raises(self) -> None:
        """Req 104: shell hook with non-zero exit → error."""
        task = Task(name="t1", instruction="hi", pre_dispatch=["!exit 1"])
        with pytest.raises(HookError, match="Shell hook exited"):
            run_pre_dispatch_hooks("hello", task, RondoConfig())

    def test_invalid_hook_type_raises(self) -> None:
        """Hook that is neither callable nor string raises TypeError."""
        task = Task(name="t1", instruction="hi", pre_dispatch=[42])
        with pytest.raises(HookError, match="must be callable"):
            run_pre_dispatch_hooks("hello", task, RondoConfig())


class TestPostDispatchHooks:
    """REQ-100-addendum reqs 110-114: post-dispatch hook execution."""

    def test_no_hooks_returns_result_unchanged(self) -> None:
        """No hooks → result passes through unmodified."""
        result = TaskResult(task_name="t1", status="done", raw_output="output")
        usage = DispatchUsage(task_name="t1")
        task = Task(name="t1", instruction="hi")
        final, trace = run_post_dispatch_hooks(result, usage, task)
        assert final is result
        assert trace == []

    def test_single_hook_transforms_result(self) -> None:
        """Single callable hook modifies the result."""
        def tag_hook(result, _usage):
            result.raw_output = f"[TAGGED] {result.raw_output}"
            return result

        result = TaskResult(task_name="t1", status="done", raw_output="output")
        usage = DispatchUsage(task_name="t1")
        task = Task(name="t1", instruction="hi", post_dispatch=[tag_hook])
        final, trace = run_post_dispatch_hooks(result, usage, task)
        assert "[TAGGED]" in final.raw_output
        assert trace[0]["status"] == "ok"

    def test_hook_failure_preserves_original(self) -> None:
        """Req 112: if hook raises, ORIGINAL result is preserved."""
        def bad_hook(_result, _usage):
            raise ValueError("boom")

        original = TaskResult(task_name="t1", status="done", raw_output="original")
        usage = DispatchUsage(task_name="t1")
        task = Task(name="t1", instruction="hi", post_dispatch=[bad_hook])
        final, trace = run_post_dispatch_hooks(original, usage, task)
        assert final.raw_output == "original"
        assert trace[0]["status"] == "error"

    def test_hook_must_return_task_result(self) -> None:
        """Req 110: hook returning non-TaskResult → error, original preserved."""
        def bad_return(_result, _usage):
            return "not a TaskResult"

        original = TaskResult(task_name="t1", status="done", raw_output="original")
        usage = DispatchUsage(task_name="t1")
        task = Task(name="t1", instruction="hi", post_dispatch=[bad_return])
        final, trace = run_post_dispatch_hooks(original, usage, task)
        assert final.raw_output == "original"
        assert trace[0]["status"] == "error"

    def test_hooks_chain_in_order(self) -> None:
        """Post-hooks chain: output of hook N is input to hook N+1."""
        def hook_a(result, _usage):
            result.raw_output += ":A"
            return result

        def hook_b(result, _usage):
            result.raw_output += ":B"
            return result

        result = TaskResult(task_name="t1", status="done", raw_output="base")
        usage = DispatchUsage(task_name="t1")
        task = Task(name="t1", instruction="hi", post_dispatch=[hook_a, hook_b])
        final, trace = run_post_dispatch_hooks(result, usage, task)
        assert final.raw_output == "base:A:B"
        assert len(trace) == 2


class TestHookTraceFormat:
    """Verify trace output format for audit trail integration."""

    def test_trace_has_required_fields(self) -> None:
        """Trace entries must have hook, duration_ms, status."""
        def noop(prompt, _task, _config):
            return prompt

        task = Task(name="t1", instruction="hi", pre_dispatch=[noop])
        _, trace = run_pre_dispatch_hooks("hello", task, RondoConfig())
        entry = trace[0]
        assert "hook" in entry
        assert "duration_ms" in entry
        assert "status" in entry
        assert isinstance(entry["duration_ms"], float)


# -- sig: mgh-6201.cd.bd955f.h00k.t35t50
