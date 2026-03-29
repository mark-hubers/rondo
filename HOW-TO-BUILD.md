# How to Build Rondo — OB1 Process Guide

**For:** Any Claude session building Rondo from ~/.claude/ or ace2
**System:** OB1 (manual build process, until OB2 replaces it)
**Status:** 766 tests, 93% coverage, 58% spec coverage, 60 E2E tests

---

## TL;DR — The Loop

```
1. ace-sprint start RONDO-FIX-NNN     ## Register sprint
2. Read the spec                       ## Know WHAT to build
3. Write tests FIRST (TDD)            ## Tests should FAIL
4. Write code to make tests pass       ## Tests should PASS
5. ace-build full                      ## 8-gate quality check
6. ai-review (Phase 3b)               ## External AI review
7. Fix findings                        ## Don't ship with known bugs
8. E2E spike                          ## Prove it works for real
9. ace-sprint done RONDO-FIX-NNN      ## Close sprint
10. git commit                         ## Ship it
```

---

## Before Starting

```bash
## Enable Caliber build mode (unlocks protected source paths)
## Mark must type this in the CC prompt — it's a keyword, not a command
caliber build

## If importing rondo from ace2 scripts fails (ModuleNotFoundError):
/opt/homebrew/bin/uv tool install --editable --force ~/git/mhubers/ace2/rondo

## Health check
ace-preflight

## Check where we are
ace-sprint status

## Check Rondo test status
cd ~/git/mhubers/ace2/rondo && .venv/bin/python -m pytest tests/ -q

## Check spec coverage (current: ~58%)
python3 scripts/traceability.py
```

---

## The Sprint (Step by Step)

### Step 1: Register Sprint
```bash
ace-sprint register RONDO-FIX-NNN --layer FIX --orbit 5 --round 7
ace-sprint start RONDO-FIX-NNN
```

### Step 2: Read the Spec
Specs live in `~/git/mhubers/ace2/rondo/specs/`. Read the requirements table:
```bash
grep "^| [0-9]" rondo/specs/Rondo-REQ-NNN-name.md | head -20
```

### Step 3: Write Tests FIRST (TDD)
Add tests to the appropriate test file. Tests should FAIL because the code doesn't exist yet.
```bash
## Run just your new tests — should RED
.venv/bin/python -m pytest tests/test_xxx.py::TestNewClass -v --tb=short
```

### Step 4: Write Code
Make the tests pass. Follow existing patterns:
- New module? Copy preflight.py as template
- New field? Add to engine.py dataclass
- New CLI flag? Add to cli.py `_add_common_flags` + `_build_config`
- New dispatch feature? Add to dispatch.py `_build_subprocess_cmd`

### Step 5: Build Gate
```bash
cd ~/git/mhubers/ace2 && ace-build full
```
Must pass: ruff lint, ruff format, bandit, mypy, pytest, pylint ≥ 9.0

### Step 6: AI Review (Phase 3b — MANDATORY)
```bash
cd ~/git/mhubers/ace2
python3 scripts/ai_review.py rondo/src/rondo/CHANGED_FILE.py --provider gemini --save
```
Log findings: `ace-sprint finding --severity ... --category ai-review --description "..."`
Fix all findings before committing.

### Step 7: E2E Spike
Run a real test of the feature:
```bash
CLAUDECODE="" ~/.local/bin/rondo preflight         ## Or whatever you built
CLAUDECODE="" ~/.local/bin/rondo run file.py --dry-run --verbose
```

### Step 8: Close Sprint
```bash
ace-sprint activity RONDO-FIX-NNN --loop write_tests --cat test_write --activity "N new tests: ..."
ace-sprint activity RONDO-FIX-NNN --loop verify --cat test_write --activity "NNN tests pass. ..."
ace-sprint done RONDO-FIX-NNN --force
```

