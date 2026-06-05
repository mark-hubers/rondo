# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch parsing — JSON extraction + error classification.

Rondo-REQ-100 reqs 25-27, Rondo-IFS-100, Rondo-STD-108.
Extracted from dispatch.py (Session 91 Sprint 19 — Cursor review Finding #144).

Import direction:
    dispatch_parse.py → imports engine (for DispatchUsage type)
"""

from __future__ import annotations

import json
import re
from typing import Any

from rondo.engine import DispatchUsage


def _is_result_dict(parsed: Any) -> bool:
    """A dict matching either recognized result schema — REQ-100 req 123.

    `status` = three-field contract (req 079 shape).
    `passed` = smart-return schema (REQ-111 shape).
    RONDO-298 (Finding #290): the old status-only gate rejected Rondo's OWN
    smart-return outputs — 80 successful dispatches were misfiled "partial".
    """
    return isinstance(parsed, dict) and ("status" in parsed or "passed" in parsed)


def parse_task_json(text: str) -> dict[str, Any] | None:
    r"""Extract the last recognized result-JSON block from Claude's text output.

    Looks for JSON blocks in code fences first, then bare JSON objects.
    Accepts both result schemas (REQ-100 req 123). Bare extraction uses
    json.JSONDecoder.raw_decode — a real scanner that handles nested
    objects, arrays, and escaped braces (req 124; the old flat regex
    `\\{[^{}]*\\}` could not). Last matching block wins (req 125).
    Returns None if no recognized result found (REQ-100 req 26 → "partial").
    """
    # -- Try code-fenced JSON blocks first (last one wins)
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    for block in reversed(fenced):
        try:
            parsed = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if _is_result_dict(parsed):
            return parsed

    # -- Bare JSON objects: scan every '{' with raw_decode (req 124)
    decoder = json.JSONDecoder()
    last_match: dict[str, Any] | None = None
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            parsed, end = decoder.raw_decode(text, start)
        except ValueError:
            idx = start + 1
            continue
        if _is_result_dict(parsed):
            last_match = parsed
        # -- skip past the decoded object so nested '{' aren't re-scanned
        idx = max(end, start + 1)

    return last_match


def parse_stream_json_events(
    lines: list[str],
    task_name: str = "",
) -> tuple[list[dict[str, Any]], DispatchUsage]:
    """Parse stream-json output line by line (Rondo-IFS-100 req 1).

    Returns:
        Tuple of (all_events, dispatch_usage).
        DispatchUsage has defaults for missing fields (Rondo-IFS-100 req 9).
    """
    events: list[dict[str, Any]] = []
    usage = DispatchUsage(task_name=task_name)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        events.append(event)
        event_type = event.get("type", "")

        # -- rate_limit_event → DispatchUsage rate limit fields (Rondo-IFS-100 req 2)
        if event_type == "rate_limit_event":
            info = event.get("rate_limit_info", {})
            usage = DispatchUsage(
                task_name=usage.task_name,
                model=usage.model,
                cost_usd=usage.cost_usd,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_create_tokens=usage.cache_create_tokens,
                duration_ms=usage.duration_ms,
                duration_api_ms=usage.duration_api_ms,
                num_turns=usage.num_turns,
                context_window=usage.context_window,
                rate_limit_status=info.get("status", "unknown"),
                is_using_overage=info.get("isUsingOverage", False),
                rate_limit_resets_at=info.get("resetsAt", 0),
            )

        # -- result event → DispatchUsage cost/token/duration (Rondo-IFS-100 req 3)
        elif event_type == "result":
            u = event.get("usage", {})
            model_usage = event.get("modelUsage", {})
            ctx_window = 0
            for model_info in model_usage.values():
                ctx_window = model_info.get("contextWindow", 0)
                break

            usage = DispatchUsage(
                task_name=usage.task_name,
                model=usage.model,
                cost_usd=event.get("total_cost_usd", 0.0),
                input_tokens=u.get("input_tokens", 0),
                output_tokens=u.get("output_tokens", 0),
                cache_read_tokens=u.get("cache_read_input_tokens", 0),
                cache_create_tokens=u.get("cache_creation_input_tokens", 0),
                duration_ms=event.get("duration_ms", 0),
                duration_api_ms=event.get("duration_api_ms", 0),
                num_turns=event.get("num_turns", 0),
                context_window=ctx_window,
                rate_limit_status=usage.rate_limit_status,
                is_using_overage=usage.is_using_overage,
                rate_limit_resets_at=usage.rate_limit_resets_at,
                budget_exceeded=event.get("subtype") == "error_max_budget_usd",
            )

    return events, usage


def extract_structured_output(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract result from StructuredOutput tool_use events.

    When --json-schema is used, CC returns a StructuredOutput tool call.
    Returns the LAST StructuredOutput input dict, or None if not found.
    Rondo-REQ-100 req 079.
    """
    result = None
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        content = message.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "StructuredOutput":
                result = block.get("input", {})
    return result


def _collect_assistant_text(events: list[dict[str, Any]]) -> str:
    """Extract concatenated assistant text from stream-json events."""
    parts: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        content = message.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "\n".join(parts)


def classify_error(stderr: str) -> str:
    """Classify error from stderr content (Rondo-STD-108 stderr patterns).

    INVARIANT: always returns a string starting with 'ERR_'.
    Property tests (test_property.py) verify this for arbitrary input.
    If you add a new return value, it MUST start with 'ERR_' or property tests fail.
    """
    if not stderr:
        return "ERR_SUBPROCESS"
    lower = stderr.lower()
    if "credit balance is too low" in lower or "invalid api key" in lower:
        return "ERR_AUTH"
    if "cannot be launched inside another" in lower:
        return "ERR_NESTED_SESSION"
    if "rate limit" in lower or "rate_limit" in lower:
        return "ERR_RATE_LIMIT"
    return "ERR_SUBPROCESS"


# -- FIX-674: recovery guidance per error code
ERROR_RECOVERY: dict[str, tuple[str, bool]] = {
    # -- code: (recovery_message, is_transient)
    "ERR_SUBPROCESS": ("Run `rondo preflight` to check environment. Claude binary may be missing or crashed.", False),
    "ERR_AUTH": ("Check API key: `rondo providers` shows status. Verify env vars or ~/.rondo/config.toml.", False),
    "ERR_NESTED_SESSION": ("Cannot dispatch from inside Claude Code. Use MCP tools (rondo_run) instead of CLI.", False),
    "ERR_RATE_LIMIT": ("Provider rate limited. Wait and retry, or switch provider with --model.", True),
    "ERR_TIMEOUT": ("Task exceeded timeout. Increase with --timeout or simplify the task.", True),
    "ERR_EMPTY_OUTPUT": ("Claude returned empty output. May be auth issue. Run `rondo preflight`.", True),
    "ERR_COST_CAP": ("Cost cap exceeded. Increase --max-budget or use a cheaper model.", False),
    "ERR_WATCHDOG_TIMEOUT": ("Task went silent (no output). May be stuck. Check provider status.", True),
    "ERR_INTERNAL": ("Internal Rondo error. Check logs and report if repeatable.", False),
    "ERR_MALFORMED_JSON": ("AI output was not valid JSON. Retry or simplify the expected output format.", True),
    "ERR_PROVIDER_DOWN": ("Provider is down. Check `rondo providers` and use fallback.", True),
    "ERR_INVALID_PROFILE": ("Cloud profile not found. Check [cloud.profiles] in ~/.rondo/config.toml.", False),
}


def get_error_recovery(error_code: str) -> tuple[str, bool]:
    """Get recovery guidance and transient flag for an error code.

    Returns (recovery_message, is_transient). Unknown codes get generic guidance.
    """
    return ERROR_RECOVERY.get(error_code, ("Check `rondo preflight` for environment issues.", False))


def extract_modified_files(raw_output: str) -> list[str]:
    """Extract file paths from Claude's output (heuristic).

    Rondo-STD-108: populated by parsing raw_output for file paths.
    """
    pattern = (
        r"(?:^|\s)"
        r"((?:\./|/)?(?:[\w.-]+/)*[\w.-]+\."
        r"(?:py|md|toml|json|sql|sh|ts|js|yaml|yml))"
        r"\b"
    )
    matches = re.findall(pattern, raw_output)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


# -- sig: mgh-6201.cd.bd955f.e4a1.b2c3d4
