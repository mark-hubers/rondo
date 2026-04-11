# Rondo CLI Examples

Ways to drive Rondo from the shell: **round files** (YAML/Python), **`rondo run`**, **`rondo review`**, and **inline prompts** (`rondo "multi-word prompt"`).

## Prerequisites

- Rondo on your PATH (`uv tool install …` or editable install from this repo — see `docs/GOLDEN-PATH.md`).
- Optional: provider keys (`rondo providers`, `~/.rondo/config.toml`).
- **YAML rounds** need PyYAML in the same environment as the `rondo` binary (the `uv`/`pip` install should pull it; if you see `No module named 'yaml'`, reinstall with project deps).

## Inline prompt mode (`rondo "…"`)

```bash
# Multi-word prompt only — the CLI treats a single token as a possible typo, not a prompt.
rondo "What is Docker and when should I use it?" --model gemini:default

# Provider tiers (recommended shorthand — resolves via ~/.rondo/config.toml):
#   gemini:high | gemini:default | gemini:low
# Or full model ids: gemini:gemini-2.5-flash

# Pipe extra context on stdin
echo "def foo(): pass" | rondo "Review this code for bugs" --model gemini:default

# Structured JSON out (default). Plain text:
rondo "Explain Docker in simple terms" --text

# Named field in JSON (for scripting)
rondo "Find security issues" --field vulnerabilities < app.py
```

**Limitations (so examples don’t lie):**

- **`--dry-run` is not available** for inline prompts — it only exists on `rondo run`, `rondo review`, `rondo overnight`, etc. To preview cost-free, use `rondo run` with a one-task round file, or `rondo review FILE --dry-run`.
- **Single-word “prompts”** are not supported as inline mode; use at least two words or use `rondo run` with a file.

## Round files (YAML / Python)

Paths below are from the **repository root** (`ace2/rondo/`).

```bash
# Preview a YAML round (no API calls)
rondo run examples/rounds/01-simple-review.yaml --dry-run

# Budget-capped batch
rondo run examples/rounds/03-budget-capped.yaml --max-budget 0.50

# Multi-provider task definition
rondo run examples/rounds/02-multi-provider.yaml --dry-run
```

## Multi-provider file review

```bash
rondo review path/to/src/main.py              # default profile (e.g. Gemini + Grok from config)
rondo review src/main.py --providers gemini,mistral --tier high
rondo review src/main.py --dry-run             # preview prompts only
```

## Observability

```bash
rondo providers
rondo learn --json          # scores from history (needs history data)
rondo metrics
rondo history
```

## Scripted prompting (if/else on JSON)

See **`examples/cli/scripted-prompting.sh`** — patterns for retry, confidence escalation, and pipelines using `jq`. Use **`gemini:default`** or **`gemini:gemini-2.5-flash`** in scripts; avoid bare `gemini:flash` (that passes model name `flash` to the API, which is not a valid Gemini model id).

## New runnable CLI examples

| File | Purpose |
|------|---------|
| `01-execution-modes.sh` | Show CLI subprocess path + provider HTTP path |
| `02-background-polling.sh` | MCP-compatible background polling recipe |
| `03-consensus-review.sh` | Two-provider file review workflow |
| `04-showcase-runner.sh` | One-command showcase + API example validation |

Run:

```bash
bash examples/cli/01-execution-modes.sh
bash examples/cli/03-consensus-review.sh src/rondo/dispatch.py
bash examples/cli/04-showcase-runner.sh
```

See also: `../INDEX.md` for the full cross-directory example map.

## Output shape

Default: structured JSON (smart return template). With `--text`, plain text only.

```json
{
  "passed": true,
  "confidence": 0.95,
  "result": "your answer here",
  "issues": [],
  "suggestions": [],
  "metadata": {},
  "_meta": {"quality": 9, "complete": true, "limitations": "..."}
}
```

## If something fails

- `rondo preflight` / `rondo preflight --json`
- `ERR_NESTED_SESSION` inside Claude Code → use **MCP** `rondo_run` / `rondo_review_file`, not the CLI subprocess path.
