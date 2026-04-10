# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch prompt — build prompts + constants for dispatch.

Rondo-REQ-100 reqs 12, 24, 079-080.
Extracted from dispatch.py (Session 91 Sprint 19 — Cursor review Finding #144).

Import direction:
    dispatch_prompt.py → imports engine (for Task type)
"""

from __future__ import annotations

import json

from rondo.engine import Task

# -- Rondo-REQ-100 req 079: canonical result schema for --json-schema
RONDO_RESULT_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["done", "error", "blocked", "partial"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "result": {"type": "string"},
            "question": {"type": "string"},
        },
        "required": ["status", "result"],
    }
)

# -- Rondo-REQ-100 req 080: default system prompt for dispatch
RONDO_DISPATCH_PROMPT = (
    "You are executing a Rondo automated task. "
    "Return your answer as structured JSON matching the result schema. "
    "Fields: status (done/error/blocked/partial), result (what you did), "
    "confidence (0.0-1.0), question (if blocked, what you need). "
    "Do not wrap in markdown code fences — use the StructuredOutput tool."
)


def build_prompt(task: Task) -> str:
    """Build the dispatch prompt from a task's three-field contract.

    Includes JSON output instructions (Rondo-REQ-100 req 24).
    """
    parts = [f"# Rondo Task: {task.name}"]

    if task.description:
        parts.append(f"\n**Description:** {task.description}")

    if task.context_files:
        files = ", ".join(task.context_files)
        parts.append(f"\n**Read these files first:** {files}")

    # -- REQ-106: structured input data in prompt
    if task.context_data:
        parts.append("\n---\n## Structured Input Data\n")
        for key, value in task.context_data.items():
            parts.append(f"### {key}")
            if isinstance(value, list) and len(value) > 100:
                lines = "\n".join(json.dumps(item) for item in value)
                parts.append(f"```jsonl\n{lines}\n```")
            else:
                parts.append(f"```json\n{json.dumps(value, indent=2)}\n```")

    parts.append(f"\n**Do:** {task.instruction}")
    parts.append(f"\n**Done when:** {task.done_when}")

    # -- REQ-111: smart return prompt injection (per-provider, COALESCE)
    # -- When a Task has return_format or model hint, use smart_return templates
    # -- Otherwise fall back to the original simple JSON format
    try:
        from rondo.smart_return import build_return_prompt  # pylint: disable=import-outside-toplevel

        provider = task.model or ""
        return_prompt = build_return_prompt(provider=provider)
        parts.append(f"\n---\n{return_prompt}")
    except (ImportError, AttributeError):
        # -- Fallback: original simple format (REQ-100 req 029)
        parts.append(
            "\n---\n"
            "**Output format:** Respond with a JSON block at the end:\n"
            "```json\n"
            '{"status": "done"|"blocked", "confidence": 0.0-1.0, '
            '"result": "what you did", "question": "if blocked, what you need"}\n'
            "```"
        )

    return "\n".join(parts)


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b2c4
