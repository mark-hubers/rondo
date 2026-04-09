# Rondo v1.0 Vision — Scripted Conversations with AI

**Created:** 2026-04-09 (Session 100)
**Author:** Mark Hubers
**Status:** VISION — not a spec, guides spec work

---

## The Core Idea

Rondo scripts conversations with AI the same way you talk to AI:

1. **Say what to do** (instruction)
2. **Say what to read** (context)
3. **Say what to return** (done_when + return_format)

AI does the work. Returns structured data. Next step uses that data.
That's it. Everything else is engine underneath.

---

## Three Layers — Same Pattern

```
Simple:    rondo "review this code" ./src/ → {"passed": true}
Medium:    rondo run review.yaml → JSON results
Power:     rondo run review.py (hooks, conditions, loops)
```

All three use the same engine. User picks their comfort level.

---

## The Three-Field Contract (REQ-100 req 3, extended)

| Field | What | Example |
|-------|------|---------|
| **Do** | instruction | "Review this code for security issues" |
| **Read** | context_files / context_data | `["./src/login.py"]` |
| **Done + Return** | done_when + return_format | `{"passed": bool, "issues": list}` |

The return_format tells AI: "give me back THIS shape." Not a wall of text.
Scriptable output. Machine-readable. Pipeline-ready.

---

## Controlled Returns Enable Chaining

```yaml
tasks:
  - name: review
    instruction: "Review for bugs"
    return_format: {"passed": bool, "issues": list}

  - name: fix
    instruction: "Fix these: {{review.issues}}"
    depends_on: review
    only_if: "not review.passed"
    return_format: {"fixed": list}

  - name: verify
    instruction: "Verify fixes work"
    depends_on: fix
    return_format: {"passed": bool}
```

Each step's return feeds the next step's input.
A conversation turned into a pipeline.

---

## Input Formats (Language-Agnostic)

| Format | Who uses it | How |
|--------|-------------|-----|
| YAML | Most users | `rondo run round.yaml` |
| JSON | Machines, CI/CD | `rondo run round.json` |
| Python | Power users (hooks, conditions) | `rondo run round.py` |
| CLI string | Quickest path | `rondo "review this"` |
| Stdin pipe | Unix composition | `git diff \| rondo "will this break?"` |

Rondo doesn't care what language made the file. It reads the task
definition and runs it.

---

## What This Means for the Codebase

### Already Built (Session 100)
- 3-process architecture (Host → MCP → Provider)
- 5 provider adapters (Gemini, Grok, Mistral, OpenAI, Ollama)
- Circuit breaker, retry, idempotency, budget caps
- Audit trail (INTENT + OUTCOME)
- Dispatch hooks (pre/post)
- 1647 tests, pylint 10.00

### Needs Building (v1.0 roadmap)
1. **YAML/JSON round loader** — `load_round_file()` handles .yaml/.json
2. **return_format field** on Task — structured output control
3. **Template variables** — `{{previous_task.field}}` in instructions
4. **depends_on / only_if** — task chaining with conditions
5. **Simple CLI** — `rondo "prompt"` without subcommands
6. **5 real examples** — copy-paste-modify

### Doesn't Change
- Engine (Round, Task, TaskResult) — just adds fields
- Dispatch pipeline — same path, hooks already wired
- Provider adapters — untouched
- Audit trail — untouched
- All existing Round files — still work

---

## The Unix Philosophy Applied to AI

```
echo "review this" | rondo → structured result | next tool
```

Do one thing well. Accept input from stdin. Produce output to stdout.
Compose with other tools. That's Rondo.

---

## Why This Matters

Everyone else treats AI as an API call.
Rondo treats AI as a **programmable pipeline with controlled returns.**

That's the difference between `curl` and `make`.
Both call HTTP. One is a tool. The other is a build system.

Rondo is the build system for AI work.
