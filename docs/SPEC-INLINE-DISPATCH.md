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

## Cursor Review Results (2026-04-01)

1. **MCP tools return data only** — cannot tell host "run this inline." Solution: return a "dispatch plan" that Claude Code interprets and executes.
2. **Agent(model="sonnet") from Opus works** but loses conversation context. Viable tier 2, not inline replacement.
3. **No standard way to detect current model** from MCP ctx. Don't auto-detect — remove "current session model" from COALESCE chain.
4. **Design is sound conceptually** but inline tier requires a CC host-level convention (not standard MCP).
5. **Simplest implementation:** `rondo_run(dry_run=True)` returns `{"kind": "inline_dispatch_plan", ...}` — Claude reads the plan, executes it itself, passes result back.

## Revised Design

```
rondo_run(prompt=...) called from MCP
    │
    ├── model not specified + dry_run?
    │   → Return dispatch PLAN (prompt + done_when + context)
    │   → Claude Code executes it inline (zero subprocess)
    │
    ├── model = local (Ollama)?
    │   → Rondo dispatches via HTTP (already works)
    │
    ├── model = different Claude model?
    │   → Rondo dispatches via subprocess --bare (5s)
    │   → OR Agent(model=X) if available
    │
    └── CLI/Python (no MCP)?
        → Subprocess --bare (fallback)
```

## Updated Requirements

| # | Requirement | Status |
|---|-------------|--------|
| 403 | ~~Current session model in COALESCE~~ REMOVED — not detectable via MCP | Dropped |
| 404 | When dry_run=True and no model specified, return `inline_dispatch_plan` JSON for host to execute | NEW |
| 405 | Agent(model=X) is tier 2 for different Claude model dispatch | Kept |
| 406 | Subprocess --bare is tier 3 fallback | Kept |
| 407 | ai_help MUST document: "omit model= to use current session, avoid subprocess" | DONE |
| 408 | inline_dispatch_plan schema: `{kind, prompt, done_when, context_files}` | NEW |
