# Rondo v0.7 Roadmap — Multi-Provider Adapters

**Source:** Cursor design review + ai_review.py analysis (Session 94)
**Goal:** Replace standalone ai_review.py with Rondo provider adapters
**Status:** Specced, ready to sprint

---

## What Exists Today

`scripts/ai_review.py` (1,260 lines) — 5 providers:
- OpenAI (Chat Completions API)
- Gemini (generateContent API)
- Mistral (Chat Completions API — same as OpenAI)
- Grok (Chat Completions API — same as OpenAI)
- Claude (Messages API)

Plus: Keychain key management, result normalization, cross-provider comparison.

---

## Architecture (Cursor-approved)

```
rondo/src/rondo/
├── providers.py              # Interface + routing (stays small)
├── adapters/
│   ├── __init__.py
│   ├── chat_completions.py   # OpenAI + Grok + Mistral (same API)
│   ├── gemini.py             # Google's unique API
│   ├── anthropic_api.py      # Claude via API (not subprocess)
│   └── ollama.py             # Move from providers.py
```

### 3 Adapter Classes (not 5)

| Adapter | Providers | API Pattern |
|---------|-----------|-------------|
| `ChatCompletionsAdapter` | OpenAI, Grok, Mistral | Same Chat Completions format |
| `GeminiAdapter` | Google Gemini | Unique generateContent |
| `AnthropicAPIAdapter` | Claude via API | Unique Messages format |
| `OllamaAdapter` | Local models | HTTP to localhost (existing) |

### Config (`~/.rondo/config.toml`)

```toml
[providers.openai]
enabled = true
base_url = "https://api.openai.com/v1"
model = "gpt-5.5"
keychain_item = "openai_api_key"
temperature = 0.2

[providers.gemini]
enabled = true
base_url = "https://generativelanguage.googleapis.com/v1beta"
model = "gemini-flash-latest"
keychain_item = "gemini_api_key"

[providers.grok]
enabled = true
base_url = "https://api.x.ai/v1"
model = "grok-beta"
keychain_item = "grok_api_key"

[providers.mistral]
enabled = true
base_url = "https://api.mistral.ai/v1"
model = "mistral-large-latest"
keychain_item = "mistral_api_key"

[providers.anthropic]
enabled = true
base_url = "https://api.anthropic.com/v1"
model = "claude-sonnet-4-6"
keychain_item = "anthropic_api_key"
```

### Routing

```
model="openai:gpt-5.5"      → ChatCompletionsAdapter(openai config)
model="gemini:flash"         → GeminiAdapter(gemini config)
model="grok:beta"            → ChatCompletionsAdapter(grok config)
model="mistral:large"        → ChatCompletionsAdapter(mistral config)
model="anthropic:sonnet"     → AnthropicAPIAdapter(anthropic config)
model="local:llama3.1:8b"    → OllamaAdapter (existing)
model=""                     → inline plan (current session)
model="sonnet"               → Claude subprocess with --bare
```

---

## Migration Plan (Cursor-recommended: wrap first)

| Step | What | Sprint |
|------|------|--------|
| 1 | Freeze ai_review.py behavior with tests | RONDO-114 |
| 2 | Extract per-provider call logic into pure functions | RONDO-115 |
| 3 | Create `adapters/` directory, move OllamaAdapter | RONDO-116 |
| 4 | Build ChatCompletionsAdapter (wraps ai_review.py functions) | RONDO-117 |
| 5 | Build GeminiAdapter | RONDO-118 |
| 6 | Build AnthropicAPIAdapter | RONDO-119 |
| 7 | Wire into providers.py routing | RONDO-120 |
| 8 | Build rondo_multi_review MCP tool (cross-provider comparison) | RONDO-121 |
| 9 | ai_review.py becomes thin client of adapters | RONDO-122 |

---

## New MCP Tool: `rondo_multi_review`

```
rondo_multi_review(
    prompt="Review this code for bugs",
    providers=["local:qwen2.5:32b", "gemini:flash", "openai:gpt-5.5"],
    files=["src/main.py"],
)
→ Returns: per-provider findings, merged findings, cost/latency stats
```

Replaces `ai-review --all-providers --compare`.

---

## Gotchas (Cursor warned)

1. Error handling: adapters must return TaskResult, not raw exceptions
2. Key loading: move to shared `rondo/auth.py` (not script-specific)
3. Timeouts: respect Rondo's task_timeout_sec + provider-specific limits
4. Concurrency: adapters must be stateless (no global mutable per-call)
5. Result schema: map ai_review.py normalized format → TaskResult.parsed_result

---

## v0.7 Three-Engine Dispatch (RONDO-129 — Session 99)

**Problem discovered:** Audit logs showed 100% failure rate (59/59) on in-session
subprocess dispatch (`claude -p`). Subprocess can't authenticate inside an existing
Claude Code session ("Not logged in"). Cloud HTTP adapters: 95% success (39/41).

**Solution:** `resolve_dispatch_engine()` in `mcp_dispatch.py` — four engines:

| Engine | When | How |
|--------|------|-----|
| **INLINE** | model="" or omitted | Return plan, host session executes with full context |
| **AGENT** | Claude model in-session (sonnet/opus/haiku) | Return plan, host spawns Agent(model=X) |
| **HTTP** | Provider prefix (gemini:/grok:/local:/openai:/mistral:/anthropic:) | Adapter dispatch via API |
| **SUBPROCESS** | background=True, :new suffix, or CLI (not in-session) | `claude -p --bare` |

**Decision tree:**
```
background=True?  → SUBPROCESS
provider prefix?  → HTTP ADAPTER
model empty?      → INLINE
:new suffix?      → SUBPROCESS
Claude model + in-session?  → AGENT
Claude model + CLI?         → SUBPROCESS
else → ERROR
```

**Tests:** 23 routing tests, zero mocking. 18 in-session + 7 out-of-session verified real.

**Findings closed:** #199 (HIGH), #198 (MEDIUM)

---

## Cross-References

- `scripts/ai_review.py` — legacy implementation (adapters replace it)
- `scripts/ai-keys.py` — Keychain management (reuse in adapters)
- REQ-109 — provider adapter spec (already covers this architecture)
- SPEC-INLINE-DISPATCH.md — provider:model routing (already built)
