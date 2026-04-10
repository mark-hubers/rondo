# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo round loader — YAML/JSON/Python round file support.

REQ-111 reqs 410-414: language-agnostic task definitions.
Detects file type by extension and parses into Round/Task objects.

Import direction:
    round_loader.py → imports engine (Round, Task only)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rondo.engine import Round, Task

logger = logging.getLogger(__name__)

# -- Valid Task fields from dataclass (REQ-111 req 414: reject unknown fields)
_VALID_TASK_FIELDS = {
    "name",
    "description",
    "instruction",
    "context_files",
    "done_when",
    "context_data",
    "model",
    "mode",
    "tool_mode",
    "bare",
    "safe_parallel",
    "human_input",
    "pre_dispatch",
    "post_dispatch",
    "return_format",
    "depends_on",
    "only_if",
}

# -- Valid Round fields
_VALID_ROUND_FIELDS = {"name", "tasks", "pre_gates", "post_gates", "description"}


def load_round(filepath: str) -> Round:
    """Load a round definition from any supported format.

    REQ-111 reqs 410-414: detects format by extension.
    - .yaml / .yml → YAML
    - .json → JSON
    - .py → Python (delegates to existing load_round_file)

    Returns a Round object ready for dispatch.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Round file not found: {filepath}")

    ext = path.suffix.lower()

    if ext in (".yaml", ".yml"):
        return _load_yaml(path)
    if ext == ".json":
        return _load_json(path)
    if ext == ".py":
        from rondo.engine import load_round_file  # pylint: disable=import-outside-toplevel

        return load_round_file(filepath)

    raise ValueError(f"Unsupported round file format: '{ext}'. Use .yaml, .json, or .py")


def _load_yaml(path: Path) -> Round:
    """Parse YAML round file into Round object.

    REQ-111 req 410, 414: uses yaml.safe_load only (no arbitrary code).
    """
    import yaml  # pylint: disable=import-outside-toplevel

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ValueError(f"YAML round file must be a mapping, got {type(data).__name__}")

    return _data_to_round(data, str(path))


def _load_json(path: Path) -> Round:
    """Parse JSON round file into Round object.

    REQ-111 req 411.
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError(f"JSON round file must be an object, got {type(data).__name__}")

    return _data_to_round(data, str(path))


def _data_to_round(data: dict[str, Any], source: str) -> Round:
    """Convert a parsed dict (from YAML or JSON) into a Round object.

    REQ-111 req 414: validates schema, rejects unknown fields.
    """
    # -- Validate round-level fields
    unknown_round = set(data.keys()) - _VALID_ROUND_FIELDS
    if unknown_round:
        raise ValueError(f"Unknown round fields in {source}: {unknown_round}")

    name = data.get("name", Path(source).stem)
    tasks_data = data.get("tasks", [])

    if not isinstance(tasks_data, list):
        raise ValueError(f"'tasks' must be a list in {source}")

    if not tasks_data:
        raise ValueError(f"Round must have at least one task in {source}")

    tasks: list[Task] = []
    for i, task_data in enumerate(tasks_data):
        if not isinstance(task_data, dict):
            raise ValueError(f"Task {i} must be a mapping in {source}")

        # -- Validate task fields
        unknown_task = set(task_data.keys()) - _VALID_TASK_FIELDS
        if unknown_task:
            raise ValueError(f"Unknown task fields in task {i} of {source}: {unknown_task}")

        if "name" not in task_data:
            raise ValueError(f"Task {i} missing required 'name' field in {source}")

        # -- Build Task with only known fields
        task_kwargs: dict[str, Any] = {}
        for field_name in _VALID_TASK_FIELDS:
            if field_name in task_data:
                task_kwargs[field_name] = task_data[field_name]

        tasks.append(Task(**task_kwargs))

    return Round(name=name, tasks=tasks)


# -- sig: mgh-6201.cd.bd955f.ld3r.r0und0
