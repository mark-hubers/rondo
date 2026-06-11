# Rondo-REQ-116: Scope Guard — one or two things per step, by default

*A lie needs ambiguity to hide in. A step that asks for ten things has ten
places to fudge; a step that asks for one has none. The scope guard makes
small, atomic, verifiable steps the DEFAULT, not a discipline you must
remember.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-06-11 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Depends on:** REQ-114 (pipelines), REQ-115 (verified execution)
**Author:** Mark Hubers — HubersTech
**Driver (Mark, plain words):** "rondo's basic job is: ask one or two things
per request, ask how it went, check it, then the next one or two steps. In
very clear steps, one-to-two things at a time, with how to do and test each."
The shrink-the-ask side of anti-lying: input shaping prevents the lie that
output verification only catches afterward.

---

## 1. Purpose & Scope

**Plain English:** the pipeline already runs steps one at a time. The scope
guard adds a check on the SHAPE of each step's ask: if a step's prompt looks
like it bundles many tasks (several files, a chain of "and then" actions, a
numbered sub-list), rondo flags it — because a fat step is where drift and
fake-success live. By default it WARNS (logged + in the envelope); a pipeline
may opt into STRICT mode where a fat step is a load-time error; a step that
genuinely needs breadth (a review pass over many files) declares
`allow_broad: true` and is exempt.

It is a HEURISTIC, not comprehension — so it never silently blocks by
default, the threshold is tunable, and the per-step override exists. Honesty
over cleverness: it nudges, it does not pretend to understand intent.

**IN scope:** a pure-Python scope score for a step prompt; warn-by-default +
opt-in strict; per-step `allow_broad`; the score/warnings surfaced in the
plan and the run envelope. **OUT of scope:** AI-based decomposition (a future
planner could SPLIT a fat step — this only DETECTS); semantic task counting.

---

## 2. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### The score

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 001 | `scope_score(prompt: str) -> dict` returns `{"score": int, "signals": [str]}` — a heuristic count of scope signals: conjoined imperatives (` and then `, ` then `, ` also `, ` additionally `), numbered/bulleted sub-task lines, and distinct file-path-like tokens beyond the first | MUST | Score test |
| 002 | The score is deterministic and pure (no I/O, no AI) — same prompt, same score | MUST | Determinism test |
| 003 | A focused single-task prompt scores 0 or 1; a clearly-bundled multi-task prompt scores above the threshold (default `_SCOPE_THRESHOLD = 3`) | MUST | Calibration test |

### Pipeline integration

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 010 | Step fields gain `allow_broad: bool` (default false). A step with `allow_broad: true` is exempt from scope checking entirely | MUST | Exempt test |
| 011 | Pipeline top-level gains `strict_scope: bool` (default false). In strict mode, loading a pipeline whose non-exempt step scores over threshold raises PipelineError naming the step + its signals | MUST | Strict test |
| 012 | In the DEFAULT (non-strict) mode, an over-threshold step is NOT blocked: a `-WARNING-` is logged and the step record carries `scope_warning` (score + signals) in the run envelope | MUST | Warn test |
| 013 | Plan mode (`--plan`) surfaces each step's scope score so the author sees fat steps BEFORE running | SHOULD | Plan test |
| 014 | No regression: existing pipelines (no strict_scope, no allow_broad) run exactly as before; a focused step carries no scope_warning | MUST | Rail test |

---

## 3. Why warn-by-default, not block

The guard is a heuristic — a long prompt can be one cohesive task. Blocking
by default would punish legitimate breadth and train authors to disable it.
So: WARN always (visible, free), STRICT is opt-in for authors who want the
discipline enforced, and `allow_broad` is the honest escape hatch for the
genuine wide step. The nudge is the product; the wall is optional.

## 4. Honest limits

- It counts surface signals, not meaning — a cleverly-worded fat step can
  score low, a verbose single task can score high. The `allow_broad` override
  and warn-default exist precisely because the heuristic is fallible.
- It DETECTS fat steps; it does not SPLIT them (that is a future AI planner).
