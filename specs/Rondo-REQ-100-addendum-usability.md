# Rondo-REQ-100 Addendum: Usability — Self-Service Round Authoring

**Parent:** Rondo-REQ-100-core.md
**Created:** 2026-03-30
**Origin:** Session 93 — USH deep-scan attempt exposed 6 usability gaps
**Status:** APPROVED

---

## Problem Statement

When a user (human or AI agent) tries to write a Rondo round file for the first
time, they hit multiple friction points:

1. No way to discover the Round/Task API without reading source code
2. No scaffolding — must write from scratch, guess imports
3. Dry-run blocked inside Claude Code (preflight rejects nested session)
4. No way to target a different project/workdir from the round file
5. Example rounds spec'd (REQ-100-052/053/054) but never built
6. No helpers to parse structured data from task results

**Evidence:** Session 93 USH scan attempt — 5 failed iterations, sys.path hack,
wrong return type, preflight block on dry-run. A user who can't author a round
file can't use Rondo at all.

---

## Requirements

### DRY-RUN + PREFLIGHT (resolves REQ-103 Q3: OPEN → DECIDED)

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | `--dry-run` MUST skip preflight entirely — dry-run shows prompts only, no dispatch, no Claude binary needed | MUST |
| U-02 | `--dry-run` inside a Claude Code session (CLAUDECODE env set) MUST work — it only formats prompts, never spawns subprocess | MUST |
| U-03 | When `--dry-run` is active, output MUST show: task name, model, prompt text, context files, done_when criteria — enough to verify the round file is correct | MUST |
| U-04 | `--skip-preflight` flag MUST be available on `rondo run` and `rondo overnight` — logged as WARNING in audit, never silent | SHOULD |

**Decision (REQ-103 Q3):** `--skip-preflight` is allowed. It MUST log a warning.
`--dry-run` always skips preflight (no dispatch = no preflight needed).

### AI-HELP ENRICHMENT

| # | Requirement | Priority |
|---|-------------|----------|
| U-05 | `rondo --ai-help` MUST include the full Round dataclass schema: field names, types, defaults, descriptions | MUST |
| U-06 | `rondo --ai-help` MUST include the full Task dataclass schema: all fields including instruction, context_files, done_when, model, mode, auto_fn | MUST |
| U-07 | `rondo --ai-help` MUST include a minimal round file example (copy-paste ready) showing `from rondo.engine import Round, Task` and `def build_round() -> Round:` | MUST |
| U-08 | `rondo --ai-help` MUST include the Gate/GateResult schema for users writing gated rounds | SHOULD |
| U-09 | `rondo --ai-help` output MUST be valid JSON (parseable by AI agents via `--ai-help | jq`) | MUST |

### INIT SCAFFOLDING

| # | Requirement | Priority |
|---|-------------|----------|
| U-10 | `rondo init` MUST create a starter round file in the current directory | MUST |
| U-11 | `rondo init` MUST generate a valid Python file with `build_round() -> Round:` that runs with `rondo run` immediately (no edits needed for hello-world) | MUST |
| U-12 | `rondo init --name <name>` MUST set the round name and first task name from the flag | SHOULD |
| U-13 | Generated file MUST include comments explaining each field and common patterns | MUST |
| U-14 | `rondo init` MUST NOT overwrite an existing file — error with message | MUST |

### PROJECT/WORKDIR FLAG

| # | Requirement | Priority |
|---|-------------|----------|
| U-15 | `rondo run --project <path>` MUST set the working directory for all dispatched tasks to `<path>` | MUST |
| U-16 | `--project` path MUST be validated: directory exists, is readable | MUST |
| U-17 | When `--project` is set, `claude -p` subprocess MUST be spawned with `cwd=<path>` so tasks have access to that project's files and MCP servers | MUST |
| U-18 | `--project` MUST be available on `rondo run`, `rondo live`, and `rondo overnight` | MUST |
| U-19 | If `--project` is not set, default is CWD (current behavior, no change) | MUST |

### EXAMPLE ROUNDS (implements existing REQ-100-052/053/054)

| # | Requirement | Priority |
|---|-------------|----------|
| U-20 | `examples/round_hello.py` — 1 task, no gates, simplest possible round. Must run with `rondo run examples/round_hello.py --dry-run` | MUST |
| U-21 | `examples/round_file_check.py` — auto task (check file exists) + pre-gate (verify CWD). Demonstrates auto_fn and gate patterns | MUST |
| U-22 | `examples/round_multi_task.py` — 3 tasks with model hints, context_files, different done_when criteria. Parallel-ready | MUST |
| U-23 | `examples/round_overnight.py` — multi-phase overnight round file. Demonstrates build_phases() for `rondo overnight` | SHOULD |
| U-24 | All example files MUST be tested in the test suite (test_examples.py) — living docs, not dead code | MUST |
| U-25 | All example files MUST have header comments with usage: `rondo run examples/X.py --dry-run` | MUST |

