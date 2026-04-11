# Verifying Rondo Examples (for humans and for Claude)

Use this when you change docs, CLI, or MCP tools. Goal: **examples match the shipped binary** and **don’t promise flags or paths that don’t exist**.

## What “real usage” should cover (>75%)

| Area | Examples / docs |
|------|------------------|
| Single-task dispatch | MCP `rondo_run`, CLI `rondo run` + round files, inline `rondo "two words …"` |
| Multi-provider review | `rondo review`, MCP `rondo_multi_review`, `rondo_review_file` |
| Observability | `rondo_health`, `rondo_metrics`, `rondo_cost`, `rondo_history`, `rondo_dispatch_info` |
| Cloud tiered dispatch | MCP `rondo_cloud` |
| Pipelines | MCP `rondo_chain`, background `rondo_run` + `rondo_run_status` |
| Local / cheap | `rondo_explain`, Ollama models via `local:…` or legacy names |
| Ops / recovery | `rondo preflight`, `rondo providers`, Cookbook “RED health” recipe |

If all of those are documented with **working** commands, you are covering the majority of practical use.

## Automated checks (no API keys required)

From the **rondo repo root**:

```bash
rondo --version
rondo preflight
rondo run examples/rounds/round_hello.py --dry-run    # may exit 0 or 1 when tasks are skipped — check output text
```

Optional: `bash examples/verify-examples.sh` from the repo root (same checks + path existence).

Run the full test suite before a release:

```bash
.venv/bin/python -m pytest tests/ -q
```

## Inline CLI quirks (easy to get wrong)

1. **Multi-word only** — `rondo "fix this"` works; a single token is not treated as an inline prompt.
2. **No `--dry-run`** on inline mode — use `rondo run FILE --dry-run` or MCP `dry_run=True`.

## Prompt you can give Claude to test MCP

Paste this in a session where the **Rondo MCP server is enabled**:

> Run these in order and paste concise results (no secrets):
> 1. `rondo_dispatch_info()` — confirm version and tool list.
> 2. `rondo_health()` — note GREEN/YELLOW/RED.
> 3. `rondo_models()` — list configured providers/models.
> 4. `rondo_run(prompt="Reply with the single word: pong", model="gemini:default", dry_run=True)` — must not charge; confirm JSON or plan.
> 5. If step 4 returns an inline dispatch plan, execute the embedded prompt yourself and return structured JSON per the rondo-dispatch skill.
> 6. `rondo_multi_review(prompt="Say hello in one sentence.", providers='[\"gemini:gemini-2.5-flash\"]', dry_run=True)` — preview only.

Adjust provider strings to match `~/.rondo/config.toml`. If a step fails, capture the error string and fix config or docs — don’t “assume” success.

## Prompt you can give Claude to test CLI

> From `ace2/rondo`, run:
> `rondo run examples/rounds/round_hello.py --dry-run`
> and
> `rondo "smoke test inline prompt" --dry-run` (expect failure explaining `--dry-run` is invalid for inline — that proves our docs are honest).
> Then run:
> `rondo run examples/rounds/round_hello.py --dry-run` again and confirm exit 0.

(The second command **should** error: it documents the limitation.)
