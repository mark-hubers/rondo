# VER-100: Rondo Verification Plan

*Every requirement traced to its proof. Every test mapped to what it proves.*

**Product name:** Rondo — AI Task Orchestration Engine
**Created:** 2026-03-13 | **Updated:** 2026-03-16 | **Status:** ACTIVE
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Architect:** Mark G. Hubers — HubersTech
**AI Assistant:** Claude (Opus 4.6) — production code built to Mark's specifications
**AI Reviewer:** Gemini (Google AI) — Cold review, found cross-field validation gap

---

## 1. Verification Methods

| Method | Code | When Used |
|--------|------|-----------|
| **Test** | T | Automated test in pytest suite — deterministic, repeatable |
| **Spike** | S | Live prototype proved concept before specs were written |
| **Demonstration** | D | Live run shows behavior (integration, overnight, CLI) |
| **Inspection** | I | Human review of code, output, or documentation |
| **Analysis** | A | Static analysis, AST scan, or code review |
| **Cold Witness** | CW | Independent AI reviewer (Gemini) validates blind |

**Priority:** Test > Spike > Demo > Analysis > Inspection. Automated proof always preferred.

---

## 2. Spec-to-Test Traceability Matrix

### REQ-100: Core — Engine + Dispatch (49 requirements)

#### Engine — Data Model (Reqs 1-7)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 1 | Round contains name, gates, tasks | T | `test_engine.py::test_round_structure` |
| 2 | Task has name, mode, status | T | `test_engine.py::test_task_fields` |
| 3 | Interactive task: Do/Read/Done | T | `test_engine.py::test_three_field_contract` |
| 4 | Auto task: callable returns (bool, str) | T | `test_engine.py::test_auto_task_run` |
| 5 | Gate: name, check_fn, blocking | T | `test_engine.py::test_gate_check` |
| 6 | Pre-gates block on failure | T | `test_engine.py::test_blocking_pregate` |
| 7 | Post-gates after all tasks | T | `test_engine.py::test_postgate_timing` |

#### Engine — State Machine (Reqs 8-11)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 8 | State: pending/running/done/blocked/partial/error/skipped | T | `test_engine.py::test_state_transitions` |
| 9 | Round complete when all tasks terminal | T | `test_engine.py::test_round_completion` |
| 10 | Serializable to JSON | T | `test_engine.py::test_serialize_round` |
| 11 | Resumable from JSON | T | `test_engine.py::test_resume_round` |

#### Dispatch — Subprocess (Reqs 12-16)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 12 | Invokes claude -p | T | `test_dispatch.py::test_subprocess_command` |
| 13 | Strips CLAUDECODE env | T | `test_dispatch.py::test_claudecode_stripped` |
| 14 | Captures stdout, stderr, exit code, duration | T | `test_dispatch.py::test_result_capture` |
| 15 | Saves result to JSON file | T | `test_dispatch.py::test_result_saved` |
| 16 | Dry-run shows prompt without invoking | T | `test_dispatch.py::test_dry_run` |

#### Dispatch — Auth (Reqs 17-19)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 17 | auth=max strips ANTHROPIC_API_KEY | T | `test_dispatch.py::test_auth_max_strips_key` |
| 18 | auth=api keeps ANTHROPIC_API_KEY | T | `test_dispatch.py::test_auth_api_keeps_key` |
| 19 | --auth flag selectable, default max | T | `test_cli.py::test_auth_flag` |

#### Dispatch — Model Routing (Reqs 20-23)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 20 | Passes --model to subprocess | T | `test_dispatch.py::test_model_flag` |
| 21 | COALESCE: CLI > task > default | T | `test_dispatch.py::test_model_coalesce` |
| 22 | Default is sonnet | T | `test_dispatch.py::test_model_default` |
| 23 | Task can hint a model | T | `test_engine.py::test_task_model_hint` |

#### Dispatch — Result Contract (Reqs 24-28)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 24 | Prompt requests JSON output | I | Review prompt template |
| 25 | Valid JSON parsed and stored | T | `test_dispatch.py::test_json_parsing` |
| 26 | Malformed JSON -> status "partial" | T | `test_dispatch.py::test_malformed_json` |
| 27 | Exit code != 0 -> status "error" | T | `test_dispatch.py::test_error_exit_code` |
| 28 | Result includes metadata fields | T | `test_dispatch.py::test_result_metadata` |

