# Rondo-REQ-114: Prompt Pipelines — prompt programs with plan/apply discipline

*A prompt program is code: declared steps, typed outputs, hard budgets, a plan
before any spend, and an audit trail after. This is what Rondo is FOR.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-06-10 | **Status:** BUILT (verified 2026-06-14, RONDO-432)
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Depends on:** REQ-100 (Core), REQ-109 (Providers), REQ-111 (Smart Dispatch), STD-105 (cost), STD-113 (Audit), STD-114 (Sanitization), REQ-113 (matrix — placeholder/budget precedents)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):** Rondo's thesis is PROMPT CODING —
prompts treated like programs, not chat. Today the building blocks exist
(rounds, schemas, budgets, dry-run, audit) but multi-step composition is a
thin demo: `rondo_chain` blindly appends step N's output to step N+1's
prompt, has no per-step contracts, no budget ceiling, discards raw outputs,
and lets a FAILED step's empty output flow silently onward. This spec defines
the real thing: a declarative pipeline — named steps, explicit data wiring,
typed step outputs, per-step models, one hard budget, plan-before-apply —
executed through the SAME guarded dispatch path as everything else (audit,
sanitize, envelopes, quarantine all apply per step automatically).

Mental model: **Terraform for prompts.** `plan` shows every step, model, and
cost estimate before a cent is spent; `apply` runs it with a hard ceiling;
the state (every step's full output + cost + status) is preserved and audited.

**IN scope:** pipeline YAML definition + loader, named-step output wiring via
placeholders, per-step model/contract/failure policy, pipeline budget,
plan mode, sequential execution engine, result envelope, runnable flagship
example, CLI subcommand.
**OUT of scope (v1):** parallel step graphs (DAGs), loops/conditionals,
MCP tool wiring (rides CLI/API first), .py pipeline files (YAML only — the
round-trust lesson), streaming step output.

---

## 2. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Definition & loading

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 001 | Pipeline file is YAML (safe_load only): `name`, `budget_usd`, `steps[]`; unknown top-level or step fields REJECTED with a clear error | MUST | Loader test |
| 002 | Step fields: `name` (unique, identifier-safe), `prompt`, `model` (default config default), `expect` (optional output contract), `on_fail` (`stop` default \| `continue`), `retries` (0 default, max 2) | MUST | Loader test |
| 003 | `prompt` supports `{{inputs.X}}` (caller-supplied) and `{{steps.NAME.output}}` (prior step) placeholders; any UNRESOLVED placeholder at load/run time ABORTS — a template must never be dispatched as content (REQ-113 req 005 lesson) | MUST | Placeholder test |
| 004 | A step may only reference steps DECLARED BEFORE it (no forward/self references) — rejected at load | MUST | Wiring test |
| 005 | `expect` contract (v1): `required` (list of top-level JSON keys). Step raw output is parsed via the house result-JSON extractor; missing key(s) or unparseable JSON = step FAILURE with `ERR_CONTRACT` detail naming the missing keys | MUST | Contract test |

### Budget & plan (the Terraform discipline)

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 010 | `budget_usd` is a HARD pipeline ceiling: before each step, if spent-so-far + the step's estimate exceeds it, the pipeline STOPS with `ERR_BUDGET_EXCEEDED`, prior step results preserved (partials are results — never discarded) | MUST | Budget test |
| 011 | Plan mode dispatches NOTHING and emits: every step in order, its model, resolved prompt PREVIEW (placeholders shown symbolically for not-yet-run steps), per-step cost estimate, pipeline total estimate vs budget | MUST | Plan test |
| 012 | Plan mode has zero side effects (no audit records, no files) — same purity as RONDO-403 plan_only | MUST | Plan-purity test |

### Execution

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 020 | Steps run SEQUENTIALLY through the guarded dispatch entry (`rondo_run_file`) so every step gets audit INTENT/OUTCOME, sanitize, envelopes, quarantine — pipelines add NO unguarded path | MUST | Seam test |
| 021 | Step failure honors `on_fail`: `stop` (default) ends the pipeline with status `partial`; `continue` marks the step failed and proceeds — but a later step referencing the FAILED step's output ABORTS (no silent empty-string flow; the rondo_chain disease) | MUST | Failure test |
| 022 | `retries: N` re-dispatches a failed step up to N times (contract failures included); each retry is a separate audited dispatch | MUST | Retry test |
| 023 | Result envelope: pipeline `status` (`done`/`partial`/`error`), per-step records with FULL raw output, parsed output (when `expect` present), cost, duration, status, error detail; `total_cost_usd` | MUST | Envelope test |
| 024 | Step outputs pass between steps EXPLICITLY via placeholders only — never auto-appended (deterministic wiring; what the prompt says is what the model sees) | MUST | Wiring test |
| 025 | The engine accepts an injectable dispatch callable (tests are hermetic; production default = real guarded path) — the matrix pattern | MUST | Seam test |

### Surface

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 030 | CLI: `rondo pipeline <file.yaml> [--plan] [--input K=V ...]`; exit 0 done, 1 partial/error, 2 invalid definition | MUST | CLI test |
| 031 | Python API: `load_pipeline(path)` + `run_pipeline(spec, inputs=..., dispatch=..., plan=...)` exported from `rondo.pipeline` | MUST | API test |
| 032 | A runnable flagship example ships WITH this feature (examples ARE docs): a real multi-step pipeline doing real work, live-verified with logged cost | MUST | `examples/pipelines/claude-builder.yaml` (+ index) |

---

## 3. The flagship: claude-builder (rondo drives Claude Code itself)

The proving pipeline (`examples/pipelines/claude-builder.yaml`): 10 enforced
steps in which rondo drives a Claude Code subprocess to build a working
todo-list CLI + its test suite from nothing. Every step must answer "did you
actually do it?" (smart-return `passed=true/false`, verified by RUNNING the
work); `passed=false` blocks advancement and a retry is the fix loop — no step
7 until step 6 is PROVEN. Budget-capped; every intermediate visible in the
result envelope. Live-verified (RONDO-406→417, $0 on max auth); driver
`examples/api/claude_step_driver.py`.

