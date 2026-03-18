# STD-004: Quality

*How Rondo ensures its own code quality — TDD, convention enforcement, and coverage. Rondo tests itself, not its consumers.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** redacted
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-STD-004, Caliber-STD-004

---

## 1. Purpose & Scope

Defines the quality standards for Rondo's own codebase: TDD discipline, convention enforcement via AST-based tests, and coverage requirements. Rondo is a stateless dispatch framework — it tests its OWN engine, dispatch, and runner logic. Self-correction is N/A (Rondo has no spec-driven AI build loop; consumers like OB do that).

**IN scope:**
- TDD rules for Rondo's own test suite
- Convention enforcement for Rondo's source code
- Coverage requirements and ratchet
- Gate pre/post condition testing
- Round definition testing patterns

**OUT of scope:**
- Self-correction (OB-STD-004 domain — Rondo is stateless, no iterative AI builds)
- Consumer test requirements (OB/ACE define their own)
- Build gate tooling (STD-002: Observability handles prefixes)

---

## 3. Requirements

### Test-Driven Development

1. Tests written BEFORE or WITH code — never after. No "I'll add tests later."
2. Every public function in `rondo/` has at least one test. No exceptions for "simple" functions.
3. Test names describe the scenario, not the implementation: `test_blocking_gate_halts_round`, not `test_gate_method_2`.
4. Tests are deterministic — same input, same result, every time. No network-dependent or time-dependent tests. All dispatch tests use mocked subprocesses.
5. No test depends on another test's state. Each test sets up its own fixtures, runs, and tears down. Fully isolated.
6. Test failures produce actionable messages: what was expected, what was received, and enough context to fix without reading the test source.
7. New features require a failing test FIRST — the test defines the contract, the code fulfills it.

### What Rondo Tests

8. Engine logic: Round/Task/Gate dataclass construction, validation (`validate_task()`, `validate_round()`), state machine transitions (pending > running > terminal states).
9. Dispatch logic: subprocess argument construction, environment variable stripping (CLAUDECODE, ANTHROPIC_API_KEY), stream-json parsing, result contract parsing, malformed output handling.
10. Runner logic: pre-gate evaluation, task sequencing, post-gate evaluation, RoundResult assembly, status calculation (req 46 from REQ-001).
11. Config logic: TOML loading, COALESCE resolution, validation (type checks, range checks), zero-config defaults, env var overrides.
12. Gate pre/post conditions: blocking gates halt the round, non-blocking gates log warnings, gate results appear in RoundResult.
13. Round definitions: example rounds in `examples/` are used as test fixtures — they MUST be valid, loadable, and produce correct Round objects.
14. Error paths: subprocess timeout, non-zero exit code, empty stdout, malformed JSON, missing config file, invalid model name. Every error path has a test.

### Convention Enforcement

15. Conventions are enforced by AST-based tests, not comments or code review.
16. Convention tests use `ast.walk` to inspect code structure — never regex for code patterns.
17. Every convention has a test that fails if the pattern is violated. The test IS the enforcement.
18. New conventions: write the test FIRST, then update code to pass.
19. Convention tests run on every build — part of the mandatory gate.

20. Rondo convention categories:

| Category | What It Enforces | Example |
|----------|-----------------|---------|
| **Naming** | snake_case functions, PascalCase classes | `test_public_functions_use_snake_case` |
| **Imports** | No internal imports in engine.py | `test_engine_has_no_dispatch_imports` |
| **Type safety** | Type hints on all public functions | `test_public_functions_have_return_types` |
| **Security** | No `shell=True` in subprocess calls | `test_no_shell_true_in_subprocess` |
| **Secrets** | No hardcoded API keys or tokens | `test_no_hardcoded_secrets` |
| **Isolation** | Round definitions import only engine | `test_example_rounds_import_only_engine` |

21. Convention count is tracked and only goes up. Removing a convention requires documented rationale.

### Coverage

22. Coverage threshold: 80% minimum line coverage. Enforced by the build gate.
23. Coverage ratchet: the threshold only goes UP, never down. Once Rondo hits 85%, it cannot drop to 80%.
24. New code must be covered — uncovered new lines are flagged as warnings on first sprint, escalating to blockers after baseline.
25. Branch coverage preferred over line coverage for decision paths — a function can have 100% line coverage and miss an entire `else` branch.
26. Test-only files, config files, and example round definitions are excluded from coverage measurement — only `src/rondo/` production code counts.
27. 100% coverage is not the goal — meaningful coverage is. A test that asserts `True` covers a line but proves nothing.

### Testing Patterns Specific to Rondo

28. Subprocess mocking: all dispatch tests mock `subprocess.Popen` (or `subprocess.run`). Never call `claude -p` in unit tests.
29. Stream-json fixtures: maintain JSON fixture files with real stream-json output for parsing tests. These fixtures are snapshots of actual Claude responses.
30. Round definition tests: dynamically import example rounds, call `build_round()`, validate the returned Round object has correct structure.
31. Integration tests (optional, marked `@pytest.mark.integration`): actually dispatch to Claude. Skipped in CI, run manually.

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
├── test_parallel.py        # parallel runner (REQ-002)
├── test_overnight.py       # overnight scheduler (REQ-002)
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

The compound effect (OB-STD-004 section 5) applies to Rondo through tests and conventions, not through AI self-correction loops.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches OB-STD-004 topics (TDD, conventions, coverage) adapted for Rondo. 31 requirements. Self-correction N/A — Rondo tests itself, consumers do the learning. Convention categories for dispatch framework. Subprocess mocking and stream-json fixtures as testing patterns. |