### RESULT PARSING HELPERS

| # | Requirement | Priority |
|---|-------------|----------|
| U-26 | `TaskResult.extract_json()` MUST attempt to parse `raw_output` as JSON, returning dict or None | SHOULD |
| U-27 | `TaskResult.extract_code_blocks()` MUST extract fenced code blocks from `raw_output`, returning list of (language, content) tuples | SHOULD |
| U-28 | `TaskResult.extract_table()` MUST extract markdown tables from `raw_output`, returning list of dicts (header→value) | MAY |
| U-29 | Parsing helpers MUST be best-effort — never raise, return None/empty on failure | MUST |
| U-30 | Parsing helpers MUST NOT modify the original `raw_output` — they are read-only views | MUST |

### MCP DISPATCH STATUS (USH production feedback — Finding #165, #166)

| # | Requirement | Priority |
|---|-------------|----------|
| U-31 | `rondo_run_status` MUST return per-task progress: task name + status (done/running/pending) for each task in the round | MUST |
| U-32 | `rondo_run_status` MUST include completed task results inline (raw_output truncated to 2000 chars) so callers don't need to read separate files | MUST |

### INLINE TASK DISPATCH (USH production feedback — Finding #167)

| # | Requirement | Priority |
|---|-------------|----------|
| U-33 | `rondo_run` MUST accept an optional `prompt` parameter for one-off tasks without a round file. When `prompt` is set, Rondo creates an in-memory Round with one Task using the prompt as instruction | MUST |
| U-34 | Inline dispatch MUST accept `done_when` parameter (defaults to "Task completed. Return results.") | SHOULD |
| U-35 | Inline dispatch MUST return the same JSON structure as file-based dispatch | MUST |

### MCP DISPATCH OBSERVABILITY (USH production feedback)

