# STD-103: Quality

*How Rondo ensures its own code quality — TDD, convention enforcement, and coverage. Rondo tests itself, not its consumers.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** redacted
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-004, STD-103 (Caliber)
**Depends on:** CORE-STD-004, CORE-STD-012, STD-112, STD-100, CORE-STD-021, REQ-101

---

## 1. Purpose & Scope

Defines the quality standards for Rondo's own codebase: TDD discipline, convention enforcement via AST-based tests, and coverage requirements. Rondo is a stateless dispatch framework — it tests its OWN engine, dispatch, and runner logic. Self-correction is Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. (Rondo has no spec-driven AI build loop; consumers like OB do that).

**IN scope:**
- TDD rules for Rondo's own test suite
- Convention enforcement for Rondo's source code
- Coverage requirements and ratchet
- Gate pre/post condition testing
- Round definition testing patterns

**OUT of scope:**
- Self-correction (CORE-STD-004 domain — Rondo is stateless, no iterative AI builds)
- Consumer test requirements (OB/ACE define their own)
- Build gate tooling (STD-101: Observability handles prefixes)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

AI dispatch frameworks are deceptively simple to build and deceptively hard to trust. Without rigorous TDD and convention enforcement, subtle bugs hide: a malformed stream-json parse passes silently, an environment variable leaks to a subprocess, a gate condition evaluates incorrectly. Rondo's quality standards prevent these bugs from reaching production dispatches.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Test-Driven Development
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL tests written BEFORE or WITH code — never after. No "I'll add tests later." | MUST |
| 002 | System SHALL every public function in `rondo/` has at least one test. No exceptions for "simple" functions | MUST |
| 003 | System SHALL test names describe the scenario, not the implementation: `test_blocking_gate_halts_round`, not `test_gate_method_2` | MUST |
| 004 | System SHALL tests are deterministic — same input, same result, every time. No network-dependent or time-dependent tests. All dispatch tests use mocked subprocesses | MUST |
| 005 | System SHALL no test depends on another test's state. Each test sets up its own fixtures, runs, and tears down. Fully isolated | MUST |
| 006 | System SHALL test failures produce actionable messages: what was expected, what was received, and enough context to fix without reading the test source | MUST |
| 007 | System SHALL new features require a failing test FIRST — the test defines the contract, the code fulfills it | MUST |

### What Rondo Tests
| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | System SHALL engine logic: Round/Task/Gate dataclass construction, validation (`validate_task()`, `validate_round()`), state machine transitions (pending > running > terminal states) | MUST |
| 009 | System SHALL dispatch logic: subprocess argument construction, environment variable stripping (CLAUDECODE, ANTHROPIC_API_KEY), stream-json parsing, result contract parsing, malformed output handling | MUST |
| 010 | System SHALL runner logic: pre-gate evaluation, task sequencing, post-gate evaluation, RoundResult assembly, status calculation (req 46 from REQ-100) | MUST |
| 011 | System SHALL config logic: TOML loading, COALESCE resolution, validation (type checks, range checks), zero-config defaults, env var overrides | MUST |
| 012 | System SHALL gate pre/post conditions: blocking gates halt the round, non-blocking gates log warnings, gate results appear in RoundResult | MUST |
| 013 | Round definitions: example rounds in `examples/` are used as test fixtures — they MUST be valid, loadable, and produce correct Round objects | MUST |
| 014 | System SHALL error paths: subprocess timeout, non-zero exit code, empty stdout, malformed JSON, missing config file, invalid model name. Every error path has a test | MUST |

### Convention Enforcement
| ID | Requirement | Priority |
|----|-------------|----------|
| 015 | System SHALL conventions are enforced by AST-based tests, not comments or code review | MUST |
| 016 | System SHALL convention tests use `ast.walk` to inspect code structure — never regex for code patterns | MUST |
| 017 | System SHALL every convention has a test that fails if the pattern is violated. The test IS the enforcement | MUST |
| 018 | System SHALL new conventions: write the test FIRST, then update code to pass | MUST |
| 019 | System SHALL convention tests run on every build — part of the mandatory gate | MUST |
| 020 | System SHALL rondo convention categories: | MUST |

| Category | What It Enforces | Example |
|----------|-----------------|---------|
| **Naming** | snake_case functions, PascalCase classes | `test_public_functions_use_snake_case` |
| **Imports** | No internal imports in engine.py | `test_engine_has_no_dispatch_imports` |
| **Type safety** | Type hints on all public functions | `test_public_functions_have_return_types` |
| **Security** | No `shell=True` in subprocess calls | `test_no_shell_true_in_subprocess` |
| **Secrets** | No hardcoded API keys or tokens | `test_no_hardcoded_secrets` |
| **Isolation** | Round definitions import only engine | `test_example_rounds_import_only_engine` |
| ID | Requirement | Priority |
|----|-------------|----------|
| 021 | System SHALL convention count is tracked and only goes up. Removing a convention requires documented rationale | MUST |

