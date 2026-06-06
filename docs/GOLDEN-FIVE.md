# The Golden Five — your first hour with Rondo

*Five commands, in order, each verified live on 2026-06-06. No prior Rondo
knowledge assumed. Total cost if you run everything: under 5 cents.*

If any step surprises you, that's a bug — please report it (step 1 builds
the redacted report for you).

---

## 1. Is my install healthy? (free)

```bash
rondo doctor
```

Six checks — config, provider keys (shown last-4 only, never full), model
registry, data dirs, the claude binary, versions. Every non-PASS row comes
with a one-line fix. Exit 0 = healthy.

Something wrong and you want help? `rondo doctor --bundle` writes a
secrets-redacted report file you can paste into an issue.

## 2. One prompt, structured JSON back (~$0.0001)

```bash
rondo "Reply with exactly: OK" --model gemini:gemini-flash-latest
```

Stdout is validated JSON: `{"passed": true, "result": "OK", ...}` — pipe it
to `jq`, branch on fields, script around it. That's the core trick: **prompting
as a dependable workflow surface**. A failed dispatch returns an honest error
envelope (`status`, `error_code`, `error_message`, `error_help`) — never a
silent empty result.

`--text` gives the raw model text with no JSON wrapper.

## 3. A round file — tasks as data (~$0.01)

```bash
rondo run examples/rounds/07-task-affinity.yaml --dry-run   # free preview
rondo run examples/rounds/07-task-affinity.yaml             # live
```

Three tasks, three models, one YAML file. Each task carries a `task_type`,
so Rondo's scoring learns which model is best at WHICH job from your own
dispatch history. Unknown YAML fields are rejected at load — typos can't
silently change behavior.

## 4. An experiment, not a vibe (~$0.01)

```bash
rondo matrix run examples/rounds/08-matrix-with-judge.yaml --dry-run  # grid + cost estimate
rondo matrix run examples/rounds/08-matrix-with-judge.yaml           # live
rondo matrix report judge-demo
```

Model × replicates as one budgeted grid: a hard cost ceiling, resumable
manifest, and an external judge model scoring every cell against your rubric
— fair cross-model comparison instead of "it felt better."

## 5. The fleet view (free)

```bash
rondo nightly --no-notify   # drift + retry queue + 7-day reliability, one sweep
rondo metrics               # cost / reliability / latency scoreboard
```

Rondo watches its own health: retired models get caught BEFORE dispatches
404, failed work self-classifies into a retry queue, and the 7-day success
rate is compared against a 95% target — honestly (a window with no data says
so; it never fakes 100%).

Want this running while you sleep?
`rondo schedule --cmd nightly --interval daily --name nightly-watchdog --install`

---

## Where next

| Want | Go to |
|------|-------|
| All 90 runnable examples | `examples/INDEX.md` |
| Full getting-started | `docs/GETTING-STARTED.md` |
| The error contract | `docs/ERROR-ENVELOPE-CONTRACT.md` |
| MCP (Claude Code) path | `examples/mcp/README.md` |
| Recipes | `docs/COOKBOOK.md` |