#### Round Definitions (Reqs 29-33)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 29 | Function returns Round object | T | `test_engine.py::test_round_builder` |
| 30 | Self-contained | A | Code review: no dispatch imports |
| 31 | Accepts parameters | T | `test_engine.py::test_parameterized_round` |
| 32 | Only imports engine module | A | Import check via AST or grep |
| 33 | Under 50 lines | I | `wc -l` on round definition files |

#### Package Structure and CLI (Reqs 34-41)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 34 | Importable Python package | T | `test_engine.py::test_public_imports` |
| 35 | __init__.py exports all public types | T | `test_engine.py::test_init_exports` |
| 36 | CLI entry point `rondo` command | T | `test_cli.py::test_cli_entrypoint` |
| 37 | Subcommands: run, overnight, report, dry-run | T | `test_cli.py::test_subcommands` |
| 38 | `run` accepts path to round definition file | T | `test_cli.py::test_run_with_file` |
| 39 | Dynamic import of round definition | T | `test_cli.py::test_dynamic_import` |
| 40 | Auto-detect sequential vs parallel | T | `test_cli.py::test_auto_runner_selection` |
| 41 | All STD-109 CLI flags on `run` subcommand | T | `test_cli.py::test_cli_flags` |

#### Living Example Rounds (Reqs 42-44)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 42 | Example rounds have build_round() function | T | `test_examples.py::test_example_build_round` |
| 43 | Examples used as test fixtures | T | `test_examples.py::test_examples_as_fixtures` |
| 44 | 3+ examples ship (minimal, gated, multi-task) | I | Count files in `examples/` |

#### Public API Contract (Reqs 45-46)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 45 | run_round() accepts Round + optional config, returns RoundResult | T | `test_engine.py::test_run_round_contract` |
| 46 | RoundResult.status calculated from task statuses | T | `test_engine.py::test_round_result_status_calculation` |

#### Dispatch — Permission Mode (Reqs 47-49)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 47 | --permission-mode passed to subprocess | T | `test_dispatch.py::test_permission_mode_passed` |
| 48 | COALESCE: CLI > config > default "auto" | T | `test_config.py::test_permission_mode_coalesce` |
| 49 | Valid modes: default/acceptEdits/plan/auto/bypassPermissions | T | `test_config.py::test_all_valid_permission_modes` |

---

### REQ-101: Automation — Parallel + Overnight + Report (41 requirements)

#### Parallel Execution (Reqs 1-9)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 1 | Uses ThreadPoolExecutor | A | Code review |
| 2 | Configurable workers, default 4 | T | `test_parallel.py::test_worker_config` |
| 3 | Configurable throttle, default 2s | T | `test_parallel.py::test_throttle` |
| 4 | Results collected as completed | T | `test_parallel.py::test_result_order` |
| 5 | Conflict detection flags shared files | T | `test_parallel.py::test_conflict_detection` |
| 6 | Conflicts listed in summary | T | `test_parallel.py::test_conflict_in_summary` |
| 7 | Reports done/error/wall/task/speedup | T | `test_parallel.py::test_summary_stats` |
| 8 | Single failure doesn't crash others | T | `test_parallel.py::test_task_isolation` |
| 9 | Same JSON format as sequential | T | `test_parallel.py::test_result_format` |

#### Overnight Scheduler (Reqs 10-18)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 10 | Accepts list of round definitions | T | `test_overnight.py::test_phase_list` |
| 11 | Phases sequential, tasks may be parallel | D | Run overnight with multi-task phase |
| 12 | Phase failure doesn't block next | T | `test_overnight.py::test_phase_isolation` |
| 13 | Configurable modes | T | `test_overnight.py::test_mode_config` |
| 14 | 3+ modes supported | T | `test_overnight.py::test_three_modes` |
| 15 | Modes configurable, not hardcoded | A | No OB/ACE round names in code |
| 16 | No interactive input required | D | Run from cron-like invocation |
| 17 | Logs start/end events | T | `test_overnight.py::test_event_logging` |
| 18 | Rolling 100-entry log | T | `test_overnight.py::test_rolling_log` |

