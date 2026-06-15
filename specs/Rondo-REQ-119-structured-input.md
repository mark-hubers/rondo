# Rondo-REQ-119: Structured Task Input

*Tasks can receive structured data (JSON, findings, results) — not just file paths.*

**Product:** Rondo
**Category:** REQ (Requirement)
**Created:** 2026-03-28 | **Status:** PARTIAL (verified 2026-06-14, RONDO-432)
**Owner:** Mark G. Hubers
**Depends on:** Rondo-REQ-100 (Core Engine — Task, TaskResult, dispatch_task), CORE-STD-023 (CLI Help Standard)
**Used by:** OB db-validate (Layer 2), Caliber AI review, any tool passing findings to AI
**Follows:** CORE-STD-025 (Event Table), CORE-STD-032 (AI Activity)

---

## 1. Purpose & Scope

Today Rondo tasks only accept file paths (`context_files`). When OB's db-validate finds 711 warnings, it has to write them to a temp file and pass the path. That's a workaround, not a design.

Tasks need to accept structured data directly — findings, results, configuration — so the AI gets clean input without temp file management.

**IN scope:**
- `context_data` field on Task — structured dict/list passed to AI
- `context_data` field on TaskResult — stored in result JSON files (Rondo has no DB — per REQ-100)
- Data gets injected into the prompt alongside context_files
- Works in both live and batch mode
- Size enforcement at task creation (engine level), not dispatch time

**OUT scope:**
- Binary data (images, PDFs)
- Full streaming (chunked delivery mid-task — JSONL in prompts IS supported)
- Task chaining (passing one task's output as next task's input — separate spec)

---

## 2. The Problem

```python
## TODAY (workaround):
findings = run_layer1_checks()
temp_file = "/tmp/findings.json"
Path(temp_file).write_text(json.dumps(findings))
task = Task(
    name="review",
    context_files=[temp_file],   ## ← hack: write to file, pass path
    instruction="Review findings...",
)

## SHOULD BE:
task = Task(
    name="review",
    context_data={"findings": findings},  ## ← direct data, no temp file
    instruction="Review findings...",
)
```

---

## 3. Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Task dataclass SHALL have `context_data: dict` field (default empty dict) | MUST |
| 002 | TaskResult dataclass SHALL have `context_data: dict` field — copy of input data for audit trail | MUST |
| 003 | `context_data` SHALL be serialized to JSON and included in the prompt after context_files content | MUST |
| 004 | `context_data` keys SHALL be labeled in the prompt: `## Input Data: {key}\n{json}` — format shared with dispatch.py `build_prompt()` | MUST |
| 005 | Combined size of `context_files` content + `context_data` JSON SHALL be capped at `max_context_bytes` (default 500KB per REQ-100 req 003 — NOTE: REQ-100 currently only mentions context_files; this req EXTENDS the cap to include context_data). Engine SHALL enforce at task creation, not at dispatch. | MUST |
| 006 | `context_data` SHALL work in both live mode and batch mode | MUST |
| 007 | `context_data` and `context_files` can be used together — data appended after files in prompt | SHOULD |
| 008 | Live mode (`live.py`) SHALL show `context_data` keys and sizes when presenting a task | MUST |
| 009 | `context_data` values MUST be JSON-serializable — engine SHALL reject non-serializable values at task creation with clear error | MUST |
| 010 | `context_data` SHALL support JSONL format for list values — when a value is a list, it MAY be serialized as one JSON object per line instead of one big array. This enables streaming large datasets without loading all into memory. | SHOULD |
| 011 | When `context_data` contains a list > 100 items, dispatch SHOULD use JSONL format in the prompt (one item per line). The prompt SHALL tell the AI: "Input is JSONL — one JSON object per line. Parse each line independently." | SHOULD |

---

## 4. Architecture

```
Calling script (e.g., db-validate):
  findings = run_layer1_checks()
       │
       ▼
  task = Task(
      name="review-findings",
      instruction="For each finding: real or false positive?",
      context_files=["platform.yaml"],
      context_data={"findings": findings, "product": "ob"},
      done_when="JSON array with verdict per finding",
  )
       │
       ▼
  Engine validates:
    - context_data is JSON-serializable? ✓
    - combined size < max_context_bytes? ✓
       │
       ▼
  dispatch.py build_prompt():
    1. Instruction text
    2. Content of context_files (read from disk)
    3. For each key in context_data:
         ## Input Data: findings
         [{"check": "follows_tags", ...}, ...]
         ## Input Data: product
         "ob"
       │
       ▼
  Claude receives full prompt, processes, returns result
       │
       ▼
  TaskResult stores:
    - AI response (existing)
    - context_data copy (NEW — audit trail)
    - usage stats (existing)
```

