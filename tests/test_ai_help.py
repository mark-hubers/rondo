# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo ai-help — CORE-STD-023 machine-readable capability description.

VER-001 verification matrix: AI agents can discover Rondo capabilities.
"""

import json

from rondo.ai_help import get_ai_help, get_capabilities


class TestAiHelp:
    """AI-readable help output."""

    def test_ai_help_is_valid_json(self):
        data = get_ai_help()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert "name" in parsed
        assert parsed["name"] == "rondo"

    def test_ai_help_has_version(self):
        data = get_ai_help()
        assert "version" in data
        assert "0.2" in data["version"]

    def test_ai_help_has_commands(self):
        data = get_ai_help()
        assert "commands" in data
        assert len(data["commands"]) >= 5

    def test_ai_help_commands_have_description(self):
        data = get_ai_help()
        for cmd in data["commands"]:
            assert "name" in cmd
            assert "description" in cmd

    def test_ai_help_has_config_options(self):
        data = get_ai_help()
        assert "config" in data
        assert len(data["config"]) >= 5

    def test_ai_help_has_task_schema(self):
        data = get_ai_help()
        assert "task_schema" in data
        assert "instruction" in str(data["task_schema"])


class TestCapabilities:
    """Capability discovery for AI agents."""

    def test_capabilities_list(self):
        caps = get_capabilities()
        assert "dispatch" in caps
        assert "preflight" in caps
        assert "history" in caps

    def test_dispatch_capability_details(self):
        caps = get_capabilities()
        dispatch = caps["dispatch"]
        assert "models" in dispatch
        assert "sonnet" in dispatch["models"]

    def test_preflight_capability_details(self):
        caps = get_capabilities()
        pf = caps["preflight"]
        assert "checks" in pf
        assert len(pf["checks"]) >= 5


class TestAiHelpCLI:
    """CLI integration for --ai-help."""

    def test_ai_help_flag(self, capsys):
        from rondo.cli import main

        exit_code = main(["--ai-help"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["name"] == "rondo"
        assert exit_code == 0


# -- ──────────────────────────────────────────────────────────────
# --  U-05 to U-09: Enriched ai-help (RONDO-33)
# -- ──────────────────────────────────────────────────────────────


class TestAiHelpRoundSchema:
    """U-05: --ai-help includes Round dataclass schema."""

    def test_round_schema_present(self):
        data = get_ai_help()
        assert "round_schema" in data

    def test_round_schema_has_fields(self):
        data = get_ai_help()
        rs = data["round_schema"]
        assert "name" in str(rs)
        assert "tasks" in str(rs)
        assert "pre_gates" in str(rs)
        assert "post_gates" in str(rs)


class TestAiHelpTaskSchemaComplete:
    """U-06: --ai-help Task schema includes ALL fields."""

    def test_task_schema_has_description(self):
        data = get_ai_help()
        props = data["task_schema"]["properties"]
        assert "description" in props

    def test_task_schema_has_mode(self):
        data = get_ai_help()
        props = data["task_schema"]["properties"]
        assert "mode" in props

    def test_task_schema_has_auto_fn(self):
        data = get_ai_help()
        props = data["task_schema"]["properties"]
        assert "auto_fn" in props


class TestAiHelpExampleRoundFile:
    """U-07: --ai-help includes a copy-paste ready example round file."""

    def test_example_round_file_present(self):
        data = get_ai_help()
        assert "example_round_file" in data

    def test_example_has_build_round(self):
        data = get_ai_help()
        example = data["example_round_file"]
        assert "def build_round()" in example

    def test_example_has_imports(self):
        data = get_ai_help()
        example = data["example_round_file"]
        assert "from rondo.engine import Round, Task" in example

    def test_example_is_valid_python(self):
        """The example must actually compile."""
        data = get_ai_help()
        compile(data["example_round_file"], "<ai-help-example>", "exec")


class TestAiHelpGateSchema:
    """U-08: --ai-help includes Gate/GateResult schema."""

    def test_gate_schema_present(self):
        data = get_ai_help()
        assert "gate_schema" in data

    def test_gate_schema_has_fields(self):
        data = get_ai_help()
        gs = data["gate_schema"]
        assert "name" in str(gs)
        assert "check_fn" in str(gs)
        assert "blocking" in str(gs)


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b2c5