#### Self-Healing Watchdog (Reqs 19-23)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 19 | Monitors dispatch for hung conditions | T | `test_overnight.py::test_watchdog_detects_hung` |
| 20 | Kills no-output dispatch after timeout | T | `test_overnight.py::test_watchdog_kills_hung` |
| 21 | Continues after watchdog kill | T | `test_overnight.py::test_watchdog_continues` |
| 22 | Rate limit backoff pause | T | `test_overnight.py::test_rate_limit_backoff` |
| 23 | Watchdog logs every intervention | T | `test_overnight.py::test_watchdog_logging` |

#### Usage Threshold Gating (Reqs 24-28)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 24 | Checks rate_limit_event before each phase | T | `test_overnight.py::test_usage_check_before_phase` |
| 25 | isUsingOverage triggers configurable action | T | `test_overnight.py::test_overage_action` |
| 26 | Blocked status pauses until reset | T | `test_overnight.py::test_blocked_pause` |
| 27 | on_overage configurable (continue/pause/stop) | T | `test_overnight.py::test_overage_config` |
| 28 | Usage decisions logged to event log | T | `test_overnight.py::test_usage_decision_logging` |

#### Morning Report (Reqs 29-36)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 29 | Aggregates all phases | T | `test_report.py::test_aggregation` |
| 30 | Grouped by round type | I | Review report output |
| 31 | Shows done/failed/duration per round | T | `test_report.py::test_round_stats` |
| 32 | Health indicators | T | `test_report.py::test_health_colors` |
| 33 | Action items from failures | T | `test_report.py::test_action_items` |
| 34 | Saves to dated file | T | `test_report.py::test_dated_filename` |
| 35 | Includes totals and timestamp | T | `test_report.py::test_report_totals` |
| 36 | Includes usage summary (cost, tokens, overage, watchdog) | T | `test_report.py::test_usage_summary` |

#### Worktree Isolation (Reqs 37-41)

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 37 | Supports optional git worktree per worker | T | `test_parallel.py::test_worktree_creation` |
| 38 | Each task runs in own worktree, results merged | D | Run parallel with worktree isolation enabled |
| 39 | Worktree opt-in via config or CLI | T | `test_parallel.py::test_worktree_config` |
| 40 | Without worktree, conflict detection is active | T | `test_parallel.py::test_conflict_without_worktree` |
| 41 | Worktrees cleaned up after round | T | `test_parallel.py::test_worktree_cleanup` |

---

### IFS-100: Claude Code CLI Interface (10 requirements)

#### Stream-JSON Metadata Parsing

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 1 | Reads stream-json line by line | T | `test_dispatch.py::test_stream_json_parsing` |
| 2 | Extracts rate_limit_event | T | `test_dispatch.py::test_rate_limit_extraction` |
| 3 | Extracts result event (cost/tokens) | T | `test_dispatch.py::test_result_metadata_extraction` |
| 4 | Extracts system init (model/version) | T | `test_dispatch.py::test_init_event_extraction` |
| 5 | Verifies model matches requested | T | `test_dispatch.py::test_model_verification` |
| 6 | isUsingOverage flag captured | T | `test_dispatch.py::test_overage_flag` |
| 7 | total_cost_usd captured per dispatch | T | `test_dispatch.py::test_cost_capture` |
| 8 | duration_ms captured | T | `test_dispatch.py::test_duration_capture` |
| 9 | Handles missing rate_limit_event | T | `test_dispatch.py::test_missing_rate_limit` |
| 10 | 1M context model variant accepted | T | `test_dispatch.py::test_1m_model_variant` |

---

### STD-108: Error Handling and Resilience (10 rules)

