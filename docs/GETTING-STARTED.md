# Getting started with Rondo

Rondo runs **scripted AI work**: you describe tasks (in the CLI, YAML, JSON, or Python), and it dispatches to the right model, enforces budgets, and returns **structured JSON** you can pipe to other tools.

This guide goes from a 30-second first run to the full CLI. For architecture and contracts, see `specs/VISION-rondo-v1.md` and `specs/Rondo-REQ-111-smart-dispatch.md`.
For a guided first-run flow, see `docs/GETTING-STARTED-WOW.md`.
For the five-command first hour (each verified live), see `docs/GOLDEN-FIVE.md`.

Full cross-directory example map: `examples/INDEX.md` (90 examples by dispatch mode, providers, and use case).
Dispatch envelope contract (status + error_code semantics): `docs/ERROR-ENVELOPE-CONTRACT.md`.

---

## 1. Quickstart (about 30 seconds)

### Install

From the repo (editable install):

```bash
cd rondo && pip install -e .
```

Requires **Python 3.12+**. Configure providers and keys in `~/.rondo/config.toml` (template: `rondo init --config`, or copy `examples/config.toml`).

### One command, JSON back

Use a **multi-word** prompt so the CLI treats it as inline dispatch (not a mistyped subcommand):

```bash
rondo "review this code for obvious bugs"
```

Stdout is **validated JSON** by default (smart return + `validate_return_json`). Default model comes from config (`[routing]` / provider defaults). Override:

```bash
rondo "summarize this diff" --model gemini:gemini-flash-latest
```

Plain text (no smart-return JSON instructions):

```bash
rondo "explain this error" --text
```

That’s the minimal loop: **install → prompt → structured output on stdout.**

---

## 2. Round files (about 5 minutes)

Rondo accepts **`.yaml` / `.yml`**, **`.json`**, or **`.py`** round files. Unknown fields are rejected at load time (see `round_loader.py`).

### YAML — two-task review

Save as `review.yaml`:

```yaml
name: two-step-review
tasks:
  - name: scan
    instruction: "Scan this codebase for risky patterns and summarize findings."
    done_when: "Short bullet list of issues, no prose."

  - name: deep-dive
    instruction: "For the top issue from the scan, propose concrete fixes."
    done_when: "Patches or step-by-step edits only."
```

Run:

```bash
rondo run review.yaml
```

Add `--dry-run` to print prompts without calling the model.

### JSON — same round

Save as `review.json`:

```json
{
  "name": "two-step-review",
  "tasks": [
    {
      "name": "scan",
      "instruction": "Scan this codebase for risky patterns and summarize findings.",
      "done_when": "Short bullet list of issues, no prose."
    },
    {
      "name": "deep-dive",
      "instruction": "For the top issue from the scan, propose concrete fixes.",
      "done_when": "Patches or step-by-step edits only."
    }
  ]
}
```

```bash
rondo run review.json
```

### Python — hooks (power user)

Hooks are **Python round files** only: `pre_dispatch` / `post_dispatch` lists on `Task`.

See `examples/04-with-hooks.py`: email redaction before dispatch (`pre_dispatch`) and a cost warning after (`post_dispatch`).

```bash
rondo run examples/04-with-hooks.py
```

More examples in `examples/`: `01-simple-review.yaml`, `02-multi-provider.yaml`, `03-budget-capped.yaml`, `05-overnight-batch.yaml`.

---

## 3. Smart returns (what makes Rondo different)

For dispatch paths that build the full task prompt (`dispatch_prompt.build_prompt`), Rondo can append a **return-format block** so models emit consistent JSON (`smart_return.py`). Inline CLI output is passed through `validate_return_json()` for pretty-printed, scored objects.

### Default JSON shape

The default instruction asks for (among others):

| Field | Meaning |
|--------|---------|
| `passed` | Whether the task succeeded or found no blocking issues |
| `confidence` | 0.0–1.0 |
| `result` | Main answer |
| `issues` / `suggestions` | Lists of strings |
| `metadata` | Free-form context |
| `_meta` | `quality`, `complete`, `limitations` |

If the model returns non-JSON or messy text, Rondo tries brace-balanced extraction; worst case you get `_parse_error` and raw text in `result` (`validate_return_json`).

### CLI flags (inline and global)

| Flag | Effect |
|------|--------|
| `--field <name>` | Ask the model to put the main answer in that field **and** keep the standard fields (COALESCE: defaults + named field). |
| `--return-schema '<json>'` | Full custom schema string — **wins over** `--field` and defaults. |
| `--text` | No JSON return prompt; raw model text on stdout. |

Precedence: **`--return-schema` → `--field` + defaults → defaults only** (REQ-111).

### Per-provider templates

Built-in tuned templates apply when the provider key matches **`gemini`**, **`grok`**, or **`local`** (prefix before `:` in `model`). Others use the shared default block.

Optional overrides in `~/.rondo/config.toml`: `[return_prompts.<provider>]` (see REQ-111) — formatting only, not your user content.

---

## 4. Dispatch hooks (power user)

Implemented in `hooks.py` and wired from `runner._dispatch_with_safety_net`.

| Phase | What | Forms |
|-------|------|--------|
| **Pre-dispatch** | Transform the prompt before the model sees it | Python `def(prompt, task, config) -> str`, **or** shell: string starting with `!` (stdin = prompt, stdout = new prompt; exit ≠ 0 fails the task). |
| **Post-dispatch** | Transform `TaskResult` after the model returns | **Python callables only:** `(result, usage) -> TaskResult`. On exception, the **original** result is kept and a warning is logged. |

**Example themes** (from `examples/04-with-hooks.py`):

- **PII:** regex strip emails in a pre-hook.
- **Cost:** read `usage.cost_usd` in a post-hook and warn over a threshold.

Shell pre-hook sketch:

```python
Task(
    name="t",
    instruction="…",
    done_when="…",
    pre_dispatch=["!sed 's/SECRET/[REDACTED]/g'"],
)
```

---

## 5. Multi-provider dispatch

### Same work, different models

`examples/02-multi-provider.yaml` runs the **same instruction** with three tasks and different `model:` lines (e.g. `gemini:gemini-flash-latest`, `grok:grok-4.3`, `local:…`). Adjust models to what you have enabled.

### Budget caps

`examples/03-budget-capped.yaml` is a multi-task batch. Cap spend:

```bash
rondo run examples/03-budget-capped.yaml --max-budget 0.50
```

### Circuit breaker

On repeated failures (notably the Claude subprocess path), Rondo’s circuit breaker can **short-circuit** dispatch to avoid hammering a broken path (`dispatch.py` / `retry` module). You don’t configure it per round file; it’s automatic guardrail behavior.

### Provider scoring (`rondo learn`)

`scoring.py` reads recent **audit JSONL** under `~/.rondo/audit`, aggregates per model, and writes **`~/.rondo/learned/provider_scores.json`** (when enough samples exist).

```bash
rondo learn
rondo providers --scores
```

Scores blend success, cost, and latency; JSON-quality fields are included when present in audit records. Use this to **compare** providers after you’ve run real work — not before first use.

---

## 6. CLI reference

Rondo exposes **16 subcommands** plus optional **inline prompt** mode (first argument is a multi-word string, not a known command).

### Inline prompt (no subcommand)

| Example | Notes |
|---------|--------|
| `rondo "your prompt here" --model gemini:gemini-flash-latest --field bugs` | JSON to stdout by default; `--text` for raw. |
| `git diff \| rondo "will this break tests?"` | Stdin appended as context (up to 1 MB). |

### Subcommands

| Command | Purpose | Example |
|---------|---------|---------|
| `run` | Run a `.py` / `.yaml` / `.json` round | `rondo run myround.yaml --dry-run` |
| `live` | Interactive / human-in-the-loop rounds | `rondo live round.py --from 1` |
| `overnight` | Long-running batch (`build_phases`) | `rondo overnight phases.py --mode standard` |
| `report` | Morning report from results dir | `rondo report ./reports` |
| `preflight` | Environment check without dispatch | `rondo preflight --json` |
| `history` | Dispatch history | `rondo history --expensive` |
| `audit` | Audit trail query / maintenance | `rondo audit <id> --json` |
| `flaky` | Flaky task templates | `rondo flaky --threshold 0.2` |
| `spool` | Result spool mailbox | `rondo spool list` |
| `metrics` | Aggregated metrics | `rondo metrics --json` |
| `mcp` | Start MCP stdio server | `rondo mcp` |
| `init` | Scaffold round or config | `rondo init --name myround` |
| `schedule` | `launchd` plist helper | `rondo schedule round.py --interval daily` |
| `learn` | Compute provider scores | `rondo learn --json` |
| `providers` | Provider status / scores | `rondo providers --scores` |
| `review` | Multi-provider file review | `rondo review src/foo.py --tier default` |

