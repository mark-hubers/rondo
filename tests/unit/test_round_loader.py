# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.round_loader — YAML/JSON/Python round file loading.

REQ-111 reqs 410-414.
VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json

import pytest
import yaml

from rondo.engine import Round
from rondo.round_loader import load_round


class TestYAMLLoader:
    """REQ-111 reqs 410, 414: YAML round file parsing."""

    def test_load_simple_yaml(self, tmp_path) -> None:
        """Basic YAML round file loads correctly."""
        f = tmp_path / "round.yaml"
        f.write_text(yaml.dump({
            "name": "test-round",
            "tasks": [{"name": "t1", "instruction": "do something"}],
        }))
        result = load_round(str(f))
        assert isinstance(result, Round)
        assert result.name == "test-round"
        assert len(result.tasks) == 1
        assert result.tasks[0].name == "t1"

    def test_yaml_multiple_tasks(self, tmp_path) -> None:
        """YAML with multiple tasks loads all tasks."""
        f = tmp_path / "multi.yaml"
        f.write_text(yaml.dump({
            "name": "multi",
            "tasks": [
                {"name": "t1", "instruction": "first"},
                {"name": "t2", "instruction": "second", "model": "gemini:flash"},
                {"name": "t3", "instruction": "third", "done_when": "done"},
            ],
        }))
        result = load_round(str(f))
        assert len(result.tasks) == 3
        assert result.tasks[1].model == "gemini:flash"
        assert result.tasks[2].done_when == "done"

    def test_yaml_unknown_field_rejected(self, tmp_path) -> None:
        """REQ-111 req 414: unknown task fields are rejected."""
        f = tmp_path / "bad.yaml"
        f.write_text(yaml.dump({
            "name": "bad",
            "tasks": [{"name": "t1", "instruction": "hi", "bogus_field": True}],
        }))
        with pytest.raises(ValueError, match="Unknown task fields"):
            load_round(str(f))

    def test_yaml_unknown_round_field_rejected(self, tmp_path) -> None:
        """Unknown round-level fields are rejected."""
        f = tmp_path / "bad.yaml"
        f.write_text(yaml.dump({
            "name": "bad",
            "unknown_top": True,
            "tasks": [{"name": "t1", "instruction": "hi"}],
        }))
        with pytest.raises(ValueError, match="Unknown round fields"):
            load_round(str(f))

    def test_yaml_missing_name_rejected(self, tmp_path) -> None:
        """Tasks missing name field are rejected."""
        f = tmp_path / "no_name.yaml"
        f.write_text(yaml.dump({
            "name": "test",
            "tasks": [{"instruction": "no name here"}],
        }))
        with pytest.raises(ValueError, match="missing required 'name'"):
            load_round(str(f))

    def test_yaml_empty_tasks_rejected(self, tmp_path) -> None:
        """Round with no tasks is rejected."""
        f = tmp_path / "empty.yaml"
        f.write_text(yaml.dump({"name": "empty", "tasks": []}))
        with pytest.raises(ValueError, match="at least one task"):
            load_round(str(f))

    def test_yml_extension_works(self, tmp_path) -> None:
        """REQ-111 req 412: .yml extension also works."""
        f = tmp_path / "round.yml"
        f.write_text(yaml.dump({
            "name": "yml-test",
            "tasks": [{"name": "t1", "instruction": "hi"}],
        }))
        result = load_round(str(f))
        assert result.name == "yml-test"

    def test_yaml_name_defaults_to_filename(self, tmp_path) -> None:
        """If name not provided, uses filename stem."""
        f = tmp_path / "my-review.yaml"
        f.write_text(yaml.dump({
            "tasks": [{"name": "t1", "instruction": "hi"}],
        }))
        result = load_round(str(f))
        assert result.name == "my-review"


class TestJSONLoader:
    """REQ-111 req 411: JSON round file parsing."""

    def test_load_simple_json(self, tmp_path) -> None:
        """Basic JSON round file loads correctly."""
        f = tmp_path / "round.json"
        f.write_text(json.dumps({
            "name": "json-test",
            "tasks": [{"name": "t1", "instruction": "do something"}],
        }))
        result = load_round(str(f))
        assert isinstance(result, Round)
        assert result.name == "json-test"

    def test_json_with_all_task_fields(self, tmp_path) -> None:
        """JSON task with many fields loads correctly."""
        f = tmp_path / "full.json"
        f.write_text(json.dumps({
            "name": "full",
            "tasks": [{
                "name": "t1",
                "instruction": "review code",
                "done_when": "list all bugs",
                "model": "gemini:flash",
                "context_files": ["src/app.py"],
                "bare": True,
            }],
        }))
        result = load_round(str(f))
        assert result.tasks[0].model == "gemini:flash"
        assert result.tasks[0].bare is True
        assert result.tasks[0].context_files == ["src/app.py"]


class TestPythonFallback:
    """REQ-111 req 413: Python round files still work."""

    def test_py_delegates_to_engine(self, tmp_path) -> None:
        """Python files delegate to existing load_round_file."""
        f = tmp_path / "round.py"
        f.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='py-test', tasks=[Task(name='t1', instruction='hi')])\n"
        )
        result = load_round(str(f))
        assert result.name == "py-test"


class TestEdgeCases:
    """Error handling and edge cases."""

    def test_file_not_found(self) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_round("/nonexistent/round.yaml")

    def test_unsupported_extension(self, tmp_path) -> None:
        """Unsupported extension raises ValueError."""
        f = tmp_path / "round.toml"
        f.write_text("")
        with pytest.raises(ValueError, match="Unsupported"):
            load_round(str(f))

    def test_invalid_yaml_content(self, tmp_path) -> None:
        """Non-mapping YAML raises ValueError."""
        f = tmp_path / "bad.yaml"
        f.write_text("- just a list\n- not a mapping\n")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_round(str(f))

    def test_invalid_json_content(self, tmp_path) -> None:
        """Non-object JSON raises ValueError."""
        f = tmp_path / "bad.json"
        f.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="must be an object"):
            load_round(str(f))


# -- sig: mgh-6201.cd.bd955f.1d3e.e35e50