**Not yet built (named here as the next pipeline, not a shipped one):** a
`release-notes.yaml` assembly line — 9 steps over rondo's own `git log`,
multi-provider, with one provider's claims hostile-reviewed and fact-checked
by another. Designed, not implemented; do not cite it as existing.

---

## 4. Honest limits (declared, not hidden)

- v1 is sequential — no DAG parallelism (parallel rounds exist for fan-out;
  pipelines are for DATA-DEPENDENT step sequences).
- `expect.required` checks key presence, not deep types/values — deep
  validation is the caller's step (a fact-check step IS the deep validator).
- Cost estimates are admission heuristics (STD-105), not quotes; the hard
  ceiling is enforced on actuals as they land.

---

## 5. Audit refinements (RONDO-433, 2026-06-15 — Cursor independent review)

An independent Cursor deep audit (`reports/cursor-reviews/review-20260615-081804.md`)
hardened the engine against the spec's own MUSTs. Behavior clarified/changed:

- **req 010 (budget) now MODEL-AWARE on step 0.** The run-mode admission gate
  was using a flat `_MIN_STEP_EST_USD` floor for the first step, so a single
  expensive step under a small budget could overshoot the "hard ceiling"
  unbounded. It now admits against `max(prior_high_cost, _estimate_step_cost)`
  — the same estimator plan mode uses. The run envelope also carries `budget_usd`
  so an overshoot is visible in-band.
- **req 023 `duration` is REAL.** Per-step `duration_sec` is now recorded
  (was listed as a MUST but absent).
- **req 005 (contract) checks the PRIMARY result object**, not the last — an
  appended decoy JSON object can no longer satisfy a contract the real output
  fails (parity with the passed=false self-report's all-objects stance).
- **Step field `allow_passed_false`** (additive to req 002): opt OUT of the
  `passed=false` self-report gate for a data step whose legitimate deliverable
  carries that key. Default false — the anti-lying gate stays ON. (Joins the
  other post-v1 step fields: `tools`, `max_turns`, `add_dir`, `timeout`,
  `verify`, `allow_broad`.)
- **req 011 (`--plan`) no longer requires inputs.** Plan dispatches nothing, so
  unsupplied `{{inputs.X}}` are shown symbolically rather than hard-erroring;
  the resolvability check still gates actual runs (req 003).
