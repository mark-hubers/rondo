# Rondo MCP Examples

These are **tool calls** from Claude Code (or any MCP client), not shell commands. They cover the bulk of day-to-day Rondo usage: single dispatch, multi-provider review, file review, health, cost, and cloud tiered dispatch.

**Truthful defaults:** `rondo_run` in the MCP server passes `dry_run` through — check your installed `mcp_server.py`: many builds default `dry_run=False` on the tool so calls are **live**. Use `dry_run=True` for previews when you are unsure.

Use **full provider strings** or **tiers** in `providers` JSON — examples below are copy-paste correct:

- Tiers: `gemini:high`, `gemini:default`, `gemini:low` (resolve from `~/.rondo/config.toml`)
- Full ids: `gemini:gemini-2.5-flash`, `grok:grok-3`, `mistral:mistral-large-latest`

Avoid shorthand like `gemini:flash` as a model name — it becomes the literal model `flash`, which is not a valid Gemini API id.

## 1. Single dispatch (`rondo_run`)

```text
rondo_run(
    prompt="Summarize the security implications of this design in 5 bullets.",
    model="gemini:default",
    dry_run=False,
)
```

Returns JSON: task results, cost, duration — or an **inline/agent dispatch plan** for Claude models; the host is supposed to execute the plan (see `rondo-dispatch` skill).

## 2. Multi-provider review (`rondo_multi_review`)

```text
rondo_multi_review(
    prompt="Review this architecture for scalability issues.\n\n```text\n<paste design>\n```",
    providers='["gemini:gemini-2.5-flash", "grok:grok-3"]',
    dry_run=False,
)
```

## 3. File review (`rondo_review_file`)

```text
rondo_review_file(path="/absolute/path/to/file.py", dry_run=False)
```

## 4. Health (`rondo_health`)

```text
rondo_health()
```

## 5. Metrics (`rondo_metrics`)

```text
rondo_metrics()
```

## 6. Second opinion — local (`rondo_explain`)

Requires Ollama (or configured local model). Near-zero dollar cost.

```text
rondo_explain(output="The previous model claimed X …", question="Is this correct?")
```

## 7. Cloud dispatch with tier (`rondo_cloud`)

```text
rondo_cloud(prompt="Deep analysis of coupling in this module.", tier="high", dry_run=False)
```

## 8. Other high-use tools (add to your mental model)

| Tool | When |
|------|------|
| `rondo_cost` | Spend over last N days |
| `rondo_history` | Recent dispatches |
| `rondo_dispatch_info` | Version, capabilities, what’s enabled |
| `rondo_models` | What models/providers are configured |
| `rondo_chain` | Pipeline: step N output → step N+1 |
| `rondo_run_status` | Poll a **background** `rondo_run` |

## Output

All tools return **JSON strings**. Multi-review results include per-provider entries with status, output, cost, and duration.
