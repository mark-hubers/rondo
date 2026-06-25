# How to Build Rondo

A short, mechanical guide to the build loop. For the *why* behind the rules,
see `CONTRIBUTING.md`. For the stable public surface (CLI commands, MCP tools,
config keys), see `docs/API-STABILITY.md`.

## Setup

```bash
git clone <repo-url> rondo
cd rondo
uv sync --extra dev          # create .venv with runtime + dev dependencies
uv tool install --editable . # put the `rondo` CLI on your PATH
rondo doctor                 # confirm the install is healthy (free, no dispatch)
```

## The TDD loop

```
1. Read the spec            # specs/Rondo-*.md — know WHAT to build
2. Write the test FIRST     # it must FAIL (RED)
3. Write code to pass it    # GREEN
4. bin/build                # the 6-gate quality check, before EVERY commit
5. Live-verify              # run the real command/dispatch, not just unit tests
6. git commit
```

Run one test while iterating:

```bash
.venv/bin/python -m pytest tests/unit/test_xxx.py::TestNewClass -v --tb=short
```

## The build gate

```bash
bin/build
```

Six gates, all must pass: ruff lint, ruff format, bandit (security), mypy,
pytest (zero-collected = hard fail), pylint ≥ 9.0. The build bumps the build
counter automatically.

## Three interfaces

```bash
## 1. Python import (for scripts / automation)
from rondo import dispatch_task, RondoConfig
result, usage = dispatch_task(task, config)

## 2. CLI (for humans, shell scripts)
rondo run round.py --dry-run
rondo metrics --json
rondo audit --cost

## 3. MCP stdio (for Claude Code — tools called mid-conversation)
## Enable in your Claude Code settings.json:
##   "rondo": { "command": "/path/to/.local/bin/rondo", "args": ["mcp"] }
```

## The always-on dispatch pipeline

Every dispatch (success or error) automatically produces:

```
dispatch_task()
  → INTENT audit record (crash-safe)
  → subprocess / auto_fn
  → OUTCOME audit record
  → sanitize (scrub secrets)
  → spool file (mailbox for consumers)
  → history record
  → metrics dict (in TaskResult.metrics)
  → return to caller
```

No flags needed; the caller ignores what it doesn't need.

## Versioning (CalVer + build counter)

```
Format:  MAJOR.MINOR.PATCH+YYYYMMDD.BUILD
Example: 0.7.0+20260615.12
```

Single source of truth: `pyproject.toml` holds the base version; `_version.py`
reads it and adds build metadata. Never hardcode a version string — always
`from rondo._version import get_version`. Bump the build counter via
`rondo version --bump` (or `from rondo._version import bump_build`).

## Convention locks (enforced by `tests/conventions/`)

- SPDX header + module docstring with spec references on every module
- Import layers enforced (engine → config → dispatch → runner → parallel → …)
- No bare `print` in library modules (CLI/output modules are exempt)
- Cyclomatic complexity ≤ 15 per function (extract, never exempt)
- Every CLI flag has a test (the dead-flag lock)

A lock firing on your change means *fix the change* or update the registry with
a rationale — never weaken a lock. See `CONTRIBUTING.md`.
