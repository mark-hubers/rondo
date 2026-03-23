# STD-109: Configuration

*How Rondo is configured — TOML file, CLI flags, sane defaults, COALESCE resolution.*

**Created:** 2026-03-13 | **Updated:** 2026-03-14 | **Status:** DRAFT
**Classification:** open
**Version:** 0.6
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Nothing | **Blocks:** REQ-100 (Core), REQ-101 (Automation)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Defines how every Rondo setting is resolved — from CLI flags, config files, and
defaults — using a single consistent pattern. Rondo works out of the box with
zero config. A TOML file adds project-level customization. CLI flags override
everything.

**IN scope:**
- Config resolution order (COALESCE)
- TOML config file format and location
- All configurable settings with types and defaults
- Config validation rules
- Config discovery (how Rondo finds the config file)

**OUT of scope:**
- Round definitions (consumer's responsibility)
- Claude Code configuration (Anthropic's product)
- Environment variables beyond ANTHROPIC_API_KEY and CLAUDECODE

---

## Principle

Rondo works with zero config. Every setting has a sane default. A config file
adds project-level customization. CLI flags override everything. The resolution
pattern is COALESCE: first non-null wins.

---

## Rules

1. Rondo MUST work out of the box with no config file. All settings have defaults.
2. Project-level config MUST be TOML format (Python 3.12+ has `tomllib` in
   stdlib — zero external dependencies).
3. Config file location: `rondo.toml` in the project root, or path specified
   via `--config` flag.
4. CLI flags MUST override config file values.
5. Config file values MUST override defaults.
6. Resolution order: CLI flag → config file → hardcoded default. First non-null
   wins (COALESCE pattern).
7. Unknown config keys MUST be ignored with a warning (forward compatibility).
8. Invalid config values MUST raise a clear error at startup, not at dispatch time.
9. Config MUST be loaded once at startup and be immutable for the session.
10. Config MUST be representable as a single Python dataclass for type safety.

---

## COALESCE Resolution

The core configuration pattern. Same concept as SQL COALESCE: first non-null wins.

```
COALESCE(cli_flag, config_file, default)

Example — resolving the model:
  CLI: --model opus        → "opus"       (wins if provided)
  Config: default_model    → "sonnet"     (wins if CLI not provided)
  Default:                 → "sonnet"     (fallback)
```

### Resolution Walkthrough

```python
def resolve(cli_value, config_value, default_value):
    """COALESCE: first non-None wins."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value
```

### Per-Task COALESCE (Model Routing)

Tasks can hint a model. This extends the chain:

```
COALESCE(cli_flag, task_hint, config_file, default)

Example:
  CLI: --model opus        → "opus"       (global override — wins)
  Task: model="haiku"      → "haiku"      (task-specific — wins if no CLI)
  Config: default_model    → "sonnet"     (project default)
  Default:                 → "sonnet"     (hardcoded fallback)
```

---

## Configurable Settings

| Setting | CLI Flag | Config Key | Type | Default | Validation |
|---------|----------|-----------|------|---------|------------|
| Auth mode | `--auth` | `auth` | str | `"max"` | Must be "max" or "api" |
| Model | `--model` | `default_model` | str | `"sonnet"` | Must be valid model name |
| Workers | `--workers` | `workers` | int | `4` | 1-32 |
| Throttle | `--throttle` | `throttle_sec` | float | `2.0` | 0.0-60.0 |
| Task timeout | `--timeout` | `task_timeout_sec` | int | `300` | 10-3600 |
| Results dir | `--results-dir` | `results_dir` | str | `"reports/rondo-results"` | Valid path |
| Report dir | `--report-dir` | `report_dir` | str | `"reports"` | Valid path |
| Claude binary | — | `claude_binary` | str | `"claude"` | Executable on PATH |
| Dry run | `--dry-run` | — | bool | `false` | CLI only (not in config) |
| Verbose | `--verbose` | `verbose` | bool | `false` | — |
| Output format | `--output-format` | `output_format` | str | `"stream-json"` | "text", "json", "stream-json" |
| Effort | `--effort` | `effort` | str | `"high"` | "low", "medium", "high", "max" |
| Watchdog timeout | `--watchdog-timeout` | `watchdog_timeout_sec` | int | `60` | 10-600 |
| Rate limit backoff | `--backoff` | `rate_limit_backoff_sec` | int | `60` | 10-600 |
| On overage | `--on-overage` | `on_overage` | str | `"continue"` | "continue", "pause", "stop" |
| Permission mode | `--permission-mode` | `permission_mode` | str | `"auto"` | "default", "acceptEdits", "plan", "auto", "bypassPermissions" |
| Worktree isolation | `--worktree` | `worktree_isolation` | bool | `false` | — |

---

## Config Dataclass

```python
@dataclass(frozen=True)
class RondoConfig:
    """Immutable configuration — loaded once at startup."""

    # -- dispatch
    auth: str = "max"
    default_model: str = "sonnet"
    effort: str = "high"
    output_format: str = "stream-json"
    claude_binary: str = "claude"
    task_timeout_sec: int = 300

    # -- parallel
    workers: int = 4
    throttle_sec: float = 2.0

    # -- permissions
    permission_mode: str = "auto"

    # -- self-healing (REQ-101 watchdog + usage gating)
    watchdog_timeout_sec: int = 60
    rate_limit_backoff_sec: int = 60
    on_overage: str = "continue"
    worktree_isolation: bool = False

    # -- paths
    results_dir: str = "reports/rondo-results"
    report_dir: str = "reports"

    # -- flags
    dry_run: bool = False
    verbose: bool = False
```

**Why frozen:** Config is immutable after creation. No mid-session changes.
Thread-safe by design (STD-110 concurrency safety).

**Note on `dry_run`:** CLI-only (not settable in TOML config file). The dataclass
holds it because COALESCE resolves CLI → config → default into one object. The TOML
parser simply never populates it.

---

## Config File Format

```toml
# -- Rondo project configuration
# -- Location: rondo.toml (project root) or --config path

# -- Dispatch settings
auth = "max"                    # "max" (subscription) or "api" (pay-per-token)
default_model = "sonnet"        # opus, sonnet, haiku, opus[1m], sonnet[1m]
effort = "high"                 # low, medium, high, max
output_format = "stream-json"   # text, json, stream-json (stream-json recommended)
claude_binary = "claude"        # path to claude binary (usually just "claude")
task_timeout_sec = 300          # seconds before killing a hung task
permission_mode = "auto"        # default, acceptEdits, plan, auto, bypassPermissions

# -- Parallel execution
workers = 4                     # max concurrent task dispatches
throttle_sec = 2.0              # seconds between task launches

# -- Self-healing (REQ-101 watchdog + usage gating)
watchdog_timeout_sec = 60       # seconds of no output before watchdog kills task
rate_limit_backoff_sec = 60     # seconds to wait after rate limit hit
on_overage = "continue"         # continue, pause, stop — action when isUsingOverage=true
worktree_isolation = false      # optional git worktree per worker for parallel safety

# -- Output paths
results_dir = "reports/rondo-results"   # task result JSON files
report_dir = "reports"                  # morning report output
```

---

## Config Discovery

How Rondo finds the config file:

```
1. If --config flag provided → use that path exactly
2. Else: look for rondo.toml in current working directory
3. If not found → use all defaults (zero-config mode)
```

**No walk-up search.** Unlike some tools that search parent directories,
Rondo only looks in the CWD or the explicit path. This keeps behavior
predictable and avoids surprises in CI/CD environments.

---

## Validation

Config is validated at load time. Errors are clear and immediate:

```python
def validate_config(config: RondoConfig) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []

    if config.auth not in ("max", "api"):
        errors.append(f"auth must be 'max' or 'api', got '{config.auth}'")

    if config.workers < 1 or config.workers > 32:
        errors.append(f"workers must be 1-32, got {config.workers}")

    if config.throttle_sec < 0 or config.throttle_sec > 60:
        errors.append(f"throttle_sec must be 0-60, got {config.throttle_sec}")

    if config.task_timeout_sec < 10 or config.task_timeout_sec > 3600:
        errors.append(f"task_timeout_sec must be 10-3600, got {config.task_timeout_sec}")

    if config.output_format not in ("text", "json", "stream-json"):
        errors.append(f"output_format must be text/json/stream-json, got '{config.output_format}'")

    if config.effort not in ("low", "medium", "high", "max"):
        errors.append(f"effort must be low/medium/high/max, got '{config.effort}'")

    if config.watchdog_timeout_sec < 10 or config.watchdog_timeout_sec > 600:
        errors.append(f"watchdog_timeout_sec must be 10-600, got {config.watchdog_timeout_sec}")

    if config.rate_limit_backoff_sec < 10 or config.rate_limit_backoff_sec > 600:
        errors.append(f"rate_limit_backoff_sec must be 10-600, got {config.rate_limit_backoff_sec}")

    if config.on_overage not in ("continue", "pause", "stop"):
        errors.append(f"on_overage must be continue/pause/stop, got '{config.on_overage}'")

    valid_models = ("opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]")
    if config.default_model not in valid_models:
        errors.append(f"default_model must be one of {valid_models}, got '{config.default_model}'")

    valid_perms = ("default", "acceptEdits", "plan", "auto", "bypassPermissions")
    if config.permission_mode not in valid_perms:
        errors.append(
            f"permission_mode must be one of {valid_perms}, got '{config.permission_mode}'"
        )

    if not config.claude_binary:
        errors.append("claude_binary must not be empty")

    if not config.results_dir:
        errors.append("results_dir must not be empty")

    if not config.report_dir:
        errors.append("report_dir must not be empty")

    # -- Cross-field relationships
    if config.watchdog_timeout_sec >= config.task_timeout_sec:
        errors.append(
            f"watchdog_timeout_sec ({config.watchdog_timeout_sec}) must be less than "
            f"task_timeout_sec ({config.task_timeout_sec})"
        )

    return errors
```

**Cross-field relationships:** Some settings have dependencies on each other.
The watchdog detects silence *within* a running task, so it must always fire
before the task's total timeout. If `watchdog_timeout_sec >= task_timeout_sec`,
the watchdog is useless — the task would be killed first.

**Startup behavior:** If validation returns errors, Rondo prints them all and
exits with code 1. No partial config — either everything is valid or nothing runs.

---

## Config Loading Flow

```
Startup
    │
    ├── Parse CLI flags
    │
    ├── Find config file (--config or CWD/rondo.toml)
    │       │
    │       ├── Found → parse TOML with tomllib
    │       │
    │       └── Not found → empty dict (all defaults)
    │
    ├── COALESCE each setting: CLI → config → default
    │
    ├── Create frozen RondoConfig dataclass
    │
    ├── Validate all fields
    │       │
    │       ├── Valid → proceed
    │       │
    │       └── Invalid → print errors, exit 1
    │
    └── Config is immutable for the rest of the session
```

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

REQUIRED — fill before build.

---

## 4. Architecture / Design

REQUIRED — fill before build.

---

## 6. Data Boundary

REQUIRED — fill before build.

---

## 7. MCP / API Interface

— if applicable.

---

## 8. States & Modes

— if applicable.

---

## 11. Quality Attributes

— if applicable.

---

## 13. Integration Points

REQUIRED — fill before build.

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-012 | Requirement readiness tracking |
| CORE-STD-013 | TrackerData — universal tracking |
| CORE-IFS-005 | MCP standard — AI tool access |

---

## 15. Self-Correction

— if applicable.

---

## 16. Assumptions

REQUIRED — fill before build.

---

## 17. Success Criteria

REQUIRED — fill before build.

---

## 18. Build Notes / Estimate

— filled during build.

---

## 19. Test Categories

— filled during build.

---

## 20. Failure Modes

— if applicable.

---

## 21. Dependencies + Used By

REQUIRED — fill before build.

---

## 22. Decisions

REQUIRED — fill before build.

---

## 23. Open Questions

— if applicable.

---

## 24. Glossary

— if applicable.

---

## 25. Risk / Criticality

— if applicable.

---

## 26. External Scan

— if applicable.

---

## 27. Security Considerations

— if applicable.

---

## 28. Performance / Resource

— if applicable.

---

## 29. Approval Record

— filled after build.

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

— filled after build.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — 6 rules, settings table, TOML example |
| 0.2 | 2026-03-14 | Beefed up: COALESCE walkthrough, dataclass, validation, discovery, flow diagram, output_format + effort settings |
| 0.3 | 2026-03-14 | Deep review fixes: added 4 missing fields to RondoConfig (watchdog_timeout_sec, rate_limit_backoff_sec, on_overage, worktree_isolation), completed validate_config(), added dry_run note, updated TOML example |
| 0.4 | 2026-03-14 | Deep review v2: added 4 missing validations to validate_config() (default_model, claude_binary, results_dir, report_dir) |
| 0.5 | 2026-03-14 | Added permission_mode setting — controls Claude Code's `--permission-mode` flag for tool access in non-interactive dispatch |
| 0.6 | 2026-03-14 | Added cross-field relationship validation: watchdog_timeout_sec must be < task_timeout_sec |
