# Rondo-SOP-101: Build & Run Procedure

*How to build, test, and run Rondo from scratch.*

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-SOP-002, Rondo-SOP-101 (Caliber), Rondo-SOP-101 (Rondo)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)

---

## 1. Purpose & Scope

**What this SOP does:** Step-by-step procedure for setting up, building, testing, and
running Rondo from a clean checkout. Covers prerequisites, environment setup, build gates,
test execution, and runtime verification.

**IN scope:**
- Prerequisites and system requirements
- Python venv setup and package installation
- Build gates (format, lint, security, types, tests)
- Running Rondo (single task, overnight, parallel)
- Verification and troubleshooting

**OUT scope:**
- Spec creation (Rondo-SOP-100 owns that)
- Release process (Rondo-SOP-102 owns that)
- Incident response (Rondo-SOP-103 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without a documented build procedure, new contributors (or Mark after a long break) waste
time figuring out the right Python version, the correct venv setup, which bandit rules to
skip, and what "passing" looks like. This SOP eliminates guesswork.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Build procedure reproducible from clean checkout in <10 minutes | MUST |
| 002 | All 6 build gates must pass before code is considered buildable | MUST |
| 003 | Coverage floor enforced at 90% | MUST |
| 004 | Tests mock Claude CLI — no real API calls during build | MUST |
| 005 | Troubleshooting section covers common failures | SHOULD |


## Prerequisites

| Requirement | Minimum Version | Check Command |
|-------------|----------------|---------------|
| Python | 3.12+ | `python3 --version` |
| pip / uv | latest | `pip --version` or `uv --version` |
| Git | 2.30+ | `git --version` |
| Claude CLI | latest | `claude --version` |
| ruff | latest | `ruff --version` |
| bandit | latest | `bandit --version` |
| mypy | latest | `mypy --version` |

**Claude CLI** is required because Rondo dispatches tasks to Claude via subprocess.

**Operating system:** macOS (primary), Linux (supported).

---

## 4. Architecture / Design

### Build Gate Pipeline

```
1. ruff format --check    → Code formatting
2. ruff check             → Linting
3. bandit -r src/rondo/   → Security scan
4. mypy src/rondo/        → Type checking
5. pytest tests/          → Test suite
6. Coverage check         → >= 90%
```

All 6 gates must pass. Failure in any gate blocks the build.

---

## 5. Data Model

Not applicable — this is a build procedure. No runtime data model.

---

## 6. Data Boundary

### Setup

1. Clone the repository:
   ```bash
   git clone <repo-url> rondo
   cd rondo
   ```

2. Create or activate the venv:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install Rondo in editable mode:
   ```bash
   pip install -e .
   ```

4. Verify the CLI is available:
   ```bash
   rondo --help
   ```

5. Verify Claude CLI is accessible:
   ```bash
   claude --version
   ```

---

## 7. MCP / API Interface

Not applicable for this SOP. Future: CORE-STD-021 MCP tools could trigger build gates
remotely, enabling CI/CD integration without SSH access.

---

## 8. States & Modes

### Build

Rondo is a Python package. No compile step.

1. Install in editable mode (if not done in setup):
   ```bash
   pip install -e .
   ```

2. Run format and lint:
   ```bash
   ruff format --check src/ tests/
   ruff check src/ tests/
   ```

3. Run security scan:
   ```bash
   bandit -r src/rondo/ --skip B404,B603
   ```
   B404/B603 are skipped because Rondo's core function is invoking Claude via subprocess.

4. Run type checks:
   ```bash
   mypy src/rondo/
   ```

---

## 9. Configuration

### Test

1. Run the full test suite:
   ```bash
   pytest tests/ -v --tb=short
   ```

2. Run with coverage:
   ```bash
   pytest tests/ --cov=rondo --cov-report=term-missing
   ```

3. Coverage floor is 90% (enforced in `pyproject.toml`).

4. **Passing looks like:** All tests green, coverage >= 90%.

5. Note: Tests mock the Claude CLI — they do not make real API calls.

---

## 10. Rules & Constraints

1. **All 6 gates must pass.** No exceptions. Format, lint, security, types, tests, coverage. Violation ID: `SOP101-ALL-GATES`
2. **B404/B603 are expected.** Bandit subprocess warnings are legitimate for Rondo. Skip them. Violation ID: `SOP101-BANDIT-SKIP`
3. **No real API calls in tests.** All provider interactions are mocked. Violation ID: `SOP101-MOCK-ONLY`
4. **90% coverage floor.** Non-negotiable. Violation ID: `SOP101-COVERAGE-FLOOR`

### Run

Rondo runs via the `rondo` CLI:

1. Run a single task:
   ```bash
   rondo run task_file.py
   ```

2. Run with specific model:
   ```bash
   rondo run --model sonnet task_file.py
   ```

3. Run overnight batch:
   ```bash
   rondo overnight
   ```

4. Run parallel tasks:
   ```bash
   rondo parallel tasks/
   ```

5. Configuration in `rondo.toml`:
   ```toml
   [rondo]
   model = "sonnet"
   timeout = 300
   ```

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Reproducibility | Same result on clean checkout | Build must be deterministic |
| Speed | Full build + test in <5 minutes | Fast feedback loop |
| Coverage | >= 90% | Sufficient for critical dispatch code |
| Security | Zero bandit findings (excluding B404/B603) | No security regressions |

---

## 12. Shared Patterns

### Verify

After setup, confirm Rondo is working:

| Check | Command | Expected |
|-------|---------|----------|
| CLI responds | `rondo --help` | Shows usage info |
| Lint passes | `ruff check src/rondo/` | No errors |
| Types pass | `mypy src/rondo/` | Success |
| Tests pass | `pytest tests/ -v` | All green |
| Coverage met | `pytest tests/ --cov=rondo` | >= 90% |
| Claude accessible | `claude --version` | Version string |

If all checks pass, Rondo is ready for development.

---

## 13. Integration Points

| Integration | What | Notes |
|-------------|------|-------|
| `bin/build` | Self-contained build gate | runs all 6 gates |
| pre-commit hooks | Automated gate enforcement | Runs on every commit |
| CI/CD (future) | Automated build pipeline | Same 6 gates |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-003 (Quality) | 90% coverage floor, 6 build gates |
| CORE-STD-012 (Requirement Readiness) | Build gates validate spec readiness |
| CORE-STD-013 (TrackerData) | Build results logged as trackerdata |
| CORE-STD-021 (MCP Standard) | Future MCP tool for remote build triggering |
| Rondo-STD-111 (Code Quality) | ruff lint rules |

---

## 15. Self-Correction

- If a build gate fails, the error output includes the exact command to re-run and the
  exact file/line that failed. No "build failed" without context.
- If coverage drops below 90% after a code change, pytest reports exactly which lines
  are uncovered, guiding the developer to write targeted tests.
- If a new bandit rule fires (not B404/B603), it must be investigated, not skipped.

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `rondo: command not found` | Run `pip install -e .` in the rondo directory |
| Claude CLI not found | Install Claude Code CLI, ensure on PATH |
| B404/B603 bandit errors | Use `--skip B404,B603` (expected for subprocess usage) |
| Timeout on dispatch | Check `rondo.toml` timeout value, increase if needed |
| Import errors | Confirm venv is activated and editable install ran |

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Python 3.12+ is available on the build machine | May need pyenv or container |
| A2 | pip install -e . works for monorepo structure | May need explicit path configuration |
| A3 | Claude CLI is installed and on PATH | Preflight (Rondo-REQ-103) catches this |
| A4 | macOS or Linux build environment | Windows not supported |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Clean checkout → build in <10 minutes | Time the procedure |
| 2 | All 6 gates pass | Run each gate command |
| 3 | Coverage >= 90% | pytest --cov output |
| 4 | rondo --help works | CLI test |
| 5 | Troubleshooting covers top 5 issues | Manual review |

---

## 18. Build Notes / Estimate

Not applicable — this IS the build procedure.

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Gate | Each build gate runs independently | 6 |
| Smoke | rondo --help, rondo run with mock | 2 |
| Coverage | Coverage report matches floor | 1 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Python version too old | Build fails at syntax level | Prerequisites table + check command |
| Missing dependency | Import error at test time | pip install -e . covers all deps |
| Bandit false positive | Build blocked by legitimate code | --skip known false positives |
| Coverage drop after refactor | Gate fails | Write tests before refactoring |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| CORE-SOP-001 | Universal build procedure template |
| Rondo-STD-111 | Code quality rules (ruff config) |
| DEC-017 | Universal SOP numbering |

| Used By | Why |
|---------|-----|
| Rondo-SOP-102 | Release procedure pre-checks use this build process |
| All developers | Entry point for development |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 6 build gates (not 3, not 10) | 2026-03-18 | Covers format, lint, security, types, tests, coverage |
| D2 | B404/B603 skip is permanent | 2026-03-18 | Subprocess is Rondo's core pattern, not a vulnerability |
| D3 | 90% coverage floor | 2026-03-18 | High enough for dispatch-critical code, not 100% which penalizes exploration |
| D4 | Mock all AI providers in tests | 2026-03-18 | Tests must be fast, free, and deterministic |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should there be a `rondo build` CLI command that runs all 6 gates? | Developer convenience | OPEN |
| Q2 | Should build results be persisted for trend analysis? | Build performance tracking | OPEN |
| Q3 | Should there be a Docker-based build for reproducibility? | CI/CD portability | OPEN — future |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Build gate** | One of 6 quality checks that must pass before code is considered buildable |
| **Coverage floor** | Minimum test coverage percentage (90%) enforced by build |
| **Editable install** | `pip install -e .` — package installed as symlink for development |
| **B404/B603** | Bandit rules for subprocess — false positives for Rondo |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Build tool version drift | Medium | Gates behave differently | Pin tool versions in requirements-dev.txt |
| Coverage drops unnoticed | Low | Quality regression | 90% floor enforced in CI |
| New developer can't build | Medium | Lost productivity | This SOP + troubleshooting section |

---

## 26. External Scan

Build gate pattern is standard in Python projects. Tools used (ruff, bandit, mypy, pytest)
are industry-standard. The 6-gate pattern is self-contained in `bin/build`. Similar to
GitHub Actions CI workflows with multiple quality checks.

---

## 27. Security Considerations

- Bandit security scan runs on every build. B404/B603 are the only allowed skips.
- Dependencies should be audited regularly (`pip audit` or equivalent).
- No real API keys used during testing — all providers mocked.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Full build (all 6 gates) | <5 minutes | Most time in pytest |
| Format check | <5 seconds | ruff format is fast |
| Lint | <10 seconds | ruff check is fast |
| Security scan | <15 seconds | bandit scans src/ only |
| Type check | <30 seconds | mypy on src/ only |
| Test suite | <3 minutes | All tests mocked |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not applicable — this is a build procedure SOP.

---

## 31. AI Went Wrong

Not applicable — this is a build procedure SOP.

---

## 32. AI Assumptions

Not applicable — this is a build procedure SOP.

---

## 33. AI Cost

Not applicable — this is a build procedure SOP.

---

## 34. Notes

- The B404/B603 bandit skip is a deliberate decision, not a workaround. Rondo's core
  purpose is invoking Claude via subprocess. Bandit flagging subprocess as a vulnerability
  would make every file in the project fail the security scan.
- The 90% coverage floor was chosen because Rondo has critical financial implications
  (AI costs money). Under-tested dispatch code could silently overspend.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Build execution procedure | WORKING | `bin/build` documented and operational | After build changes |
| Gate failure handling | WORKING | Fix-recheck loop documented | Every sprint |
| Build environment setup | WORKING | Shared venv documented | After env changes |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal CORE-SOP-002 for Rondo. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
