# API Stability — what Rondo promises not to break

**Status:** ACTIVE contract (RONDO-340, SOP-106 dimension 9)
**Version covered:** 0.7.x | **Created:** 2026-06-06
**Lock:** `tests/conventions/test_api_stability.py` derives the CLI/MCP
surface from source and fails the build if this doc drifts from reality.

---

## TL;DR

| Surface | Promise |
|---------|---------|
| CLI subcommands + flags | Stable — deprecation policy applies |
| Exit codes (0, 1, 2, 130) | Stable contract (RONDO-335) — will not change meaning |
| Error envelope (JSON) | Stable contract (RONDO-328, docs/ERROR-ENVELOPE-CONTRACT.md) |
| MCP tool names + parameters | Stable — deprecation policy applies |
| config.toml keys | Stable — deprecation policy applies |
| Python imports (`import rondo`) | **NO promise pre-1.0** — CLI/MCP/config are the contract |
| Anything marked Experimental | May change or vanish without a deprecation window |

---

## What "stable" means at 0.7.x

Rondo is pre-1.0. "Stable" does not mean frozen — it means **covered by
the deprecation policy below**: you get a warning at least one minor
version before anything is removed or changes meaning. Surfaces NOT
listed here (internal modules, file layouts under `~/.rondo/`, report
formats) carry no promise yet.

## Deprecation policy

1. A surface slated for removal first emits a `-WARNING-` deprecation
   notice at use time, naming the replacement.
2. The warning ships for at least **one minor version** before removal
   (deprecated in 0.8.x → earliest removal 0.9.0).
3. Exit codes and the error-envelope field names are never repurposed —
   new meanings get new codes/fields.
4. Experimental surfaces are exempt: they may change in any release.

---

## Stable surface 1: CLI subcommands (24)

Derived from `src/rondo/cli.py` (`build_parser()`); the conventions lock
keeps this list complete.

| Command | What it does |
|---------|--------------|
| `run` | Execute a round definition file (.py/.yaml/.json) |
| `pipeline` | Run a REQ-114 prompt pipeline YAML (plan/apply prompt programs) |
| `live` | Execute round in live mode (human reviews) |
| `overnight` | Phase scheduler with watchdog response |
| `report` | Morning report generation |
| `replay` | Replay one saved task dispatch by run id |
| `compare` | Compare two saved task runs by id |
| `preflight` | Check dispatch environment without running |
| `history` | Show dispatch history |
| `audit` | Query dispatch audit trail |
| `flaky` | Show flaky task templates |
| `spool` | Manage result spool (list/clean/export/consume) |
| `metrics` | Dispatch metrics for dashboards and health |
| `mcp` | Start MCP stdio server (Claude Code integration) |
| `init` | Create a starter round file or config |
| `schedule` | Create launchd plist for recurring dispatch |
| `doctor` | Install diagnosis — zero dispatches, zero cost |
| `models` | Model registry tools (--verify, --tiers, --docs-drift) |
| `nightly` | Watchdog sweep: drift + retry queue + 7d reliability |
| `learn` | Compute provider scores from dispatch history — **Experimental** |
| `providers` | Show configured providers with health status |
| `matrix` | Experiment matrix: model × effort × context grid |
| `retryq` | Retry queue lifecycle (list/sweep/drain/purge-dead) |
| `version` | Show version or bump build counter |
| `review` | Send file to 2+ cloud providers for independent review |

Inline prompt mode (`rondo "prompt"` with no subcommand) is stable (req 400).

### Exit codes (stable contract — RONDO-335)

Defined at `src/rondo/cli.py` and documented in `--help` epilog:

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | task/dispatch failure or unexpected error |
| 2 | bad arguments or unknown subcommand |
| 130 | interrupted (Ctrl+C) |

---

## Stable surface 2: MCP tools (27)

Derived from `src/rondo/mcp_server.py` (`create_mcp_server()`).

| Tool | What it does |
|------|--------------|
| rondo_run | Run AI tasks (file_path or prompt) |
| rondo_run_status | Query background task status (heartbeat/brief/full) |
| rondo_retry | Retry a failed dispatch |
| rondo_verify | REQ-115 verified execution: rondo checks declared postconditions itself |
| rondo_cloud | Dispatch to cloud provider (HTTP adapter) |
| rondo_chain | Chain sequential AI tasks |
| rondo_benchmark | Benchmark a prompt across models |
| rondo_explain | Explain AI-generated output |
| rondo_review_file | AI code review of one file |
| rondo_multi_review | Same prompt to N providers, merged findings |
| rondo_jury | REQ-118 cross-vendor jury: different vendors judge an artifact; disagreement is the signal (experimental) |
| rondo_review_codebase | AI review of an entire codebase |
| rondo_summarize | Summarize code/docs |
| rondo_diff | Diff two task results |
| rondo_metrics | Full dispatch metrics dashboard |
| rondo_health | Quick health check (GREEN/YELLOW/RED; UNKNOWN = zero providers configured) |
| rondo_doctor | Install diagnosis |
| rondo_fleet | Fleet watchdog sweep |
| rondo_audit_summary | Recent dispatch audit records |
| rondo_history | Dispatch history query |
| rondo_cost | Cost report (default 30 days) |
| rondo_models | Model registry info |
| rondo_templates | Built-in round templates |
| rondo_dispatch_info | Version, commands, capabilities |
| rondo_schedule_list | List scheduled jobs |
| rondo_schedule_create | Create launchd schedule |
| rondo_spool_consume | Consume result spool |

The MCP resource `rondo://help` is stable.

---

## Stable surface 3: config.toml keys

Parsed by `src/rondo/config.py` (`load_config()` → frozen `RondoConfig`).
Discovery order is itself stable: `$RONDO_CONFIG` →
`$XDG_CONFIG_HOME/rondo/config.toml` → `~/.config/rondo/config.toml` →
`~/.rondo/config.toml` (legacy).

| Group | Keys |
|-------|------|
| Dispatch | auth, default_model, default_execution, effort, output_format, claude_binary, task_timeout_sec, round_timeout_sec |
| Parallel | workers, throttle_sec |
| Permissions | permission_mode |
| Self-healing | watchdog_timeout_sec, rate_limit_backoff_sec, on_overage, worktree_isolation |
| Paths | results_dir, report_dir, audit_dir |
| Cost/output | max_budget_usd, json_schema, dispatch_system_prompt |
| Claude -p mode | claude_p_rules, claude_p_allowed_tools, claude_p_max_turns, claude_p_add_dir, claude_p_json_schema |
| Claude agent mode | claude_agent_rules, claude_agent_max_turns, claude_agent_allowed_tools |
| Spool | spool_enabled |
| Project | project |
| Flags | bare, dry_run, verbose |
| Providers | providers.NAME.enabled / cheap_model / default_model / best_model / trust |

---

## Experimental (no deprecation window)

| Surface | Why experimental |
|---------|------------------|
| `learn` command + learned-routing data | Auto-apply design has 3 open questions (specs/Rondo-DESIGN-registry-auto-apply.md, req 606) — semantics may change when answered |
| Python library imports (`from rondo import ...`) | Pre-1.0; will be declared at 1.0 |
| `~/.rondo/` on-disk layouts (audit/spool/retry file formats) | Internal; read via CLI/MCP, not directly |

---

## Change history

| Date | Change |
|------|--------|
| 2026-06-06 | Initial contract (RONDO-340): surface derived from cli.py + mcp_server.py, deprecation policy declared, lock added |
