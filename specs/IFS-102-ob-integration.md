# IFS-102: OB Integration Contract

*How Rondo talks to OB — what it sends, what it receives, when it connects, and what it never touches. The execution muscle plugged into the methodology brain.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Architect:** Mark G. Hubers — HubersTech
**Implements:** CORE-IFS-001 (Integration Contract Standard) — universal payload/transport/isolation patterns
**Depends on:** REQ-100 (Core), REQ-101 (Automation), CORE-IFS-001 (universal contract), OB-IFS-102, IFS-100, OB-REQ-103, OB-REQ-128, OB-SOP-100, REQ-109
**Connects to:** OB-IFS-102 (External Integration), OB-REQ-128 (Dispatch), OB-REQ-103 (Sprint)
**References:** CORE-IFS-001 §5 (field mapping), CORE-IFS-001 §3 reqs 53-57 (status/severity vocab), CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)
**Decision:** DEC-017 (OB standalone standards — Rondo is standalone, OB is standalone, they plug together)

---

## 1. Purpose & Scope

**What this spec does:**
Defines the exact contract between Rondo and OB. Rondo is a standalone AI dispatch engine that works without OB — give it a task JSON, it dispatches to Claude, returns structured results. When OB is present, Rondo becomes the execution arm of the methodology: OB sends rounds of AI work (code generation, spec writing, review, testing, analysis — any OA that needs AI), Rondo executes them and returns results that OB stores, learns from, and feeds back. This spec owns the Rondo SIDE of that connection — what Rondo provides, expects, and refuses to do.

**IN scope:**
- What Rondo receives from OB (input contract — OAPayload)
- What Rondo returns to OB (output contract — RoundResult/TaskResult/GateResult)
- OB mode detection (when OB integration activates)
- OB-specific CLI flags and configuration
- Field-level mapping (Rondo dataclasses → OB tables)
- Worktree management lifecycle (create, build, merge, cleanup)
- Overnight automation behavior under OB control
- Error handling when OB is unavailable
- Isolation boundaries (what Rondo never touches)

