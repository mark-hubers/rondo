# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.config — Rondo-STD-109 rules 1-10, Rondo-STD-108 rule 4.

VER-001 verification matrix: every test maps to a numbered rule.
TDD: these tests are written BEFORE config.py exists.
"""

import warnings
from dataclasses import FrozenInstanceError

import pytest

# -- Add rondo/src to path so we can import rondo

from rondo.config import (
    RondoConfig,
    load_config,
    resolve,
    validate_config,
)


# -- Rondo-STD-109 Rule 1: Works with zero config
class TestZeroConfig:
    def test_default_config_all_fields_populated(self):
        """RondoConfig() with no args produces a valid config."""
        config = RondoConfig()
        assert config.auth == "max"
        assert config.default_model == "sonnet"
        assert config.workers == 4
        assert config.throttle_sec == 2.0
        assert config.task_timeout_sec == 300
        assert config.results_dir == "reports/rondo-results"
        assert config.report_dir == "reports"
        assert config.claude_binary == "claude"
        assert config.dry_run is False
        assert config.verbose is False

    def test_default_config_validates(self):
        """Default config passes all validation checks."""
        config = RondoConfig()
        errors = validate_config(config)
        assert errors == []

    def test_load_config_no_file(self, tmp_path):
        """load_config with no config file returns defaults."""
        config = load_config(config_path=None, search_dir=tmp_path)
        assert config.auth == "max"
        assert config.default_model == "sonnet"
        assert config.workers == 4


# -- Rondo-STD-109 Rule 2: TOML format
class TestTomlLoading:
    def test_load_from_toml_file(self, tmp_path):
        """Config loaded from TOML file populates fields."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('auth = "api"\ndefault_model = "opus"\nworkers = 8\n')
        config = load_config(config_path=toml_file)
        assert config.auth == "api"
        assert config.default_model == "opus"
        assert config.workers == 8

    def test_partial_toml_fills_defaults(self, tmp_path):
        """TOML file with only some settings fills rest from defaults."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("workers = 16\n")
        config = load_config(config_path=toml_file)
        assert config.workers == 16
        assert config.auth == "max"  # -- default
        assert config.default_model == "sonnet"  # -- default


# -- Rondo-STD-109 Rule 3: Config discovery (--config or CWD)
class TestConfigDiscovery:
    def test_explicit_config_path(self, tmp_path):
        """--config flag path is used directly."""
        toml_file = tmp_path / "custom.toml"
        toml_file.write_text("workers = 12\n")
        config = load_config(config_path=toml_file)
        assert config.workers == 12

    def test_discover_in_search_dir(self, tmp_path):
        """Discovers rondo.toml in search_dir."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("workers = 6\n")
        config = load_config(config_path=None, search_dir=tmp_path)
        assert config.workers == 6

    def test_no_walk_up(self, tmp_path):
        """Does NOT walk up parent directories to find config."""
        # -- Put config in parent, search in child
        parent = tmp_path
        child = tmp_path / "subdir"
        child.mkdir()
        toml_file = parent / "rondo.toml"
        toml_file.write_text("workers = 99\n")
        # -- Searching in child should NOT find parent's config
        config = load_config(config_path=None, search_dir=child)
        assert config.workers == 4  # -- default, not 99


# -- Rondo-STD-109 Rule 4: CLI overrides config
class TestCliOverride:
    def test_cli_overrides_config_file(self, tmp_path):
        """CLI flag value wins over config file value."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("workers = 8\n")
        config = load_config(
            config_path=toml_file,
            cli_overrides={"workers": 2},
        )
        assert config.workers == 2

    def test_cli_overrides_multiple_fields(self, tmp_path):
        """Multiple CLI overrides all take effect."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('auth = "api"\ndefault_model = "opus"\n')
        config = load_config(
            config_path=toml_file,
            cli_overrides={"auth": "max", "default_model": "haiku"},
        )
        assert config.auth == "max"
        assert config.default_model == "haiku"


# -- Rondo-STD-109 Rule 5: Config overrides defaults
class TestConfigOverride:
    def test_config_file_overrides_defaults(self, tmp_path):
        """Config file value wins over hardcoded default."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("throttle_sec = 5.0\n")
        config = load_config(config_path=toml_file)
        assert config.throttle_sec == 5.0  # -- not the default 2.0


# -- Rondo-STD-109 Rule 6: COALESCE resolution
class TestCoalesce:
    def test_resolve_cli_wins(self):
        """CLI value wins when all three provided."""
        assert resolve("cli", "config", "default") == "cli"

    def test_resolve_config_wins_no_cli(self):
        """Config value wins when CLI is None."""
        assert resolve(None, "config", "default") == "config"

    def test_resolve_default_wins_no_cli_no_config(self):
        """Default wins when both CLI and config are None."""
        assert resolve(None, None, "default") == "default"

    def test_resolve_cli_none_explicit(self):
        """None CLI is skipped, not used."""
        assert resolve(None, "config", "default") == "config"

    def test_full_coalesce_chain(self, tmp_path):
        """End-to-end: CLI → config → default."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("workers = 8\nthrottle_sec = 5.0\n")
        config = load_config(
            config_path=toml_file,
            cli_overrides={"workers": 2},  # -- CLI overrides config
        )
        assert config.workers == 2  # -- CLI won
        assert config.throttle_sec == 5.0  # -- config won (no CLI)
        assert config.auth == "max"  # -- default won (no CLI, no config)


# -- Rondo-STD-109 Rule 7: Unknown keys ignored with warning
class TestUnknownKeys:
    def test_unknown_toml_keys_ignored(self, tmp_path):
        """Unknown keys in TOML are ignored — config still loads."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('workers = 8\nfuture_setting = "something"\nanother_unknown = 42\n')
        config = load_config(config_path=toml_file)
        assert config.workers == 8  # -- known key works
        # -- no crash from unknown keys

    def test_unknown_keys_produce_warning(self, tmp_path):
        """Unknown keys emit a warning."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("bogus_key = true\n")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            load_config(config_path=toml_file)
            # -- Should have at least one warning about unknown key
            unknown_warnings = [x for x in w if "bogus_key" in str(x.message)]
            assert len(unknown_warnings) >= 1


# -- Rondo-STD-109 Rule 8: Invalid values error at startup
class TestValidationErrors:
    def test_invalid_auth(self):
        config = RondoConfig(auth="bad")
        errors = validate_config(config)
        assert any("auth" in e for e in errors)

    def test_invalid_workers_low(self):
        config = RondoConfig(workers=0)
        errors = validate_config(config)
        assert any("workers" in e for e in errors)

    def test_invalid_workers_high(self):
        config = RondoConfig(workers=100)
        errors = validate_config(config)
        assert any("workers" in e for e in errors)

    def test_invalid_throttle_negative(self):
        config = RondoConfig(throttle_sec=-1.0)
        errors = validate_config(config)
        assert any("throttle" in e for e in errors)

    def test_invalid_throttle_too_high(self):
        config = RondoConfig(throttle_sec=100.0)
        errors = validate_config(config)
        assert any("throttle" in e for e in errors)

    def test_invalid_timeout_low(self):
        config = RondoConfig(task_timeout_sec=5)
        errors = validate_config(config)
        assert any("timeout" in e for e in errors)

    def test_invalid_timeout_high(self):
        config = RondoConfig(task_timeout_sec=9999)
        errors = validate_config(config)
        assert any("timeout" in e for e in errors)

    def test_invalid_output_format(self):
        config = RondoConfig(output_format="xml")
        errors = validate_config(config)
        assert any("output_format" in e for e in errors)

    def test_invalid_effort(self):
        config = RondoConfig(effort="extreme")
        errors = validate_config(config)
        assert any("effort" in e for e in errors)

    def test_invalid_watchdog_low(self):
        config = RondoConfig(watchdog_timeout_sec=1)
        errors = validate_config(config)
        assert any("watchdog" in e for e in errors)

    def test_invalid_watchdog_high(self):
        config = RondoConfig(watchdog_timeout_sec=9999)
        errors = validate_config(config)
        assert any("watchdog" in e for e in errors)

    def test_invalid_backoff_low(self):
        config = RondoConfig(rate_limit_backoff_sec=1)
        errors = validate_config(config)
        assert any("backoff" in e or "rate_limit" in e for e in errors)

    def test_invalid_on_overage(self):
        config = RondoConfig(on_overage="crash")
        errors = validate_config(config)
        assert any("on_overage" in e for e in errors)

    def test_invalid_model(self):
        config = RondoConfig(default_model="gpt-4")
        errors = validate_config(config)
        assert any("model" in e for e in errors)

    def test_empty_claude_binary(self):
        config = RondoConfig(claude_binary="")
        errors = validate_config(config)
        assert any("claude_binary" in e for e in errors)

    def test_empty_results_dir(self):
        config = RondoConfig(results_dir="")
        errors = validate_config(config)
        assert any("results_dir" in e for e in errors)

    def test_empty_report_dir(self):
        config = RondoConfig(report_dir="")
        errors = validate_config(config)
        assert any("report_dir" in e for e in errors)

    def test_multiple_errors_returned(self):
        """All errors returned at once, not just the first."""
        config = RondoConfig(auth="bad", workers=0, effort="extreme")
        errors = validate_config(config)
        assert len(errors) >= 3

    def test_valid_config_no_errors(self):
        config = RondoConfig()
        errors = validate_config(config)
        assert errors == []


# -- Rondo-STD-109 Rule 9: Config loaded once, immutable (frozen dataclass)
class TestConfigImmutable:
    def test_frozen_cannot_set_field(self):
        """Frozen dataclass raises on attribute assignment."""
        config = RondoConfig()
        with pytest.raises(FrozenInstanceError):
            config.workers = 99

    def test_frozen_cannot_delete_field(self):
        """Frozen dataclass raises on attribute deletion."""
        config = RondoConfig()
        with pytest.raises(FrozenInstanceError):
            del config.workers


# -- Rondo-STD-109 Rule 10: Config is a dataclass
class TestConfigIsDataclass:
    def test_is_dataclass(self):
        from dataclasses import fields

        config = RondoConfig()
        # -- fields() only works on dataclasses — would raise if not
        field_names = [f.name for f in fields(config)]
        assert "auth" in field_names
        assert "workers" in field_names
        assert "default_model" in field_names


# -- Rondo-STD-108 Rule 4: Configurable timeout, default 5 min
class TestTimeoutConfig:
    def test_timeout_default_300(self):
        config = RondoConfig()
        assert config.task_timeout_sec == 300

    def test_timeout_configurable(self):
        config = RondoConfig(task_timeout_sec=600)
        assert config.task_timeout_sec == 600

    def test_timeout_from_toml(self, tmp_path):
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text("task_timeout_sec = 120\n")
        config = load_config(config_path=toml_file)
        assert config.task_timeout_sec == 120


# -- Additional config fields (Rondo-STD-109 settings table)
class TestAllConfigFields:
    def test_effort_default(self):
        assert RondoConfig().effort == "high"

    def test_output_format_default(self):
        assert RondoConfig().output_format == "stream-json"

    def test_watchdog_default(self):
        assert RondoConfig().watchdog_timeout_sec == 60

    def test_rate_limit_backoff_default(self):
        assert RondoConfig().rate_limit_backoff_sec == 60

    def test_on_overage_default(self):
        assert RondoConfig().on_overage == "continue"

    def test_worktree_isolation_default(self):
        assert RondoConfig().worktree_isolation is False

    def test_all_valid_models(self):
        """All documented model names are accepted."""
        for model in ("opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]"):
            config = RondoConfig(default_model=model)
            errors = validate_config(config)
            assert errors == [], f"Model '{model}' should be valid"

    def test_all_valid_efforts(self):
        """All documented effort levels are accepted."""
        for effort in ("low", "medium", "high", "max"):
            config = RondoConfig(effort=effort)
            errors = validate_config(config)
            assert errors == [], f"Effort '{effort}' should be valid"

    def test_all_valid_output_formats(self):
        """All documented output formats are accepted."""
        for fmt in ("text", "json", "stream-json"):
            config = RondoConfig(output_format=fmt)
            errors = validate_config(config)
            assert errors == [], f"Format '{fmt}' should be valid"

    def test_all_valid_overage_actions(self):
        """All documented on_overage actions are accepted."""
        for action in ("continue", "pause", "stop"):
            config = RondoConfig(on_overage=action)
            errors = validate_config(config)
            assert errors == [], f"Action '{action}' should be valid"

    def test_permission_mode_default(self):
        """Rondo-REQ-100 req 48: default permission_mode is 'auto'."""
        config = RondoConfig()
        assert config.permission_mode == "auto"

    def test_all_valid_permission_modes(self):
        """Rondo-REQ-100 req 49: all documented permission modes are accepted."""
        for mode in ("default", "acceptEdits", "plan", "auto", "bypassPermissions"):
            config = RondoConfig(permission_mode=mode)
            errors = validate_config(config)
            assert errors == [], f"Permission mode '{mode}' should be valid"

    def test_invalid_permission_mode(self):
        """Rondo-REQ-100 req 49: invalid permission mode rejected."""
        config = RondoConfig(permission_mode="yolo")
        errors = validate_config(config)
        assert any("permission_mode" in e for e in errors)

    def test_permission_mode_coalesce(self, tmp_path):
        """Rondo-REQ-100 req 48: COALESCE — CLI → config → default 'auto'."""
        # -- Config file sets bypassPermissions
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('permission_mode = "bypassPermissions"\n')

        # -- No CLI override → config wins
        config = load_config(config_path=toml_file)
        assert config.permission_mode == "bypassPermissions"

        # -- CLI override → CLI wins
        config = load_config(
            config_path=toml_file,
            cli_overrides={"permission_mode": "acceptEdits"},
        )
        assert config.permission_mode == "acceptEdits"

        # -- No config, no CLI → default wins
        config = load_config(config_path=None, search_dir=tmp_path / "empty")
        assert config.permission_mode == "auto"


# ──────────────────────────────────────────────────────────────────
#  Cross-field relationship validation
# ──────────────────────────────────────────────────────────────────


class TestRelationshipValidation:
    def test_watchdog_must_be_less_than_task_timeout(self):
        """Watchdog fires within a task — must be shorter than task timeout."""
        config = RondoConfig(watchdog_timeout_sec=300, task_timeout_sec=60)
        errors = validate_config(config)
        assert any("watchdog_timeout_sec" in e and "task_timeout_sec" in e for e in errors)

    def test_watchdog_equal_to_task_timeout_fails(self):
        """Equal values also invalid — watchdog must be strictly less."""
        config = RondoConfig(watchdog_timeout_sec=300, task_timeout_sec=300)
        errors = validate_config(config)
        assert any("watchdog_timeout_sec" in e for e in errors)

    def test_watchdog_less_than_task_timeout_passes(self):
        """Valid: watchdog < task timeout."""
        config = RondoConfig(watchdog_timeout_sec=60, task_timeout_sec=300)
        errors = validate_config(config)
        assert not any("watchdog_timeout_sec" in e for e in errors)

    def test_default_config_relationship_valid(self):
        """Default config has watchdog (60) < task_timeout (300)."""
        config = RondoConfig()
        errors = validate_config(config)
        assert len(errors) == 0


# -- Session 91: deepen config coverage
class TestNewConfigFields:
    """Session 91 fields in RondoConfig."""

    def test_bare_default_false(self):
        config = RondoConfig()
        assert config.bare is False

    def test_json_schema_default_empty(self):
        config = RondoConfig()
        assert config.json_schema == ""

    def test_dispatch_system_prompt_default_empty(self):
        config = RondoConfig()
        assert config.dispatch_system_prompt == ""

    def test_max_budget_default_none(self):
        config = RondoConfig()
        assert config.max_budget_usd is None

    def test_all_new_fields_set(self):
        config = RondoConfig(
            bare=True, json_schema="auto",
            dispatch_system_prompt="auto", max_budget_usd=0.50,
        )
        assert config.bare is True
        assert config.json_schema == "auto"
        assert config.dispatch_system_prompt == "auto"
        assert config.max_budget_usd == 0.50

    def test_config_frozen_cannot_modify(self):
        config = RondoConfig()
        with pytest.raises(FrozenInstanceError):
            config.bare = True


