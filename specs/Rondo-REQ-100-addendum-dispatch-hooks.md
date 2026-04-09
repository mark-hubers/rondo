# Rondo-REQ-100 Addendum: Dispatch Hooks — Pre/Post Processing Pipeline

**Parent:** Rondo-REQ-100-core.md
**Created:** 2026-04-09
**Origin:** Session 100 — 5 independent AI reviews (Gemini, Grok, Mistral, Qwen, Cursor) unanimously recommended dispatch hooks as #1 priority feature
**Status:** DRAFT

---

## Problem Statement

Rondo has pre/post GATES (Python functions that block/allow execution) but no
mechanism for users to inject processing logic AROUND each dispatch without
blocking. Power users need to:

1. Sanitize/transform prompts before dispatch (PII redaction, template expansion)
2. Post-process results after dispatch (format conversion, notification, logging)
3. Integrate Rondo into larger pipelines (CI/CD, data processing, monitoring)
4. Apply org-specific policies without modifying Rondo source code

**Gates vs Hooks:**
- Gates: block/allow a round. Binary pass/fail. Run once per round.
- Hooks: transform data around each TASK dispatch. Run per-task. Non-blocking.

**Evidence:** All 5 AI reviewers identified this as highest-leverage missing
feature. Cursor: "Small surface, huge leverage. Fits Unix story."

---

## Requirements

### Pre-Dispatch Hooks

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 100 | Round files MAY define `pre_dispatch` as a list of callables `(prompt: str, task: Task, config: RondoConfig) -> str`. Each callable receives the prompt and returns a (possibly modified) prompt. | MUST | Unit test |
| 101 | Pre-dispatch hooks run in order. Output of hook N is input to hook N+1. Final output is the dispatched prompt. | MUST | Chain test |
| 102 | If a pre-dispatch hook raises an exception, the task MUST be marked `error` with `ERR_HOOK_FAILED` and the hook name in `error_message`. The dispatch MUST NOT proceed. | MUST | Error test |
| 103 | Pre-dispatch hooks MUST be logged in the audit trail (STD-113) as a `HOOK_PRE` event with hook name and duration. | MUST | Audit test |
| 104 | Pre-dispatch hooks MAY be Python callables OR shell commands (string starting with `!`). Shell hooks receive prompt on stdin, return modified prompt on stdout. Exit code != 0 = error. | SHOULD | Shell hook test |
| 105 | Pre-dispatch hooks MUST NOT have access to API keys or provider credentials. They receive the prompt and task metadata only. | MUST | Security test |

### Post-Dispatch Hooks

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 110 | Round files MAY define `post_dispatch` as a list of callables `(result: TaskResult, usage: DispatchUsage) -> TaskResult`. Each callable receives the result and returns a (possibly modified) result. | MUST | Unit test |
| 111 | Post-dispatch hooks run in order after dispatch completes but BEFORE finalize_dispatch (audit OUTCOME, sanitize, spool). | MUST | Order test |
| 112 | If a post-dispatch hook raises, the ORIGINAL result (pre-hook) MUST be preserved and finalized. The hook failure is logged as WARNING. | MUST | Resilience test |
| 113 | Post-dispatch hooks MUST be logged in the audit trail as `HOOK_POST` events. | MUST | Audit test |
| 114 | Post-dispatch hooks MUST NOT modify `raw_output` to inject content that bypasses sanitization (STD-114). Sanitization runs AFTER hooks. | MUST | Security test |

### Config-Level Hooks (Global)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 120 | `~/.rondo/config.toml` MAY define `[hooks.pre_dispatch]` and `[hooks.post_dispatch]` as lists of shell commands that apply to ALL dispatches. | SHOULD | Config test |
| 121 | Round-file hooks run AFTER config-level hooks (COALESCE: config-global first, then round-specific). | MUST | Order test |
| 122 | `rondo hooks list` CLI command MUST show all active hooks (config + current round file). | SHOULD | CLI test |

---

## Data Model Changes

```python
@dataclass
class Task:
    # ... existing fields ...
    pre_dispatch: list[Callable | str] = field(default_factory=list)
    post_dispatch: list[Callable | str] = field(default_factory=list)
```

---

## Example Usage

```python
from rondo.engine import Round, Task

def redact_pii(prompt: str, task, config) -> str:
    """Remove email addresses from prompts before dispatch."""
    import re
    return re.sub(r'\b[\w.]+@[\w.]+\.\w+\b', '[REDACTED]', prompt)

def log_cost(result, usage):
    """Log cost after each dispatch."""
    if usage.cost_usd > 0.10:
        print(f"  HIGH COST: ${usage.cost_usd:.4f} for {result.task_name}")
    return result

def build_round():
    return Round(
        name="reviewed-dispatch",
        tasks=[
            Task(
                name="analyze",
                instruction="Review this code for security issues",
                pre_dispatch=[redact_pii],
                post_dispatch=[log_cost],
            ),
        ],
    )
```

---

## Architecture

```
  Round file defines hooks
         |
         v
  [pre_dispatch hooks] → prompt in → modified prompt out
         |
         v
  [dispatch to provider]
         |
         v
  [post_dispatch hooks] → result in → modified result out
         |
         v
  [finalize_dispatch] → audit, sanitize, spool (existing pipeline)
```

Hooks are lightweight — they don't change the dispatch architecture. They add
two extension points in the existing `_dispatch_with_safety_net` path.

---

## Risk

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Hook modifies prompt in a way that breaks provider | Medium | Medium | Audit trail captures both original and hooked prompt |
| Hook raises exception and blocks dispatch | Medium | Low | Req 102: error status, no dispatch. Req 112: post-hooks preserve original |
| Shell hook injection via untrusted round file | Low | High | Round files are user-authored Python — same trust level as the code itself |

---

## Version History

| Ver | Date | Changes |
|-----|------|---------|
| 0.1 | 2026-04-09 | Initial draft. Session 100: 5-AI consensus feature. |
