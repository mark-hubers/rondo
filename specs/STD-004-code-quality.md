# STD-004: Code Quality Gates

*Automated enforcement of code quality — linting, complexity, coverage, conventions, signing.*

**Created:** 2026-03-14 | **Updated:** 2026-03-14 | **Status:** DRAFT
**Depends on:** VER-001 (verification matrix) | **Blocks:** REQ-001 (build gate)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Defines every automated quality gate that protects the Rondo codebase. Each gate
is enforced by tooling — not human discipline. If a gate fails, the build fails.
No exceptions without spec-level justification.

**IN scope:**
- Linting rules and configuration (ruff)
- Security scanning (bandit)
- Cyclomatic complexity cap
- Test coverage floor
- Convention lock tests (AST-based structural enforcement)
- Code signing (orbit-sign)
- Code hygiene policies (TODO markers, wildcard imports, mutable defaults)
- Docstring and type annotation requirements
- Gate execution order and fail-fast behavior

**OUT of scope:**
- Test strategy and verification matrix (VER-001)
- Error handling patterns (STD-001)
- Configuration resolution (STD-002)

---

## Item 2: Principle

Every quality rule that can be checked by a machine MUST be checked by a machine.
Human discipline does not scale. Automated gates enforce quality at zero ongoing
attention cost — they catch violations on every build, every commit, forever.

---

## Item 3: Gate Execution Order

