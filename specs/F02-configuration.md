# F02: Configuration

*How Rondo is configured — TOML file, CLI flags, sane defaults.*

**Created:** 2026-03-13 | **Status:** DRAFT

---

## Principle

Rondo works with zero config. Every setting has a sane default. A config file adds project-level customization. CLI flags override everything. The resolution pattern is COALESCE: CLI → config → default.

---

## Rules

1. Rondo MUST work out of the box with no config file. All settings have defaults.
2. Project-level config MUST be TOML format (Python 3.12 has `tomllib` in stdlib — zero dependencies).
3. Config file location: `rondo.toml` in the project root, or path specified via `--config` flag.
4. CLI flags MUST override config file values.
5. Config file values MUST override defaults.
6. Resolution order: CLI flag → config file → hardcoded default. First non-null wins (COALESCE).

---

## Configurable Settings

| Setting | CLI Flag | Config Key | Default |
|---------|----------|-----------|---------|
| Auth mode | `--auth max\|api` | `auth` | `max` |
| Model | `--model opus\|sonnet\|haiku` | `default_model` | `sonnet` |
| Workers | `--workers N` | `workers` | `4` |
| Throttle | `--throttle N` | `throttle_sec` | `2.0` |
| Task timeout | `--timeout N` | `task_timeout_sec` | `300` |
| Results dir | — | `results_dir` | `reports/rondo-results` |
| Report dir | — | `report_dir` | `reports` |
| Claude binary | — | `claude_binary` | `claude` |
| Dry run | `--dry-run` | — | `false` |

---

## Config File Example

```toml
## -- Rondo project configuration

auth = "max"
default_model = "sonnet"
workers = 4
throttle_sec = 2.0
task_timeout_sec = 300
results_dir = "reports/rondo-results"
report_dir = "reports"
claude_binary = "claude"
```

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft |
