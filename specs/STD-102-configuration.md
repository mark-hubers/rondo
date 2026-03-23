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
**Matches:** CORE-STD-003, STD-102 (Caliber)

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

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Configuration scattered across hardcoded values, environment variables, and ad-hoc flags creates unpredictable behavior. When Rondo dispatches at 3 AM with different config than expected, the results are wrong and the debug trail is opaque. A single, documented resolution chain (COALESCE) eliminates "it works on my machine" failures.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Configuration File
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL operational config lives in `rondo.toml` at the project root — never hardcoded in source | MUST |
| 002 | System SHALL config hierarchy follows COALESCE (first non-null wins): CLI flags > environment vars > `rondo.toml` > built-in defaults | MUST |
| 003 | System SHALL config file is human-editable TOML, well-commented. No binary formats, no YAML, no JSON | MUST |
| 004 | System SHALL config validation runs at startup — fail fast with a clear error message listing all invalid keys, not one at a time | MUST |
| 005 | System SHALL invalid config = hard stop. Rondo refuses to run rather than guess what you meant | MUST |
| 006 | System SHALL every config key has a documented default. `rondo config show` (or `--show-config` flag) prints the full resolved config with the source of each value (cli/env/file/default) | MUST |
| 007 | System SHALL boolean config uses explicit `true`/`false` — no implicit truthy/falsy | MUST |

### Config Keys
| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | System SHALL config file structure: | MUST |

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
| ID | Requirement | Priority |
|----|-------------|----------|
| 009 | API keys and credentials MUST come from environment variables only — never in `rondo.toml`, never in version control | MUST |
| 010 | System SHALL `ANTHROPIC_API_KEY` is the standard env var for API-mode auth. When `auth = "max"`, Rondo strips this from the child process environment | MUST |
| 011 | System SHALL no config value is logged if it could be a secret. Config show/dump masks env-sourced values: `ANTHROPIC_API_KEY = ****` | MUST |

### Path Resolution
| ID | Requirement | Priority |
|----|-------------|----------|
| 012 | System SHALL all paths in config are relative to the project root (where `rondo.toml` lives). Never absolute paths in config files | MUST |
| 013 | System SHALL canonical path resolution via `config.py` — all path construction goes through `RondoConfig`. No `os.path.join` scattered in source | MUST |
| 014 | System SHALL missing directories are created on first use — Rondo never fails because a results directory does not exist yet | MUST |
| 015 | System SHALL path resolution is deterministic: same root + same config = same paths on any machine | MUST |

### Round Definitions (Code, Not Config)
| ID | Requirement | Priority |
|----|-------------|----------|
| 016 | System SHALL round definitions are Python code, not TOML. They need logic (gates, closures, conditionals) that config formats cannot express | MUST |
| 017 | A round definition file MUST contain a `build_round()` function that returns a `Round` object | MUST |
| 018 | Round definitions MUST import only from `rondo.engine` (Round, Task, Gate). They MUST NOT import Rondo internals (dispatch, runner, config) | MUST |
| 019 | System SHALL round definitions MAY accept parameters to customize their tasks. The CLI passes parameters via `--param key=value` | SHOULD |
| 020 | System SHALL model selection per task follows COALESCE: CLI `--model` flag > `task.model` hint > `config.default_model` > `"sonnet"` hardcoded fallback | MUST |

### Auth Mode
| ID | Requirement | Priority |
|----|-------------|----------|
| 021 | Auth mode MUST be selectable via CLI flag (`--auth max|api`). Default: `max` | MUST |
| 022 | System SHALL when `auth = "max"`: strip `ANTHROPIC_API_KEY` from child environment. Claude uses the subscription plan ($0 marginal cost) | MUST |
| 023 | System SHALL when `auth = "api"`: preserve `ANTHROPIC_API_KEY` in child environment. Claude uses pay-per-token billing | MUST |
| 024 | System SHALL auth mode is logged on every dispatch at INFO level: `"Dispatching task 'X' (model=sonnet, auth=max)"` | MUST |

### Config Validation
| ID | Requirement | Priority |
|----|-------------|----------|
| 025 | System SHALL unknown keys in `rondo.toml` are warnings, not errors — forward-compatible with newer Rondo versions | MUST |
| 026 | System SHALL type mismatches are hard errors: string where integer expected = fail | MUST |
| 027 | System SHALL range validation: `task_timeout_sec` must be > 0, `workers` must be >= 1, `throttle_sec` must be >= 0 | MUST |
| 028 | System SHALL `rondo config validate` checks the config file without running anything — exit 0 = valid, exit 1 = errors printed to stderr | MUST |

### Environment Variable Overrides
| ID | Requirement | Priority |
|----|-------------|----------|
| 029 | System SHALL every config key has a corresponding env var: `RONDO_DISPATCH_MODEL`, `RONDO_PATHS_RESULTS_DIR`, `RONDO_PARALLEL_WORKERS` | MUST |
| 030 | System SHALL naming convention: `RONDO_` prefix + section + key, all uppercase, dots become underscores | MUST |
| 031 | System SHALL env vars override config file values — useful for CI/CD or overnight automation where config files may differ | SHOULD |

---
## 4. Architecture / Design

Configuration resolves through a 4-layer COALESCE chain: CLI flags (highest priority) > environment variables > `rondo.toml` file > built-in defaults (lowest). `RondoConfig` is the single Python object that holds the resolved configuration. All code reads from `RondoConfig`, never directly from env vars or TOML.

---

## 5. Data Model

`RondoConfig` is a Python dataclass with sections matching `rondo.toml` structure: `dispatch` (model, auth, timeout), `paths` (results_dir, rounds_dir), `parallel` (workers, throttle), `overnight` (enabled, phases_dir). Each field carries a `_source` annotation for debugging.

---

## 6. Data Boundary

Configuration is resolved at startup and frozen. No runtime config changes. The resolved `RondoConfig` is passed to the runner, which passes relevant fields to dispatch. Config never crosses the spool boundary — result files do not contain config values (except model and auth_mode in DispatchUsage).

---

## 7. MCP / API Interface

No MCP interface for configuration. Config is local to the Rondo process. CORE-IFS-005 MCP tools do not expose or modify Rondo configuration. Future: `rondo_query_routing` (Rondo-IFS-100) may expose the resolved model routing table read-only.

---

## 8. States & Modes

Two auth modes: `max` (subscription, $0 marginal) and `api` (pay-per-token). One execution mode per config: sequential (`workers=1`) or parallel (`workers>1`). Overnight mode (`overnight.enabled=true`) activates the scheduler. Modes are set at startup, not changed during execution.

---

## 9. Configuration

This IS the configuration spec. See section 3 for all config keys, section 10 for COALESCE resolution order, and the `rondo.toml` example in section 3 rule 8 for the complete file format.

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

## 11. Quality Attributes

- **Predictability:** Same config + same input = same behavior, every time.
- **Transparency:** `rondo config show` prints every resolved value with its source.
- **Safety:** Invalid config = hard stop. No guessing, no partial runs.

---

## 12. Shared Patterns

- **COALESCE:** CLI > env > file > default. Same pattern used in STD-105 model selection and across ACE2.
- **Zero-config operation:** Works out of the box with sensible defaults. Shared design principle with Caliber.
- **Fail-fast validation:** All config checked at startup, not discovered mid-run. Shared with STD-101 error handling.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo config → Dispatch | model, auth, timeout | COALESCE resolution |
| Rondo config → Runner | workers, throttle | Parallel execution limits |
| Rondo config → OB | Config source annotations in logs | STD-101 logging |
| Rondo config → CORE-STD-012 | Config-dependent readiness states | Dependency tracking |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-003 | Parent configuration standard — Rondo adapts COALESCE, validation, env overrides |
| CORE-STD-012 | Requirement readiness — config validity is a prerequisite for dispatch readiness |
| CORE-STD-013 | TrackerData — config changes are trackable events |
| CORE-IFS-005 | MCP standard — future config queries via MCP tools |

---

## 15. Self-Correction

