# Rondo

Turn prompts into reliable, scriptable AI workflows.

## What Rondo Is (and Is Not)

Rondo is a scripted AI prompting engine for operational work. You define prompts, routing, retry behavior, and output contracts so the same workflow can run from MCP, CLI, or Python API without re-prompting by hand.

Rondo is not a chatbot framework and not a general app orchestration SDK. It does not try to replace LangChain/DSPy graph tooling or full agent platforms. It focuses on dependable dispatch, repeatable outputs, and workflow-safe envelopes for real operator loops.

Think of Rondo as "Terraform for prompts": declarative, repeatable runs with explicit execution modes, clear result contracts, and auditable behavior.

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
Fastest onboarding path: `docs/GETTING-STARTED-WOW.md`.

## Signature Capabilities (June 2026)

```bash
rondo matrix run exp.yaml --dry-run     # model × effort × context experiment grids:
                                        # budgeted, blind-scorable, resumable (REQ-113)
rondo providers --refresh --drift       # catch retired models BEFORE dispatches 404
rondo providers --scores                # 7-day learned model performance (auto-tune)
rondo retryq list                       # self-classifying retry queue (dead-letter, aging)
rondo metrics                           # 7d/30d reliability scoreboard vs 95% target
```

Thinking models (Opus 4.8-era) are handled automatically: adaptive thinking,
effort control, output headroom, and **streamed dispatch** with an event
watchdog — a model may think for many minutes safely. Every failure carries
the provider's own explanation into the audit trail.

**The documentation IS the examples**: 85 real, runnable files under
`examples/` (start at `examples/INDEX.md`); smoke-checked by
`examples/verify-examples.sh`, with key paths exercised in the test suite.

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
- **Full example index:** `examples/INDEX.md` (all 85 examples mapped by mode/provider/use case)

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

## Execution Modes (Plan vs Results)

Rondo separates:
- `execution` = **how** work runs,
- `model` = **where** it routes.

| You want... | Use this | You get back... |
|---|---|---|
| AI to run in your current host/session loop | `execution="inline"` | A plan for YOU to execute in your current code |
| AI to run independently and return completed results | `execution="subprocess"` | Completed results from a separate Rondo process |
| Host agent orchestration with explicit model | `execution="agent"` | A plan for your host to spawn a Claude Agent |
| Cloud/provider adapter call (Gemini/Grok/OpenAI/Mistral/Anthropic/local) | `model="provider:model"` | Completed results via the provider's HTTP API |
| Let caller defaults decide | `execution=""` | MCP defaults to inline; Python/CLI defaults to subprocess |

Provider-prefixed models (for example `gemini:...`, `anthropic:...`) route HTTP adapters and bypass execution mode routing.

### Host spawn example for `execution="agent"`

When Rondo returns an agent plan, the host is responsible for launching an agent with that plan payload.

```python
import json
from rondo.mcp_dispatch import rondo_run_file

plan = json.loads(
    rondo_run_file(
        prompt="Review src/rondo/envelope.py and propose safer error handling.",
        model="sonnet",
        execution="agent",
        dry_run=False,
    )
)

if plan.get("kind") == "agent_dispatch_plan":
    # -- Host contract: spawn an Agent using plan prompt/model/project.
    host.spawn_agent(
        model=plan["model"],
        prompt=plan["prompt"],
        working_dir=plan.get("project") or ".",
    )
```

### Option C conflict truth table

| plan_only | execution | Result |
|---|---|---|
| false | `""` | Option C auto-execute, results |
| false | `subprocess` | Subprocess results |
| false | `inline` | Option C auto-execute, results |
| false | `agent` | Agent plan (host spawns) |
| true | `""` | Inline plan JSON (debug) |
| true | `subprocess` | Inline plan JSON (plan_only wins) |
| true | `inline` | Inline plan JSON (debug) |
| true | `agent` | Agent plan JSON (debug) |

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