---

## 5. Data Model

**Changes to existing dataclasses in `rondo/src/rondo/engine.py`:**

```python
@dataclass
class Task:
    # ... existing fields ...
    context_data: dict = field(default_factory=dict)  ## NEW: structured input

@dataclass
class TaskResult:
    # ... existing fields ...
    context_data: dict = field(default_factory=dict)  ## NEW: audit copy of input
```

**Changes to `rondo/src/rondo/dispatch.py` `build_prompt()`:**

```python
## After context_files content, append structured data:
if task.context_data:
    parts.append("\n---\n## Structured Input Data\n")
    for key, value in task.context_data.items():
        parts.append(f"### {key}")
        if isinstance(value, list) and len(value) > 100:
            ## JSONL for large lists — one object per line (req 011)
            lines = "\n".join(json.dumps(item) for item in value)
            parts.append(f"```jsonl\n{lines}\n```")
        else:
            parts.append(f"```json\n{json.dumps(value, indent=2)}\n```")
```

**Changes to `rondo/src/rondo/live.py` `present_task()`:**

```python
## Show context_data summary when presenting task:
if task.context_data:
    print(f"INPUT DATA ({len(task.context_data)} keys):")
    for key, value in task.context_data.items():
        size = len(json.dumps(value))
        print(f"  {key}: {size} bytes")
```

---

## 10. Rules & Constraints

1. `context_data` is OPTIONAL. Existing tasks with only `context_files` keep working unchanged.
2. `context_data` must be JSON-serializable. Engine validates at task creation.
3. Size limit: combined `context_files` content + `context_data` JSON < `max_context_bytes`.
4. `context_data` is READ-ONLY during dispatch. The AI cannot modify input data.
5. Task chaining (output→input between tasks) is OUT OF SCOPE — separate spec if needed.
6. **Security:** `context_data` is injected into the prompt as text. Values are JSON-encoded, not executed. However, string values could contain prompt injection attempts. The dispatch layer SHALL NOT eval or exec any context_data content — JSON serialization only.
7. **Storage:** Results go to JSON files in `results_dir` (per REQ-100). Rondo has no database. Consumers (OB, Caliber) copy results to their own DBs if needed.

---

## 34. Feature Maturity

| Feature | Status | Evidence |
|---------|--------|----------|
| `context_data` on Task | THEORY | Specced, not coded |
| `context_data` on TaskResult | THEORY | Specced, not coded |
| Prompt injection of data | THEORY | Code snippet in section 5 |
| Size enforcement at engine | THEORY | Specced in req 005 |
| Live mode data display | THEORY | Code snippet in section 5 |
| JSONL for large lists | THEORY | Auto when list > 100 items (req 011) |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-28 | Session 90: Initial spec. Needed for OB db-validate Layer 2. |
| 1.1 | 2026-03-28 | Session 90: 4-AI review fixes — TaskResult field, size enforcement at engine, live mode display, chaining deferred, feature maturity table. |
| 1.2 | 2026-03-28 | Session 90: Added JSONL support for large lists (reqs 010-011). Mistral suggestion from AI review. |
| 1.3 | 2026-03-28 | Session 90: Fixed 4 AI findings — storage is JSON files not DB, size cap extends REQ-100, security note, JSONL parse instruction in prompt. |


## Renumber Note (Session 104)

**Was Rondo-REQ-106** — that number was already held by Dispatch Trend Alerting (created 2026-03-20, referenced by STD-113/IFS-101/REQ-105). This spec (created 2026-03-28) collided into the number. Renumbered REQ-114; REQ-111's references updated. RONDO-307.

**Then Rondo-REQ-114 again COLLIDED** — Prompt Pipelines (Rondo-REQ-114-prompt-pipelines) already owned that number. Cursor's 2026-06-15 audit (finding 7) flagged the duplicate id. Renumbered to **REQ-119** (above-max, no gap-collision risk); REQ-111/REQ-106 refs and engine.py citations updated. RONDO-433.
