# Rondo Golden Path — Zero to Dispatch in 5 Minutes

*The shortest path from install to your first useful AI dispatch.*

**Audience:** New user (or Mark after 3 months away)
**Prerequisites:** Python 3.12+, Claude Code with Max plan

---

## Step 1: Install (30 seconds)

```bash
# Install uv (if needed) + Rondo — one command, no venv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install --editable ~/git/mhubers/ace2/rondo --force
rondo --version
```

`uv tool install` creates an isolated environment automatically. No venv activation needed — `rondo` is on your PATH.

## Step 2: Configure Providers (60 seconds)

```bash
rondo init --config
```

This creates `~/.rondo/config.toml` from the template. Edit it:

```toml
[providers.gemini]
enabled = true
# Set GEMINI_API_KEY in env or add api_key here

[providers.grok]
enabled = true
# Set XAI_API_KEY in env
```

Check they're reachable:

```bash
rondo providers
```

Expected: `gemini UP`, `grok UP` (latency shown).

## Step 3: First Dispatch — Dry Run (30 seconds)

```bash
rondo init              # creates round.py in current dir
rondo run round.py --dry-run
```

This shows what WOULD be dispatched without running anything. Check the prompt looks right.

## Step 4: First Real Dispatch (60 seconds)

```bash
rondo run round.py
```

Output:
```
done: All findings reported as a numbered list. ($0.0912)
```

Your first dispatch is done. The result is saved to `reports/rondo-results/`.

## Step 5: Dispatch to a Cloud Provider (60 seconds)

```bash
rondo run round.py --model gemini:gemini-2.5-flash
```

Same task, different provider. Or use the multi-provider review:

```bash
rondo review round.py --dry-run           # see what providers + models
rondo review round.py                     # real dispatch to 2 providers
```

## Step 6: Check What Happened (30 seconds)

```bash
rondo history                             # last 10 dispatches
rondo metrics                             # cost, success rate, health
rondo audit                               # full audit trail
```

## Step 7: MCP Integration (already done)

If you installed Rondo in Claude Code's MCP config, all 22 tools are available:

```
rondo_run, rondo_health, rondo_metrics, rondo_cloud, rondo_multi_review,
rondo_models, rondo_templates, rondo_history, rondo_diff, rondo_explain,
rondo_chain, rondo_benchmark, rondo_review_file, ...
```

Claude uses these automatically when dispatching to other models.

---

## Common Patterns

### Pattern A: Quick Code Review (2 providers)

```bash
rondo review src/main.py
```

Sends to Gemini + Grok by default, merges findings.

### Pattern B: Overnight Batch

```bash
rondo overnight examples/rounds/phases_overnight.py
```

Runs all phases sequentially, generates morning report.

### Pattern C: Inline Prompt via MCP

In Claude Code, just ask:
> "Use rondo to review this file with Gemini"

Claude calls `rondo_run(prompt="...", model="gemini:gemini-2.5-flash")` automatically.

Execution mode note:
- MCP defaults to `execution="" -> inline` (host plan)
- For scripted runs or fresh sessions, use `execution="subprocess"`
- For host Agent plans, use `execution="agent"`

### Pattern D: Local Model ($0 cost)

```bash
rondo run round.py --model llama3.1:8b
```

Routes through Ollama. Zero cost, fast feedback.

---

## When Things Go Wrong

| Symptom | Fix |
|---------|-----|
| `ERR_SUBPROCESS` | Claude binary not found or nested session. Run `rondo preflight` |
| `ERR_NESTED_SESSION` | Can't dispatch from inside Claude Code. Use MCP tools instead |
| `ERR_AUTH` | API key missing. Check `rondo providers` or env vars |
| `ERR_TIMEOUT` | Task took too long. Add `--timeout 120` |
| Morning report says 0 errors | Check if tasks were "skipped" — may be dry-run |

```bash
rondo preflight              # full environment check
rondo preflight --json       # machine-readable
```

---

## File Locations

| What | Where |
|------|-------|
| Config | `~/.rondo/config.toml` |
| Results | `reports/rondo-results/` |
| History | `reports/history/` |
| Audit trail | `reports/audit/` |
| Spool (overnight) | `~/.rondo/spool/` |
| Morning reports | `reports/rondo-morning-YYYYMMDD.md` |

---

*See also: `docs/RONDO-REFERENCE.md` (full system guide), `specs/Rondo-SOP-101-build-run.md` (build procedure)*