### Coverage
| ID | Requirement | Priority |
|----|-------------|----------|
| 022 | System SHALL coverage threshold: 80% minimum line coverage. Enforced by the build gate | MUST |
| 023 | System SHALL coverage ratchet: the threshold only goes UP, never down. Once Rondo hits 85%, it cannot drop to 80% | MUST |
| 024 | System SHALL new code must be covered — uncovered new lines are flagged as warnings on first sprint, escalating to blockers after baseline | MUST |
| 025 | System SHALL branch coverage preferred over line coverage for decision paths — a function can have 100% line coverage and miss an entire `else` branch | MUST |
| 026 | System SHALL test-only files, config files, and example round definitions are excluded from coverage measurement — only `src/rondo/` production code counts | MUST |
| 027 | System SHALL 100% coverage is not the goal — meaningful coverage is. A test that asserts `True` covers a line but proves nothing | MUST |

### Testing Patterns Specific to Rondo
| ID | Requirement | Priority |
|----|-------------|----------|
| 028 | System SHALL subprocess mocking: all dispatch tests mock `subprocess.Popen` (or `subprocess.run`). Never call `claude -p` in unit tests | MUST |
| 029 | System SHALL stream-json fixtures: maintain JSON fixture files with real stream-json output for parsing tests. These fixtures are snapshots of actual Claude responses | MUST |
| 030 | System SHALL round definition tests: dynamically import example rounds, call `build_round()`, validate the returned Round object has correct structure | MUST |
| 031 | System SHALL integration tests (optional, marked `@pytest.mark.integration`): actually dispatch to Claude. Skipped in CI, run manually | MUST |

---
## 4. Architecture / Design

Quality is enforced at three gates: (1) pre-commit hooks (ruff, bandit, mypy), (2) `ace-build full` (lint + security + types + tests + coverage), (3) convention lock tests (AST-based structural enforcement). All three gates must pass before code merges. No gate can be bypassed without removing the hook config (which is tracked in git).

---

## 5. Data Model

No dedicated data model. Quality metrics (coverage %, test count, convention count) are tracked as golden numbers (STD-112). Test results are standard pytest output. Convention test results are standard test pass/fail.

---

## 6. Data Boundary

Quality enforcement is internal to Rondo's development process. It does not cross product boundaries. OB and Caliber define their own quality standards. The shared boundary is convention naming patterns — Rondo convention tests verify compliance with STD-100 data conventions.

---

## 7. MCP / API Interface

No MCP interface for quality metrics. Quality data stays in the development pipeline. Future: CORE-STD-021 MCP tools could expose test results for cross-product quality dashboards, but this is not planned for v1.0.

---

## 8. States & Modes

Tests run in two modes: unit (default, mocked subprocesses, fast) and integration (`@pytest.mark.integration`, real Claude dispatches, slow, skipped in CI). Convention tests always run — they are unit tests that inspect source code structure.

---

## 9. Configuration

Coverage threshold configured in `pyproject.toml` under `[tool.coverage]`. Convention count tracked in STD-112 golden numbers. No runtime configuration — quality gates are fixed rules, not tuneable parameters.

---

## 10. Rules & Constraints

### Test Organization

```
tests/
├── test_engine.py          # Round, Task, Gate, state machine, validation
├── test_dispatch.py        # subprocess, stream-json, result parsing
├── test_runner.py          # sequential execution, gates, RoundResult
├── test_config.py          # TOML, COALESCE, validation, env vars
├── test_cli.py             # CLI arg parsing, exit codes
├── test_examples.py        # example round loading, structure validation
├── test_parallel.py        # parallel runner (REQ-101)
├── test_overnight.py       # overnight scheduler (REQ-101)
├── test_conventions.py     # AST-based convention enforcement
└── fixtures/
    └── stream-json/        # real stream-json output samples
```

### What Self-Correction Looks Like for Rondo

Rondo does not have OB's `ai_went_wrong` / `ai_assumptions` spec sections because Rondo is not built iteratively from specs by AI. However:

- Rondo's TEST SUITE is its self-correction mechanism
- Every bug found becomes a test (regression lock)
- Convention tests prevent structural drift
- Coverage ratchet prevents blind spots from growing

The compound effect (CORE-STD-004 section 5) applies to Rondo through tests and conventions, not through AI self-correction loops.

---

## 11. Quality Attributes

- **Reproducibility:** Tests are deterministic — no network, no time dependencies, no inter-test state.
- **Ratchet behavior:** Coverage and convention counts only go up. Regression is a build failure.
- **Actionable failures:** Every test failure message tells you what to fix, not just what failed.

---

## 12. Shared Patterns

