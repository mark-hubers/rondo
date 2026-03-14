# VER-001: Verification Plan

*How every requirement gets proved — test, demonstration, analysis, or inspection.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** REQ-001, REQ-002 | **Blocks:** Nothing
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

### Morning Report

| Req | Requirement (short) | Method | Test/Evidence |
|-----|---------------------|--------|--------------|
| 19 | Aggregates all phases | Test | `test_report.py::test_aggregation` |
| 20 | Grouped by round type | Inspection | Review report output |
| 21 | Shows done/failed/duration per round | Test | `test_report.py::test_round_stats` |
| 22 | Health indicators | Test | `test_report.py::test_health_colors` |
| 23 | Action items from failures | Test | `test_report.py::test_action_items` |
| 24 | Saves to dated file | Test | `test_report.py::test_dated_filename` |
| 25 | Includes totals and timestamp | Test | `test_report.py::test_report_totals` |

---

## Coverage Summary

| Spec | Total Reqs | Test | Demo | Analysis | Inspection |
|------|-----------|------|------|----------|------------|
| REQ-001 | 33 | 28 | 0 | 3 | 2 |
| REQ-002 | 25 | 20 | 2 | 1 | 2 |
| **Total** | **58** | **48** | **2** | **4** | **4** |

83% verified by automated test. 100% covered by at least one method.

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial verification matrix for REQ-001 + REQ-002 |