### Step 9: Commit
```bash
cd ~/git/mhubers/ace2
git add rondo/
git commit -m "Session NN Sprint N (RONDO-FIX-NNN): what was done"
```

---

## Where Things Live

| What | Where |
|------|-------|
| Source code | `rondo/src/rondo/*.py` (16 modules) |
| Tests | `rondo/tests/test_*.py` (727 tests) |
| E2E tests | `rondo/tests/test_integration_e2e.py` (60 tests) |
| Spike tests | `rondo/tests/test_spikes.py` (9 CC flag sentinels) |
| Specs | `rondo/specs/Rondo-*.md` (40 files) |
| Examples | `rondo/examples/` (11 round definitions) |
| Config | `rondo/pyproject.toml`, `rondo/rondo.toml` |
| Scripts | `rondo/scripts/traceability.py`, `rondo/scripts/setup-rondo.sh` |
| History | `rondo/reports/history/` (JSONL per day) |
| Reports | `rondo/reports/` |
| AI reviews | `reports/ai-reviews/` (Gemini/Grok JSON) |

## Module Architecture

```
L0 (data):     engine.py, config.py
L1 (dispatch): dispatch.py, dispatch_prompt.py, dispatch_parse.py
L2 (orchestr): runner.py, parallel.py
L3 (batch):    overnight.py
Utility:       preflight.py, history.py, notify.py, ai_help.py
Output:        report.py, live.py
Entry:         cli.py, __init__.py, __main__.py
```

## Convention Rules

- Every module has SPDX header + docstring with spec refs
- Every module ends with `# -- sig: mgh-6201.cd.bd955f.XXXX.YYYYYY`
- Import layers enforced (engine→config→dispatch→runner→parallel→...)
- No bare print in library modules (except cli.py, live.py, notify.py)
- Cyclomatic complexity max 15 per function
- Test files reference VER-001
- MgH signature on every .py file (5-segment hex format)

## What's Left to Build (to hit 75% spec coverage)

| Spec | Reqs | Priority | What |
|------|------|----------|------|
| REQ-100 deeper | ~12 | HIGH | Remaining MUST reqs |
| REQ-101 deeper | ~20 | MEDIUM | Spool system, watchdog |
| REQ-107 Flakiness | 19 | MEDIUM | New module — needs history |
| REQ-108 Templates | 17 | MEDIUM | New module — task reuse tracking |
| STD-112 Golden Numbers | 16 | LOW | Drift detection |
| STD-113 Audit Trail | 22 | MEDIUM | Deepen history |
| STD-114 Output Sanitization | 21 | MEDIUM | Secret detection in AI output |
| dispatch.py Phase 2 | — | HIGH | Remove duplicates, use new modules |

## Quick Commands

```bash
## Run all tests
cd ~/git/mhubers/ace2/rondo && .venv/bin/python -m pytest tests/ -v

## Run E2E only
.venv/bin/python -m pytest tests/test_integration_e2e.py -v

## Run with coverage
.venv/bin/python -m pytest tests/ --cov=rondo --cov-report=term

## Run traceability
python3 scripts/traceability.py

## Check installed CLI
rondo preflight
rondo --ai-help
rondo history
rondo --version

## Reinstall after changes
/opt/homebrew/bin/uv tool install --editable --force ~/git/mhubers/ace2/rondo
```

---

## OB1 Rules (Non-Negotiable)

1. **TDD** — write tests FIRST, make them fail, then code
2. **ace-sprint start/done** — track every sprint in DB
3. **ace-build full** — before every commit
4. **AI review (Phase 3b)** — external AI reviews changed files ($0.003/review)
5. **E2E spike** — prove it works with real CLI, not just unit tests
6. **No agents for code** — agents bypass Caliber, do inline only
7. **Read the spec** — before coding anything
8. **Fix findings** — don't ship with known bugs from AI review
9. **`caliber build`** — say this at session start to unlock protected source paths

---

*This guide is for OB1. When OB2 replaces OB1, this file gets archived.*
