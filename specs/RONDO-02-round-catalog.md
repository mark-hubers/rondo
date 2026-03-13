# RONDO-02: Round Catalog

*What each round type checks, when to run it, and what model to use.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** RONDO-01 (Core Framework) | **Blocks:** Nothing
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Catalogs every round type that Rondo can run. Each entry defines what the round checks, how many tasks it creates, which models to use, and when it should run (overnight, on-demand, or both).

**IN scope:**
- Round type definitions (what each round does)
- Task breakdown per round (count, model assignments)
- Scheduling guidance (when to run each round)
- Gate definitions per round (pre/post conditions)

**OUT of scope:**
- Framework architecture (RONDO-01: Core Framework)
- Prompt engineering details (implementation, not spec)
- Result format details (RONDO-01 defines the contract)

---

## The Problem

Without a catalog, round definitions are tribal knowledge — buried in code, undocumented, and inconsistent. A new round author doesn't know what patterns exist, what models to use, or how to structure gates.

The catalog also serves as the overnight scheduler's menu: "what CAN Rondo do?" must be answerable from one document.

---

## Round Types

### 1. Spec Health (`spec-health`)

**Purpose:** Check a single spec for staleness, completeness, cross-ref integrity, and OB2 readiness.

**Scope:** One spec file per round invocation. Run across all specs with `--all-ob` or `--all`.

**Tasks:**

| # | Task | Model | Why That Model |
|---|------|-------|---------------|
| 1 | Section completeness | sonnet | Pattern matching against required sections |
| 2 | Requirement quality | opus | Judgment: are requirements testable and specific? |
| 3 | Cross-reference check | sonnet | Pattern: do referenced specs exist? |
| 4 | Staleness detection | sonnet | Date comparison: last modified vs dependencies |
| 5 | Test coverage mapping | sonnet | Pattern: do requirements map to tests? |
| 6 | OB2 alignment | opus | Judgment: does spec reflect OB2 decisions? |
| 7 | Assumption validation | opus | Judgment: are assumptions still true? |
| 8 | Health score | opus | Synthesis: overall score from all checks |

**Gates:**
- Pre: Spec file exists (blocking)
- Post: Results recorded

**When to run:** Every night (default + full mode). On-demand after spec changes.

---

### 2. Digest Refresh (`digest-refresh`)

**Purpose:** Detect stale digests and regenerate them from current spec content.

**Scope:** One spec per invocation. Overnight runs top 10 stalest.

**Tasks:**

| # | Task | Model | Why That Model |
|---|------|-------|---------------|
| 1 | Staleness check | sonnet | Compare digest date vs spec last-modified |
| 2 | Generate digest | opus | Judgment: summarize spec into concise digest |
| 3 | Quality check | sonnet | Pattern: does digest cover all major sections? |

**Gates:**
- Pre: Spec file exists, digest directory exists (blocking)
- Post: Digest file written

**When to run:** Every night (default + full mode). On-demand after major spec rewrites.

---

### 3. Build Check (`build-check`)

**Purpose:** Run the full build pipeline and analyze results.

**Scope:** Entire project.

**Tasks:**

| # | Task | Mode | Details |
|---|------|------|---------|
| 1 | Ruff format | AUTO | `ruff format --check` |
| 2 | Ruff lint | AUTO | `ruff check` |
| 3 | Bandit security | AUTO | `bandit -r src/` |
| 4 | Mypy types | AUTO | `mypy src/` |
| 5 | Pytest | AUTO | `pytest tests/` |
| 6 | Analysis | INTERACTIVE (opus) | Interpret failures, suggest fixes |

**Gates:**
- Pre: `pyproject.toml` exists (blocking)
- Post: Results recorded

**When to run:** On-demand before commits. NOT in overnight (use `ace-build` directly).

---

### 4. Convention Check (`convention-check`)

**Purpose:** Scan codebase for convention violations.

**Scope:** Entire project source tree.

**Tasks:**

| # | Task | Model | Why That Model |
|---|------|-------|---------------|
| 1 | Naming conventions | sonnet | Pattern: snake_case, PascalCase enforcement |
| 2 | Import organization | sonnet | Pattern: stdlib → third-party → local ordering |
| 3 | Dead code detection | sonnet | Pattern: unused functions, unreachable branches |
| 4 | Comment style | haiku | Simple: `## --` convention check |
| 5 | Architecture layers | opus | Judgment: do imports respect layer boundaries? |
| 6 | Convention summary | opus | Synthesis: prioritized violation list |

**Gates:**
- Pre: Source directory exists (blocking)
- Post: Results recorded

**When to run:** Every night (default + full mode). On-demand before round closes.

---

### 5. Sprint Close (`sprint-close`)

**Purpose:** Assess whether the active sprint is ready to close.

**Scope:** Current sprint (reads ACTIVE-SPRINT.md).

**Tasks:**

| # | Task | Model | Why That Model |
|---|------|-------|---------------|
| 1 | Metrics collection | sonnet | Pattern: LOC, test count, coverage from build |
| 2 | Code quality review | opus | Judgment: is the code clean enough to close? |
| 3 | Symbol registration | sonnet | Pattern: new functions/classes registered? |
| 4 | Tracker freshness | sonnet | Pattern: are trackers updated with sprint results? |
| 5 | Close readiness | opus | Synthesis: go/no-go with specific blockers |

