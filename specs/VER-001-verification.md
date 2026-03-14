# VER-001: Verification Plan

*How every requirement gets proved — test, demonstration, analysis, or inspection.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** REQ-001, REQ-002, IFS-001 | **Blocks:** Nothing
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Maps every requirement in REQ-001 and REQ-002 to a verification method. For each requirement, this document says HOW we prove it works — by writing a test, running a demonstration, performing analysis, or doing a manual inspection.

**IN scope:**
- Verification method per requirement (Test / Demo / Analysis / Inspection)
- Test file mapping (which test file proves which requirement)
- Acceptance criteria for demonstrations

**OUT of scope:**
- Test implementation (code lives in `rondo/tests/`)
- Test framework selection (pytest, assumed)
- CI/CD pipeline (platform-specific)

---

## Verification Methods (DO-178C vocabulary)

| Method | What It Means | When to Use |
|--------|--------------|-------------|
| **Test** | Automated test proves the requirement | Deterministic behavior, measurable output |
| **Demonstration** | Manual or scripted run shows it working | Integration behavior, visual confirmation |
| **Analysis** | Code review or static analysis proves it | Architecture rules, design patterns |
| **Inspection** | Read the code/output and verify by eye | Documentation, formatting, naming |

---

## REQ-001 (Core) Verification Matrix

### Engine — Data Model

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 1 | Round contains name, gates, tasks | Test | `test_engine.py::test_round_structure` |
| 2 | Task has name, mode, status | Test | `test_engine.py::test_task_fields` |
| 3 | Interactive task: Do/Read/Done | Test | `test_engine.py::test_three_field_contract` |
| 4 | Auto task: callable returns (bool, str) | Test | `test_engine.py::test_auto_task_run` |
| 5 | Gate: name, check_fn, blocking | Test | `test_engine.py::test_gate_check` |
| 6 | Pre-gates block on failure | Test | `test_engine.py::test_blocking_pregate` |
| 7 | Post-gates after all tasks | Test | `test_engine.py::test_postgate_timing` |

### Engine — State Machine

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 8 | State: pending→running→passed/failed/skipped | Test | `test_engine.py::test_state_transitions` |
| 9 | Round complete when all tasks terminal | Test | `test_engine.py::test_round_completion` |
| 10 | Serializable to JSON | Test | `test_engine.py::test_serialize_round` |
| 11 | Resumable from JSON | Test | `test_engine.py::test_resume_round` |

### Dispatch — Subprocess

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 12 | Invokes claude -p | Test | `test_dispatch.py::test_subprocess_command` |
| 13 | Strips CLAUDECODE env | Test | `test_dispatch.py::test_claudecode_stripped` |
| 14 | Captures stdout, stderr, exit code, duration | Test | `test_dispatch.py::test_result_capture` |
| 15 | Saves result to JSON file | Test | `test_dispatch.py::test_result_saved` |
| 16 | Dry-run shows prompt without invoking | Test | `test_dispatch.py::test_dry_run` |

### Dispatch — Auth

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 17 | auth=max strips ANTHROPIC_API_KEY | Test | `test_dispatch.py::test_auth_max_strips_key` |
| 18 | auth=api keeps ANTHROPIC_API_KEY | Test | `test_dispatch.py::test_auth_api_keeps_key` |
| 19 | --auth flag selectable, default max | Test | `test_cli.py::test_auth_flag` |

### Dispatch — Model Routing

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 20 | Passes --model to subprocess | Test | `test_dispatch.py::test_model_flag` |
| 21 | COALESCE: CLI → task → default | Test | `test_dispatch.py::test_model_coalesce` |
| 22 | Default is sonnet | Test | `test_dispatch.py::test_model_default` |
| 23 | Task can hint a model | Test | `test_engine.py::test_task_model_hint` |

### Dispatch — Result Contract

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 24 | Prompt requests JSON output | Inspection | Review prompt template |
| 25 | Valid JSON parsed and stored | Test | `test_dispatch.py::test_json_parsing` |
| 26 | Malformed JSON → status "partial" | Test | `test_dispatch.py::test_malformed_json` |
| 27 | Exit code != 0 → status "error" | Test | `test_dispatch.py::test_error_exit_code` |
| 28 | Result includes metadata fields | Test | `test_dispatch.py::test_result_metadata` |

### Round Definitions

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 29 | Function returns Round object | Test | `test_engine.py::test_round_builder` |
| 30 | Self-contained | Analysis | Code review: no dispatch imports |
| 31 | Accepts parameters | Test | `test_engine.py::test_parameterized_round` |
| 32 | Only imports engine module | Analysis | Import check via AST or grep |
| 33 | Under 50 lines | Inspection | `wc -l` on round definition files |

---

## REQ-002 (Automation) Verification Matrix

### Parallel Execution

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 1 | Uses ThreadPoolExecutor | Analysis | Code review |
| 2 | Configurable workers, default 4 | Test | `test_parallel.py::test_worker_config` |
| 3 | Configurable throttle, default 2s | Test | `test_parallel.py::test_throttle` |
| 4 | Results collected as completed | Test | `test_parallel.py::test_result_order` |
| 5 | Conflict detection flags shared files | Test | `test_parallel.py::test_conflict_detection` |
| 6 | Conflicts listed in summary | Test | `test_parallel.py::test_conflict_in_summary` |
| 7 | Reports done/error/wall/task/speedup | Test | `test_parallel.py::test_summary_stats` |
| 8 | Single failure doesn't crash others | Test | `test_parallel.py::test_task_isolation` |
| 9 | Same JSON format as sequential | Test | `test_parallel.py::test_result_format` |