| Rule | Rule (short) | Method | Test/Evidence | Cross-ref |
|------|-------------|--------|--------------|-----------|
| 1 | Every result includes name, status, duration, prompt | T | `test_dispatch.py::test_result_metadata` | REQ-100 req 28 |
| 2 | Subprocess vs task-logic errors distinguishable | T | `test_dispatch.py::test_error_exit_code` | REQ-100 req 27 |
| 3 | Malformed JSON -> status partial | T | `test_dispatch.py::test_malformed_json` | REQ-100 req 26 |
| 4 | Configurable timeout, default 5 min | T | `test_config.py::test_timeout_config` | STD-109 |
| 5 | Kill sequence: SIGTERM -> 5s -> SIGKILL | T | `test_dispatch.py::test_kill_sequence` | — |
| 6 | Single failure doesn't crash framework | T | `test_parallel.py::test_task_isolation` | REQ-101 req 8 |
| 7 | Failed phase doesn't block next | T | `test_overnight.py::test_phase_isolation` | REQ-101 req 12 |
| 8 | No credentials in result files | T | `test_dispatch.py::test_credential_sanitization` | — |
| 9 | All exceptions caught, logged, converted to error results | A | Code review: dispatch wraps in try/except | — |
| 10 | Morning report always generated | T | `test_report.py::test_report_on_all_failures` | — |

---

### STD-109: Configuration (10 rules)

| Rule | Rule (short) | Method | Test/Evidence | Cross-ref |
|------|-------------|--------|--------------|-----------|
| 1 | Works with zero config | T | `test_config.py::test_zero_config` | — |
| 2 | TOML format | T | `test_config.py::test_toml_loading` | — |
| 3 | Config discovery (--config or CWD) | T | `test_config.py::test_config_discovery` | — |
| 4 | CLI overrides config | T | `test_config.py::test_cli_override` | — |
| 5 | Config overrides defaults | T | `test_config.py::test_config_override` | — |
| 6 | COALESCE resolution | T | `test_config.py::test_coalesce` | — |
| 7 | Unknown keys ignored with warning | T | `test_config.py::test_unknown_keys` | — |
| 8 | Invalid values error at startup | T | `test_config.py::test_validation_errors` | — |
| 9 | Config loaded once, immutable | A | RondoConfig is frozen dataclass | — |
| 10 | Config is a dataclass | I | STD-109 code review | — |

---

### STD-110: Concurrency and Safety (15 rules)

| Rule | Rule (short) | Method | Test/Evidence | Cross-ref |
|------|-------------|--------|--------------|-----------|
| C1 | ThreadPoolExecutor for I/O-bound | A | Code review | REQ-101 req 1 |
| C2 | No shared mutable state | A | Each thread creates own TaskResult | — |
| C3 | Throttle between launches | T | `test_parallel.py::test_throttle` | REQ-101 req 3 |
| C4 | Conflict detection | T | `test_parallel.py::test_conflict_detection` | REQ-101 req 5 |
| C5 | Conflict is advisory | T | `test_parallel.py::test_conflict_in_summary` | REQ-101 req 6 |
| C6 | Bounded workers (1-32) | T | `test_config.py::test_validation_errors` | STD-109 |
| C7 | Task thread isolation | T | `test_parallel.py::test_task_isolation` | REQ-101 req 8 |
| S1 | List args, never shell=True | A | Code review: all subprocess calls use list | — |
| S2 | Credential stripping | T | `test_dispatch.py::test_claudecode_stripped` + `test_auth_max_strips_key` | REQ-100 reqs 13, 17 |
| S3 | No credentials in output | T | `test_dispatch.py::test_credential_sanitization` | STD-108 rule 8 |
| S4 | Prompts don't contain secrets | I | Round definition review | — |
| S5 | Restrictive file permissions (0o600) | T | `test_dispatch.py::test_result_file_permissions` | — |
| R1 | Subprocess timeout with SIGTERM-first kill | T | `test_dispatch.py::test_kill_sequence` | STD-108 rule 5 |
| R2 | Bounded result files (1MB) | T | `test_dispatch.py::test_output_truncation` | — |
| R3 | Rolling event log (100 entries) | T | `test_overnight.py::test_rolling_log` | REQ-101 req 18 |

---

### STD-111: Code Quality Gates (18 rules)

| Rule | Rule (short) | Method | Test/Evidence |
|------|-------------|--------|--------------|
| 1 | Ruff lint passes with zero errors | T | `test_conventions.py::TestNoStarImports` + build gate |
| 2 | Ruff format passes | T | Build gate (ruff format --check) |
| 3 | Bandit passes with zero issues | T | Build gate (bandit -r src/) |
| 4 | Coverage >= 90% (fail_under) | T | pytest-cov `fail_under = 90` in pyproject.toml |
| 5 | Cyclomatic complexity <= 15 | T | `test_conventions.py::TestCyclomaticComplexity` |
| 6 | SPDX headers on all files | T | `test_conventions.py::TestSPDXHeaders` |
| 7 | Module docstrings on all source | T | `test_conventions.py::TestModuleDocstrings` |
| 8 | No relative imports | T | `test_conventions.py::TestNoRelativeImports` |
| 9 | No print() in source (use logging) | T | `test_conventions.py::TestNoPrintInSource` |
| 10 | No wildcard imports | T | `test_conventions.py::TestNoWildcardImports` |
| 11 | No bare `dict` annotations | T | `test_conventions.py::TestNoBareDictAnnotation` |
| 12 | orbit-sign signature on all files | T | `test_conventions.py::TestSignaturePresent` |
| 13 | Test files match test_*.py | T | `test_conventions.py::TestTestFileNaming` |
| 14 | Test classes start with Test | T | `test_conventions.py::TestTestClassNaming` |
| 15 | Public functions have docstrings | T | `test_conventions.py::TestPublicFunctionDocstrings` |
| 16 | Public functions have return types | T | `test_conventions.py::TestPublicFunctionTypeAnnotations` |
| 17 | No TODO/FIXME/HACK/XXX markers | T | `test_conventions.py::TestNoTodoFixmeHack` |
| 18 | No mutable default arguments | T | `test_conventions.py::TestNoMutableDefaultArgs` |

---

## 3. Test Index — Test Files to Spec Mapping

Each test file, what it contains, and which specs it proves.

| Test File | Tests | Proves Specs | What It Covers |
|-----------|-------|-------------|----------------|
| `test_engine.py` | 71 | REQ-100 reqs 1-11, 23, 29-31, 34-35, 45-46 | Round/Task/Gate data model, state machine, serialization, resume, public API |
| `test_dispatch.py` | 72 | REQ-100 reqs 12-18, 20-22, 24-28, 47; IFS-100 reqs 1-10; STD-108 rules 1-3, 5, 8; STD-110 S2-S3, S5, R1-R2 | Subprocess invocation, auth, model routing, result parsing, stream-json, credential safety, kill sequence |
| `test_config.py` | 61 | REQ-100 reqs 48-49; STD-109 rules 1-8; STD-110 C6 | TOML loading, COALESCE resolution, CLI override, validation, zero-config, permission modes |
| `test_cli.py` | 64 | REQ-100 reqs 19, 36-41 | CLI entry point, subcommands, flags, dynamic import, auto-runner selection |
| `test_runner.py` | 28 | REQ-100 (runner orchestration) | Sequential runner, gate enforcement, task dispatch coordination |
| `test_parallel.py` | 28 | REQ-101 reqs 1-9, 37-41; STD-110 C3-C5, C7 | ThreadPoolExecutor, throttle, conflict detection, worktree isolation, task isolation |
| `test_overnight.py` | 31 | REQ-101 reqs 10-28; STD-108 rules 6-7; STD-110 R3 | Phase scheduling, watchdog, usage gating, event logging, rolling log |
| `test_report.py` | 20 | REQ-101 reqs 29-36; STD-108 rule 10 | Aggregation, health indicators, action items, dated files, usage summary |
| `test_examples.py` | 25 | REQ-100 reqs 42-44 | Living example rounds, build_round() contract, examples as test fixtures |
| `test_conventions.py` | 18 | STD-111 rules 1-18 | Convention lock classes — SPDX, docstrings, complexity, signing, naming |

**Total: 418 test functions across 10 test files.**

---

## 4. Coverage Summary

### Requirements (REQ + IFS)

| Spec | Total Reqs | Test (T) | Demo (D) | Analysis (A) | Inspection (I) |
|------|-----------|----------|----------|--------------|----------------|
| REQ-100 | 49 | 43 | 0 | 2 | 4 |
| REQ-101 | 41 | 35 | 3 | 2 | 1 |
| IFS-100 | 10 | 10 | 0 | 0 | 0 |
| **Total** | **100** | **88** | **3** | **4** | **5** |

**88% verified by automated test. 100% covered by at least one method.**

### Standards (STD — cross-referenced)

| Spec | Total Rules | Test (T) | Analysis (A) | Inspection (I) | Cross-ref to REQ |
|------|------------|----------|--------------|----------------|-----------------|
| STD-108 | 10 | 8 | 1 | 0 | 6 rules also tested via REQ |
| STD-109 | 10 | 8 | 1 | 1 | 4 rules also tested via REQ |
| STD-110 | 15 | 10 | 4 | 1 | 8 rules also tested via REQ |
| STD-111 | 18 | 18 | 0 | 0 | All automated via convention tests |
| **Total** | **53** | **44** | **6** | **2** | -- |

### Grand Total

| Category | Items | Verified |
|----------|-------|----------|
| Requirements (REQ-100, REQ-101, IFS-100) | 100 | 100 (100%) |
| Standards (STD-108 through STD-111) | 53 | 53 (100%) |
| **All verified items** | **153** | **153 (100%)** |
| Automated tests (T only) | -- | 132 of 153 (86%) |

### Spike Validation Evidence

Requirements validated by spike prototypes (Sessions 74-75) before specs were written.
Spikes proved concepts work but diverge from production code vocabulary/structure.
Production code was built from specs, not spikes. Full gap analysis: `rondo/spikes/SPIKE-TRACKER.md`.

| Req Range | Spike File | What Was Proved | Divergence from Production |
|-----------|-----------|----------------|---------------------------|
| REQ-100 1-7 | `spikes/engine.py` | Round/Task/Gate model, pre/post gates, three-field contract | Status vocab (PASSED->done), DB coupling removed |
| REQ-100 8-11 | `spikes/engine.py` | State transitions, serialization, resume | Status vocab changed to 5-value |
| REQ-100 12-16 | `spikes/dispatch.py` | `claude -p` invocation, env stripping, result capture | Uses text mode, not stream-json |
| REQ-100 17-19 | `spikes/dispatch.py` | Auth switching (max strips key, api keeps key) | Aligned with spec |
| REQ-100 20-23 | `spikes/dispatch.py` | `--model` flag, COALESCE per-task hints | Aligned with spec |
| REQ-100 25-28 | `spikes/dispatch.py` | JSON parsing, malformed fallback, error handling | Returns dict, not TaskResult dataclass |
| REQ-101 1-9 | `spikes/parallel.py` | ThreadPoolExecutor, throttle, conflict detection, isolation | No files_modified field, no DispatchUsage |
| REQ-101 10-18 | `spikes/overnight.py` | Phase execution, failure isolation, event log, no stdin | Hardcoded OB rounds (spec: configurable modes) |
| REQ-101 19-23 | -- | **Not spiked** | Built from spec (watchdog) |
| REQ-101 24-28 | -- | **Not spiked** | Built from spec (usage gating) |
| REQ-101 29-36 | `spikes/report.py` | Result aggregation, grouping, dated file | Missing health indicators, usage summary |
| REQ-101 37-41 | -- | **Not spiked** | Built from spec (worktree isolation) |
| IFS-100 1-10 | -- | **Not spiked** (text mode only) | Session 76 spike proved stream-json works |

---

## 5. Key Findings from Building Rondo

These findings emerged from the 7-day Orbital journey (Sessions 74-77) and represent
hard-won methodology lessons — not theoretical analysis.

| # | Finding | Source | Impact |
|---|---------|--------|--------|
| 1 | **Specs before code — always.** AI tried to skip specs 3 times. Process discipline must be enforced, not assumed. | Day 5, Google AI review | ORB-03/04 is mandatory, never optional |
| 2 | **Spike code is NOT production code.** Spikes prove ideas. Production code is built from specs. Vocabulary, structure, and contracts diverge. | Day 3 vs Day 5 | Clean separation: `spikes/` vs `src/` |
| 3 | **Inner orbits form everywhere.** The original model had one inner orbit (07-08-09). Reality shows orbits at every adjacent pair. | Day 4 (3 loops at ORB-03/04) | Dynamic inner orbits are a methodology feature |
| 4 | **External AI review catches builder blind spots.** Google AI (Gemini) found the cross-field validation gap that Claude missed. | Day 5 evening | ORB-04 should include independent/external review |
| 5 | **Convention locks are force multipliers.** 15 convention test classes enforce 18 rules automatically. No human discipline needed. | Day 5 hardening | STD-111 exists because of this discovery |
| 6 | **ORB compression works for small products.** With <15 source files, ORB-07/08/09 compress into ORB-05/06 without quality loss. | Full journey | Product size determines orbit count |
| 7 | **REQ-100 went through 8 versions in 5 days.** Spec refinement is iterative and never "done" on first pass. | Day 1-5 | Budget time for spec iterations |
| 8 | **Deep review v1 found 30 issues (5 build-blockers).** Self-review alone is insufficient. Must do cross-spec consistency checks. | Day 4 | Multi-pass review catches more |
| 9 | **COALESCE is the core config idiom.** `COALESCE(CLI, config, default)` resolves every configuration decision uniformly. | Day 3 design | Applied to auth, model, timeout, workers, throttle |
| 10 | **AI compliance with process rules decays under enthusiasm.** Both Claude and Gemini tried to jump ahead when excited about building. | Days 4-5 | Guardrails must be automated, not honor-system |

---

## 6. The Convergence Test

### What It Is

Rondo was the first product built entirely using the Orbital Development methodology.
The convergence test is a controlled experiment: rebuild Rondo from its specs repeatedly,
each time with improved guardrails, and measure whether the code improves.

**Analogy:** Compiler bootstrap — use a compiler to compile itself. Each pass should
produce identical or better output. If it degrades, there's a bug in the compiler.
For Orbital, the "compiler" is the methodology and the "output" is the code.

### Baseline (v1.0 — Session 77)

| Metric | Baseline |
|--------|----------|
| Source files | 10 |
| Test files | 10 |
| Total tests | 446 |
| Coverage | 95% |
| Pylint score | 10.00/10 |
| Convention lock classes | 15 |
| Spec count | 8 |
| REQ-100 requirements | 49 |
| Verified items (VER-100) | 153 |
| Build gates passing | 6/6 |
| orbit-sign verified | All files |
| Cyclomatic complexity max | <= 15 |

### Convergence Criteria

Rebuild produces **equal or better** numbers on ALL metrics. If any metric degrades,
the methodology has a regression that must be investigated.

### Why This Matters

- If methodology is sound, repeated application yields consistent or improving results
- If AI model changes degrade output, the test detects it (see Caliber S55: 489% drift)
- The specs ARE the product — code is a derivation. Convergence proves the derivation is stable.

---

## 7. Rondo + Caliber Integration: The buggy.py Spike

### What Happened (Caliber Spike S41)

Caliber's auto-fix loop has two layers: tool-fix first (ruff --fix), then AI-fix via
Rondo for issues tools can't resolve. The buggy.py spike proved this architecture works.

| Step | What | Result |
|------|------|--------|
| 1 | buggy.py scored **67/100** — type hint gaps, os.system, bare except, missing docs | Caliber score baseline |
| 2 | Tool-fix layer ran ruff --fix | Fixed formatting, simple lint issues |
| 3 | Tools loop forever on os.system, missing type hints (not auto-fixable) | Tools layer reached limit |
| 4 | AI-fix layer dispatched via Rondo: `claude -p "fix these issues"` | Claude fixed remaining issues |
| 5 | buggy.py scored **97/100** — in **81 seconds** | Caliber score after AI fix |

### What This Proves

1. **Rondo is a general dispatch engine.** It sends prompts to Claude and collects results.
   Caliber uses it for auto-fix. Any product can use it for any AI task.
2. **Two-layer fix converges.** Tools handle the mechanical (fast, cheap). AI handles
   the semantic (slow, expensive). Combined: fast AND thorough.
