# Rondo

Turn prompts into reliable, scriptable AI workflows.

Rondo is built for real work:
- MCP in Claude Code,
- CLI automation in shells and CI,
- Python API workflows when you need code-level control.

It gives you structured results, repeatable dispatch, routing across models/providers, and workflow patterns that scale beyond copy/paste prompting.

---

## Why Rondo Is Useful

Most AI usage is still manual:
1. ask model,
2. copy output,
3. ask follow-up,
4. lose context, repeat.

Rondo makes that loop scriptable:
- define steps,
- run with consistent output,
- branch on JSON fields,
- compare runs,
- retry failures,
- track cost/health/history.

That is the core value: **prompting as a dependable workflow surface**, not one-off chat luck.

---

## 60-Second Start

```bash
cd rondo
pip install -e .

# Real prompt run (structured JSON by default)
rondo "review this design for top 3 risks"
```

More setup and modes: `docs/GETTING-STARTED.md`.

---

## Three Ways To Use Rondo

### 1) MCP (Claude Code) - primary interactive workflow

Use tool calls like:
- `rondo_run`
- `rondo_multi_review`
- `rondo_review_file`
- `rondo_cloud`
- `rondo_run_status`
- `rondo_retry`
- `rondo_diff`

Start here:
- `examples/mcp/README.md` (13 MCP examples)
- **Full example index:** `examples/INDEX.md` (all 62 examples mapped by mode/provider/use case)

### 2) CLI (scripts, CI, terminal workflows)

```bash
rondo "summarize this architecture"
rondo run examples/rounds/01-simple-review.yaml
rondo review src/rondo/mcp_dispatch.py --providers gemini,grok --tier default
```

Start here:
- `examples/cli/README.md`
- **Full example index:** `examples/INDEX.md`

### 3) Python API (library workflows)

```python
from rondo.mcp_dispatch import rondo_run_file

result_json = rondo_run_file(
    prompt="Return JSON: {\"summary\": \"...\"} for this module",
    model="sonnet",
    execution="subprocess",
    dry_run=False,
)
```

Start here:
- `examples/api/README.md`
- **Full example index:** `examples/INDEX.md`

---

## Execution Modes (Important)

Rondo separates:
- `execution` = **how** work runs,
- `model` = **where** it routes.

| execution | behavior |
|---|---|
| `inline` | returns host plan JSON (`inline_dispatch_plan`) |
| `agent` | returns host agent plan JSON (`agent_dispatch_plan`) |
| `subprocess` | performs dispatch and returns task results |
| `""` (auto) | defaults by caller: MCP -> inline, Python/CLI -> subprocess |

Provider-prefixed models (for example `gemini:...`, `anthropic:...`) route HTTP adapters and bypass execution mode routing.

---

## What You Can Build With It

- Multi-provider consensus review loops.
- Find -> fix -> verify pipelines.
- Background dispatch + polling orchestration.
- Retry/diff-based regression checking.
- Cost-aware routing and model benchmarking.
- Structured prompt scripting with predictable control flow.

See:
- `examples/mcp/`
- `examples/cli/`
- `examples/api/`

---

## Realness Promise

Rondo examples are intended as living usage patterns, not fake snippets.

The examples are used as test fixtures (`tests/integration/test_api_examples.py` and related suites), so breakage is surfaced early.

---

## Documentation Map

- Quick start and core usage: `docs/GETTING-STARTED.md`
- Error/result envelope contract: `docs/ERROR-ENVELOPE-CONTRACT.md`
- Full reference: `docs/RONDO-REFERENCE.md`
- Fast path: `docs/GOLDEN-PATH.md`
- Pattern recipes: `docs/COOKBOOK.md`
- Try-now guide: `TRY.md`
- Specs: `specs/`

---

## If You Want To Feel The Power Fast

Run these in order:
1. `examples/mcp/01-inline-host-plan.md`
2. `examples/mcp/03-subprocess-fresh-session.md`
3. `examples/mcp/05-background-polling.md`
4. `examples/mcp/06-multi-provider-review.md`
5. `examples/mcp/11-retry-failed-dispatch.md`

That sequence shows the real value curve from single prompt to resilient workflow.
