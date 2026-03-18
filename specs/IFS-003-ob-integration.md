# IFS-003: OB Integration Contract

*How Rondo talks to OB — what it sends, what it receives, when it connects, and what it never touches. The execution muscle plugged into the methodology brain.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Architect:** Mark G. Hubers — HubersTech
**Depends on:** REQ-001 (Core), REQ-002 (Automation)
**Connects to:** OB-IFS-003 (External Integration), OB-33 (Dispatch), OB-05 (Sprint)
**References:** CONTRACTS.md (JSON format), NAMING-MAP.md (field mapping)
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
- OB's internal storage (OB-01 owns that)
- OB's dispatch engine (OB-33 owns that)
- How OB calls Rondo (OB-IFS-003 owns that)
- Caliber integration (Caliber-IFS-003 or Rondo's internal Caliber calls)
- Claude Code CLI details (IFS-001 owns that)
- Rondo's engine internals (REQ-001 owns that)

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

### OB Mode Detection (when does integration activate?)

1. Rondo detects OB by checking for `.ob/config.toml` in the project root.
2. If `.ob/config.toml` exists AND `[rondo] enabled = true`: OB integration mode activates automatically.
3. If `.ob/config.toml` exists but `[rondo] enabled = false`: standalone mode (OB present but Rondo integration off).
4. If `.ob/config.toml` does not exist: standalone mode (no OB, Rondo works with raw task JSON).
5. Manual override: `--ob-mode on|off` CLI flag forces integration mode regardless of config.
6. `rondo run --ob-mode on` without `.ob/config.toml` present → ERROR: "OB config not found at .ob/config.toml"

### What Rondo Receives from OB (Input Contract)

7. Rondo receives an `OAPayload` ($contract: "OAPayload", $version: "1.0") containing everything needed to execute one or more OAs.
8. The payload `dispatch` section specifies: sprint_id, project, actions (OA IDs to run), triggered_by, dispatched_at.
9. The payload `spec` section provides a spec digest: spec_id, digest_hash, purpose, requirements, data_model, rules, success_criteria — Rondo uses these as context for AI prompts.
10. The payload `ai_memory` section provides learning from previous builds: ai_went_wrong (mistakes to avoid), ai_assumptions (design choices made), ai_review (independent reviewer findings), build_history (array of {build, errors, iterations, cost}).
11. The payload `context` section provides: language, mode (single/batch), file_to_build (or files for batch), existing_files (SHA hashes), build_order, current_position.
12. The payload `runtime` section provides: oa_runtime (container ID), container_image, model, tool_mode, timeout_sec, max_tokens.
13. When `--ob-payload <file>` is provided, Rondo reads the full OAPayload from that file instead of building its own Round from a Python definition.
14. When `--ob-payload -` is provided, Rondo reads the OAPayload from stdin (pipeline mode: `ob dispatch | rondo run --ob-payload -`).
15. Rondo MUST accept round definitions from the payload — OB defines the round structure (tasks, gates, ordering), Rondo executes it. Rondo does not decide WHAT to do; OB decides that.
16. Worktree isolation config: the payload MAY include a `worktree` section specifying `enabled: true`, `branch_prefix`, and `cleanup_policy`. Rondo creates worktrees per these settings.
17. Overnight batch schedules: OB MAY send a `schedule` section with an ordered list of sprint_ids and their associated OAPayloads. Rondo's overnight scheduler processes them in order.

### What Rondo Returns to OB (Output Contract)

18. After execution, Rondo produces a JSON result matching the `OAResult` contract ($contract: "OAResult", $version: "1.0").
19. The result `dispatch` section returns: sprint_id, actions_run, started_at, completed_at, duration_ms.
20. Per-OA results as entries in the `results` array: oa_id, status (done/partial/error/skipped), exit_code, timing (queued_at, started_at, completed_at, duration_ms, queue_wait_ms, api_duration_ms), output (files_created, lines_generated, raw_stdout, raw_stderr, log_file), findings, ai metadata, metrics.
21. AI cost data as `DispatchUsage` per task: model_used, input_tokens, output_tokens, cache_read_tokens, cache_create_tokens, cost_usd, duration_ms, num_turns. OB stores these in `sprint_intelligence`.
22. Gate results: for each pre-gate and post-gate, Rondo returns `GateResult` with gate name, passed (bool), detail (string), duration_ms. OB stores in `gate_checks`.
23. Generated content: when an OA produces code, specs, or tests, the full file content is included in `output.files_created` with paths relative to the project root and raw content or SHA reference.
24. The `learn` section returns feedback for the compound loop: ai_went_wrong_update (new mistakes discovered), ai_assumptions_update (new design choices), ai_cost_update (tokens, cost_usd, iterations).
25. Worktree merge status: when worktree isolation was used, the result includes a `worktree` section with merge_status (merged/conflict/pending), conflicted_files (if any), and worktree_path.
26. Convergence data: when a task ran through fix-check iterations (via Caliber), the result includes iterations count, errors_before, errors_after, converged (bool).

### Field-Level Mapping (Rondo → OB)

27. Field mapping is the AUTHORITATIVE contract between the two products:

| Rondo Dataclass.Field | OB Table.Column | Notes |
|----------------------|----------------|-------|
| `RoundResult.status` | `round_states.status` | done/partial/error/skipped (NAMING-MAP vocabulary) |
| `RoundResult.duration_sec` | `round_states.duration_sec` | Wall-clock seconds for the full round |
| `TaskResult.status` | `sprint_results.status` | Per-task status |
| `TaskResult.task_name` | `sprint_results.task_name` | Matches OA name from payload |
| `TaskResult.parsed_result` | `sprint_results.result_json` | Structured JSON from Claude response |
| `TaskResult.raw_stdout` | `sprint_results.raw_output` | Full stdout capture |
| `TaskResult.findings[]` | `audit_findings.*` | Findings discovered during execution |
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

28. Field mapping changes require BOTH specs updated (this spec + NAMING-MAP.md) — never change one without the other.
29. New fields: add to NAMING-MAP.md first, then update both specs. NAMING-MAP is the bridge.

### Isolation Boundaries (what Rondo NEVER does)

30. Rondo NEVER writes directly to OB's database — all data flows through JSON contracts (OAResult).
31. Rondo NEVER reads OB's internal tables — spec digests, AI memory, and sprint context come via OAPayload, not DB queries.
32. Rondo NEVER calls OB's internal Python modules — no `from ob_queries import` in Rondo code.
33. Rondo NEVER modifies `.ob/config.toml` — it reads config, OB writes config.
34. Rondo NEVER advances sprint state — OB decides when a sprint moves from BUILD to VERIFY to COMPLETE. Rondo reports results. OB decides next steps.
35. Rondo NEVER bypasses OB's gates — if OB includes a gate in the payload, Rondo executes it and reports the result. Rondo does not skip gates or override gate failures.
36. Rondo CAN run without OB present — standalone mode must always work, even if OB is uninstalled. Give Rondo a task, it dispatches, it returns a result. No OB needed.

### Transport (how OB and Rondo physically connect)

37. Transport is progressive — same contract, different pipes:

| Transport | When | How | Latency |
|-----------|------|-----|---------|
| **Pipe (stdin/stdout)** | Local, same machine | `ob dispatch \| rondo run --ob-payload -` | Microseconds |
| **File** | Local, async | `ob dispatch > payload.json && rondo run --ob-payload payload.json --ob-result result.json` | Milliseconds |
| **Unix socket** | Local, service mode | Rondo listens on socket, OB connects | Milliseconds |
| **HTTPS** | Remote, networked | OB POST to `https://rondo.internal/run`, mTLS required | Seconds |
| **Queue** | Remote, async | OB publishes to queue, Rondo worker consumes | Seconds+ |

38. Start with pipe and file (simplest). Add HTTPS when Rondo runs on a different machine. Queue when scaling to multiple Rondo workers processing different sprints.
39. Transport is TRANSPARENT to the contract — OAPayload JSON is identical regardless of transport. Change the pipe, not the data.
40. HTTPS transport requires mTLS (mutual TLS) — both OB and Rondo authenticate. Aligns with OB-STD-005 rule 16.
41. Queue transport preserves ordering per-sprint — OAs for the same sprint must complete in order. Different sprints MAY be dispatched to different Rondo workers.

### Error Handling (when OB is unavailable)

42. OB DB locked → Rondo completes its execution, writes OAResult to file, logs WARNING: "OB unavailable — results saved to {path}, import with `ob store-result {path}`"
43. OB config missing required fields → Rondo falls back to standalone mode, logs WARNING: "OB config incomplete — running standalone"
44. OAPayload malformed → Rondo rejects with exit code 2 and structured error: `{"error": "Invalid payload", "detail": "{specifics}", "contract": "OAPayload", "version": "1.0"}`
45. OAPayload version mismatch (payload $version != supported) → Rondo rejects with clear error: "Unsupported OAPayload version: {v}. Supported: 1.0"
46. Network timeout (HTTPS/queue transport) → Rondo completes locally, queues result for later delivery. Result file is the fallback — never lose work.
47. Claude CLI failure mid-round → Rondo records the failed task as status "error" with stderr content, continues to next task in the round (STD-020 error resilience), and includes the partial round result in the OAResult.

### Standalone Behavior (Rondo without OB)

48. Without OB, Rondo works with Python round definitions (REQ-001): a `build_round()` function returns a `Round` object, Rondo dispatches tasks and returns a `RoundResult`.
49. Standalone results use the same JSON format as OB-connected results. The only difference: no `dispatch.sprint_id` (populated as null), no `spec` digest in the payload.
50. Standalone Rondo can still accept `--ob-payload` with a hand-crafted JSON file — useful for testing the OB integration path without running OB.
51. Transition from standalone to OB-connected requires ZERO code changes in Rondo — only adding `.ob/config.toml` with `[rondo] enabled = true`.

### Worktree Management (parallel build isolation)

52. OB MAY include a `worktree` section in the OAPayload instructing Rondo to use git worktree isolation for a task or set of tasks.
53. Rondo creates worktrees using `git worktree add` with a branch name derived from the sprint_id: `rondo/{sprint_id}/{task_index}`.
54. Each task dispatched to a worktree runs in that worktree's directory — file paths in the prompt are relative to the worktree root.
55. After all tasks in a worktree complete, Rondo attempts to merge the worktree branch back to the source branch.
56. If merge conflicts occur, Rondo records the conflict in the OAResult `worktree` section with `merge_status: "conflict"` and `conflicted_files: [...]`. Rondo does NOT resolve conflicts — OB or the human decides.
57. Worktree cleanup: after merge (or conflict recording), Rondo removes the worktree (`git worktree remove`) and deletes the temporary branch.
58. Post-merge shakedown: after a successful worktree merge, Rondo runs the post-gates from the round definition (typically a Caliber check) against the merged code. If the shakedown fails, the merge is flagged in the result as `shakedown_failed: true`.
59. Worktree cleanup on error: if a task fails catastrophically (OOM, disk full), Rondo still attempts worktree cleanup. If cleanup fails, it logs a WARNING and records `cleanup_failed: true` in the result.

### Overnight Automation (OB-controlled scheduling)

60. When OB provides a `schedule` section in the payload, Rondo's overnight scheduler processes sprints in order.
61. For each sprint in the schedule, Rondo: loads the OAPayload, executes the round, captures the OAResult, and saves it to the configured results directory.
62. Sprint advancement: Rondo DOES NOT advance sprint state. Rondo returns the result. OB reads the result and decides whether to advance (BUILD → VERIFY → COMPLETE). This is OB's decision, not Rondo's.
63. All-gates-pass shortcut: when OB detects that all pre-gates, tasks, and post-gates passed for a sprint, OB MAY advance the sprint without human intervention. Rondo just reports — OB decides.
64. Overnight failure: if a sprint's round fails, Rondo logs the failure, saves the partial OAResult, and moves to the next sprint in the schedule. Never halt the overnight pipeline for one sprint's failure.
65. Morning report: Rondo generates its standard morning report (REQ-002 reqs 29-36) covering all sprints processed. OB MAY consume this report or generate its own from the individual OAResults.

### Feedback Loop (the compound intelligence path)

66. Rondo sends OAResult with a `learn` section containing: ai_went_wrong_update, ai_assumptions_update, ai_cost_update.
67. OB writes the learn data to its spec_sections table and build_improvement_metrics.
68. Next build: OB reads stored learning, injects it into the new OAPayload's ai_memory section.
69. Rondo reads ai_memory from the payload, formats it into the Claude prompt: "Previous builds found: {went_wrong}. Assumptions made: {assumptions}. Avoid repeating: {specific mistakes}."
70. Build N+1 is smarter than Build N. Rondo is the vehicle; OB is the memory. The compound effect comes from the loop, not from either product alone.

### Configuration in .ob/config.toml

71. Rondo reads these sections from OB's config:

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

72. Rondo ONLY reads these sections — it never writes to config.
73. Missing sections → Rondo uses its own defaults from `rondo.toml` (standalone behavior).
74. Invalid values → WARNING + use default, never crash.
75. COALESCE pattern applies: CLI flag → OB config → rondo.toml → hardcoded default.

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
 │  ├── audit_findings           │                               │
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

## 6. Data Boundary

**What Rondo produces (for OB):**

| Output | Format | OB Consumer |
|--------|--------|-------------|
| RoundResult (status, duration) | JSON in OAResult | round_states (OB-05) |
| TaskResult[] (per-task status, output) | JSON array in OAResult.results | sprint_results (OB-05) |
| DispatchUsage[] (tokens, cost, model) | JSON in OAResult.results[*].ai | sprint_intelligence (OB-12) |
| GateResult[] (pre-gate, post-gate) | JSON in OAResult.gates | gate_checks (OB-05) |
| Finding[] (issues found during execution) | JSON in OAResult.results[*].findings | audit_findings (OB-07) |
| Generated files (code, specs, tests) | JSON in OAResult.results[*].output | file system (via OB import) |
| Worktree merge status | JSON in OAResult.worktree | sprint_results (merge metadata) |
| Learn data (mistakes, assumptions, cost) | JSON in OAResult.learn | spec_sections, build_improvement_metrics |
| Morning report | Markdown file | Human consumption (OB MAY also parse) |

**What Rondo consumes (from OB):**

| Input | Format | OB Producer |
|-------|--------|-------------|
| OAPayload (full task definition) | JSON file or stdin | OB-33 (Dispatch) |
| Spec digest (8 sections) | JSON in OAPayload.spec | OB-30 (Spec Management) |
| AI memory (went_wrong, assumptions) | JSON in OAPayload.ai_memory | OB-12 (Build Integration) |
| Build history (previous runs) | JSON array in OAPayload.ai_memory | build_improvement_metrics |
| Context (files, build order) | JSON in OAPayload.context | OB sprint planner |
| Runtime config (model, timeout) | JSON in OAPayload.runtime | OB config system |
| Worktree config | JSON in OAPayload.worktree | OB config system |
| Overnight schedule | JSON in OAPayload.schedule | OB scheduler |
| Budget config | TOML in .ob/config.toml | OB budget tracking |
| Model config | TOML in .ob/config.toml | OB config system |

---

## 10. Rules & Constraints

1. **Contract versioning:** Every OAPayload and OAResult has `$contract` + `$version`. Rondo MUST reject unknown versions.
2. **Backward compatibility:** New optional fields can be added (minor version). Removing or changing required fields = major version bump.
3. **NAMING-MAP is the bridge:** Field mapping lives in NAMING-MAP.md. Both this spec and OB-IFS-003 reference it. Change one, change both.
4. **Rondo is the AUTHORITY on execution data.** OB stores it and learns from it. But Rondo defines what a TaskResult is, what a DispatchUsage contains, what convergence metrics look like.
5. **OB is the AUTHORITY on methodology data.** Rondo doesn't know about orbits, methodology phases, or spec categories. It receives a payload and executes it. Round structures in the payload are OB's design.
6. **Rondo is the AUTHORITY on worktree lifecycle.** OB tells Rondo to use worktrees. Rondo creates, builds, merges, and cleans up. OB never runs `git worktree` commands.
7. **Sprint state belongs to OB.** Rondo reports task results. OB advances sprints. Rondo never writes `sprint.status = 'complete'`.
8. **Schedule ordering is OB's responsibility.** OB sends sprints in the right order. Rondo processes them in the order received. If OB sends them wrong, Rondo doesn't reorder.
9. **Results are immutable.** Once Rondo writes an OAResult, it never modifies it. If a re-run is needed, a new OAResult is produced with a new timestamp.
10. **Every dispatch costs money.** Rondo MUST track and return accurate cost data. OB's budget enforcement depends on these numbers.

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
| A7 | Claude Code's `--output-format stream-json` provides accurate token/cost data | If Anthropic changes the format, IFS-001 and dispatch.py need updates |
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

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-001 | Core engine defines Round, Task, Gate, RoundResult, TaskResult, DispatchUsage, GateResult |
| REQ-002 | Automation defines parallel dispatch, overnight scheduler, morning report |
| IFS-001 | Claude CLI interface (how Rondo calls `claude -p`) |
| STD-020 | Error resilience (task failure → continue, not crash) |
| STD-021 | Configuration (COALESCE pattern, TOML loading) |
| OB-33 | OAPayload/OAResult contract format definition |
| OB-IFS-003 | OB's side of the integration (how OB calls Rondo) |
| OB-05 | Sprint lifecycle (Rondo reports to, but never modifies) |
| NAMING-MAP.md | Field mapping authority |
| CONTRACTS.md | JSON format examples |
| DEC-017 | OB standalone standards — both products work independently |

| Used By | Why |
|---------|-----|
| OB-12 | Build Integration consumes Rondo's OAResult for sprint tracking |
| OB-05 | Sprint Management uses Rondo results to decide state transitions |
| OB-07 | Finding Management receives findings discovered during AI execution |
| OB-09 | Quality tracking receives gate results and convergence metrics |
| OB-33 | Dispatch engine needs to know what format Rondo accepts |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | JSON contracts, never direct DB access | 2026-03-18 | Isolation. Rondo and OB can be developed independently. Same principle as Caliber-IFS-003 D1. |
| D2 | OB mode detection via .ob/config.toml | 2026-03-18 | Simple, no magic. File exists = OB is here. Same mechanism as Caliber. |
| D3 | Rondo is the execution authority, OB is the methodology authority | 2026-03-18 | Clear ownership. Rondo knows HOW to dispatch. OB knows WHAT to dispatch and WHY. |
| D4 | Rondo never advances sprint state | 2026-03-18 | Sprint lifecycle is OB's domain. Rondo reports; OB decides. Prevents split-brain state. |
| D5 | Rondo completes even if OB is down | 2026-03-18 | Never block AI execution on infrastructure. Results are saved to file as fallback. |
| D6 | Worktree lifecycle owned by Rondo, worktree policy owned by OB | 2026-03-18 | OB says "use worktrees." Rondo does the git work. OB never touches `git worktree`. |
| D7 | Overnight schedule ordering is OB's responsibility | 2026-03-18 | Rondo processes in order received. If dependencies exist, OB encodes them by ordering. |
| D8 | Same OAPayload/OAResult format for standalone and OB-connected | 2026-03-18 | One format, two modes. Standalone just leaves OB-specific fields null. Zero format branching. |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-18 | Initial spec. 75 requirements across 12 sections. OB mode detection, input contract (OAPayload with spec digest, AI memory, worktree config, overnight schedule), output contract (OAResult with RoundResult, TaskResult, DispatchUsage, GateResult, worktree merge status, learn section), field mapping (17 fields to 7 OB tables), 5-level transport progression (pipe → file → socket → HTTPS → queue), isolation boundaries (6 rules), standalone behavior (4 reqs), worktree management (8 reqs), overnight automation (6 reqs), feedback loop (5 reqs), OB config (5 reqs), 8 assumptions, 16 success criteria, 8 decisions. Session 79. |
