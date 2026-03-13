# F03: Concurrency & Safety

*How Rondo runs tasks in parallel safely — no injection, no leaks, no corruption.*

**Created:** 2026-03-13 | **Status:** DRAFT

---

## Principle

Rondo dispatches subprocesses that can modify files. Parallel execution means multiple processes running at once. Safety means: no command injection, no credential leaks, no file corruption from concurrent writes, no unbounded resource consumption.

---

## Concurrency Rules

1. Parallel dispatch MUST use `concurrent.futures.ThreadPoolExecutor` (I/O-bound work, not CPU-bound).
2. No shared mutable state between task threads. Each task gets its own result dict.
3. Throttle delay between task launches MUST be configurable (default: 2 seconds) to respect external rate limits.
4. Conflict detection MUST flag files mentioned by 2+ concurrent task outputs.
5. Conflict detection is advisory (warning), not preventive (blocking). Consumer decides how to handle.
6. Worker count MUST be bounded by config. No unbounded thread creation.
7. If a task thread raises an unhandled exception, the executor MUST NOT crash. Other tasks continue.

## Security Rules

8. Subprocess invocation MUST use list arguments (`["claude", "-p", prompt]`), NEVER `shell=True`.
9. `ANTHROPIC_API_KEY` MUST NEVER appear in: result JSON files, log output, error messages, prompts, or morning reports.
10. `CLAUDECODE` env var MUST always be stripped from child environments to prevent nested-session blocking.
11. Task prompts MUST NOT contain credentials, tokens, or secrets. If context files contain secrets, the round definition is responsible for excluding them.
12. Result files MUST be written with restrictive permissions (owner read/write only where platform supports it).

## Resource Rules

13. Every subprocess MUST have a configurable timeout (default: 5 minutes). Timed-out processes MUST be killed.
14. Result files MUST be bounded in size — if raw_output exceeds a configurable limit (default: 1MB), truncate with a note.
15. The overnight event log MUST be bounded (rolling 100 entries). No unbounded file growth.

---

## Why These Rules

| Rule | Attack / Failure It Prevents |
|------|------------------------------|
| No shell=True | Command injection via task name or file path |
| API key stripping | Credential leak in result files shared or committed to git |
| CLAUDECODE stripping | Nested session guard blocks all dispatch |
| Subprocess timeout | Hung process blocks worker thread forever |
| Bounded result files | One verbose Claude response fills disk |
| Rolling event log | Months of overnight runs don't exhaust disk |
| Conflict detection | Two tasks overwrite each other's output |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft |
