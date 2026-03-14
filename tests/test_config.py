"""Tests for rondo.config — STD-002 rules 1-10, STD-001 rule 4.

VER-001 verification matrix: every test maps to a numbered rule.
TDD: these tests are written BEFORE config.py exists.
"""
import sys
import warnings
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.config import (
    RondoConfig,
    load_config,
    resolve,
    validate_config,
)


# -- STD-002 Rule 1: Works with zero config
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


# -- STD-002 Rule 2: TOML format
class TestTomlLoading:

    def test_load_from_toml_file(self, tmp_path):
        """Config loaded from TOML file populates fields."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text(
            'auth = "api"\n'
            'default_model = "opus"\n'
            "workers = 8\n"
        )
        config = load_config(config_path=toml_file)
        assert config.auth == "api"
        assert config.default_model == "opus"
        assert config.workers == 8

    def test_partial_toml_fills_defaults(self, tmp_path):
        """TOML file with only some settings fills rest from defaults."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('workers = 16\n')
        config = load_config(config_path=toml_file)
        assert config.workers == 16
        assert config.auth == "max"  # -- default
        assert config.default_model == "sonnet"  # -- default


# -- STD-002 Rule 3: Config discovery (--config or CWD)
class TestConfigDiscovery:

    def test_explicit_config_path(self, tmp_path):
        """--config flag path is used directly."""
        toml_file = tmp_path / "custom.toml"
        toml_file.write_text('workers = 12\n')
        config = load_config(config_path=toml_file)
        assert config.workers == 12

    def test_discover_in_search_dir(self, tmp_path):
        """Discovers rondo.toml in search_dir."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('workers = 6\n')
        config = load_config(config_path=None, search_dir=tmp_path)
        assert config.workers == 6

    def test_no_walk_up(self, tmp_path):
        """Does NOT walk up parent directories to find config."""
        # -- Put config in parent, search in child
        parent = tmp_path
        child = tmp_path / "subdir"
        child.mkdir()
        toml_file = parent / "rondo.toml"
        toml_file.write_text('workers = 99\n')
        # -- Searching in child should NOT find parent's config
        config = load_config(config_path=None, search_dir=child)
        assert config.workers == 4  # -- default, not 99


# -- STD-002 Rule 4: CLI overrides config
class TestCliOverride:

    def test_cli_overrides_config_file(self, tmp_path):
        """CLI flag value wins over config file value."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('workers = 8\n')
        config = load_config(
            config_path=toml_file,
            cli_overrides={"workers": 2},
        )
        assert config.workers == 2

    def test_cli_overrides_multiple_fields(self, tmp_path):
        """Multiple CLI overrides all take effect."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text(
            'auth = "api"\n'
            'default_model = "opus"\n'
        )
        config = load_config(
            config_path=toml_file,
            cli_overrides={"auth": "max", "default_model": "haiku"},
        )
        assert config.auth == "max"
        assert config.default_model == "haiku"


# -- STD-002 Rule 5: Config overrides defaults
class TestConfigOverride:

    def test_config_file_overrides_defaults(self, tmp_path):
        """Config file value wins over hardcoded default."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('throttle_sec = 5.0\n')
        config = load_config(config_path=toml_file)
        assert config.throttle_sec == 5.0  # -- not the default 2.0


# -- STD-002 Rule 6: COALESCE resolution
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
        toml_file.write_text(
            'workers = 8\n'
            'throttle_sec = 5.0\n'
        )
        config = load_config(
            config_path=toml_file,
            cli_overrides={"workers": 2},  # -- CLI overrides config
        )
        assert config.workers == 2       # -- CLI won
        assert config.throttle_sec == 5.0  # -- config won (no CLI)
        assert config.auth == "max"       # -- default won (no CLI, no config)


# -- STD-002 Rule 7: Unknown keys ignored with warning
class TestUnknownKeys:

    def test_unknown_toml_keys_ignored(self, tmp_path):
        """Unknown keys in TOML are ignored — config still loads."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text(
            'workers = 8\n'
            'future_setting = "something"\n'
            'another_unknown = 42\n'
        )
        config = load_config(config_path=toml_file)
        assert config.workers == 8  # -- known key works
        # -- no crash from unknown keys

    def test_unknown_keys_produce_warning(self, tmp_path):
        """Unknown keys emit a warning."""
        toml_file = tmp_path / "rondo.toml"
        toml_file.write_text('bogus_key = true\n')
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            load_config(config_path=toml_file)
            # -- Should have at least one warning about unknown key
            unknown_warnings = [x for x in w if "bogus_key" in str(x.message)]
            assert len(unknown_warnings) >= 1


# -- STD-002 Rule 8: Invalid values error at startup
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


# -- STD-002 Rule 9: Config loaded once, immutable (frozen dataclass)
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


# -- STD-002 Rule 10: Config is a dataclass
class TestConfigIsDataclass:

    def test_is_dataclass(self):
        from dataclasses import fields
        config = RondoConfig()
        # -- fields() only works on dataclasses — would raise if not
        field_names = [f.name for f in fields(config)]
        assert "auth" in field_names
        assert "workers" in field_names
        assert "default_model" in field_names


# -- STD-001 Rule 4: Configurable timeout, default 5 min
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


# -- Additional config fields (STD-002 settings table)
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