- **AST-based convention enforcement:** Same pattern used in ACE2 OB convention locks.
- **Coverage ratchet:** Threshold only increases — shared with Caliber quality standards.
- **Subprocess mocking:** `unittest.mock.patch` for `subprocess.Popen` — standard Python testing pattern.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo tests → ace-build | Test pass/fail gates the build | Build gate (6 hard gates) |
| Rondo conventions → STD-100 | Convention tests verify data standard compliance | Field naming, status vocabulary |
| Rondo coverage → STD-112 | Coverage % is a golden number | Drift detection |
| Rondo tests → CORE-STD-012 | Test pass is a readiness prerequisite | Requirement readiness |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-004 | Parent quality standard — Rondo adapts TDD, conventions, coverage |
| CORE-STD-012 | Requirement readiness — all tests passing is a prerequisite for READY state |
| CORE-STD-013 | TrackerData — test results are trackable events for trend analysis |
| CORE-STD-021 | MCP standard — future quality dashboards via MCP tools |

---

## 15. Self-Correction

Rondo's test suite IS its self-correction mechanism. Every bug found becomes a regression test. Convention tests prevent structural drift. The coverage ratchet prevents blind spots from growing. This is CORE-STD-004's compound effect applied through tests rather than AI feedback loops.

---

## 16. Assumptions

1. pytest is the test runner — no migration to unittest or nose planned.
2. AST-based tests can detect all convention violations (no runtime-only conventions).
3. Stream-json fixture files represent real Claude output accurately.
4. Coverage measurement via `pytest-cov` is accurate for Python source.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Coverage >= 80% and ratchet never decreases | `ace-build full` gate |
| 2 | Every public function has at least one test | Convention test |
| 3 | Every convention has an enforcing AST test | Convention meta-test |
| 4 | No test depends on another test's state | Randomized test order (`pytest-random-order`) |

---

## 18. Build Notes / Estimate

Convention tests: 4 hours (6 categories). Stream-json fixtures: 2 hours (collect real output). Subprocess mocking: 2 hours (Popen mock wrapper). Coverage config: 1 hour. Total: ~9 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Engine tests | Dataclass construction, validation, state transitions |
| Dispatch tests | Subprocess args, env stripping, stream-json parsing |
| Runner tests | Gate evaluation, task sequencing, result assembly |
| Convention tests | AST-based naming, imports, type hints, security |
| Config tests | TOML loading, COALESCE, validation |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Flaky test (non-deterministic) | False failures block builds | Isolation rule (req 5) + no network/time deps |
| Convention test false positive | Valid code blocked | Review convention definition, adjust AST pattern |
| Coverage drops below threshold | Build blocked | Ratchet prevents gradual erosion |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-004 | Parent quality standard |
| Depends on | CORE-STD-012 | Readiness tracking requires tests passing |
| Used by | STD-112 | Golden numbers track test count and coverage |
| Used by | All Rondo specs | Convention tests enforce cross-spec compliance |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: AST over regex for conventions | Regex matches strings, AST matches structure — fewer false positives | 2026-03-18 |
| D2: 80% coverage floor, not 100% | 100% incentivizes trivial assertions. 80% with ratchet grows naturally. | 2026-03-18 |
| D3: No self-correction section | Rondo is not AI-built iteratively. Tests are the correction mechanism. | 2026-03-18 |

---

## 23. Open Questions

None currently. Quality standards are stable and proven by the existing test suite.

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Convention lock** | AST-based test that enforces a structural rule in source code |
| **Coverage ratchet** | Threshold that only increases — once hit, cannot drop back |
| **Stream-json fixture** | Captured real Claude output used as test input |

---

## 25. Risk / Criticality

**HIGH.** Quality standards protect every dispatch. A bug in dispatch logic (wrong env vars, malformed args) could send secrets to Claude or produce wrong results. Convention tests are the primary defense against structural regression.

---

## 26. External Scan

Python testing best practices: pytest, coverage.py, AST inspection. No novel approaches — proven patterns from industry (Google testing blog, Martin Fowler's test pyramid). Rondo's convention lock pattern is adapted from ACE2 OB.

---

## 27. Security Considerations

Convention tests enforce security rules: no `shell=True` in subprocess, no hardcoded secrets, no sqlite3 imports. These are security-critical conventions. See STD-107 rule 5 for the full list. Convention tests are the automated enforcement of security policy.

---

## 28. Performance / Resource

Full test suite runs in <10 seconds (mocked subprocesses, no I/O). Convention tests add ~2 seconds (AST parsing). Integration tests (when enabled) take 30-300 seconds per dispatch. CI runs unit + convention only.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) requires all tests passing before a requirement reaches READY state. CORE-STD-013 (TrackerData) can ingest test result trends for quality dashboards. CORE-STD-021 MCP tools could expose quality metrics in future versions.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Quality gate definitions | WORKING | 6 gates from ace-build applied to Rondo | After gate changes |
| Quality thresholds | WORKING | Pass/fail thresholds defined | After threshold changes |
| Quality trending | THEORY | Specced for multi-build quality tracking | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-004 topics (TDD, conventions, coverage) adapted for Rondo. 31 requirements. Self-correction Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. — Rondo tests itself, consumers do the learning. Convention categories for dispatch framework. Subprocess mocking and stream-json fixtures as testing patterns. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
