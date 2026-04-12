# Getting Started Wow Path (10 Minutes)

This is the fastest way to feel what Rondo does in real workflows.

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

You should get structured output with normalized envelope fields.

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

