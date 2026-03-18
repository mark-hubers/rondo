# SOP-001: Build & Run Procedure

*How to build, test, and run Rondo from scratch.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-SOP-001, Caliber-SOP-001, Rondo-SOP-001

---

## 1. Prerequisites

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

## 2. Setup

1. Clone the repository (Rondo lives inside the ace2 monorepo):
   ```bash
   git clone <repo-url> ace2
   cd ace2/rondo
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

## 3. Build

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

## 4. Test

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

## 5. Run

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

## 6. Verify

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

## 7. Troubleshooting

| Problem | Fix |
|---------|-----|
| `rondo: command not found` | Run `pip install -e .` in the rondo directory |
| Claude CLI not found | Install Claude Code CLI, ensure on PATH |
| B404/B603 bandit errors | Use `--skip B404,B603` (expected for subprocess usage) |
| Timeout on dispatch | Check `rondo.toml` timeout value, increase if needed |
| Import errors | Confirm venv is activated and editable install ran |

---

## 8. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal SOP-001 for Rondo. |
