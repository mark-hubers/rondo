# Getting Started Wow Path (10 Minutes)

This is the fastest way to feel what Rondo does in real workflows.

`uv` is Astral's fast Python package/runtime tool; install it from [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).  
If you do not use `uv`, you can use `pip` equivalents for these steps (for example `pip install -e .` and `python ...`).

## 1) Install Rondo

```bash
uv tool install -e .
```

From repo root, this installs the `rondo` CLI in your user tools.

## 2) Run Fast Validation (Green)

```bash
rondo-test --fast
```

This confirms core wiring (unit tests, lint, fast contracts).

## 3) Run the Showcase

```bash
rondo-test --showcase
```

You will see 10 real demo sections (inline, subprocess, agent, multi-provider, consensus, escalation, JSON return, polling, idempotency, and more).

## 4) Try CLI Hello World

```bash
rondo "Return JSON only: {\"message\":\"hello world from rondo\"}"
```

No Claude Code CLI installed (or running inside a Claude Code session)?
Route to a provider API directly — same JSON contract:

```bash
rondo "Return JSON only: {\"message\":\"hello world from rondo\"}" --model gemini:gemini-flash-latest
```

You should get structured output with normalized envelope fields. A failed
dispatch returns an honest error envelope (`error_code`, `error_message`,
`error_help`) — never a silent empty result.

## 5) Try `rondo_run` from MCP

In Claude Code, call the MCP tool:

```text
rondo_run(
  prompt="Return JSON only: {\"status\":\"ok\",\"source\":\"mcp\"}",
  model="sonnet",
  execution="inline",
  dry_run=false
)
```

This confirms MCP path and envelope compatibility.

If you use `execution="agent"`, Rondo returns an `agent_dispatch_plan`; your host then spawns an agent with `plan["model"]` + `plan["prompt"]` in the target project directory.

## 6) Run One Real API Example

```bash
python examples/api/01_simple_dispatch.py
```

This shows direct Python usage using the same dispatch contract.

## 7) Find More Examples

Open:

- `examples/INDEX.md`

Use the mode/provider/category columns to pick a workflow quickly.

## 8) Learn the Result Contract

Read:

- `docs/ERROR-ENVELOPE-CONTRACT.md`

This is the canonical status/error schema used across MCP, API, and CLI.

