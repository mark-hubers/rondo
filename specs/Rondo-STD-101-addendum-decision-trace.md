# Rondo-STD-101 Addendum: Decision Trace — Interactive Dispatch Debugging

**Parent:** Rondo-STD-101-observability.md
**Created:** 2026-04-09
**Origin:** Session 100 — AI review consensus: "makes the router visible, builds trust"
**Status:** DRAFT

---

## Problem Statement

Rondo makes routing decisions based on provider health, model routing tables,
budget caps, circuit breaker state, fallback chains, and tier resolution. When
a dispatch goes to an unexpected provider or fails, users have no way to see
WHY that decision was made without reading debug logs after the fact.

**Current state:**
- `structured_log` captures events but requires post-mortem log reading
- `rondo_health()` shows provider status but not routing decisions
- No way to see "Rondo picked Gemini because Grok was down and budget was low"

**What's needed:** A real-time decision trace that shows each routing decision
as it happens, and a post-hoc explain command for completed dispatches.

---

## Requirements

### CLI Debug Mode

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 200 | `rondo run --debug` MUST print each routing decision to stderr as it happens: provider selection, fallback triggers, budget checks, circuit breaker state. | MUST | CLI test |
| 201 | Debug output MUST use structured format: `[DECIDE] provider=gemini reason="tier:default, health:UP, cost_est:$0.003"` | MUST | Format test |
| 202 | Debug output MUST NOT include prompt content, API keys, or raw_output. Only metadata: provider, model, reason, cost estimate, latency estimate. | MUST | Security test |
| 203 | Debug mode MUST NOT change dispatch behavior — same routing, same results, just with visibility. | MUST | Behavior test |
| 204 | Debug output MUST include timing: `[DECIDE +0.3s]` elapsed since dispatch start. | SHOULD | Timing test |

### MCP Decision Trace

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 210 | `rondo_run` MCP tool MUST accept optional `trace=True` parameter. When set, the response JSON includes a `decisions` array with each routing decision. | MUST | MCP test |
| 211 | Decision trace in MCP response: `[{"step": "provider_select", "chose": "gemini:flash", "reason": "tier:default", "alternatives": ["grok:grok-3"], "elapsed_ms": 12}]` | MUST | Schema test |
| 212 | Decision trace MUST include budget state: `{"step": "budget_check", "running_cost": 0.05, "cap": 0.10, "action": "proceed"}` | MUST | Budget test |
| 213 | Decision trace MUST include circuit breaker state: `{"step": "breaker_check", "provider": "openai", "state": "CLOSED", "consecutive_errors": 0}` | SHOULD | Breaker test |

### Post-Hoc Explain

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 220 | `rondo explain <dispatch_id>` CLI command MUST reconstruct the decision trace from the audit trail (STD-113 INTENT + OUTCOME records). | SHOULD | CLI test |
| 221 | `rondo_explain` MCP tool (existing) SHOULD be extended to include decision trace when audit records contain trace data. | SHOULD | MCP test |

### Audit Trail Extension

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 230 | INTENT audit records (STD-113 req 003) MUST include a `decisions` field when trace is enabled. This persists the decision trace for post-hoc explain. | MUST | Audit test |
| 231 | Decision trace data MUST NOT increase INTENT record size by more than 500 bytes (typical: 200-300 bytes for 3-5 decisions). | SHOULD | Size test |

---

## Architecture

Decision trace is implemented as a lightweight collector passed through the
dispatch pipeline:

```
  resolve_dispatch_engine()  →  [DECIDE: engine=http, provider=gemini]
         |
  get_provider_with_fallback()  →  [DECIDE: primary=gemini UP, no fallback needed]
         |
  budget_check()  →  [DECIDE: running=$0.05, cap=$0.10, action=proceed]
         |
  dispatch()  →  [DECIDE: dispatched to gemini:flash, timeout=300s]
         |
  finalize_dispatch()  →  [DECIDE: cost=$0.003, status=done, audit=recorded]
```

The collector is a simple list of dicts. No new classes needed — just
`decisions: list[dict]` threaded through existing functions.

---

## Example Output

```
$ rondo run my_round.py --debug
[DECIDE +0.0s] engine=http provider=gemini reason="tier:default"
[DECIDE +0.0s] health provider=gemini status=UP latency=45ms
[DECIDE +0.0s] budget running=$0.000 cap=$1.000 action=proceed
[DECIDE +0.1s] breaker provider=gemini state=CLOSED errors=0
[DECIDE +2.3s] dispatched model=gemini-2.5-flash tokens_in=1204 tokens_out=856
[DECIDE +2.3s] cost=$0.003 total_running=$0.003
[DECIDE +2.4s] finalized audit=recorded sanitized=yes spooled=yes
  done | analyze | gemini-2.5-flash | $0.003 | 2.3s
```

---

## Risk

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Trace overhead slows dispatch | Low | Low | List append is O(1). Trace is <1ms total. |
| Trace leaks sensitive data | Medium | High | Req 202: no prompts, keys, or output. Metadata only. |
| Trace format changes break consumers | Low | Medium | Schema version in trace header. |

---

## Version History

| Ver | Date | Changes |
|-----|------|---------|
| 0.1 | 2026-04-09 | Initial draft. Session 100: AI-reviewed consensus feature. |
