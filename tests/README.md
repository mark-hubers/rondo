# Rondo Test Suite — Layer Guide

**Total tests:** 1613+ across 7 layers
**Layout:** `rondo/tests/<layer>/` — each layer has a distinct purpose
**Inventory:** see `rondo/docs/TEST-INVENTORY.md` for a full auto-generated listing

## Quick start

```bash
# -- Run everything except cloud + ollama (free, fast, default)
cd ~/git/mhubers/ace2
ace-build test

# -- Run ONE layer
.venv/bin/python -m pytest rondo/tests/unit/

# -- Run ONE file
.venv/bin/python -m pytest rondo/tests/pat/test_routing.py

# -- Run cloud tests (costs ~$0.10 in real API calls)
.venv/bin/python -m pytest rondo/tests/pat/ -m cloud

# -- Run ollama tests (needs local `ollama serve`)
.venv/bin/python -m pytest rondo/tests/pat/ -m ollama
```

## Performance monitoring

```bash
# -- Show 20 slowest tests (useful for spotting slowdowns)
.venv/bin/python -m pytest rondo/tests/ --durations=20

# -- Only count tests, don't run them (fast structural sanity check)
.venv/bin/python -m pytest rondo/tests/ --co -q

# -- Full build with metrics captured in OB DB
cd ~/git/mhubers/ace2 && ace-build full --product rondo
```

As of 2026-04-07, the slowest test is ~4 seconds (an e2e multi-task dry run).
The full 1618-test suite runs in ~63 seconds total. If any test exceeds 5
seconds, investigate — it's either doing real I/O that should be mocked or
using `time.sleep()` when `threading.Barrier` would work better.

## Layer purpose

| Layer | Purpose | Speed | External deps |
|-------|---------|-------|---------------|
| **unit/** | Pure logic, single module, no I/O | instant (<1ms each) | None |
| **integration/** | Multiple components together, one dispatch | fast (~10ms each) | None |
| **e2e/** | Full pipeline lifecycles, real files | medium (~50ms each) | Filesystem |
| **pat/** | Product acceptance, real behavior, no mocking | fast (~20ms each) | None (except cloud-marked) |
| **cloud/** | Real cloud provider API calls | slow (~2s each) | **$$ Real API** |
| **chaos/** | Failure injection, partial outages | medium | Filesystem |
| **conventions/** | Style, layering, security rules | fast | AST parsing |

## When to write tests in which layer

### unit/ — "Does this single function do what it says?"

Write here for:
- Pure functions with deterministic input/output
- Parser logic, formatter logic, pattern matchers
- Data structure operations
- Config resolution (COALESCE, etc.)

Example: `test_sanitize.py::test_bearer_token_pattern_redacts_valid_token`

### integration/ — "Do these 2-5 components work together?"

Write here for:
- Audit + sanitize ordering
- Circuit breaker + retry + dispatch flow
- Cache + tenant isolation + audit
- Structured logging through the dispatch chain

Example: `test_integration_reliability.py::test_audit_trail_records_dispatches_while_breaker_is_open`

### e2e/ — "Does the full system work from entry point to persistence?"

Write here for:
- Complete dispatch lifecycle (prompt → result → audit → spool)
- Crash recovery scenarios
- Multi-dispatch state transitions

Example: `test_integration_e2e.py::test_complete_audit_lifecycle`

### pat/ — "Does the product actually work like the docs say?"

Product Acceptance Tests — the contract with the user. Write here for:
- Router decision tree (`resolve_dispatch_engine`)
- MCP server tool responses
- Every documented invariant that must hold

**Critical rule:** NO mocking, NO `pytest.skip` on feature failures, NO `dry_run=True` copouts. If it fails, it **FAILS**.

### cloud/ — "Does the real provider still work?"

Marked `@pytest.mark.cloud`. Excluded from default runs because:
- Each call costs real money (~$0.01-0.05)
- Requires real API keys
- Network-dependent

Run explicitly: `pytest -m cloud`

### chaos/ — "Does the system survive partial outages?"

Failure injection scenarios — disk full, network timeout, corrupted file, process kill mid-dispatch.

### conventions/ — "Is the code still following our rules?"

Style enforcement as tests. Catches:
- Missing docstrings
- Import layering violations
- Hardcoded secrets
- File size limits
- Spec reference requirements

Example: `test_conventions.py::test_import_layers_enforced`

## Testing principles (Rondo-specific)

These evolved from real lessons — see `rondo/docs/ADR-001-test-strategy.md` for the full reasoning.

1. **Real > mocked.** Every dispatch test uses real dispatch code. Only the outbound network call is replaced with `FakeProvider`/`FlakyProvider`.

2. **One assertion per invariant, not per test.** A test can have multiple assertions if they all verify the same invariant from different angles.

3. **Test names describe behavior, not implementation.** `test_circuit_breaker_persists_across_restart` beats `test_breaker_1`.

4. **No silent skips.** `pytest.skip` is reserved for platform-incompatible tests (e.g., Windows-only paths on macOS). Never for "feature might be broken."

5. **Tenant isolation is always tested.** Every persistence test runs against `tmp_path` and `RONDO_TEST_DIR`. Zero writes to the real `~/.rondo/`.

## File size guideline

Industry best practice: **200-500 lines per test file.** Rondo's own guideline:
- **< 200 lines:** fine, may merge with related file later
- **200-500 lines:** sweet spot
- **500-800 lines:** acceptable if all tests share tight coupling
- **> 800 lines:** code smell, split by feature

See RONDO-207 commit `92c1f54e` for the monster-split precedent (2227-line file → 6 files of 218-597 lines each).
