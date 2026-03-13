# F01: Error Handling & Resilience

*How Rondo handles failures — subprocess crashes, bad output, timeouts.*

**Created:** 2026-03-13 | **Status:** DRAFT

---

## Principle

Rondo runs unattended. Every failure must be captured, recorded, and survivable. No silent failures. No crashes from bad subprocess output. No hung processes blocking the pipeline.

---

## Rules

1. Every task result (success or failure) MUST include: task name, error message (if any), wall-clock duration, and the prompt that was sent.
2. Subprocess errors (exit code != 0) MUST be distinguishable from task-logic errors (Claude returned "blocked") in the result JSON.
3. If Claude returns malformed JSON, dispatch MUST fall back to raw output with status "partial" — never discard good work because parsing failed.
4. Subprocess timeouts MUST be configurable. Default: 5 minutes per task.
5. A timed-out subprocess MUST be killed and recorded as status "error" with reason "timeout".
6. A single task failure MUST NOT crash the framework or affect other tasks.
7. In overnight mode, a failed phase MUST NOT block subsequent phases.
8. API keys, tokens, and credentials MUST NEVER appear in result files or error logs.
9. All exceptions in dispatch MUST be caught, logged with context, and converted to error results.
10. The morning report MUST always be generated — even if all phases fail. "Everything failed" is useful information.

---

## Error Categories

| Category | Example | Status | Recovery |
|----------|---------|--------|----------|
| Subprocess crash | exit code 1, segfault | error | Log stderr, continue to next task |
| Empty output | Claude returned nothing | error | Log, may indicate auth failure |
| Malformed JSON | Claude didn't follow format | partial | Use raw output as result |
| Timeout | Task exceeded time limit | error | Kill process, log duration |
| Auth failure | Invalid API key, expired | error | Log, distinguishable from logic errors |
| Gate failure | Pre-condition not met | blocked | Skip round, log reason |
| Network error | DNS, connection refused | error | Log, retry is caller's decision |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft |
