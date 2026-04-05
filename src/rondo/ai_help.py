# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo AI help — machine-readable capability description for AI agents.

CORE-STD-023: tools output JSON for AI agents describing what they can do,
what parameters they accept, and how to use them.

Data loaded from data/ai_help_data.json (config-driven, not hardcoded).
Dynamic parts (version, CLI commands) added at runtime.

Usage:
    rondo --ai-help          # JSON to stdout
    from rondo.ai_help import get_ai_help
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rondo._version import get_version as _get_rondo_version

# -- Cache: loaded once per process
_help_data: dict[str, Any] | None = None
_DATA_FILE = Path(__file__).parent / "data" / "ai_help_data.json"


def _load_data() -> dict[str, Any]:
    """Load AI help data from JSON file, cache on first call."""
    global _help_data  # noqa: PLW0603
    if _help_data is not None:
        return _help_data
    _help_data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return _help_data


def get_ai_help() -> dict[str, Any]:
    """Return complete AI-readable help as a dict.

    This is what an AI agent reads to understand how to use Rondo.
    Static data from JSON + dynamic parts (version, commands) added here.
    """
    data = _load_data()
    return {
        "name": "rondo",
        "version": _get_rondo_version(),
        "description": data["description"],
        "deployment": data["deployment"],
        "important": data["important"],
        "providers": data["providers"],
        "mcp_tools": data["mcp_tools"],
        "commands": _get_commands(),
        "how_it_works": data["how_it_works"],
        "quick_examples": data["quick_examples"],
        "polling_tiers": data["polling_tiers"],
        "config": data["config_options"],
        "round_schema": data["round_schema"],
        "task_schema": data["task_schema"],
        "gate_schema": data["gate_schema"],
        "result_schema": data["result_schema"],
        "capabilities": data["capabilities"],
        "examples": data["examples"],
        "install": data["install"],
        "example_round_file": data["example_round_file"],
    }


def _get_commands() -> list[dict[str, str]]:
    """All CLI commands — derived from build_parser() (U-55 SSOT)."""
    from rondo.cli import build_parser  # pylint: disable=import-outside-toplevel

    commands: list[dict[str, str]] = []
    parser = build_parser()
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices:
            for name, sub in action.choices.items():
                commands.append({"name": name, "description": sub.description or sub.format_usage().strip()})
            break
    return commands


def get_capabilities() -> dict[str, Any]:
    """Return capability map for AI agents."""
    return _load_data()["capabilities"]


def build_round() -> Any:
    """Build a demo round from the example in ai_help data.

    Used by test_ai_help to verify the example is valid Python.
    Returns a Round object (typed as Any to avoid circular import).
    """
    from rondo.engine import Round, Task  # pylint: disable=import-outside-toplevel

    return Round(
        name="my-round",
        tasks=[
            Task(
                name="review-code",
                description="Review Python code for issues",
                instruction="Review the code for issues.",
                context_files=["src/main.py"],
                done_when="All files reviewed.",
            ),
        ],
    )


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b3c6