**Gates:**
- Pre: ACTIVE-SPRINT.md exists (blocking), ace-build passes (blocking)
- Post: Results recorded

**When to run:** On-demand at end of sprint. NOT overnight.

---

### 6. Knowledge Mine (`knowledge-mine`)

**Purpose:** Extract decisions, corrections, patterns, and gaps from recent journal entries.

**Scope:** ACE-JOURNAL.md (last 50 entries).

**Tasks:**

| # | Task | Model | Why That Model |
|---|------|-------|---------------|
| 1 | Decision extraction | opus | Judgment: identify decisions with rationale |
| 2 | Correction patterns | opus | Judgment: what mistakes keep recurring? |
| 3 | Pattern recognition | opus | Judgment: what workflows are emerging? |
| 4 | Spec gap detection | sonnet | Pattern: journal mentions unspecced topics? |
| 5 | Memory freshness | sonnet | Pattern: are MEMORY.md entries still valid? |
| 6 | Knowledge synthesis | opus | Synthesis: prioritized knowledge items |

**Gates:**
- Pre: ACE-JOURNAL.md exists (blocking)
- Post: Results recorded

**When to run:** Full overnight mode only. On-demand after intensive sessions.

---

### 7. PR Review (`pr-review`)

**Purpose:** AI code review of uncommitted changes.

**Scope:** Dynamic — reads `git diff` to build task list.

**Tasks:**

| # | Task | Model | Details |
|---|------|-------|---------|
| 1-15 | Per-file review | sonnet (.py, .sql, .toml), haiku (.md) | One task per changed file (max 15) |
| 16 | Bulk overflow | sonnet | If >15 files, remaining get quick scan |
| 17 | Architecture impact | opus | Cross-cutting: layer boundaries, circular deps |
| 18 | Test coverage | sonnet | Cross-cutting: do changes have tests? |
| 19 | PR summary | opus | Verdict: APPROVE / COMMENT / REQUEST_CHANGES |

**Gates:**
- Pre: Files changed vs base branch (blocking)
- Post: Review recorded

**When to run:** On-demand before merge/push. NOT overnight (no uncommitted changes).

---

### 8. Test Gaps (`test-gaps`)

**Purpose:** Find untested source modules and prioritize what needs tests.

**Scope:** Dynamic — discovers `src/ace2/*.py` and pairs with `tests/test_*.py`.

**Tasks:**

| # | Task | Model | Details |
|---|------|-------|---------|
| 1-20 | Per-module analysis | sonnet | Check each public function for test coverage |
| 21 | Gap summary | opus | Prioritized list: HIGH/MEDIUM/LOW by function visibility |

**Gates:**
- Pre: `src/ace2/` exists (blocking)
- Post: Results recorded

**When to run:** Full overnight mode. On-demand before major releases.

---

### 9. Design Check (`design-check`)

**Purpose:** 15-item design checklist from OB Round 2 methodology.

**Scope:** One spec per invocation.

**Tasks:** 15 checklist items per OB methodology (existing round definition).

**When to run:** On-demand during design rounds only.

---

## Overnight Phase Assignment

| Phase | Round Type | Mode: quick | Mode: default | Mode: full |
|-------|-----------|:-----------:|:-------------:|:----------:|
| 1 | spec-health (all OB) | YES | YES | YES |
| 2 | convention-check | — | YES | YES |
| 3 | digest-refresh (top 10) | — | YES | YES |
| 4 | knowledge-mine | — | — | YES |
| 5 | test-gaps | — | — | YES |

**Not overnight:** build-check (use ace-build), sprint-close (manual), pr-review (no uncommitted changes), design-check (manual).

---

## Model Budget Guidance

| Model | Cost (API) | Best For | Round Types |
|-------|-----------|----------|-------------|
| haiku | Lowest | Simple pattern checks | convention (comment style) |
| sonnet | Medium | Pattern matching, code scanning | Most tasks (default) |
| opus | Highest | Judgment, synthesis, scoring | Health scores, PR verdicts, knowledge extraction |

**Rule of thumb:** If the task requires _judgment_ (is this good? what's the priority?), use opus. If it requires _matching_ (does this exist? is this formatted right?), use sonnet. If it's trivial, use haiku.

**Max plan:** Model choice affects speed, not cost. Use opus freely overnight.
**API plan:** Model choice affects cost. Use haiku/sonnet for bulk, opus only for synthesis tasks.

---

## Adding a New Round Type

To add a new round definition:

1. Create `rondo/src/rounds/your_round.py`
2. Define a `build_your_round()` function that returns a `Round` object
3. Each task gets: name, instruction (Do), context_files (Read), done_when (Done), model hint
4. Define pre-gates (blocking conditions) and post-gates (recording)
5. Register in runner CLI choices and parallel CLI choices
6. Add entry to this catalog (RONDO-02)
7. Test with `--dry-run` before live dispatch

**Target:** New round definition in under 50 lines of Python.

---

## Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 9 round types for v1 | 2026-03-13 | Covers spec health, code quality, knowledge, and review — the high-value overnight work |
| D2 | PR review is on-demand only | 2026-03-13 | No uncommitted changes at night. Run manually before push |
| D3 | Model hints in round definitions | 2026-03-13 | Round authors know what each task needs. CLI can override for cost control |
| D4 | Dynamic round definitions (pr-review, test-gaps) | 2026-03-13 | Task count depends on changed files / source modules. Can't be static |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial catalog — 9 round types from spike learnings (Session 75) |