### Common flags (`run`, `live`, `overnight`)

| Flag | Meaning |
|------|---------|
| `--dry-run` | Show prompts; no model call |
| `--model` | Model override (e.g. `sonnet`, `gemini:gemini-flash-latest`) |
| `--auth max\|api` | Subscription vs API-key billing for Claude |
| `--max-budget` | Max cost (USD) for a run |
| `--project DIR` | Working directory for tasks |
| `--workers N` | Parallelism where applicable |
| `--bare` | Faster Claude dispatch (`--bare`); skips some client hooks — use only when appropriate |
| `--config PATH` | Alternate `rondo.toml` |

### Top-level flags (before subcommand)

| Flag | Meaning |
|------|---------|
| `--field` | Named JSON field for smart return |
| `--return-schema` | Full JSON schema string |
| `--text` | Plain text output |
| `--model` | Default model for inline mode |
| `--ai-help` | Machine-readable capability JSON |
| `--version` | Print version |

---

## Experiment Matrix — compare models like a scientist (REQ-113)

One command runs a model × effort × context × replicates grid: budgeted,
resumable, blind-scorable. Rondo's signature capability.

```yaml
# exp.yaml
name: my-comparison
prompt_file: prompts/task.md          # may contain {{essay}} placeholders
inputs:
  essay: drafts/essay-v7.md           # substituted into {{essay}}
models: [anthropic:claude-opus-4-8, openai:gpt-5.5]
efforts: [low, max]                   # thinking models sweep; others collapse
replicates: 2
blind: true                           # results coded until you reveal
baseline: plans/split-plan.md         # length/structure deltas in report
budget_usd: 2.50                      # HARD ceiling: estimate-abort + mid-run stop
```

```bash
rondo matrix run exp.yaml --dry-run   # grid + cost estimate, zero spend
rondo matrix run exp.yaml             # execute (resumable — re-run skips done cells)
rondo matrix report my-comparison     # replicate mean±stdev, noisy flags
rondo matrix reveal my-comparison     # de-anonymize (seal SHA-256 verified)
```

### Fleet operations (June 2026)

```bash
rondo doctor                # is this install healthy + exactly what to fix (free)
rondo nightly               # watchdog sweep: drift + retryq + 7d reliability (free)
rondo models --tiers        # derived auto-tiers from live catalogs (free)
rondo models --verify       # canary every configured model (~cents)
rondo models --docs-drift   # stale model IDs in examples/docs (free)
rondo retryq list           # self-classifying retry queue
```

Honesty rules baked in: self-ratings are labeled *uncalibrated* and never
ranked on; an unresolved `{{placeholder}}` aborts instead of dispatching a
template; one cell's failure never kills the run.

## Keeping the model fleet healthy

```bash
rondo providers --refresh --drift   # catch retired models BEFORE dispatches 404
rondo providers --scores            # 7-day learned per-model performance
rondo metrics                       # 7d/30d success scoreboard vs 95% target
```

---

## Next steps

- Copy and edit files under `examples/`.
- Tune `~/.rondo/config.toml` for providers and routing.
- Read `docs/WHY-RONDO.md` or `docs/GOLDEN-PATH.md` for deeper workflows.
- For Claude Code workflows, use `examples/mcp/` (13 MCP examples).
- For shell automation patterns, use `examples/cli/` (scripted real-world recipes).
- For the canonical map of all examples, use `examples/INDEX.md`.
- For status/error troubleshooting by `error_code`, use `docs/ERROR-ENVELOPE-CONTRACT.md`.
