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
model = "gpt-4.1"
keychain_item = "openai_api_key"
temperature = 0.2

[providers.gemini]
enabled = true
base_url = "https://generativelanguage.googleapis.com/v1beta"
model = "gemini-2.5-flash"
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
model="openai:gpt-4.1"      → ChatCompletionsAdapter(openai config)
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
    providers=["local:qwen2.5:32b", "gemini:flash", "openai:gpt-4.1"],
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

## Cross-References

- `scripts/ai_review.py` — reference implementation (keep until adapters proven)
- `scripts/ai-keys.py` — Keychain management (reuse in adapters)
- REQ-109 — provider adapter spec (already covers this architecture)
- SPEC-INLINE-DISPATCH.md — provider:model routing (already built)
