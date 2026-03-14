# IFS-001: Claude Code CLI Interface

*The exact contract between Rondo and Claude Code's `claude -p` command.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** Claude Code CLI (Anthropic) | **Blocks:** REQ-001 (Core)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Documents the interface between Rondo (the conductor) and Claude Code's `claude -p` (the orchestra). Defines exactly what Rondo sends, what it expects back, and what environment conditions must be met.

**IN scope:**
- Command-line invocation format
- Environment variable requirements
- Input format (prompt structure)
- Output format (expected response)
- Error conditions and exit codes
- Model and effort flags

**OUT of scope:**
- Claude Code internals (Anthropic's product, may change)
- Rondo's dispatch logic (REQ-001)
- Authentication with Anthropic's servers

---

## The Interface

### Invocation

```
claude -p <prompt> [--model <model>] [--effort <effort>]
```

| Flag | Values | Required | Default |
|------|--------|----------|---------|
| `-p` | Prompt text (string) | YES | — |
| `--model` | `opus`, `sonnet`, `haiku` | NO | sonnet |
| `--effort` | `low`, `medium`, `high`, `max` | NO | high |

### Environment Variables

| Variable | Rondo Action | Why |
|----------|-------------|-----|
| `CLAUDECODE` | MUST strip from child env | Prevents "cannot launch inside another session" error |
| `ANTHROPIC_API_KEY` | Strip when auth=max, keep when auth=api | Controls billing: subscription vs pay-per-token |

### Input (Prompt Format)

Rondo sends a structured prompt built from the three-field contract:

```markdown
# Rondo Task N: {task_name}

**Description:** {description}

**Read these files first:** {comma-separated file paths}

**Do:** {instruction}

**Done when:** {completion criteria}

---
**Output format:** Respond with a JSON block at the end:
```json
{"status": "done"|"blocked", "confidence": 0.0-1.0,
 "result": "what you did", "question": "if blocked, what you need"}
```
```

### Expected Output

Claude writes to stdout. Rondo expects a JSON block somewhere in the output:

```json
{
  "status": "done",
  "confidence": 0.85,
  "result": "Found 3 missing sections in spec",
  "question": ""
}
```

**Parsing rules:**
1. Search stdout for a JSON block matching the expected schema
2. If valid JSON found → use it
3. If no JSON or malformed → status "partial", store raw output as result
4. If stdout is empty → status "error"

### Exit Codes

| Exit Code | Meaning | Rondo Action |
|-----------|---------|-------------|
| 0 | Success | Parse output for JSON result |
| 1 | Error (auth, config, crash) | Record "error" with stderr |
| Non-zero | Unknown error | Record "error" with stderr |

### Stderr

Rondo captures stderr separately. It may contain:
- Auth errors ("Credit balance is too low")
- Nested session errors ("cannot be launched inside another Claude Code session")
- Model errors, rate limit messages

Stderr content is stored in the result JSON for debugging but never shown in reports.

---

## Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `claude -p` interface is stable across versions | Rondo may break on Claude Code updates — pin version or test |
| A2 | Prompt text can be arbitrary length | Very long prompts may fail — test limits |
| A3 | Claude respects `--model` flag for all model names | New models may use different flag format |
| A4 | Stdout contains the complete response | Truncation would lose the JSON block |

---

## Version Compatibility

This interface was tested against Claude Code as of 2026-03-13. Anthropic may change the CLI interface at any time. Rondo should:
1. Pin to a known-working Claude Code version if possible
2. Test interface assumptions on every upgrade
3. Log Claude Code version in overnight results for debugging

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial interface documentation |
