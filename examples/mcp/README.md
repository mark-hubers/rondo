# rondo-meta: mode=inline,subprocess,agent,http provider=anthropic,gemini,grok,mistral,openai,ollama category=config value="MCP playbook overview with copy/paste entry points"

# Rondo MCP Examples — Real, Copy/Paste Workflows

These examples are for Claude Code (or any MCP client) calling Rondo tools directly.
They are designed as:
- real usage patterns,
- prompt-scripting templates,
- living references for daily work.

## Ground Rules

-PASS- These are MCP tool calls, not shell commands.
-PASS- Most examples are live by default (`dry_run=False` where supported).
-WARNING- Provider-prefixed model strings should be full IDs (for example `gemini:gemini-flash-latest`), not shorthand like `gemini:flash`.

## 13 MCP Examples

| File | What it teaches |
|------|------------------|
| `01-inline-host-plan.md` | Default MCP inline behavior and host-plan execution |
| `02-agent-host-plan.md` | `execution="agent"` with explicit model |
| `03-subprocess-fresh-session.md` | `execution="subprocess"` for isolated runs |
| `04-provider-http-bypass.md` | Provider prefixes bypass execution mode |
| `05-background-polling.md` | Background dispatch and status polling tiers |
| `06-multi-provider-review.md` | Consensus review with multiple providers |
| `07-review-file.md` | Real file review workflow via `rondo_review_file` |
| `08-cloud-profile-tier.md` | Profile/tier cloud dispatch patterns |
| `09-chain-pipeline.md` | Multi-step chain where output feeds next step |
| `10-benchmark-model-selection.md` | Benchmark models before choosing defaults |
| `11-retry-failed-dispatch.md` | Recover failed work with `rondo_retry` |
| `12-diff-two-runs.md` | Compare output drift across runs with `rondo_diff` |
| `13-observability-suite.md` | Health, metrics, cost, history, audit workflow |

## Why these matter

These examples are meant to answer the big questions quickly:
1. How do I call Rondo from MCP in real work?
2. How do I script prompts and decisions with structured JSON?
3. How do I prove behavior (plans vs subprocess vs HTTP) and monitor reliability?

Use this folder as your MCP playbook.

See also: `../INDEX.md` for the full cross-directory example map.
Envelope semantics and `error_code` troubleshooting: `../../docs/ERROR-ENVELOPE-CONTRACT.md`.
