# ADR-001: Rondo Test Strategy

**Status:** Accepted
**Date:** 2026-04-07
**Sprint:** RONDO-207
**Deciders:** Mark Hubers

## Context

Rondo's test suite needs to prove correctness of a dispatch engine with many
interacting subsystems: router → provider → HTTP → audit → sanitize → spool →
metrics → history. Each subsystem has its own modes (auth, retry, budget,
tenant, observability). A bad test strategy either:

- **Misses real bugs** by testing each component in isolation and missing
  cross-component ordering issues
- **Burns cycles** by over-testing implementation details that change on
  every refactor
- **Creates false confidence** by mocking the very thing being tested

This ADR records the strategy decisions made during RONDO-207 and why.

## Decisions

### 1. Layer structure: pyramid with Trophy tilt

Rondo uses 7 test layers:

```
tests/
├── unit/         (1155 tests, 73%)  ← pure logic
├── integration/  (165 tests,  10%)  ← 2-5 components together
├── pat/          (133 tests,   8%)  ← product acceptance
├── e2e/          (114 tests,   7%)  ← full lifecycles
├── conventions/  (31 tests,    2%)  ← style/layering/security
├── chaos/        (15 tests,    1%)  ← failure injection
└── cloud/        (marker, ~9 tests) ← real API calls
```

**Shape:** classical pyramid (lots of unit, fewer integration) with a tilt
toward the Testing Trophy (Kent C. Dodds) pattern of more integration tests.

**Rejected alternatives:**
- **Pure pyramid** — over-weights brittle unit tests on implementation details
- **Pure Trophy** — would need 3-4x the integration test count; too expensive
  to maintain given Rondo's surface area
- **BDD-only** — too abstract for a technical library; dispatch details matter

### 2. No-mock policy for dispatch path

**Decision:** Every test that exercises the dispatch code runs REAL dispatch.
Only the outbound network call is replaced with a `FakeProvider` or
`FlakyProvider` stand-in.

**Why:** Session 99 lesson — AI reviewers rated Rondo 8.5/10 while its primary
use case (in-session dispatch) had a 100% failure rate. Tests hid this behind
`pytest.skip` and `dry_run=True` shortcuts. The dispatch pipeline had bugs
nobody caught because nobody ran it end-to-end in tests.

**Consequence:** Fake providers must be realistic (return proper `TaskResult`
objects, support failure modes). The cost is higher fixture effort; the win
is that every test proves a real code path works.

### 3. No silent skips on feature failures

**Decision:** `pytest.skip` is reserved for platform incompatibility (Windows
paths on macOS, etc.). It is NEVER used to hide a feature that's broken.

**Why:** Same Session 99 incident. Tests were skipping when features failed,
so CI was green while production was broken.

**Enforcement:** conventions/test_conventions.py — grep-style check for
`pytest.skip` in test files with a justification requirement.

### 4. Per-tenant isolation in every persistence test

**Decision:** Every test that touches audit, spool, keys, or idempotency
MUST use `tmp_path` and `RONDO_TEST_DIR` so it cannot write to the user's
real `~/.rondo/` directory.

**Why:** A test that wrote to real `~/.rondo/audit/` corrupted Mark's real
audit trail and polluted subsequent dispatches with test data.

**Enforcement:** `conftest.py::_clean_test_env` autouse fixture sets
`RONDO_TEST_DIR` to `tmp_path` for every test. Module-level singletons that
bypass this (like `_GLOBAL_BREAKER`) must be re-instantiated per test with
explicit `persist_path=tmp_path/X`.

### 5. File size limit: 200-500 lines sweet spot

**Decision:** Test files should live in the 200-500 line range. Over 800 is
a refactor candidate.

**Why:** Industry consensus (Brian Okken's *Python Testing with pytest*, Martin
Fowler on test readability). Large test files hurt:
- Navigation (scrolling to find the failing test)
- Parallel execution (pytest-xdist can't shard a single file well)
- Code review (reviewers skim past large diffs)
- IDE responsiveness (syntax highlighting, linting)

**Evidence of benefit:** RONDO-207 split two monsters:
- `test_real_dispatch.py` (2227 lines, 133 tests) → 6 files of 218-597 lines
- `test_mcp.py` (1802 lines) → 5 files of 120-547 lines

Post-split: same test count, better parallelism, clearer failures, all
pylint/ruff checks still green.

### 6. Test layer convention enforcement via tests

**Decision:** Use `test_conventions.py` in `tests/conventions/` to enforce
structural rules as tests — import layering, file size, spec references,
signature footers, no hardcoded secrets.

**Why:** Conventions documented in prose get ignored. Conventions enforced
by tests cannot be ignored — CI fails if you violate them.

**Examples:**
- `TestImportLayering::test_import_layers_enforced` — blocks cross-layer
  imports that would create cycles
- `TestMgHSignature::test_all_files_have_signature` — every source file
  has a deterministic identifier footer
- `TestNoHardcodedKeys::test_no_hardcoded_keys_in_source` — no `sk-*`
  literals in source code

### 7. Integration tests cross 2-5 components; unit tests stay within 1

**Decision:** If a test exercises only one module (e.g., `sanitize.py`), it
goes in `unit/`. If it exercises two or more modules working together (e.g.,
`audit + sanitize + tenant scoping`), it goes in `integration/`.

**Boundary rule:** An integration test should fail if **any** of its components
break, not just one. That's what makes it high-value — it catches wiring bugs
that isolated unit tests miss.

**Counter-example — BAD integration test:**
```python
def test_audit_record_intent_calls_sanitize(self):
    # -- This is really a unit test of audit.record_intent with a mock sanitize.
    # -- It doesn't cross a real component boundary.
    ...
```

**Counter-example — GOOD integration test:**
```python
def test_sanitize_runs_before_audit_outcome_stores_scrubbed(self, tmp_path):
    # -- Exercises real audit + real sanitize + real file I/O.
    # -- Fails if ANY of: sanitize regex is wrong, audit writes before
    # -- sanitize runs, tenant scoping is broken, atomic_write fails.
    ...
```

## Consequences

**Positive:**
- Tests catch real bugs (proven by the 67 findings closed in RONDO-204/205/206)
- Test suite runs in ~22s for 1641 tests (fast enough for tight loops)
- Pylint 9.89/10 held across multiple large refactors
- File layout readable by humans without a tour guide
- Convention tests catch drift automatically

**Negative:**
- More fixture effort per test (`FakeProvider`, `FlakyProvider`, `tmp_path` setup)
- Some duplicated setup code across tests (mitigated by `conftest.py` autouse)
- Split files occasionally make test discovery harder (mitigated by
  `rondo/docs/TEST-INVENTORY.md` regeneration)

## References

- **Testing Pyramid** — Mike Cohn, *Succeeding with Agile* (2009)
- **Testing Trophy** — Kent C. Dodds, [kentcdodds.com/blog/write-tests](https://kentcdodds.com/blog/write-tests)
- **Python Testing with pytest** — Brian Okken, 2nd edition
- **Session 99 lesson** — see `rondo/docs/LEARNINGS-FROM-RONDO-BUILD.md` (legacy)
- **RONDO-207 Phase 1+2** — commit `92c1f54e` (monster file splits)
- **RONDO-207 Phase 3** — commit `ff98b743` (Trophy-tilt integration tests)

## Change log

- **2026-04-07** — Initial ADR (RONDO-207), documenting decisions from
  Sessions 99-101 and the RONDO-204/205/206/207 sprint cluster.
