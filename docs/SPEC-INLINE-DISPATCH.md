# Rondo Inline Dispatch — Spec Draft for AI Review

**Finding:** #199 | **Priority:** HIGH | **Status:** DRAFT — needs AI review before build

---

## Problem

When Rondo runs inside Claude Code via MCP and dispatches to a Claude model, it spawns a NEW `claude -p` subprocess. This:
- Takes 5-70 seconds for startup overhead
- Loses the current conversation context
- Creates a separate process when we're ALREADY inside Claude Code

**90% of Rondo usage is scripting the CURRENT AI session** — not spawning new ones.

---

## Proposed Design: 3-Tier Dispatch

```
rondo_run(prompt=..., model=...) called from MCP
    │
    ├── Is model == current session model?
    │   YES → INLINE: return structured result (current session does the work)
    │
    ├── Is model a different Claude model?
    │   YES → AGENT: use Agent(model=X) inside current session
    │
    ├── Is model a local model (Ollama)?
    │   YES → HTTP: direct call to Ollama API (already works)
    │
    └── Not in MCP (CLI/Python)?
        → SUBPROCESS: claude -p --bare (fallback)
```

---

## New Requirements for REQ-100

| # | Requirement |
|---|-------------|
| 403 | Model COALESCE chain: CLI flag → task.model → **current session model** → config.default_model → "sonnet" |
| 404 | When running inside MCP with same model as current session, dispatch SHOULD execute inline (no subprocess) |
| 405 | When running inside MCP with different Claude model, dispatch SHOULD use Agent(model=X) |
| 406 | When not running inside MCP (CLI/Python), dispatch uses subprocess with --bare |
| 407 | Rondo MUST detect MCP context via ctx.session parameter |
| 408 | Inline dispatch returns structured TaskResult same as subprocess dispatch |

---

## Context Handling

| Dispatch tier | Conversation context? | Repo/file access? | Tools? |
|--------------|----------------------|-------------------|--------|
| Inline (same model) | YES — full | YES | YES |
| Agent (different model) | NO — repo only | YES | YES (but no Caliber) |
| HTTP/Ollama | NO — prompt only | NO | NO |
| Subprocess/bare | NO — fresh session | YES (via --bare) | Minimal |

For Agent dispatch: Rondo includes relevant context via `context_files` parameter.

---

## Questions for AI Review

1. Can an MCP tool signal "the current session should do this work" — or can it only return data?
2. Is Agent(model="sonnet") from an Opus session reliable? Any known issues?
3. Is there a way to detect the current session's model from MCP ctx?
4. Should inline dispatch be opt-in (flag) or automatic (detect and decide)?
5. What happens if inline dispatch fails — should it fall back to subprocess?