Config validation at startup is a form of self-correction: detect bad config before it causes dispatch failures. The `rondo config validate` command enables pre-flight checking. CORE-STD-011 patterns do not apply — config is operator-set, not AI-learned.

---

## 16. Assumptions

1. TOML remains the config format — no migration to YAML or JSON planned.
2. Environment variables are set before Rondo starts — no runtime env changes.
3. `rondo.toml` is in the project root — no search-up-directory-tree logic.
4. All config keys have documented defaults — no required-but-no-default keys.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | `rondo run` works with no `rondo.toml` present | Zero-config test |
| 2 | `rondo config show` prints source annotation for every value | Show test |
| 3 | Invalid config type → hard error at startup with all invalid keys listed | Validation test |

---

## 18. Build Notes / Estimate

TOML parser: use `tomllib` (stdlib Python 3.11+). Config dataclass: 2 hours. COALESCE resolver: 2 hours. Validation: 2 hours. `config show` and `config validate` CLI: 1 hour. Total: ~7 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| COALESCE tests | CLI > env > file > default resolution order |
| Validation tests | Type mismatches, range violations, unknown keys |
| Zero-config tests | Default values produce valid config |
| Env override tests | Every config key overridable via `RONDO_` env var |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Missing `rondo.toml` | Defaults used — works fine | Zero-config design |
| Invalid TOML syntax | Hard error at startup | TOML parser error messages |
| Env var type mismatch | Hard error at startup | Type coercion with validation |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-003 | Parent configuration standard |
| Depends on | CORE-STD-012 | Config readiness prerequisites |
| Used by | STD-105 | Model selection reads from config |
| Used by | STD-104 | Path resolution reads from config |
| Used by | REQ-100 | Core dispatch uses resolved config |
| Used by | REQ-101 | Automation reads parallel/overnight config |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: TOML not YAML | TOML is simpler, less ambiguous, stdlib support in Python 3.11+ | 2026-03-18 |
| D2: Round defs in Python, not TOML | Rounds need logic (gates, conditionals) that TOML cannot express | 2026-03-18 |
| D3: Unknown keys = warning, not error | Forward compatibility with newer Rondo versions | 2026-03-18 |

---

## 23. Open Questions

None currently. Config format and COALESCE chain are stable.

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **COALESCE** | First non-null value in a precedence chain wins |
| **Auth mode** | `max` (subscription) or `api` (pay-per-token) — how Claude is billed |
| **Zero-config** | Rondo works with all defaults, no config file required |

---

## 25. Risk / Criticality

**MEDIUM.** Bad config causes dispatch failures, but fail-fast validation catches most issues at startup. The main risk is env var misconfiguration in CI/CD or overnight automation where the operator is not watching.

---

## 26. External Scan

TOML is a well-established config format (Cargo, pyproject.toml). COALESCE is a standard pattern (SQL, Terraform). No novel approaches — proven patterns adapted for dispatch context.

---

## 27. Security Considerations

API keys via env vars only — never in `rondo.toml`. Config show/dump masks sensitive values. File permissions on `rondo.toml`: 0644 (readable, but no secrets inside). See STD-107 rules 1, 9, 16 for full security requirements.

---

## 28. Performance / Resource

Config resolution happens once at startup (~1ms for TOML parse + COALESCE). No runtime config overhead. Config is frozen after startup — no re-reading, no file watching, no performance impact during dispatch.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

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

CORE-STD-012 (Requirement Readiness) uses config validity as a prerequisite — a requirement cannot be READY if its config dependencies are invalid. CORE-STD-013 (TrackerData) records config change events for audit. CORE-IFS-005 MCP tools may expose read-only config queries in future versions.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Configuration standards | THEORY | Specced for Rondo config format | Phase 1 build |
| Configuration hierarchy | THEORY | Specced for defaults < project < user | Phase 1 build |
| Runtime configuration | WORKING | Environment variables used currently | After config changes |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-003 topics (config, paths, validation, env overrides) adapted for Rondo. 31 requirements. TOML for dispatch settings, Python for round definitions. COALESCE chain, zero-config operation, auth switching. No schema versioning section (Rondo has no DB). |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval record (Mark, Session 84). |