### Overnight Scheduler

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 10 | Accepts list of round definitions | Test | `test_overnight.py::test_phase_list` |
| 11 | Phases sequential, tasks may be parallel | Demo | Run overnight with multi-task phase |
| 12 | Phase failure doesn't block next | Test | `test_overnight.py::test_phase_isolation` |
| 13 | Configurable modes | Test | `test_overnight.py::test_mode_config` |
| 14 | 3+ modes supported | Test | `test_overnight.py::test_three_modes` |
| 15 | Modes configurable, not hardcoded | Analysis | No OB/ACE round names in code |
| 16 | No interactive input required | Demo | Run from cron-like invocation |
| 17 | Logs start/end events | Test | `test_overnight.py::test_event_logging` |
| 18 | Rolling 100-entry log | Test | `test_overnight.py::test_rolling_log` |

### Self-Healing Watchdog

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 19 | Monitors dispatch for hung conditions | Test | `test_overnight.py::test_watchdog_detects_hung` |
| 20 | Kills no-output dispatch after timeout | Test | `test_overnight.py::test_watchdog_kills_hung` |
| 21 | Continues after watchdog kill | Test | `test_overnight.py::test_watchdog_continues` |
| 22 | Rate limit backoff pause | Test | `test_overnight.py::test_rate_limit_backoff` |
| 23 | Watchdog logs every intervention | Test | `test_overnight.py::test_watchdog_logging` |

### Usage Threshold Gating

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 24 | Checks rate_limit_event before each phase | Test | `test_overnight.py::test_usage_check_before_phase` |
| 25 | isUsingOverage triggers configurable action | Test | `test_overnight.py::test_overage_action` |
| 26 | Blocked status pauses until reset | Test | `test_overnight.py::test_blocked_pause` |
| 27 | on_overage configurable (continue/pause/stop) | Test | `test_overnight.py::test_overage_config` |
| 28 | Usage decisions logged to event log | Test | `test_overnight.py::test_usage_decision_logging` |

### Morning Report

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 29 | Aggregates all phases | Test | `test_report.py::test_aggregation` |
| 30 | Grouped by round type | Inspection | Review report output |
| 31 | Shows done/failed/duration per round | Test | `test_report.py::test_round_stats` |
| 32 | Health indicators | Test | `test_report.py::test_health_colors` |
| 33 | Action items from failures | Test | `test_report.py::test_action_items` |
| 34 | Saves to dated file | Test | `test_report.py::test_dated_filename` |
| 35 | Includes totals and timestamp | Test | `test_report.py::test_report_totals` |
| 36 | Includes usage summary (cost, tokens, overage, watchdog) | Test | `test_report.py::test_usage_summary` |

### Worktree Isolation

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 37 | Supports optional git worktree per worker | Test | `test_parallel.py::test_worktree_creation` |
| 38 | Each task runs in own worktree, results merged | Demo | Run parallel with worktree isolation enabled |
| 39 | Worktree opt-in via config or CLI | Test | `test_parallel.py::test_worktree_config` |
| 40 | Without worktree, conflict detection is active | Test | `test_parallel.py::test_conflict_without_worktree` |
| 41 | Worktrees cleaned up after round | Test | `test_parallel.py::test_worktree_cleanup` |

---

## IFS-001 (Interface) Verification Matrix

### Stream-JSON Metadata Parsing

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------
| 1 | Reads stream-json line by line | Test | `test_dispatch.py::test_stream_json_parsing` |
| 2 | Extracts rate_limit_event | Test | `test_dispatch.py::test_rate_limit_extraction` |
| 3 | Extracts result event (cost/tokens) | Test | `test_dispatch.py::test_result_metadata_extraction` |
| 4 | Extracts system init (model/version) | Test | `test_dispatch.py::test_init_event_extraction` |
| 5 | Verifies model matches requested | Test | `test_dispatch.py::test_model_verification` |
| 6 | isUsingOverage flag captured | Test | `test_dispatch.py::test_overage_flag` |
| 7 | total_cost_usd captured per dispatch | Test | `test_dispatch.py::test_cost_capture` |
| 8 | duration_ms captured | Test | `test_dispatch.py::test_duration_capture` |
| 9 | Handles missing rate_limit_event | Test | `test_dispatch.py::test_missing_rate_limit` |
| 10 | 1M context model variant accepted | Test | `test_dispatch.py::test_1m_model_variant` |

---

## Coverage Summary

| Spec | Total Reqs | Test | Demo | Analysis | Inspection |
|------|-----------|------|------|----------|------------|
| REQ-001 | 33 | 28 | 0 | 3 | 2 |
| REQ-002 | 41 | 34 | 2 | 1 | 2 |
| IFS-001 | 10 | 10 | 0 | 0 | 0 |
| **Total** | **84** | **72** | **2** | **4** | **4** |

86% verified by automated test. 100% covered by at least one method.

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial verification matrix for REQ-001 + REQ-002 |
| 0.2 | 2026-03-14 | Added IFS-001 stream-json verification (10 tests). Total: 68 reqs, 58 automated tests |
| 0.3 | 2026-03-14 | Added REQ-002 watchdog (5), usage gating (5), report usage (1), worktree (5). Total: 84 reqs, 72 automated tests |