**OUT of scope:**
- OB's internal storage (OB-REQ-100 owns that)
- OB's dispatch engine (OB-REQ-128 owns that)
- How OB calls Rondo (OB-IFS-102 owns that)
- Caliber integration (IFS-102 (Caliber) or Rondo's internal Caliber calls)
- Claude Code CLI details (IFS-100 owns that)
- Rondo's engine internals (REQ-100 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo dispatches AI tasks. OB orchestrates methodology. These are two standalone products that work independently — but when connected, they create something neither can do alone: methodology-driven AI execution with compound learning.

Without a formal contract:
- OB doesn't know what format Rondo expects for task dispatch
- Rondo doesn't know what OB expects back
- Field names drift (`RoundResult.status` vs `round_states.status` — are they the same?)
- Nobody knows who manages worktrees (OB tells Rondo which ones, or Rondo decides?)
- Overnight automation has no agreed handshake (who controls the schedule? Who advances the sprint?)
- Error recovery is ad hoc (what happens when OB's DB is locked mid-sprint?)
- The boundary is unclear (can Rondo update sprint status in OB's DB? No. Never.)

This spec makes the plug explicit. Rondo and OB can be developed independently as long as they honor this contract. Rondo is the muscle — it does what it's told and reports back. OB is the brain — it decides what needs doing and learns from the results.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### OB Mode Detection (when does integration activate?)
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL rondo detects OB by checking for `.ob/config.toml` in the project root | MUST |
| 002 | System SHALL if `.ob/config.toml` exists AND `[rondo] enabled = true`: OB integration mode activates automatically | MUST |
| 003 | System SHALL if `.ob/config.toml` exists but `[rondo] enabled = false`: standalone mode (OB present but Rondo integration off) | MUST |
| 004 | System SHALL if `.ob/config.toml` does not exist: standalone mode (no OB, Rondo works with raw task JSON) | MUST |
| 005 | System SHALL manual override: `--ob-mode on|off` CLI flag forces integration mode regardless of config | MUST |
| 006 | System SHALL `rondo run --ob-mode on` without `.ob/config.toml` present → ERROR: "OB config not found at .ob/config.toml" | MUST |

### What Rondo Receives from OB (Input Contract)
| ID | Requirement | Priority |
|----|-------------|----------|
| 007 | System SHALL rondo receives an `OAPayload` ($contract: "OAPayload", $version: "1.0") containing everything needed to execute one or more OAs | MUST |
| 008 | System SHALL the payload `dispatch` section specifies: sprint_id, project, actions (OA IDs to run), triggered_by, dispatched_at | MUST |
| 009 | System SHALL the payload `spec` section provides a spec digest: spec_id, digest_hash, purpose, requirements, data_model, rules, success_criteria — Rondo uses these as context for AI prompts | MUST |
| 010 | System SHALL the payload `ai_memory` section provides learning from previous builds: ai_went_wrong (mistakes to avoid), ai_assumptions (design choices made), ai_review (independent reviewer findings), build_history (array of {build, errors, iterations, cost}) | MUST |
| 011 | System SHALL the payload `context` section provides: language, mode (single/batch), file_to_build (or files for batch), existing_files (SHA hashes), build_order, current_position | MUST |
| 012 | System SHALL the payload `runtime` section provides: oa_runtime (container ID), container_image, model, tool_mode, timeout_sec, max_tokens | MUST |
| 013 | System SHALL when `--ob-payload <file>` is provided, Rondo reads the full OAPayload from that file instead of building its own Round from a Python definition | MUST |
| 014 | System SHALL when `--ob-payload -` is provided, Rondo reads the OAPayload from stdin (pipeline mode: `ob dispatch | rondo run --ob-payload -`) | MUST |
| 015 | Rondo MUST accept round definitions from the payload — OB defines the round structure (tasks, gates, ordering), Rondo executes it. Rondo does not decide WHAT to do; OB decides that | MUST |
| 016 | System SHALL worktree isolation config: the payload MAY include a `worktree` section specifying `enabled: true`, `branch_prefix`, and `cleanup_policy`. Rondo creates worktrees per these settings | SHOULD |
| 017 | System SHALL overnight batch schedules: OB MAY send a `schedule` section with an ordered list of sprint_ids and their associated OAPayloads. Rondo's overnight scheduler processes them in order | SHOULD |

### What Rondo Returns to OB (Output Contract)
| ID | Requirement | Priority |
|----|-------------|----------|
| 018 | System SHALL after execution, Rondo produces a JSON result matching the `OAResult` contract ($contract: "OAResult", $version: "1.0") | MUST |
| 019 | System SHALL the result `dispatch` section returns: sprint_id, actions_run, started_at, completed_at, duration_ms | MUST |
| 020 | System SHALL per-OA results as entries in the `results` array: oa_id, status (done/partial/error/skipped), exit_code, timing (queued_at, started_at, completed_at, duration_ms, queue_wait_ms, api_duration_ms), output (files_created, lines_generated, raw_stdout, raw_stderr, log_file), findings, ai metadata, metrics | MUST |
| 021 | System SHALL aI cost data as `DispatchUsage` per task: model_used, input_tokens, output_tokens, cache_read_tokens, cache_create_tokens, cost_usd, duration_ms, num_turns. OB stores these in `sprint_intelligence` | MUST |
| 022 | System SHALL gate results: for each pre-gate and post-gate, Rondo returns `GateResult` with gate name, passed (bool), detail (string), duration_ms. OB stores in `gate_checks` | MUST |
| 023 | System SHALL generated content: when an OA produces code, specs, or tests, the full file content is included in `output.files_created` with paths relative to the project root and raw content or SHA reference | MUST |
| 024 | System SHALL the `learn` section returns feedback for the compound loop: ai_went_wrong_update (new mistakes discovered), ai_assumptions_update (new design choices), ai_cost_update (tokens, cost_usd, iterations) | MUST |
| 025 | System SHALL worktree merge status: when worktree isolation was used, the result includes a `worktree` section with merge_status (merged/conflict/pending), conflicted_files (if any), and worktree_path | MUST |
| 026 | System SHALL convergence data: when a task ran through fix-check iterations (via Caliber), the result includes iterations count, errors_before, errors_after, converged (bool) | MUST |

### Field-Level Mapping (Rondo → OB)
| ID | Requirement | Priority |
|----|-------------|----------|
| 027 | System SHALL field mapping is the AUTHORITATIVE contract between the two products: | MUST |

| Rondo Dataclass.Field | OB Table.Column | Notes |
|----------------------|----------------|-------|
| `RoundResult.status` | `round_states.status` | done/partial/error/skipped (NAMING-MAP vocabulary) |
| `RoundResult.duration_sec` | `round_states.duration_sec` | Wall-clock seconds for the full round |
| `TaskResult.status` | `sprint_results.status` | Per-task status |
| `TaskResult.task_name` | `sprint_results.task_name` | Matches OA name from payload |
| `TaskResult.parsed_result` | `sprint_results.result_json` | Structured JSON from Claude response |
| `TaskResult.raw_stdout` | `sprint_results.raw_output` | Full stdout capture |
| `TaskResult.findings[]` | `findings.*` | Findings discovered during execution |
| `DispatchUsage.model` | `sprint_intelligence.model` | Model used (opus/sonnet/haiku) |
| `DispatchUsage.input_tokens` | `sprint_intelligence.input_tokens` | Prompt tokens |
| `DispatchUsage.output_tokens` | `sprint_intelligence.output_tokens` | Completion tokens |
| `DispatchUsage.cache_read_tokens` | `sprint_intelligence.cache_read_tokens` | Cached prompt tokens reused |
| `DispatchUsage.cost_usd` | `sprint_intelligence.cost_usd` | Total cost for this dispatch |
| `DispatchUsage.duration_ms` | `sprint_intelligence.api_duration_ms` | API wall-clock time |
| `DispatchUsage.num_turns` | `sprint_intelligence.turns` | Agentic turns within single dispatch |
| `GateResult.name` | `gate_checks.gate_name` | Gate identifier |
| `GateResult.passed` | `gate_checks.passed` | 0/1 integer in OB |
| `GateResult.detail` | `gate_checks.detail` | Human-readable explanation |
| ID | Requirement | Priority |
|----|-------------|----------|
| 028 | System SHALL field mapping changes require BOTH specs updated (this spec + NAMING-MAP.md) — never change one without the other | MUST |
| 029 | System SHALL new fields: add to NAMING-MAP.md first, then update both specs. NAMING-MAP is the bridge | MUST |

### Isolation Boundaries (what Rondo NEVER does)
| ID | Requirement | Priority |
|----|-------------|----------|
| 030 | System SHALL rondo NEVER writes directly to OB's database — all data flows through JSON contracts (OAResult) | MUST |
| 031 | System SHALL rondo NEVER reads OB's internal tables — spec digests, AI memory, and sprint context come via OAPayload, not DB queries | MUST |
| 032 | System SHALL rondo NEVER calls OB's internal Python modules — no `from ob_queries import` in Rondo code | MUST |
| 033 | System SHALL rondo NEVER modifies `.ob/config.toml` — it reads config, OB writes config | MUST |
| 034 | System SHALL rondo NEVER advances sprint state — OB decides when a sprint moves from BUILD to VERIFY to COMPLETE. Rondo reports results. OB decides next steps | MUST |
| 035 | System SHALL rondo NEVER bypasses OB's gates — if OB includes a gate in the payload, Rondo executes it and reports the result. Rondo does not skip gates or override gate failures | MUST |
| 036 | System SHALL rondo CAN run without OB present — standalone mode must always work, even if OB is uninstalled. Give Rondo a task, it dispatches, it returns a result. No OB needed | MUST |

### Transport (how OB and Rondo physically connect)
| ID | Requirement | Priority |
|----|-------------|----------|
| 037 | System SHALL transport is progressive — same contract, different pipes: | MUST |

| Transport | When | How | Latency |
|-----------|------|-----|---------|
| **Pipe (stdin/stdout)** | Local, same machine | `ob dispatch \| rondo run --ob-payload -` | Microseconds |
| **File** | Local, async | `ob dispatch > payload.json && rondo run --ob-payload payload.json --ob-result result.json` | Milliseconds |
| **Unix socket** | Local, service mode | Rondo listens on socket, OB connects | Milliseconds |
| **HTTPS** | Remote, networked | OB POST to `https://rondo.internal/run`, mTLS required | Seconds |
| **Queue** | Remote, async | OB publishes to queue, Rondo worker consumes | Seconds+ |
| ID | Requirement | Priority |
|----|-------------|----------|
| 038 | System SHALL start with pipe and file (simplest). Add HTTPS when Rondo runs on a different machine. Queue when scaling to multiple Rondo workers processing different sprints | MUST |
| 039 | System SHALL transport is TRANSPARENT to the contract — OAPayload JSON is identical regardless of transport. Change the pipe, not the data | MUST |
| 040 | System SHALL hTTPS transport requires mTLS (mutual TLS) — both OB and Rondo authenticate. Aligns with CORE-STD-005 rule 16 | MUST |
| 041 | System SHALL queue transport preserves ordering per-sprint — OAs for the same sprint must complete in order. Different sprints MAY be dispatched to different Rondo workers | MUST |

### Error Handling (when OB is unavailable)
| ID | Requirement | Priority |
|----|-------------|----------|
| 042 | System SHALL oB DB locked → Rondo completes its execution, writes OAResult to file, logs WARNING: "OB unavailable — results saved to {path}, import with `ob store-result {path}`" | MUST |
| 043 | System SHALL oB config missing required fields → Rondo falls back to standalone mode, logs WARNING: "OB config incomplete — running standalone" | MUST |
| 044 | System SHALL oAPayload malformed → Rondo rejects with exit code 2 and structured error: `{"error": "Invalid payload", "detail": "{specifics}", "contract": "OAPayload", "version": "1.0"}` | MUST |
| 045 | System SHALL oAPayload version mismatch (payload $version != supported) → Rondo rejects with clear error: "Unsupported OAPayload version: {v}. Supported: 1.0" | MUST |
| 046 | System SHALL network timeout (HTTPS/queue transport) → Rondo completes locally, queues result for later delivery. Result file is the fallback — never lose work | MUST |
| 047 | System SHALL claude CLI failure mid-round → Rondo records the failed task as status "error" with stderr content, continues to next task in the round (STD-108 error resilience), and includes the partial round result in the OAResult | MUST |

### Standalone Behavior (Rondo without OB)
| ID | Requirement | Priority |
|----|-------------|----------|
| 048 | System SHALL without OB, Rondo works with Python round definitions (REQ-100): a `build_round()` function returns a `Round` object, Rondo dispatches tasks and returns a `RoundResult` | MUST |
| 049 | System SHALL standalone results use the same JSON format as OB-connected results. The only difference: no `dispatch.sprint_id` (populated as null), no `spec` digest in the payload | MUST |
| 050 | System SHALL standalone Rondo can still accept `--ob-payload` with a hand-crafted JSON file — useful for testing the OB integration path without running OB | MUST |
| 051 | System SHALL transition from standalone to OB-connected requires ZERO code changes in Rondo — only adding `.ob/config.toml` with `[rondo] enabled = true` | MUST |

### Worktree Management (parallel build isolation)
| ID | Requirement | Priority |
|----|-------------|----------|
| 052 | System SHALL oB MAY include a `worktree` section in the OAPayload instructing Rondo to use git worktree isolation for a task or set of tasks | SHOULD |
| 053 | System SHALL rondo creates worktrees using `git worktree add` with a branch name derived from the sprint_id: `rondo/{sprint_id}/{task_index}` | MUST |
| 054 | System SHALL each task dispatched to a worktree runs in that worktree's directory — file paths in the prompt are relative to the worktree root | MUST |
| 055 | System SHALL after all tasks in a worktree complete, Rondo attempts to merge the worktree branch back to the source branch | MUST |
| 056 | System SHALL if merge conflicts occur, Rondo records the conflict in the OAResult `worktree` section with `merge_status: "conflict"` and `conflicted_files: [...]`. Rondo does NOT resolve conflicts — OB or the human decides | MUST |
| 057 | System SHALL worktree cleanup: after merge (or conflict recording), Rondo removes the worktree (`git worktree remove`) and deletes the temporary branch | MUST |
| 058 | System SHALL post-merge shakedown: after a successful worktree merge, Rondo runs the post-gates from the round definition (typically a Caliber check) against the merged code. If the shakedown fails, the merge is flagged in the result as `shakedown_failed: true` | MUST |
| 059 | System SHALL worktree cleanup on error: if a task fails catastrophically (OOM, disk full), Rondo still attempts worktree cleanup. If cleanup fails, it logs a WARNING and records `cleanup_failed: true` in the result | MUST |

### Overnight Automation (OB-controlled scheduling)
| ID | Requirement | Priority |
|----|-------------|----------|
| 060 | System SHALL when OB provides a `schedule` section in the payload, Rondo's overnight scheduler processes sprints in order | MUST |
| 061 | System SHALL for each sprint in the schedule, Rondo: loads the OAPayload, executes the round, captures the OAResult, and saves it to the configured results directory | MUST |
| 062 | System SHALL sprint advancement: Rondo DOES NOT advance sprint state. Rondo returns the result. OB reads the result and decides whether to advance (BUILD → VERIFY → COMPLETE). This is OB's decision, not Rondo's | MUST |
| 063 | System SHALL all-gates-pass shortcut: when OB detects that all pre-gates, tasks, and post-gates passed for a sprint, OB MAY advance the sprint without human intervention. Rondo just reports — OB decides | SHOULD |
| 064 | System SHALL overnight failure: if a sprint's round fails, Rondo logs the failure, saves the partial OAResult, and moves to the next sprint in the schedule. Never halt the overnight pipeline for one sprint's failure | MUST |
| 065 | System SHALL morning report: Rondo generates its standard morning report (REQ-101 reqs 29-36) covering all sprints processed. OB MAY consume this report or generate its own from the individual OAResults | SHOULD |

### Feedback Loop (the compound intelligence path)
| ID | Requirement | Priority |
|----|-------------|----------|
| 066 | System SHALL rondo sends OAResult with a `learn` section containing: ai_went_wrong_update, ai_assumptions_update, ai_cost_update | MUST |
| 067 | System SHALL oB writes the learn data to its spec_sections table and build_improvement_metrics | MUST |
| 068 | System SHALL next build: OB reads stored learning, injects it into the new OAPayload's ai_memory section | MUST |
| 069 | System SHALL rondo reads ai_memory from the payload, formats it into the Claude prompt: "Previous builds found: {went_wrong}. Assumptions made: {assumptions}. Avoid repeating: {specific mistakes}." | MUST |
| 070 | System SHALL build N+1 is smarter than Build N. Rondo is the vehicle; OB is the memory. The compound effect comes from the loop, not from either product alone | MUST |

### Configuration in .ob/config.toml
| ID | Requirement | Priority |
|----|-------------|----------|
| 071 | System SHALL rondo reads these sections from OB's config: | MUST |

```toml
[rondo]
enabled = true                    # -- OB integration active
result_path = "reports/rondo/"    # -- where to save OAResults
workers = 4                       # -- parallel worker count
throttle_sec = 2                  # -- delay between task launches
[rondo.overnight]
mode = "standard"                 # -- minimal | standard | full
on_overage = "continue"           # -- continue | pause | stop
watchdog_timeout_sec = 120        # -- kill silent tasks after N seconds
[rondo.worktree]
enabled = false                   # -- worktree isolation off by default
cleanup_policy = "always"         # -- always | on_success | never
branch_prefix = "rondo"           # -- branch naming prefix
[models.build]
active = "claude-sonnet-4-6"     # -- Rondo reads model config from OB
[budget]
monthly_usd = 200.00              # -- Rondo checks budget before AI calls
```
| ID | Requirement | Priority |
|----|-------------|----------|
| 072 | System SHALL rondo ONLY reads these sections — it never writes to config | MUST |
| 073 | System SHALL missing sections → Rondo uses its own defaults from `rondo.toml` (standalone behavior) | MUST |
| 074 | System SHALL invalid values → WARNING + use default, never crash | MUST |
| 075 | System SHALL cOALESCE pattern applies: CLI flag → OB config → rondo.toml → hardcoded default | MUST |

---
## 4. Architecture / Data Flow

### Two Modes — Integration View

```
Standalone Mode (no OB):
  rondo run rounds/my_round.py
  └── load build_round() → dispatch tasks → return RoundResult
  └── no OB, no spec digest, no AI memory
  └── THIS ALWAYS WORKS

OB-Connected Mode:
  ob dispatch → rondo run --ob-payload payload.json --ob-result result.json
  └── reads spec digest + AI memory + round structure from payload
  └── dispatches tasks to Claude per payload instructions
  └── writes OAResult with field mapping
  └── OB stores, learns, feeds back
  └── requires: .ob/config.toml + API keys
```

### Data Flow Diagram

```
OB (Brain)                    Rondo (Muscle)                  Claude Code
 │                               │                               │
 │  OAPayload                    │                               │
 │  ┌─────────────────────────┐  │                               │
 │  │ dispatch: sprint_id,    │  │                               │
 │  │   actions, project      │  │                               │
 │  │ spec: digest (purpose,  │  │                               │
 │  │   reqs, rules, criteria)│  │                               │
 │  │ ai_memory: went_wrong,  │  │                               │
 │  │   assumptions, history  │  │                               │
 │  │ context: files, order   │  │                               │
 │  │ runtime: model, timeout │  │                               │
 │  │ worktree: config        │  │                               │
 │  │ schedule: sprint list   │  │                               │
 │  └─────────────────────────┘  │                               │
 ├──────────────────────────────►│                               │
 │                               │  pre-gates (check preconditions)
 │                               │                               │
 │                               │  for each task in round:      │
 │                               │    build prompt from 3-field   │
 │                               │    contract (Do, Read, Done)   │
 │                               │    + spec digest + ai_memory   │
 │                               ├──────────────────────────────►│
 │                               │  claude -p --model X           │
 │                               │  --output-format stream-json   │
 │                               │◄──────────────────────────────┤
 │                               │  structured result + tokens    │
 │                               │  + cost + cache stats          │
 │                               │                               │
 │                               │  post-gates (verify results)   │
 │                               │                               │
 │  OAResult                     │                               │
 │  ┌─────────────────────────┐  │                               │
 │  │ dispatch: actions_run,  │  │                               │
 │  │   timing                │  │                               │
 │  │ results[]: per-OA       │  │                               │
 │  │   status, exit_code,    │  │                               │
 │  │   timing, output,       │  │                               │
 │  │   findings, ai metadata │  │                               │
 │  │ gates[]: pre + post     │  │                               │
 │  │ worktree: merge_status  │  │                               │
 │  │ learn: went_wrong,      │  │                               │
 │  │   assumptions, cost     │  │                               │
 │  └─────────────────────────┘  │                               │
 │◄──────────────────────────────┤                               │
 │                               │                               │
 │  OB stores result:            │                               │
 │  ├── round_states             │                               │
 │  ├── sprint_results           │                               │
 │  ├── sprint_intelligence      │                               │
 │  ├── gate_checks              │                               │
 │  ├── findings           │                               │
 │  └── build_improvement_metrics│                               │
 │                               │                               │
 │  OB writes back to spec:      │                               │
 │  ├── ai_went_wrong            │                               │
 │  ├── ai_assumptions           │                               │
 │  └── ai_cost                  │                               │
 │                               │                               │
 │  NEXT BUILD: inject learned   │                               │
 │  data into new OAPayload     │                               │
 └──────────────────────────────►│  cycle repeats, getting       │
                                 │  smarter each time             │
```

### Overnight Automation Flow

```
OB (schedule builder)           Rondo (overnight executor)
 │                               │
 │  schedule: [                  │
 │    {sprint: S-001, payload},  │
 │    {sprint: S-002, payload},  │
 │    {sprint: S-003, payload},  │
 │  ]                            │
 ├──────────────────────────────►│
 │                               │  for each sprint:
 │                               │    ├── load OAPayload
 │                               │    ├── execute round
 │                               │    │    ├── pre-gates
 │                               │    │    ├── tasks (parallel if workers > 1)
 │                               │    │    ├── post-gates (Caliber shakedown)
 │                               │    │    └── worktree merge (if used)
 │                               │    ├── save OAResult to file
 │                               │    └── next sprint
 │                               │
 │                               │  generate morning report
 │                               │
 │  OB reads results:            │
 │  for each sprint:             │
 │    if all gates passed:       │
 │      advance sprint state     │  ← OB decides, not Rondo
 │    if gates failed:           │
 │      flag for human review    │
 │    write learn data to DB     │
 └───────────────────────────────┘
```

---

## 5. Data Model

Rondo's OB integration uses the same core dataclasses from REQ-100 (Round, Task, Gate,
RoundResult, TaskResult, GateResult, DispatchUsage). No OB-specific dataclasses exist.

The OAPayload and OAResult are JSON schemas, not Python dataclasses — they are the
serialization format for cross-product communication. Rondo parses OAPayload into its
internal dataclasses, executes, and serializes results back to OAResult JSON.

Key schema files: `rondo/schemas/oa-payload-v1.json`, `rondo/schemas/oa-result-v1.json`.

---

## 6. Data Boundary

**What Rondo produces (for OB):**

| Output | Format | OB Consumer |
|--------|--------|-------------|
| RoundResult (status, duration) | JSON in OAResult | round_states (OB-REQ-103) |
| TaskResult[] (per-task status, output) | JSON array in OAResult.results | sprint_results (OB-REQ-103) |
| DispatchUsage[] (tokens, cost, model) | JSON in OAResult.results[*].ai | sprint_intelligence (OB-SOP-100) |
| GateResult[] (pre-gate, post-gate) | JSON in OAResult.gates | gate_checks (OB-REQ-103) |
| Finding[] (issues found during execution) | JSON in OAResult.results[*].findings | findings (OB-REQ-105) |
| Generated files (code, specs, tests) | JSON in OAResult.results[*].output | file system (via OB import) |
| Worktree merge status | JSON in OAResult.worktree | sprint_results (merge metadata) |
| Learn data (mistakes, assumptions, cost) | JSON in OAResult.learn | spec_sections, build_improvement_metrics |
| Morning report | Markdown file | Human consumption (OB MAY also parse) |

**What Rondo consumes (from OB):**

| Input | Format | OB Producer |
|-------|--------|-------------|
| OAPayload (full task definition) | JSON file or stdin | OB-REQ-128 (Dispatch) |
| Spec digest (8 sections) | JSON in OAPayload.spec | OB-REQ-125 (Spec Management) |
| AI memory (went_wrong, assumptions) | JSON in OAPayload.ai_memory | OB-SOP-100 (Build Integration) |
| Build history (previous runs) | JSON array in OAPayload.ai_memory | build_improvement_metrics |
| Context (files, build order) | JSON in OAPayload.context | OB sprint planner |
| Runtime config (model, timeout) | JSON in OAPayload.runtime | OB config system |
| Worktree config | JSON in OAPayload.worktree | OB config system |
| Overnight schedule | JSON in OAPayload.schedule | OB scheduler |
| Budget config | TOML in .ob/config.toml | OB budget tracking |
| Model config | TOML in .ob/config.toml | OB config system |

---

## 7. MCP / API Interface

Future: OB MAY invoke Rondo via MCP tool per CORE-STD-021. The MCP tool would accept
OAPayload JSON and return OAResult JSON. This enables on-demand dispatch from any MCP
client without CLI subprocess overhead. Not in v1.0 scope — pipe and file transports first.

---

## 8. States & Modes

| State | Trigger | Behavior |
|-------|---------|----------|
| **Standalone** | No `.ob/config.toml` or `--ob-mode off` | Raw task JSON in, RoundResult out |
| **OB-Connected** | `.ob/config.toml` + `[rondo] enabled = true` | OAPayload in, OAResult out, field mapping active |
| **OB-Forced** | `--ob-mode on` CLI flag | OB-Connected regardless of config (requires config file) |
| **OB-Degraded** | OB config present but DB locked or incomplete | Execute normally, save result to file, warn |

Transitions: Standalone ↔ OB-Connected via config file presence. OB-Degraded is automatic
when OB infrastructure is unavailable. Recovery is automatic when OB becomes available.

**State Machine Type:** BIDIRECTIONAL
**Rationale:** States transition freely based on config and infrastructure: Standalone ↔ OB-Connected (config change), OB-Connected ↔ OB-Degraded (infrastructure availability). Recovery is automatic.
**Rollback:** Remove `.ob/config.toml` to return to Standalone. OB-Degraded auto-recovers when OB becomes available.

---

## 9. Configuration

See section 3, "Configuration in .ob/config.toml" (reqs 71-75) for the full TOML schema.
COALESCE resolution order: CLI flag → `.ob/config.toml` → `rondo.toml` → hardcoded default.

---

## 10. Rules & Constraints

1. **Contract versioning:** Every OAPayload and OAResult has `$contract` + `$version`. Rondo MUST reject unknown versions.
2. **Backward compatibility:** New optional fields can be added (minor version). Removing or changing required fields = major version bump.
3. **NAMING-MAP is the bridge:** Field mapping lives in NAMING-MAP.md. Both this spec and OB-IFS-102 reference it. Change one, change both.
4. **Rondo is the AUTHORITY on execution data.** OB stores it and learns from it. But Rondo defines what a TaskResult is, what a DispatchUsage contains, what convergence metrics look like.
5. **OB is the AUTHORITY on methodology data.** Rondo doesn't know about orbits, methodology phases, or spec categories. It receives a payload and executes it. Round structures in the payload are OB's design.
6. **Rondo is the AUTHORITY on worktree lifecycle.** OB tells Rondo to use worktrees. Rondo creates, builds, merges, and cleans up. OB never runs `git worktree` commands.
7. **Sprint state belongs to OB.** Rondo reports task results. OB advances sprints. Rondo never writes `sprint.status = 'complete'`.
8. **Schedule ordering is OB's responsibility.** OB sends sprints in the right order. Rondo processes them in the order received. If OB sends them wrong, Rondo doesn't reorder.
9. **Results are immutable.** Once Rondo writes an OAResult, it never modifies it. If a re-run is needed, a new OAResult is produced with a new timestamp.
10. **Every dispatch costs money.** Rondo MUST track and return accurate cost data. OB's budget enforcement depends on these numbers.

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Reliability | Zero data loss — results always saved to file | OB depends on complete OAResults for learning |
| Latency | <1s overhead beyond AI response time | OAPayload parsing + OAResult serialization must be fast |
| Isolation | Zero direct DB access across product boundary | Independent development, independent deployment |
| Testability | OAPayload/OAResult are plain JSON — fully testable without OB running | Contract tests don't need infrastructure |
| Backward compat | New optional fields, never break existing consumers | OB and Rondo may be at different versions |

---

## 12. Shared Patterns

- **COALESCE:** CLI flag → OB config → rondo.toml → default. Used for all config resolution.
- **Dual-Path-With-Alerting:** OB-connected is the primary path. Standalone is the fallback.
  When fallback activates (OB unavailable), Rondo ALERTs via warning log.
- **Contract envelope:** Every JSON payload has `$contract` + `$version` at the root.
  Enables forward-compatible parsing and version negotiation.
- **Immutable results:** OAResult written once, never modified. Re-runs produce new files.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| OB → Rondo | OB-IFS-102 | Inbound | OAPayload JSON |
| Rondo → OB | This spec | Outbound | OAResult JSON |
| Rondo → Claude | IFS-100 | Outbound | CLI subprocess |
| Rondo → Providers | REQ-109 | Outbound | Provider adapter interface |
| Rondo → File system | Internal | Outbound | OAResult file, morning report |
| Rondo ← Config | STD-109 | Internal | TOML / COALESCE |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-IFS-001 | Universal payload/transport/isolation patterns — this spec implements them |
| CORE-STD-005 | mTLS for HTTPS transport |
| CORE-STD-010 (Error Resilience) | Task failure → continue round, never crash pipeline |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Dispatch events, gate results logged as trackerdata entries |
| CORE-STD-021 (MCP Standard) | Future MCP tool interface for on-demand OB→Rondo dispatch |
| STD-108 | Error handling patterns for task/gate failures |
| STD-109 | COALESCE config resolution |

---

## 15. Self-Correction

- OAPayload version mismatch → Rondo rejects with supported version list, enabling OB
  to downgrade or upgrade its payload format.
- Field mapping drift → NAMING-MAP.md is the single source of truth. Automated contract
  tests compare Rondo dataclass fields against NAMING-MAP entries.
- OB DB locked → Rondo saves result to file and logs recovery command
  (`ob store-result {path}`), enabling manual import after DB recovers.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | OAPayload JSON is small enough to pass via stdin pipe | May need file-based handoff for payloads with large spec digests or many files |
| A2 | Rondo can detect OB via `.ob/config.toml` presence | May need explicit env var or CLI flag |
| A3 | Field mapping is stable across OAPayload/OAResult versions | May need adapter layer for version translation |
| A4 | Rondo's RoundResult/TaskResult is rich enough for OB's needs | May need OB-specific extension fields in the result |
| A5 | Git worktree is available on all target systems | May need fallback to directory copies on systems without git worktree support |
| A6 | Overnight sprints are independent enough to process sequentially | If sprints have dependencies, OB must encode that in schedule ordering |
| A7 | Claude Code's `--output-format stream-json` provides accurate token/cost data | If Anthropic changes the format, IFS-100 and dispatch.py need updates |
| A8 | Post-merge shakedown via Caliber is fast enough to run per-worktree merge | If shakedown is slow, may need to batch post-merge checks |

---

## 17. Success Criteria

| Scenario | Expected Result | Verification |
|----------|----------------|-------------|
| Standalone run (no OB) | Rondo dispatches tasks, returns RoundResult, no OB fields | Test |
| OB-connected run with payload | Rondo reads OAPayload, executes round, returns OAResult | Test |
| OAResult field mapping | Every Rondo field maps to correct OB column per NAMING-MAP | Test against NAMING-MAP |
| OB DB locked during run | Rondo completes, saves result to file with WARNING | Test |
| Malformed OAPayload | Rondo rejects with exit code 2 + structured error JSON | Test |
| Version mismatch | Rondo rejects with clear version error | Test |
| Feedback loop round trip | Build N learn data → OB stores → Build N+1 reads it in ai_memory | Integration test |
| Worktree create + merge | Rondo creates worktree, runs task, merges back, cleans up | Test |
| Worktree merge conflict | Rondo reports conflict with file list, does not resolve | Test |
| Post-merge shakedown fail | Rondo flags `shakedown_failed: true` in result | Test |
| Overnight 3 sprints, 1 fails | Failed sprint logged, other 2 complete, morning report generated | Test |
| Sprint not advanced by Rondo | After overnight run, sprint states unchanged in OB until OB processes results | Integration test |
| Standalone → OB transition | Adding .ob/config.toml activates OB mode, zero Rondo code changes | Test |
| Pipe transport | `ob dispatch \| rondo run --ob-payload -` works end-to-end | Integration test |
| File transport | `--ob-payload file.json --ob-result result.json` works | Test |
| Cost tracking accuracy | DispatchUsage.cost_usd matches Claude stream-json cost data | Test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| OAPayload parser | 2-3 days — JSON schema validation + dataclass mapping |
| OAResult serializer | 1-2 days — reverse mapping from dataclasses to JSON |
| OB mode detection | 0.5 day — config file check + CLI flag |
| Worktree manager | 2-3 days — git worktree lifecycle + merge + cleanup |
| Overnight scheduler | 1-2 days — sequential sprint processing + morning report |
| Contract tests | 2 days — field mapping validation against NAMING-MAP |
| Integration tests | 2-3 days — end-to-end with mock OB payloads |
| Total | ~12-16 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | OAPayload parsing, OAResult serialization, field mapping | 20 |
| Integration | Full round with mock OB payload → OAResult | 10 |
| Contract | Field mapping matches NAMING-MAP.md exactly | 17 (one per mapped field) |
| Error | Malformed payload, version mismatch, DB locked, network timeout | 8 |
| Worktree | Create, merge, conflict, cleanup, shakedown | 8 |
| Overnight | Multi-sprint schedule, failure handling, morning report | 6 |
| Mode | Standalone, OB-connected, OB-forced, OB-degraded | 4 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| OAPayload too large for stdin | Dispatch fails | Fall back to file transport |
| OB DB locked mid-overnight | Results not stored | Save to file, log recovery command |
| Worktree merge conflict | Code not integrated | Report conflict, OB/human resolves |
| Claude CLI crashes mid-task | Partial results | Record error status, continue to next task |
| NAMING-MAP drift | Field mapping broken | Automated contract tests catch on every build |
| OAPayload version unsupported | Dispatch rejected | Clear error message with supported versions |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core engine defines Round, Task, Gate, RoundResult, TaskResult, DispatchUsage, GateResult |
| REQ-101 | Automation defines parallel dispatch, overnight scheduler, morning report |
| IFS-100 | Claude CLI interface (how Rondo calls `claude -p`) |
| STD-108 | Error resilience (task failure → continue, not crash) |
| STD-109 | Configuration (COALESCE pattern, TOML loading) |
| OB-REQ-128 | OAPayload/OAResult contract format definition |
| OB-IFS-102 | OB's side of the integration (how OB calls Rondo) |
| OB-REQ-103 | Sprint lifecycle (Rondo reports to, but never modifies) |
| NAMING-MAP.md | Field mapping authority |
| CONTRACTS.md | JSON format examples |
| DEC-017 | OB standalone standards — both products work independently |

| Used By | Why |
|---------|-----|
| OB-SOP-100 | Build Integration consumes Rondo's OAResult for sprint tracking |
| OB-REQ-103 | Sprint Management uses Rondo results to decide state transitions |
| OB-REQ-105 | Finding Management receives findings discovered during AI execution |
| OB-REQ-107 | Quality tracking receives gate results and convergence metrics |
| OB-REQ-128 | Dispatch engine needs to know what format Rondo accepts |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | JSON contracts, never direct DB access | 2026-03-18 | Isolation. Rondo and OB can be developed independently. Same principle as IFS-102 (Caliber) D1. |
| D2 | OB mode detection via .ob/config.toml | 2026-03-18 | Simple, no magic. File exists = OB is here. Same mechanism as Caliber. |
| D3 | Rondo is the execution authority, OB is the methodology authority | 2026-03-18 | Clear ownership. Rondo knows HOW to dispatch. OB knows WHAT to dispatch and WHY. |
| D4 | Rondo never advances sprint state | 2026-03-18 | Sprint lifecycle is OB's domain. Rondo reports; OB decides. Prevents split-brain state. |
| D5 | Rondo completes even if OB is down | 2026-03-18 | Never block AI execution on infrastructure. Results are saved to file as fallback. |
| D6 | Worktree lifecycle owned by Rondo, worktree policy owned by OB | 2026-03-18 | OB says "use worktrees." Rondo does the git work. OB never touches `git worktree`. |
| D7 | Overnight schedule ordering is OB's responsibility | 2026-03-18 | Rondo processes in order received. If dependencies exist, OB encodes them by ordering. |
| D8 | Same OAPayload/OAResult format for standalone and OB-connected | 2026-03-18 | One format, two modes. Standalone just leaves OB-specific fields null. Zero format branching. |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should OAPayload support streaming (chunked) delivery for very large payloads? | Affects transport design for batch mode with many files | OPEN |
| Q2 | Should Rondo cache OAPayload spec digests across runs for the same spec? | Could reduce payload size for repeated builds of same spec | OPEN |
| Q3 | Should worktree branch names include a timestamp for uniqueness? | Prevents collision if same sprint is re-run before cleanup | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **OAPayload** | JSON contract sent from OB to Rondo containing everything needed to execute OAs |
| **OAResult** | JSON contract sent from Rondo to OB containing execution results |
| **OA** | Orbital Action — a unit of AI work within a sprint |
| **Worktree** | Git worktree providing filesystem isolation for parallel builds |
| **Spec digest** | Compressed spec content (purpose, reqs, rules, criteria) sent in OAPayload |
| **Compound learning** | Build N+1 is smarter than Build N via the ai_memory feedback loop |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| NAMING-MAP drift breaks field mapping | Medium | OB stores wrong data | Contract tests on every build |
| OAPayload schema evolves faster than Rondo | Low | Version mismatch rejects | Strict versioning, clear error messages |
| Worktree conflicts block overnight pipeline | Medium | Sprint incomplete | Continue to next sprint, report conflict |
| Large OAPayloads cause memory pressure | Low | OOM on small machines | File-based transport as fallback |

---

## 26. External Scan

No external products were found with a comparable AI-dispatch-to-methodology-engine contract.
Closest analogy: CI/CD runner protocols (GitLab Runner ↔ GitLab, GitHub Actions runner ↔ GitHub).
The OAPayload/OAResult pattern is similar to job definitions/results in those systems but
adds AI-specific fields (tokens, cost, ai_memory) and methodology-specific fields (spec digest).

---

## 27. Security Considerations

- OAPayload may contain source code, spec content, and AI prompts. Transport must protect
  confidentiality: pipe/file (local, no network), Unix socket (local), HTTPS (mTLS required).
- API keys are never in OAPayload — Rondo retrieves them from Keychain per REQ-109.
- OAResult may contain generated code. Stored as files on disk with project-appropriate permissions.
- Queue transport (future) must use encrypted channels and authenticated producers/consumers.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| OAPayload parse time | <100ms for typical payload | JSON parse + schema validation |
| OAResult serialize time | <50ms | Dataclass → JSON conversion |
| Worktree create/cleanup | <5s each | Git operations, disk I/O |
| Overnight throughput | Process 10+ sprints per night | Sequential, ~30min per sprint average |
| Memory per worker | <200MB | Payload in memory + AI response buffering |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not yet populated. Will be filled during first build sprint implementing OB integration.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- This is the largest Rondo spec (75 requirements) because OB integration touches every
  subsystem: dispatch, gates, worktrees, overnight, config, error handling.
- Session 79 created v1.0 with all 75 requirements. Session 84 added sections 7-8, 11-15,
  18-20, 23-34 to reach 35-section compliance.
- The feedback loop (reqs 66-70) is the most architecturally significant part — it turns
  two standalone products into a compound intelligence system.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| OB-to-Rondo dispatch contract | THEORY | Specced for OB triggering Rondo tasks | Phase 2 build |
| Task result reporting to OB | THEORY | Specced for structured results back to OB DB | Phase 2 build |
| Learning feedback loop | THEORY | Specced for OB learning from Rondo outcomes | Phase 3 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-18 | Initial spec. 75 requirements across 12 sections. OB mode detection, input contract (OAPayload with spec digest, AI memory, worktree config, overnight schedule), output contract (OAResult with RoundResult, TaskResult, DispatchUsage, GateResult, worktree merge status, learn section), field mapping (17 fields to 7 OB tables), 5-level transport progression (pipe → file → socket → HTTPS → queue), isolation boundaries (6 rules), standalone behavior (4 reqs), worktree management (8 reqs), overnight automation (6 reqs), feedback loop (5 reqs), OB config (5 reqs), 8 assumptions, 16 success criteria, 8 decisions. Session 79. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