3. **81 seconds for a 30-point quality improvement.** The economics work.
4. **Rondo's dispatch contract handles real workloads.** Auth, model selection,
   result capture, error handling — all exercised in a production-like scenario.

### Architecture

```
Caliber (quality checker)
    |
    +--> Tool-fix layer (ruff --fix, ruff format)
    |       |
    |       +--> If tools can't fix it...
    |
    +--> AI-fix layer (Rondo dispatch)
            |
            +--> claude -p "fix: {issues}" --model sonnet
            |
            +--> Capture result, re-score
            |
            +--> Loop until converged or max iterations
```

### Spike Evidence

- **Spike S41** in `caliber/spikes/SPIKE-RESULTS.md`
- Caliber VER-100 req range 24-28 (AI fix via Rondo) and 33-37 (smart build loop)
- /tmp paths cause timeout — Claude needs project-local paths with permissions

---

## 8. Production Targets

| Metric | Target | Current |
|--------|--------|---------|
| Test coverage | >= 90% (fail_under) | 95% |
| Pylint score | >= 9.0/10 | 10.00/10 |
| Complexity cap | McCabe <= 15 | All functions <= 15 |
| Convention locks | All 18 pass | 18/18 |
| Req coverage (any method) | 100% | 100% (153/153) |
| Automated test coverage | >= 80% | 86% (132/153) |
| Build gates | 6/6 | 6/6 |

---

## 1. Purpose & Scope

REQUIRED — fill before build.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

REQUIRED — fill before build.

---

## 3. Requirements

*All requirements in this spec are MUST priority unless marked SHOULD.*

REQUIRED — fill before build.

---

## 4. Architecture / Design

REQUIRED — fill before build.

---

## 5. Data Model

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

## 9. Configuration

— if applicable.

---

## 10. Rules & Constraints

REQUIRED — fill before build.

---

## 11. Quality Attributes

— if applicable.

---

## 12. Shared Patterns

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

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Verification plan structure | WORKING | Per-spec verification requirements defined | After spec additions |
| Test-to-requirement mapping | WORKING | Tests reference verified requirements | Every sprint |
| Verification matrix | THEORY | Specced for cross-spec verification tracking | Phase 2 build |
| Automated verification runner | THEORY | Specced for end-to-end verification execution | Phase 3 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial verification matrix for REQ-100 + REQ-101 |
| 0.2 | 2026-03-14 | Added IFS-100 stream-json verification (10 tests). Total: 68 reqs, 58 automated tests |
| 0.3 | 2026-03-14 | Added REQ-101 watchdog (5), usage gating (5), report usage (1), worktree (5). Total: 84 reqs, 72 automated tests |
| 0.4 | 2026-03-14 | Deep review fixes: corrected coverage counts (74 automated tests, not 72), fixed table header, aligned status vocabulary with CORE-IFS-001 reqs 53-54 |
| 0.5 | 2026-03-14 | Added spike validation evidence: which reqs were proved by spikes, what diverged, what was never spiked (watchdog, usage gating, worktree, stream-json) |
| 0.6 | 2026-03-14 | Added REQ-100 reqs 34-44: CLI entry point (8 tests), living example rounds (3 tests). Total: 95 reqs, 84 automated tests |
| 0.7 | 2026-03-14 | Deep review v2: added REQ-100 reqs 45-46 (run_round, RoundResult.status). Added CORE-IFS-001 reqs 53-54 / STD-108 / STD-111 verification matrices (35 rules traced). Total: 97 reqs + 35 STD rules = 132 verified items |
| 0.8 | 2026-03-14 | Added REQ-100 reqs 47-49: permission mode dispatch (3 tests). Total: 100 reqs + 35 STD rules = 135 verified items |
| 0.9 | 2026-03-14 | Added STD-111 verification matrix (18 code quality gate rules, all automated). Total: 100 reqs + 53 STD rules = 153 verified items |
| 1.0 | 2026-03-16 | Full rebuild to VER-100 standard. Added: 6 verification methods, test index (418 tests across 10 files), coverage summary with grand total, 10 key findings, convergence test baseline, Rondo+Caliber buggy.py integration evidence, production targets. All 153 items verified 100%. |