| # | Requirement | Priority |
|---|-------------|----------|
| U-36 | Background dispatch SHOULD track running cost (sum of completed task costs) in status response | SHOULD |
| U-37 | `dispatched_at` field in audit OUTCOME records MUST be populated from the INTENT record timestamp (Finding #162) | MUST |
| U-38 | `round_name` MUST flow from Round.name through dispatch to audit records (Finding #163) | MUST |
| U-39 | `max_budget` documentation MUST note that budget cap only works with `auth: "api"`, not `auth: "max"` (Finding #164) | MUST |

---

## Gap Check: Cross-Spec Impact

| This Addendum | Affects | How |
|--------------|---------|-----|
| U-01/U-02 (dry-run skip preflight) | REQ-103 Q3 | **Resolves** — Q3 answered: yes, skip allowed with warning |
| U-04 (--skip-preflight) | REQ-103 | **New flag** — add to preflight spec |
| U-05–U-09 (--ai-help) | IFS-100 | **New interface** — ai-help is a machine-readable API surface |
| U-15–U-19 (--project) | STD-109 | **New config field** — add to COALESCE chain |
| U-20–U-25 (examples) | REQ-100-052/053/054 | **Implements** existing reqs — no spec change needed |
| U-26–U-30 (result helpers) | STD-100 | **Extends** data standards — new methods on TaskResult |
| U-31/U-32 (per-task status) | IFS-104 | **Extends** MCP server — richer status response |
| U-33–U-35 (inline dispatch) | IFS-104 | **New interface** — prompt-based dispatch without files |
| U-37/U-38 (audit fixes) | STD-113 | **Bug fix** — dispatched_at + round_name propagation |
| U-39 (budget docs) | STD-109 | **Documentation** — max_budget limitation on Max plan |

## Cross-Spec Updates Required

| Spec | Section | Update |
|------|---------|--------|
| REQ-103 | §11 Open Questions | Q3 → DECIDED (U-01, U-04) |
| REQ-103 | Requirements table | Add req 027: `--skip-preflight` flag |
| IFS-100 | Interface definition | Add `--ai-help` as formal interface |
| IFS-104 | MCP tools | U-31/U-32 per-task status, U-33–U-35 inline dispatch |
| STD-109 | Configuration table | Add `project` field + `max_budget` limitation note |
| STD-113 | Audit trail | U-37 dispatched_at propagation, U-38 round_name flow |
| STD-100 | Data Model | Add extract methods to TaskResult |
| REQ-100 | Package layout | Add `examples/` directory with 4 files |

---

## Verification Matrix

| Req | Test Type | Test Description |
|-----|-----------|-----------------|
| U-01 | Unit | `--dry-run` with no claude binary works |
| U-02 | Unit | `--dry-run` with CLAUDECODE env set works |
| U-03 | Unit | Dry-run output contains task name, prompt, model |
| U-05 | Unit | `--ai-help` JSON contains Round schema |
| U-06 | Unit | `--ai-help` JSON contains Task schema with all fields |
| U-07 | Unit | `--ai-help` JSON contains example round file |
| U-10 | Unit | `rondo init` creates valid file |
| U-11 | E2E | Generated file runs with `rondo run --dry-run` |
| U-15 | Unit | `--project` sets subprocess CWD |
| U-20–U-23 | E2E | Each example runs with `--dry-run` |
| U-24 | Integration | test_examples.py imports and validates all examples |
| U-26 | Unit | extract_json() parses valid JSON from output |
| U-29 | Unit | extract_json() returns None on invalid output |
| U-31 | Unit | rondo_run_status returns per-task name + status |
| U-32 | Unit | rondo_run_status includes raw_output in completed tasks |
| U-33 | Unit | rondo_run(prompt="...") creates in-memory round and dispatches |
| U-35 | Unit | Inline dispatch returns same JSON as file-based |
| U-37 | Unit | Audit OUTCOME has dispatched_at from INTENT |
| U-38 | Unit | Audit OUTCOME has round_name from Round.name |

---

## Build Order

| Phase | Reqs | Why This Order |
|-------|------|---------------|
| 1 | U-01, U-02 | Unblocks testing everything else from inside CC |
| 2 | U-05–U-09 | Unblocks AI agents discovering the API |
| 3 | U-10–U-14 | Unblocks first-time users creating round files |
| 4 | U-20–U-25 | Living examples for learning and testing |
| 5 | U-15–U-19 | --project flag for cross-repo dispatching |
| 6 | U-26–U-30 | Result helpers for structured consumption |
| 7 | U-03, U-04 | Polish: better dry-run output, --skip-preflight |
| 8 | U-31, U-32 | Per-task status + results in status response (RONDO-42) |
| 9 | U-33–U-35 | Inline task dispatch without round file (RONDO-43) |
| 10 | U-37, U-38 | Audit bug fixes: dispatched_at + round_name |
| 11 | U-36, U-39 | Polish: running cost, budget doc |

---

---

## USH Production Feedback (Session 93 — First Real Use)

**Source:** USH Claude session, 4-task parallel dispatch via MCP, 2026-03-30.

### What Worked (Validated)
- MCP dispatch from inside CC (no separate terminal)
- dry_run=true default (safe first)
- background=true with polling
- 4 parallel workers (5 min vs 20+ min sequential)
- Structured JSON results
- Auto audit trail
- Results persisted to files

### Feature Requests (New Requirements)

| # | Request | Finding | Sprint |
|---|---------|---------|--------|
| U-31 | Per-task progress in `rondo_run_status` (not just "running") | #165 | RONDO-42 |
| U-32 | Task results returned IN the status response (no file reading needed) | #166 | RONDO-42 |
| U-33 | Inline task dispatch: `rondo_run(prompt="...")` without round file | #167 | RONDO-43 |
| U-34 | Running cost shown during background dispatch | — | Future |
| U-35 | Completion notification (push result vs polling) | — | Future (needs MCP notification spec) |
| U-36 | `--project` inherits target project's MCP servers | — | Future (CC architecture limitation) |

### Bugs Found

| # | Bug | Finding | Severity |
|---|-----|---------|----------|
| B-1 | `dispatched_at` empty in audit OUTCOME | #162 | Medium |
| B-2 | `round_name` not flowing to audit | #163 | Low |
| B-3 | `max_budget` misleading on Max plan (no-op) | #164 | Medium |

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-03-30 | Initial — 30 requirements across 6 features. Resolves REQ-103 Q3. Implements REQ-100-052/053/054. |
| 0.2 | 2026-03-30 | USH production feedback: +9 requirements (U-31 to U-39) in proper tables. 3 categories: MCP status (U-31/32), inline dispatch (U-33-35), observability fixes (U-36-39). 6 verification matrix entries. 4 new build phases (8-11). 6 findings (#162-167). Cross-spec updates for IFS-104, STD-113, STD-109. |