class TestConfigFromToml:
    """TOML loading for new fields."""

    def test_toml_with_new_fields(self, tmp_path):
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text(
            'bare = true\n'
            'json_schema = "auto"\n'
            'dispatch_system_prompt = "auto"\n'
            'max_budget_usd = 0.25\n'
        )
        config = load_config(config_path=str(toml_file))
        assert config.bare is True
        assert config.json_schema == "auto"
        assert config.dispatch_system_prompt == "auto"
        assert config.max_budget_usd == 0.25

    def test_toml_partial_new_fields(self, tmp_path):
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('json_schema = "auto"\n')
        config = load_config(config_path=str(toml_file))
        assert config.json_schema == "auto"
        assert config.bare is False  # default preserved


class TestConfigPermissionModes:
    """All permission modes are valid."""

    def test_all_permission_modes_valid(self):
        for mode in ["default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"]:
            config = RondoConfig(permission_mode=mode)
            errors = validate_config(config)
            assert not any("permission" in e for e in errors), f"{mode} should be valid"


class TestConfigDefaults:
    """STD-109: all config fields have sensible defaults."""

    def test_default_model_is_sonnet(self):
        """Default model is sonnet (safest for automated dispatch)."""
        config = RondoConfig()
        assert config.default_model == "sonnet"

    def test_default_auth_is_max(self):
        """Default auth is max (subscription, no API key needed)."""
        config = RondoConfig()
        assert config.auth == "max"

    def test_default_output_format_stream_json(self):
        """Default output format is stream-json (REQ-100 req 015)."""
        config = RondoConfig()
        assert config.output_format == "stream-json"

    def test_default_audit_dir_always_on(self, monkeypatch):
        """Audit dir defaults to ~/.rondo/audit (ALWAYS-ON pattern)."""
        monkeypatch.delenv("RONDO_TEST_DIR", raising=False)
        config = RondoConfig()
        assert config.audit_dir == "~/.rondo/audit"

    def test_default_task_timeout(self):
        """Task timeout defaults to 300s (5 min)."""
        config = RondoConfig()
        assert config.task_timeout_sec == 300

    def test_default_round_timeout(self):
        """Round timeout defaults to 3600s (1 hour)."""
        config = RondoConfig()
        assert config.round_timeout_sec == 3600

    def test_default_workers(self):
        """Default workers is 4."""
        config = RondoConfig()
        assert config.workers == 4

    def test_default_bare_is_false(self):
        """Bare is off by default (safety — preserves Caliber guards)."""
        config = RondoConfig()
        assert config.bare is False

    def test_default_dry_run_is_false(self):
        """Dry run is off by default."""
        config = RondoConfig()
        assert config.dry_run is False


class TestConfigValidation:
    """STD-109: config validation catches bad values."""

    def test_invalid_auth_rejected(self):
        """Auth must be 'max' or 'api'."""
        errors = validate_config(RondoConfig(auth="invalid"))
        assert any("auth" in e.lower() for e in errors)

    def test_invalid_model_rejected(self):
        """Model must be in VALID_MODELS."""
        errors = validate_config(RondoConfig(default_model="gpt-4"))
        assert any("model" in e.lower() for e in errors)

    def test_valid_config_no_errors(self):
        """Default config passes validation."""
        errors = validate_config(RondoConfig())
        assert len(errors) == 0


class TestModelResolution:
    """REQ-100: model resolution follows COALESCE chain."""

    def test_cli_model_overrides_task(self):
        """CLI --model overrides task.model."""
        from rondo.dispatch import resolve_model
        from rondo.engine import Task

        task = Task(name="t", instruction="do", done_when="done", model="haiku")
        result = resolve_model("opus", task, RondoConfig(default_model="sonnet"))
        assert result == "opus"

    def test_task_model_overrides_config(self):
        """task.model overrides config.default_model."""
        from rondo.dispatch import resolve_model
        from rondo.engine import Task

        task = Task(name="t", instruction="do", done_when="done", model="haiku")
        result = resolve_model(None, task, RondoConfig(default_model="sonnet"))
        assert result == "haiku"

    def test_config_default_used_last(self):
        """config.default_model used when no CLI or task model."""
        from rondo.dispatch import resolve_model
        from rondo.engine import Task

        task = Task(name="t", instruction="do", done_when="done")
        result = resolve_model(None, task, RondoConfig(default_model="opus"))
        assert result == "opus"


# -- sig: mgh-6201.cd.bd955f.e6d7.bf1b3b
