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
        assert "0." in data["version"]

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


class TestHowItWorks:
    """The 3-step pattern is front and center in ai-help."""

    def test_how_it_works_present(self):
        data = get_ai_help()
        assert "how_it_works" in data

    def test_three_steps(self):
        data = get_ai_help()
        steps = data["how_it_works"]["three_steps"]
        assert len(steps) == 3
        assert steps[0]["name"] == "DEFINE"
        assert steps[1]["name"] == "DISPATCH"
        assert steps[2]["name"] == "RESULT"

    def test_each_step_has_example(self):
        data = get_ai_help()
        for step in data["how_it_works"]["three_steps"]:
            assert "example" in step
            assert len(step["example"]) > 0


class TestQuickExamples:
    """Simple 'do this, get that' examples."""

    def test_quick_examples_present(self):
        data = get_ai_help()
        assert "quick_examples" in data
        assert len(data["quick_examples"]) >= 3

    def test_each_has_task_and_run(self):
        data = get_ai_help()
        for ex in data["quick_examples"]:
            assert "task" in ex or "run" in ex
            assert "name" in ex


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


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109: Provider info in ai-help (RONDO-75)
# -- ──────────────────────────────────────────────────────────────


class TestAiHelpProviders:
    """ai-help includes multi-LLM provider information."""

    def test_providers_section_exists(self):
        data = get_ai_help()
        assert "providers" in data

    def test_providers_has_claude(self):
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "claude" in names

    def test_providers_has_ollama(self):
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "ollama" in names

    def test_each_provider_has_models(self):
        data = get_ai_help()
        for p in data["providers"]:
            assert "models" in p


class TestAiHelpMCPTools:
    """ai-help lists all 20 MCP tools."""

    def test_mcp_tools_present(self):
        data = get_ai_help()
        assert "mcp_tools" in data
        assert len(data["mcp_tools"]) >= 19

    def test_mcp_tools_have_categories(self):
        data = get_ai_help()
        categories = {t["category"] for t in data["mcp_tools"]}
        assert "monitor" in categories
        assert "dispatch" in categories
        assert "advanced" in categories

    def test_rondo_cloud_in_mcp_tools(self) -> None:
        """rondo_cloud multi-provider dispatch is discoverable via ai-help."""
        data = get_ai_help()
        names = [t["name"] for t in data["mcp_tools"]]
        assert "rondo_cloud" in names

    def test_rondo_multi_review_in_mcp_tools(self) -> None:
        """rondo_multi_review parallel review is discoverable via ai-help."""
        data = get_ai_help()
        names = [t["name"] for t in data["mcp_tools"]]
        assert "rondo_multi_review" in names

    def test_cloud_tools_have_cloud_category(self) -> None:
        data = get_ai_help()
        cloud_tools = [t for t in data["mcp_tools"] if t["name"] in ("rondo_cloud", "rondo_multi_review")]
        assert len(cloud_tools) == 2
        for tool in cloud_tools:
            assert tool["category"] == "cloud"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109: Cloud providers in ai-help
# -- ──────────────────────────────────────────────────────────────


class TestAiHelpCloudProviders:
    """REQ-109: all cloud providers discoverable via --ai-help."""

    def test_gemini_provider_present(self) -> None:
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "gemini" in names

    def test_openai_provider_present(self) -> None:
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "openai" in names

    def test_grok_provider_present(self) -> None:
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "grok" in names

    def test_mistral_provider_present(self) -> None:
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "mistral" in names

    def test_anthropic_provider_present(self) -> None:
        data = get_ai_help()
        names = [p["name"] for p in data["providers"]]
        assert "anthropic" in names

    def test_each_provider_has_examples(self) -> None:
        """Cloud providers expose routing examples — not just model names."""
        data = get_ai_help()
        cloud = [p for p in data["providers"] if p["name"] not in ("claude", "ollama")]
        for provider in cloud:
            assert "examples" in provider or "example" in provider, f"{provider['name']} missing examples"

    def test_each_cloud_provider_has_tiers(self) -> None:
        """Cloud providers expose high/default/low tier mapping."""
        data = get_ai_help()
        cloud = [p for p in data["providers"] if p["name"] not in ("claude", "ollama")]
        for provider in cloud:
            assert "tiers" in provider, f"{provider['name']} missing tiers"
            assert "high" in provider["tiers"]
            assert "default" in provider["tiers"]

    def test_description_mentions_cloud_providers(self) -> None:
        """Top-level description names all major cloud providers."""
        data = get_ai_help()
        desc = data["description"]
        for name in ("Gemini", "OpenAI", "Grok", "Mistral", "Anthropic"):
            assert name in desc, f"description missing {name}"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109: Cloud dispatch capabilities in ai-help
# -- ──────────────────────────────────────────────────────────────


class TestAiHelpCloudCapabilities:
    """REQ-109: cloud_dispatch and provider_health in capabilities."""

    def test_cloud_dispatch_capability_present(self) -> None:
        caps = get_capabilities()
        assert "cloud_dispatch" in caps

    def test_cloud_dispatch_lists_providers(self) -> None:
        caps = get_capabilities()
        cd = caps["cloud_dispatch"]
        for name in ("gemini", "openai", "grok", "mistral", "anthropic"):
            assert name in cd["providers"]

    def test_provider_health_capability_present(self) -> None:
        caps = get_capabilities()
        assert "provider_health" in caps

    def test_provider_health_has_cache_ttl(self) -> None:
        caps = get_capabilities()
        ph = caps["provider_health"]
        assert ph["cache_ttl_seconds"] == 300

    def test_important_section_has_cloud_info(self) -> None:
        data = get_ai_help()
        important = data["important"]
        assert "cloud_providers" in important
        assert "multi_provider" in important
        assert "health_fallback" in important

    def test_quick_examples_include_gemini(self) -> None:
        data = get_ai_help()
        examples_str = str(data["quick_examples"])
        assert "gemini" in examples_str.lower()

    def test_quick_examples_include_multi_review(self) -> None:
        data = get_ai_help()
        examples_str = str(data["quick_examples"])
        assert "multi_review" in examples_str or "providers" in examples_str


# -- sig: mgh-6201.cd.bd955f.e4a1.a1b2c5
