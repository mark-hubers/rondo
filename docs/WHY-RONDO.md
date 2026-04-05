# Why Rondo — Honest Comparison

*When to use Rondo, when to use something else, and where Rondo is weak.*

---

## What Rondo Is

A **personal/small-team AI dispatch layer** that:
- Routes tasks to any AI provider (Claude, Gemini, Grok, Mistral, OpenAI, Ollama)
- Returns structured results (status, cost, duration, parsed output)
- Tracks everything (audit trail, metrics, history, notifications)
- Integrates with Claude Code as MCP server (22 tools)
- Runs overnight batches with morning reports

## The Niche

Rondo excels at: **local-first, multi-provider, audited AI orchestration for power users.**

---

## Rondo vs Alternatives

### vs Shell Scripts + curl

| Dimension | Shell scripts | Rondo |
|-----------|--------------|-------|
| Setup | Zero | Install + configure providers |
| Provider switching | Rewrite per API | `--model gemini:flash` |
| Error handling | DIY (usually none) | ErrorPayload + recovery guidance |
| Cost tracking | DIY | Built-in per-task cost tracking |
| Audit trail | DIY | Always-on JSONL |
| Multi-provider review | Manual | One command: `rondo review` |
| Retry/circuit breaker | DIY | Built-in (3-strike breaker) |

**Use shell scripts when:** One-off task, one provider, don't need tracking.
**Use Rondo when:** Repeated tasks, multiple providers, need audit/cost/metrics.

### vs LangChain / LlamaIndex

| Dimension | LangChain | Rondo |
|-----------|-----------|-------|
| Ecosystem | Huge (1000+ integrations) | Small (7 providers, Claude Code MCP) |
| Abstraction | Chains, agents, memory | Tasks, rounds, gates |
| Complexity | High (steep learning curve) | Low (3 concepts: Task, Round, dispatch) |
| Audience | Teams building AI products | Individual devs automating with AI |
| Vendor lock-in | Moderate (abstracts providers) | None (direct API calls) |
| Observability | LangSmith (paid) | Built-in (free, local) |
| Local models | Supported | Ollama native ($0 cost) |

**Use LangChain when:** Building a product, need agents/memory/chains, team of 5+.
**Use Rondo when:** Automating YOUR work, need audit trail, want Claude Code integration.

### vs Direct API Calls (Anthropic SDK / OpenAI SDK)

| Dimension | Direct SDK | Rondo |
|-----------|-----------|-------|
| Control | Full | Full (passes through to SDK) |
| Multi-provider | Manual per SDK | Built-in routing |
| Cost tracking | DIY | Automatic |
| Batch scheduling | DIY | `rondo overnight` + launchd |
| MCP integration | None | 22 tools for Claude Code |
| Error recovery | DIY | ErrorPayload + circuit breaker |

**Use direct SDK when:** Building a product API, need fine-grained control, custom streaming.
**Use Rondo when:** Automating dispatch, multi-provider reviews, need overnight batch.

---

## Rondo's Honest Weaknesses

1. **Single-user tool.** No multi-tenant, no shared server, no team features. Designed for Mark's machine, tested on Mark's machine.

2. **macOS-first.** Notifications, keychain, scheduling use macOS APIs. Core dispatch works on Linux but ops features are macOS-only.

3. **No streaming support.** Rondo waits for the full response. No token-by-token streaming to the user. Fine for batch; not for interactive chat.

4. **Small ecosystem.** 7 providers vs LangChain's 1000+. No vector stores, no memory, no agents. Rondo dispatches tasks — it doesn't build AI applications.

5. **Subprocess-based Claude dispatch.** Uses `claude -p` which spawns a new process per task. Works but slower than direct API for rapid-fire tasks.

6. **Round files are Python.** No sandbox. Executing `build_round()` runs arbitrary code. Fine for trusted users; dangerous if sharing round files from strangers.

7. **No web UI.** Terminal and MCP only. The morning report is markdown, not a dashboard.

---

## When to Choose Rondo

You should use Rondo if:
- You use Claude Code and want multi-model dispatch via MCP
- You need an audit trail of every AI call (compliance, cost tracking)
- You run overnight AI tasks and want morning reports
- You want to compare providers (send the same prompt to Gemini + Grok + Mistral)
- You want $0 local AI (Ollama) as a first pass before cloud

You should NOT use Rondo if:
- You're building a product (use LangChain, Vercel AI SDK, etc.)
- You need real-time streaming
- You need multi-user/team features
- You need 100+ provider integrations
- You're on Windows

---

*Rondo is a power tool, not a platform. It does one thing well: dispatch AI tasks, track results, alert on problems.*
