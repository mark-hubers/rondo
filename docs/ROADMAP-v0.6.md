# Rondo v0.6 Roadmap — "Boringly Solid 9.5"

**Source:** Cursor deep review, Session 94
**Goal:** Move from 9/10 ("very good") to 9.5/10 ("looks like it came from a team shipping infra for years")
**Status:** Specced, not started

---

## A. Harden Invariants (dispatch/finalization)

**Goal:** Make it impossible (not just tested) to bypass `_finalize_dispatch`.

| # | Task | Files | Effort | Spec |
|---|------|-------|--------|------|
| A1 | Narrow public API: only `dispatch_task`, `run_round`, `rondo_run_file` may return TaskResult | dispatch.py, runner.py, mcp_server.py | Medium | REQ-100 addendum |
| A2 | Forbid direct TaskResult construction outside finalization/runner safety-net | dispatch.py, engine.py | Medium | REQ-100 addendum |
| A3 | Document `_finalize_dispatch` as THE gate for interactive tasks | dispatch.py | Small | STD-113 update |

**Why:** Current approach uses AST guard tests (RONDO-103). This makes it a type/API constraint instead.

---

## B. Tame Global State into Managers

**Goal:** Replace module-level mutable dicts with small, testable, resettable objects.

| # | Task | Files | Effort | Spec |
|---|------|-------|--------|------|
| B1 | `BackgroundDispatchStore` — owns `_background_results`, pruning, disk save/load | mcp_server.py | Medium | IFS-104 update |
| B2 | `MetricsCache` — owns `_metrics_cache`, TTL, invalidate() for tests | mcp_tools.py | Small | IFS-104 update |
| B3 | `TaskModelRegistry` — owns `_task_model_overrides`, load/reload from TOML | providers.py | Small | REQ-109 update |

**Why:** Global mutable state is "tamed but not eliminated" per Cursor. Managers make tests deterministic and future features safer.

---

## C. Tighten Input/Output Contracts

**Goal:** Replace "anything goes JSON strings" with validated schemas and consistent error envelopes.

| # | Task | Files | Effort | Spec |
|---|------|-------|--------|------|
| C1 | Define mini-schemas for JSON-string params: `rondo_chain`, `rondo_benchmark`, `rondo_summarize` | mcp_server.py | Medium | IFS-104 update |
| C2 | Named error codes for all MCP tool failures: `ERR_INVALID_INPUT`, `ERR_INPUT_TOO_LARGE`, etc. | mcp_server.py, mcp_tools.py | Medium | STD-108 update |
| C3 | Uniform error envelope: all tools return `{"status": "error", "error": "...", "code": "ERR_..."}` on failure | mcp_server.py, mcp_tools.py | Medium | IFS-104 update |

**Why:** Agents currently "poke and see" — stricter contracts let them call tools correctly without guessing.

---

## D. Operational Polish

**Goal:** Make "what happened?" and "how do I upgrade?" easy to answer.

| # | Task | Files | Effort | Spec |
|---|------|-------|--------|------|
| D1 | Dispatch traceability doc: MCP call → dispatch_id → audit → history → spool | docs/ or ai_help.py | Small | STD-113 update |
| D2 | UPGRADE.md: 3-5 step checklist for safe version upgrades | docs/UPGRADE.md | Small | SOP-104 |
| D3 | Consistent logging with dispatch_id, task_name, model, error_code | dispatch.py, runner.py | Medium | STD-101 update |

---

## E. Documentation Glue

**Goal:** Keep humans and AI agents in sync with the above changes.

| # | Task | Files | Effort | Spec |
|---|------|-------|--------|------|
| E1 | Add "errors" section to ai_help: common error codes and meanings | ai_help.py | Small | IFS-104 update |
| E2 | Add "pitfalls" section: don't poll full status in tight loop, prompt size limits | ai_help.py | Small | IFS-104 update |
| E3 | Update THREAT-MODEL with any new constraints from A-D | THREAT-MODEL.md | Small | STD-107 update |

---

## Sprint Estimates

| Cluster | Sprints | Priority |
|---------|---------|----------|
| A (invariants) | 2-3 | High — prevents future regressions |
| B (managers) | 3 | Medium — test quality + evolution |
| C (contracts) | 2-3 | Medium — agent usability |
| D (operations) | 2 | Low — polish |
| E (docs) | 1-2 | Low — can merge with A-D sprints |

**Total:** ~10-14 sprints for full 9.5 push.

---

## Decision: When to Do This

| Option | When | Rationale |
|--------|------|-----------|
| **Now** | Before Caliber/OB | Rondo is foundational — hardening it first benefits everything |
| **After Caliber** | After Caliber spikes | Caliber's detection rules (S1-S17) would catch issues during this work |
| **Incrementally** | Mix with other work | Do A (invariants) now, B-E during Caliber/OB builds |

Mark decides.