Gates run in dependency order. Fast gates first, expensive gates last. If a gate
fails, later gates still run (collect all errors, don't hide problems).

| Order | Gate | Tool | Fail = Build Fail? | Typical Duration |
|-------|------|------|-------------------|-----------------|
| 1 | Lint | `ruff check` | Yes | <1s |
| 2 | Format | `ruff format --check` | Yes | <1s |
| 3 | Security | `bandit -r src/` | Yes | <2s |
| 4 | Tests + Coverage | `pytest --cov=rondo` | Yes | <20s |
| 5 | Convention locks | Part of pytest suite | Yes | <5s |
| 6 | Complexity | Part of convention tests | Yes | <1s |
| 7 | Signing | `orbit-sign verify` | Yes (post-build) | <1s |

---

## Item 4: Lint Rules (ruff)

**Tool:** ruff (Rust-based Python linter, replaces flake8 + isort + pyupgrade)

**Rule sets enabled:**

| Prefix | Category | What It Catches |
|--------|----------|----------------|
| E | pycodestyle errors | Syntax, whitespace, indentation |
| F | pyflakes | Unused imports, undefined names, f-string errors |
| W | pycodestyle warnings | Deprecated syntax, trailing whitespace |
| I | isort | Import ordering and grouping |
| N | pep8-naming | Function/class/variable naming violations |
| UP | pyupgrade | Legacy syntax that has modern Python equivalents |
| D | pydocstyle | Docstring presence, format, punctuation |

**Configuration** (in `pyproject.toml`):
```toml
[tool.ruff]
target-version = "py312"
line-length = 120
```

**Rules:**
1. Every source and test file MUST pass `ruff check` with zero errors.
2. Every source and test file MUST pass `ruff format --check` (PEP 8 formatting).
3. No `# noqa` comments without inline justification of WHY.

---

## Item 5: Security Scanning (bandit)

**Tool:** bandit (Python SAST — Static Application Security Testing)

**Configuration** (in `pyproject.toml`):
```toml
[tool.bandit]
skips = ["B404", "B603"]
```

**Justified skips:**

| Rule | What It Flags | Why Skipped |
|------|--------------|-------------|
| B404 | `import subprocess` | Rondo's core function IS invoking Claude via subprocess |
| B603 | `Popen` without `shell=True` | Using `Popen` without `shell=True` IS the safe pattern |

**Rules:**
1. Every source file MUST pass bandit with zero issues (excluding justified skips).
2. New skips require a comment in `pyproject.toml` explaining the security rationale.
3. `shell=True` MUST NEVER be used in subprocess calls.

---

## Item 6: Cyclomatic Complexity Cap

**Tool:** AST-based complexity calculator in convention tests

**Threshold:** Maximum cyclomatic complexity of **15** per function.

**Complexity scoring (McCabe method):**

| Construct | Complexity Added |
|-----------|-----------------|
| `if` / `elif` / `else` | +1 per branch |
| `for` / `while` | +1 per loop |
| `except` | +1 per handler |
| `and` / `or` | +1 per boolean operator |
| `assert` | +1 |
| Comprehension with `if` | +1 |

**Rules:**
1. No function SHALL exceed cyclomatic complexity of 15.
2. Functions exceeding 15 MUST be decomposed into smaller, focused functions.
3. Complexity is measured by AST analysis in `test_conventions.py`, not external tools.

**Remediation pattern:**
Extract helper functions. Example: `_dispatch_interactive()` (complexity 19) was
decomposed into 5 functions: `_make_error_result()`, `_build_subprocess_cmd()`,
`_run_subprocess()`, `_parse_and_build_result()`, and a reduced orchestrator.

---

## Item 7: Test Coverage Floor

**Tool:** pytest-cov (coverage.py backend)

**Configuration** (in `pyproject.toml`):
```toml
[tool.coverage.run]
source = ["rondo"]

[tool.coverage.report]
fail_under = 90
show_missing = true
skip_empty = true
```

**Rules:**
1. Overall project coverage MUST be ≥90%. Build fails if coverage drops below this.
2. No new module SHALL be added without corresponding tests.
3. `# pragma: no cover` is allowed ONLY for genuinely unreachable defensive code
   (e.g., `if __name__ == "__main__"` guards, corrupted loader checks). Each use
   MUST have a comment explaining why the line is unreachable.
4. Coverage is measured on every test run via `--cov=rondo`.

---

## Item 8: Convention Lock Tests

**Tool:** AST-based structural enforcement in `tests/test_conventions.py`

Convention lock tests scan every source and test file using Python's `ast` module
and enforce structural rules automatically. They run as part of the normal pytest
suite — no separate step needed.

**Convention classes (15 total):**

| Class | What It Enforces |
|-------|-----------------|
| `TestSPDXHeaders` | Every .py file has SPDX copyright + license header |
| `TestModuleDocstrings` | Every source module has a docstring |
| `TestNoRelativeImports` | All imports are absolute, not relative |
| `TestNoPrintInSource` | Source files use logging, not print() (tests exempt) |
| `TestNoStarImports` | No `from x import *` anywhere |
| `TestNoBareDictAnnotation` | `dict[str, Any]` not bare `dict` in annotations |
| `TestSignaturePresent` | Every file has orbit-sign signature line |
| `TestTestFileNaming` | Test files match `test_*.py` pattern |
| `TestTestClassNaming` | Test classes start with `Test` |
| `TestPublicFunctionDocstrings` | All public functions have docstrings |
| `TestPublicFunctionTypeAnnotations` | All public functions have return type annotations |
| `TestNoTodoFixmeHack` | No TODO, FIXME, HACK, or XXX markers in code |
| `TestNoWildcardImports` | No `from x import *` (redundant with NoStarImports — belt + suspenders) |
| `TestNoMutableDefaultArgs` | No `list`, `dict`, or `set` as default parameter values |
| `TestCyclomaticComplexity` | No function exceeds complexity of 15 |

**Rules:**
1. Every convention class uses internal loops (not `@pytest.mark.parametrize`)
   to avoid test count inflation.
2. A convention violation causes one test failure per convention class, with ALL
   violating files listed in the assertion message.
3. New convention classes MUST be added when a new structural rule is established.
4. Convention tests scan ALL `.py` files under `src/` and `tests/` automatically —
   new files are covered without any test changes.

---

## Item 9: Code Signing (orbit-sign)

**Tool:** `orbit-sign` — 5-segment cryptographic watermark

**Signature format:**
```
# -- sig: mgh-{mark}.{g}.{hubers}.{file}.{hmac}
```

| Segment | Source | Crackable? |
|---------|--------|-----------|
| 1 (4 hex) | SHA-256("mark") | Yes — dictionary attack |
| 2 (2 hex) | SHA-256("g") | Yes — dictionary attack |
| 3 (6 hex) | SHA-256("hubers") | Yes — dictionary attack |
| 4 (4 hex) | SHA-256(filename) | Yes — ties sig to file |
| 5 (6 hex) | HMAC-SHA256(key, content) | No — requires secret key |

**Rules:**
1. Every `.py` file in `src/` and `tests/` MUST have a valid orbit-sign signature.
2. Signatures MUST be the last line of the file.
3. Two blank lines MUST precede the signature line (PEP 8 top-level spacing).
4. `orbit-sign sign` MUST be run after any code changes, before commit.
5. `orbit-sign verify` confirms all 5 segments match — Segment 5 proves the file
   came from the authorized build pipeline.
6. The signing key lives at `~/.ace/signing-key` (never committed, 600 perms).

---

## Item 10: Code Hygiene Policies

### No TODO/FIXME/HACK/XXX Markers

**Rule:** Source code MUST NOT contain TODO, FIXME, HACK, or XXX comments.

**Rationale:** These markers accumulate silently. In an unattended automation tool,
"fix later" becomes "fix never." Track work items in the issue tracker or spec
system, not in code comments.

**Enforcement:** `TestNoTodoFixmeHack` convention class scans all files via regex.

### No Wildcard Imports

**Rule:** `from x import *` MUST NOT appear in any file.

**Rationale:** Wildcard imports make it impossible to trace where names come from,
break static analysis, and can silently shadow names.

**Enforcement:** `TestNoWildcardImports` convention class scans all files via AST.

### No Mutable Default Arguments

**Rule:** Function parameters MUST NOT use `list`, `dict`, or `set` literals as
default values.

**Rationale:** Mutable defaults are shared across calls — a classic Python bug.
Use `None` with a guard, or `dataclasses.field(default_factory=...)`.

```python
# -- WRONG: mutable default shared across calls
def bad(items: list = []):
    ...

# -- RIGHT: None guard creates fresh list per call
def good(items: list | None = None):
    items = items or []
    ...
```

**Enforcement:** `TestNoMutableDefaultArgs` convention class scans all files via AST.

### Public Function Requirements

**Rule:** Every public function (name not starting with `_`) MUST have:
1. A docstring (first line describes what the function does).
2. A return type annotation.

**Enforcement:** `TestPublicFunctionDocstrings` and `TestPublicFunctionTypeAnnotations`
convention classes scan all source files via AST.

---

## Item 11: Gate Bypass Rules

1. No gate may be bypassed without a spec-level justification.
2. `# noqa`, `# nosec`, `# pragma: no cover` each require an inline comment
   explaining the specific reason.
3. `--no-verify` on git commit MUST NEVER be used.
4. Pre-commit hooks (when configured) MUST NOT be disabled.

---

## 2. The Problem

REQUIRED — fill before build.

---

## 3. Requirements

REQUIRED — fill before build.

---

## 4. Architecture/Design

REQUIRED — fill before build.

---

## 5. Data Model

REQUIRED — fill before build.

---

## 6. Data Boundary

REQUIRED — fill before build.

---

## 7. MCP/API Interface

— if applicable.

---

## 8. States & Modes

— if applicable.

---

## 9. Configuration

— if applicable.

---

## 10. Rules & Constraints

REQUIRED — fill before build.

---

## 11. Quality Attributes

— if applicable.

---

## 12. Shared Patterns

— if applicable.

---

## 13. Integration Points

REQUIRED — fill before build.

---

## 14. Foundation References

— if applicable.

---

## 15. Self-Correction

— if applicable.

---

## 16. Assumptions

REQUIRED — fill before build.

---

## 17. Success Criteria

REQUIRED — fill before build.

---

## 18. Build Notes/Estimate

— filled during build.

---

## 19. Test Categories

— filled during build.

---

## 20. Failure Modes

— if applicable.

---

## 21. Dependencies + Used By

REQUIRED — fill before build.

---

## 22. Decisions

REQUIRED — fill before build.

---

## 23. Open Questions

— if applicable.

---

## 24. Glossary

— if applicable.

---

## 25. Risk/Criticality

— if applicable.

---

## 26. External Scan

— if applicable.

---

## 27. Security Considerations

— if applicable.

---

## 28. Performance/Resource

— if applicable.

---

## 29. Approval Record

— filled after build.

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

— filled after build.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| v0.1 | 2026-03-14 | Initial draft — 12 quality gates documented |
