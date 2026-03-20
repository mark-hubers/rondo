# STD-102: Configuration

*How Rondo handles configuration, paths, and round definitions. Config-driven dispatch, code-driven rounds.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-003, Caliber-STD-102

---

## 1. Purpose & Scope

Defines how Rondo resolves configuration: TOML for dispatch settings, Python dataclasses for round definitions, COALESCE for precedence, and environment variables for secrets. Two configuration domains in one spec: operational config (how to dispatch) and structural config (what to dispatch).

**IN scope:**
- TOML config file format and keys
- COALESCE precedence chain (CLI > env > config > defaults)
- Path resolution and directory layout
- Round definitions as Python code (not config)
- Auth mode and model selection config
- Environment variable overrides

**OUT of scope:**
- Round execution logic (REQ-100: Core)
- Parallel execution config (REQ-101: Automation)
- Data format rules (STD-100: Data Standards)

---

## 3. Requirements

### Configuration File

1. Operational config lives in `rondo.toml` at the project root — never hardcoded in source.
2. Config hierarchy follows COALESCE (first non-null wins): CLI flags > environment vars > `rondo.toml` > built-in defaults.
3. Config file is human-editable TOML, well-commented. No binary formats, no YAML, no JSON.
4. Config validation runs at startup — fail fast with a clear error message listing all invalid keys, not one at a time.
5. Invalid config = hard stop. Rondo refuses to run rather than guess what you meant.
6. Every config key has a documented default. `rondo config show` (or `--show-config` flag) prints the full resolved config with the source of each value (cli/env/file/default).
7. Boolean config uses explicit `true`/`false` — no implicit truthy/falsy.

### Config Keys

8. Config file structure:

```toml
# rondo.toml — Rondo project configuration

[dispatch]
claude_binary = "claude"           # path to claude CLI
default_model = "sonnet"           # fallback model (COALESCE chain)
auth = "max"                       # "max" (subscription) or "api" (pay-per-token)
permission_mode = "auto"           # Claude Code permission mode
task_timeout_sec = 300             # per-task subprocess timeout
output_format = "stream-json"     # always stream-json (do not change)

[paths]
results_dir = "reports/rondo-results"   # spool directory for result files
rounds_dir = "rounds/"                  # default location for round definition files

[parallel]
workers = 1                        # 1 = sequential, >1 = parallel (REQ-101)
throttle_sec = 2.0                 # delay between dispatches (rate limit protection)

[overnight]
enabled = false                    # overnight scheduler (REQ-101)
phases_dir = "rounds/overnight/"   # phase definition files
```

### Sensitive Values

9. API keys and credentials MUST come from environment variables only — never in `rondo.toml`, never in version control.
10. `ANTHROPIC_API_KEY` is the standard env var for API-mode auth. When `auth = "max"`, Rondo strips this from the child process environment.
11. No config value is logged if it could be a secret. Config show/dump masks env-sourced values: `ANTHROPIC_API_KEY = ****`.

### Path Resolution

12. All paths in config are relative to the project root (where `rondo.toml` lives). Never absolute paths in config files.
13. Canonical path resolution via `config.py` — all path construction goes through `RondoConfig`. No `os.path.join` scattered in source.
14. Missing directories are created on first use — Rondo never fails because a results directory does not exist yet.
15. Path resolution is deterministic: same root + same config = same paths on any machine.

### Round Definitions (Code, Not Config)

16. Round definitions are Python code, not TOML. They need logic (gates, closures, conditionals) that config formats cannot express.
17. A round definition file MUST contain a `build_round()` function that returns a `Round` object.
18. Round definitions MUST import only from `rondo.engine` (Round, Task, Gate). They MUST NOT import Rondo internals (dispatch, runner, config).
19. Round definitions MAY accept parameters to customize their tasks. The CLI passes parameters via `--param key=value`.
20. Model selection per task follows COALESCE: CLI `--model` flag > `task.model` hint > `config.default_model` > `"sonnet"` hardcoded fallback.

### Auth Mode

21. Auth mode MUST be selectable via CLI flag (`--auth max|api`). Default: `max`.
22. When `auth = "max"`: strip `ANTHROPIC_API_KEY` from child environment. Claude uses the subscription plan ($0 marginal cost).
23. When `auth = "api"`: preserve `ANTHROPIC_API_KEY` in child environment. Claude uses pay-per-token billing.
24. Auth mode is logged on every dispatch at INFO level: `"Dispatching task 'X' (model=sonnet, auth=max)"`.

### Config Validation

25. Unknown keys in `rondo.toml` are warnings, not errors — forward-compatible with newer Rondo versions.
26. Type mismatches are hard errors: string where integer expected = fail.
27. Range validation: `task_timeout_sec` must be > 0, `workers` must be >= 1, `throttle_sec` must be >= 0.
28. `rondo config validate` checks the config file without running anything — exit 0 = valid, exit 1 = errors printed to stderr.

### Environment Variable Overrides

29. Every config key has a corresponding env var: `RONDO_DISPATCH_MODEL`, `RONDO_PATHS_RESULTS_DIR`, `RONDO_PARALLEL_WORKERS`.
30. Naming convention: `RONDO_` prefix + section + key, all uppercase, dots become underscores.
31. Env vars override config file values — useful for CI/CD or overnight automation where config files may differ.

---

## 10. Rules & Constraints

### COALESCE Resolution Order

```
effective_value = CLI_flag  or  ENV_var  or  rondo.toml  or  built_in_default
                  ────────      ───────      ──────────      ────────────────
                  operator      automation   project          hardcoded
```

This applies to: model, auth, workers, timeout, results_dir, and all other config keys.

### Config Source Annotation

When displaying resolved config, annotate each value's source:

```
dispatch.default_model = "opus"       [cli: --model opus]
dispatch.auth          = "max"        [file: rondo.toml]
dispatch.task_timeout  = 300          [default]
paths.results_dir      = "/tmp/out"   [env: RONDO_PATHS_RESULTS_DIR]
```

### Zero-Config Operation

Rondo MUST work with no `rondo.toml` present. All keys have defaults. The minimum viable invocation is:

```bash
rondo run my_round.py
```

This uses: `auth=max`, `model=sonnet`, `workers=1`, `results_dir=reports/rondo-results`, `timeout=300s`.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-003 topics (config, paths, validation, env overrides) adapted for Rondo. 31 requirements. TOML for dispatch settings, Python for round definitions. COALESCE chain, zero-config operation, auth switching. No schema versioning section (Rondo has no DB). |
