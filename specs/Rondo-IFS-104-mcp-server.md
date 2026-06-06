# Rondo-IFS-104: Rondo MCP Server (Multi-Model Dispatch)

**Category:** IFS (Interface Specification)
**Product:** Rondo (Multi-Model AI Dispatch)
**Created:** 2026-03-21 Session 84
**Status:** STUB — to be expanded when Rondo is built (tool inventory kept current; rev-0004 adds rondo_doctor + rondo_fleet, RONDO-324)
**Revision:** rev-0004
**Depends on:** CORE-STD-021 (MCP Standard), Rondo-REQ-109 (Provider Adapters), Rondo-STD-100, CORE-STD-012, Rondo-STD-114, CORE-STD-013, Rondo-STD-107
**Implements:** CORE-STD-021 MCP Standard for Rondo product
**Port:** 8300

---

## 1. Purpose & Scope

Rondo's MCP server lets the AI dispatch work to other models, check provider status, and manage batch jobs — all from conversation.

**IN scope:** MCP tool definitions, transport protocol, authentication, provider routing.
**OUT of scope:** Provider adapter internals (Rondo-REQ-109), dispatch execution logic (Rondo-REQ-100), cost tracking details (Rondo-STD-105).

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified IFS correct (Session 86) -->

## 2. The Problem

Without an MCP server, Rondo can only be invoked via CLI or Python import. AI sessions cannot dispatch work to other models mid-conversation. The MCP server makes Rondo's multi-model dispatch available as a tool that Claude (or any MCP client) can call directly.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Implement CORE-STD-021 MCP Standard for Rondo product | MUST | Compliance test |
| 002 | Listen on port 8300 (Rondo's assigned port) | MUST | Port test |
| 003 | Expose query tools: providers, routing, batch_status, cost | MUST | Tool test |
| 004 | Expose action tools: dispatch, batch_submit, batch_cancel | MUST | Tool test |
| 005 | Expose status tools: provider health, capacity | MUST | Tool test |
| 006 | All tools follow CORE-STD-021 naming convention: `rondo_{category}_{action}` | MUST | Naming test |
| 007 | Authentication via MCP token (CORE-STD-021 standard) | MUST | Auth test |
| 008 | Rate limiting per MCP client session | SHOULD | Rate test |


---

## 4. Architecture / Design

MCP server wraps Rondo's dispatch engine as tool endpoints. Query tools are read-only (no side effects). Action tools trigger dispatches and return dispatch_ids. Status tools query provider health in real-time. All tools return structured JSON matching Rondo-STD-100 data conventions.

---

## 5. Data Model

MCP tool responses use Rondo's standard dataclasses: `DispatchUsage` for cost data, provider status as `{provider, model, healthy: bool, latency_ms: int}`, batch status as `{batch_id, total, completed, failed, status}`. No MCP-specific data model — reuse existing Rondo types.

---

## 6. Data Boundary

MCP is the boundary between AI conversation and Rondo's dispatch engine. Tools receive structured parameters (JSON), invoke Rondo's Python API, and return structured responses. No raw subprocess output crosses the MCP boundary — all results are parsed and sanitized (Rondo-STD-114) before returning.

---

## 7. MCP / API Interface

### Context Budget Summary

| Tool | Category | Typical Cost | Max Cost | Notes |
|------|----------|-------------|----------|-------|
| `rondo_query_providers` | Query | ~200 tokens | ~400 tokens | Provider list; ~50 tokens/provider |
| `rondo_query_routing` | Query | ~200 tokens | ~500 tokens | Routing table; ~30 tokens/route |
| `rondo_query_batch_status` | Query | ~150 tokens | ~300 tokens | Single batch with item counts |
| `rondo_query_cost` | Query | ~80 tokens | ~100 tokens | Single cost estimate |
| `rondo_action_dispatch` | Action | ~100 tokens | ~200 tokens | dispatch_id + status (result async) |
| `rondo_action_batch_submit` | Action | ~80 tokens | ~100 tokens | batch_id + item count |
| `rondo_action_batch_cancel` | Action | ~60 tokens | ~80 tokens | Confirmation + cancelled count |
| `rondo_status_providers` | Status | ~150 tokens | ~300 tokens | Health + latency per provider |
| `rondo_status_capacity` | Status | ~100 tokens | ~200 tokens | Capacity per provider |

### Planned Tools

### Query
| Tool | What | Context Cost |
|------|------|-------------|
| `rondo_query_providers` | List available AI providers and models | ~200 tokens (provider list); ~50 tokens/provider |
| `rondo_query_routing` | Show model routing table (task → model) | ~200 tokens (routing table); ~30 tokens/route |
| `rondo_query_batch_status` | Status of batch jobs | ~150 tokens (single batch status with item counts) |
| `rondo_query_cost` | Cost estimate for a dispatch | ~80 tokens (single cost estimate) |

### Action
| Tool | What | Context Cost |
|------|------|-------------|
| `rondo_action_dispatch` | Send prompt to specific model | ~100 tokens (dispatch_id + status; result is async) |
| `rondo_action_batch_submit` | Submit batch of prompts | ~80 tokens (batch_id + item count) |
| `rondo_action_batch_cancel` | Cancel running batch | ~60 tokens (confirmation + cancelled count) |

### Status
| Tool | What | Context Cost |
|------|------|-------------|
| `rondo_status_providers` | Provider health + latency | ~150 tokens (health + latency per provider) |
| `rondo_status_capacity` | Available capacity per provider | ~100 tokens (capacity per provider) |

---

## 8. States & Modes

MCP server has two states: `RUNNING` (accepting tool calls) and `STOPPED` (not listening). No graceful degradation mode — if the server cannot reach a provider, the tool call returns an error. Batch jobs have states: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.

---

## 9. Configuration

```toml
[mcp]
enabled = false                    # MCP server disabled by default
port = 8300                        # CORE-STD-021 assigned port
auth_token_env = "RONDO_MCP_TOKEN" # Auth token from env var
max_concurrent_dispatches = 5      # Limit concurrent MCP-initiated dispatches
```

---

## 10. Rules & Constraints

1. **Rondo is the ONLY model-aware component** (per architecture decision). All other products dispatch through Rondo for non-Claude work (Gemini, OpenAI). Violation ID: `IFS104-SINGLE-ROUTER`
2. **MCP tools follow CORE-STD-021 naming convention.** `rondo_{category}_{action}` format. Violation ID: `IFS104-NAMING`
3. **Action tools require authentication.** Query and status tools are read-only and may be unauthenticated in local mode. Violation ID: `IFS104-AUTH`
4. **Sanitized responses only.** No raw subprocess output, no secrets, no unsanitized AI text crosses MCP boundary. Violation ID: `IFS104-SANITIZED`

---

## 11. Quality Attributes

- **Latency:** Query/status tools respond in <100ms. Action tools respond with dispatch_id immediately, results available asynchronously.
- **Reliability:** MCP server crash does not affect Rondo CLI or Python API operation.
- **Compatibility:** Implements CORE-STD-021 standard — any MCP client can connect.
- **Resilience:** Timeout with exponential backoff on all external calls.

---

## 12. Shared Patterns

- **CORE-STD-021 MCP Standard:** Port assignment, tool naming, authentication, transport.
- **Tool categorization:** Query/Action/Status — same 3-category pattern used by all ACE2 MCP servers.
- **Structured responses:** JSON matching Rondo-STD-100 conventions — same data format as spool files.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| MCP client → Rondo | Tool call parameters | CORE-STD-021 protocol |
| Rondo → AI providers | Dispatch requests | Rondo-STD-105 dispatch protocol |
| Rondo → MCP client | Structured tool responses | Rondo-STD-100 data conventions |
| Rondo MCP → OB MCP | dispatch_ids for cross-product tracing | CORE-STD-013 TrackerData |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-021 | MCP standard — this spec implements it for Rondo |
| CORE-STD-012 | Requirement readiness — MCP tool availability is a readiness signal |
| CORE-STD-013 | TrackerData — MCP tool invocations are trackable events |
| Rondo-STD-100 | Data conventions — all MCP responses follow Rondo's data standards |
| Rondo-STD-114 | Output sanitization — MCP responses are scrubbed before returning |

---

## 15. Self-Correction

MCP tool usage patterns feed CORE-STD-011: which tools are called most, which fail most, which return the most useful results. Over time, tool implementations can be optimized based on usage data. This is future work — not applicable for the stub.

---

## 16. Assumptions

1. MCP protocol remains stable across Claude Code versions.
2. Port 8300 is available on the host machine (no conflicts).
3. Local-only deployment — no remote MCP access planned for v1.0.
4. This spec will be expanded when Rondo moves from spikes to real code.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Claude can call `rondo_query_providers` and get a provider list | Tool test |
| 2 | `rondo_action_dispatch` sends a prompt to a non-Claude model and returns result | Dispatch test |
| 3 | MCP server passes CORE-STD-021 compliance check | Compliance test |

---

## 18. Build Notes / Estimate

MCP server skeleton: 4 hours. Query tools (4 tools): 4 hours. Action tools (3 tools): 6 hours (dispatch integration). Status tools (2 tools): 2 hours. Auth: 2 hours. Total: ~18 hours. Blocked until provider adapters (Rondo-REQ-109) are built.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Protocol tests | CORE-STD-021 compliance, port binding, tool discovery |
| Tool tests | Each of 9 tools returns correct response format |
| Auth tests | Unauthenticated action calls rejected |
| Integration tests | End-to-end: MCP call → dispatch → result returned |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Port 8300 in use | MCP server fails to start | Clear error message, configurable port |
| Provider unreachable | Action tool returns error | Error response with provider status |
| Auth token missing | All action calls rejected | Startup warning if token not set |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). MCP authentication and rate limiting guards can be suspended under DR mode with human approval for emergency dispatch operations.

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-021 | MCP standard — defines protocol and conventions |
| Depends on | Rondo-REQ-109 | Provider adapters — required for multi-model dispatch |
| Depends on | Rondo-REQ-100 | Core dispatch engine — MCP wraps this |
| Depends on | CORE-STD-012 | Readiness tracking for MCP tool availability |
| Used by | OB | Cross-product dispatch via MCP tools |
| Used by | Caliber | Multi-model review dispatch via MCP |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Port 8300 | Assigned by CORE-STD-021 port registry for Rondo | 2026-03-21 |
| D2: Disabled by default | MCP server is optional — most users run CLI or Python API | 2026-03-21 |
| D3: Stub spec now, expand later | Provider adapters are not built yet — full spec premature | 2026-03-21 |

---

## 23. Open Questions

1. Should MCP server support WebSocket transport (CORE-STD-021 option)?
2. Should batch operations be synchronous or fire-and-forget with status polling?
3. How should MCP rate limiting interact with Rondo-STD-107 dispatch rate limits?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **MCP** | Model Context Protocol — standard for AI tool communication |
| **Provider** | An AI service backend (Anthropic, Google, Ollama) |
| **Batch** | Multiple prompts submitted together for parallel dispatch |

---

## 25. Risk / Criticality

**MEDIUM.** MCP server is optional for v1.0 — CLI and Python API are the primary interfaces. Risk is limited to the multi-model future use case. Main risk: CORE-STD-021 protocol changes before Rondo's MCP server is built.

---

## 26. External Scan

MCP is Anthropic's standard. Rondo implements it rather than inventing a custom protocol. No alternative AI tool protocols considered — MCP is the ecosystem standard for Claude Code.

---

## 27. Security Considerations

MCP auth token required for action tools (dispatch costs money). Query/status tools read-only in local mode. All responses sanitized per Rondo-STD-114. Rate limiting prevents MCP-initiated cost flooding. See Rondo-STD-107 for broader security context.

---

## 28. Performance / Resource

MCP server overhead: ~10MB memory, <1ms per tool call routing. Dispatch latency dominated by AI response time (10-300 seconds), not MCP protocol overhead. Server startup: <500ms.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

- Rondo is the ONLY model-aware component (per architecture decision)
- All other products dispatch through Rondo for non-Claude work (Gemini, OpenAI)
- This spec will be expanded when Rondo moves from spikes to real code
- CORE-STD-012 (Requirement Readiness) tracks MCP tool availability as a readiness prerequisite
- CORE-STD-013 (TrackerData) records MCP tool invocations for usage analysis
- CORE-STD-021 is the parent standard — this spec is the Rondo implementation

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Rondo MCP protocol | THEORY | Specced for multi-model dispatch via MCP | Phase 3 build |
| MCP tool registration | THEORY | Task dispatch, status query tools specced | Phase 3 build |
| Remote dispatch interface | THEORY | Specced for network-based task submission | Phase 3 build |


## 35. Change History

| Rev | Date | Session | What Changed |
|-----|------|---------|-------------|
| rev-0001 | 2026-03-21 | 84 | Stub — planned tools only |
| rev-0002 | 2026-03-22 | 84 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
| rev-0003 | 2026-03-22 | 84 | Added context_cost annotations to all 9 tools + Context Budget Summary table. |
| rev-0004 | 2026-03-30 | 93 | MCP dispatch: rondo_run (dry-run + real + background), rondo_run_status, project/budget/timeout params. 7 new reqs (009-015). |
| rev-0005 | 2026-03-30 | 93 | MCP resource: rondo://help for AI self-discovery. 3 new reqs (016-018). |
| rev-0006 | 2026-03-31 | 93 | Tool inventory: 14 tools (was 6). Added: spool_consume, history, cost, retry, diff, summarize, templates. Multi-AI reviewed. |

---

## Addendum: MCP Dispatch (Session 93, RONDO-38/39)

**Problem:** MCP server was monitoring-only. AI sessions couldn't dispatch tasks.
The whole point of Rondo is "tell AI to do X, get back Y." MCP must support this.

### Additional Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 009 | `rondo_run` MCP tool MUST accept `file_path` (round file) and return JSON task results | MUST |
| 010 | `rondo_run` MUST default to `dry_run=True` — real dispatch requires explicit `dry_run=False` | MUST |
| 011 | `rondo_run` MUST accept `project`, `model`, `max_budget`, `timeout_sec` parameters | MUST |
| 012 | `rondo_run` MUST strip CLAUDECODE env before dispatch to prevent nested session errors | MUST |
| 013 | `rondo_run` with `background=True` MUST return immediately with a `dispatch_id`, dispatch in thread | MUST |
| 014 | `rondo_run_status` MCP tool MUST return result of background dispatch by `dispatch_id` | MUST |
| 015 | File paths with `~` MUST be expanded before validation | MUST |

### MCP Tool Inventory (Updated)

| Tool | Type | What |
|------|------|------|
| `rondo_health` | Monitor | GREEN/YELLOW/RED status |
| `rondo_metrics` | Monitor | Cost, reliability, latency |
| `rondo_audit_summary` | Monitor | Recent dispatch records |
| `rondo_dispatch_info` | Discovery | Version, commands, capabilities |
| `rondo_run` | **Dispatch** | Run round file or inline prompt (dry-run/real/background) |
| `rondo_run_status` | **Dispatch** | Check progress (heartbeat/brief/full tiers) |
| `rondo_spool_consume` | **Dispatch** | Drain overnight result mailbox |
| `rondo_history` | **Query** | Dispatch history with model filter + aggregate |
| `rondo_cost` | **Query** | Monthly spend by model with daily average |
| `rondo_retry` | **Recovery** | Re-run failed tasks from previous dispatch |
| `rondo_diff` | **Analysis** | Compare two dispatch results — new/changed/removed |
| `rondo_summarize` | **Analysis** | Condense task results into one report via AI |
| `rondo_templates` | **Discovery** | 5 pre-built round templates (code-review, security, etc.) |

### MCP Resources

| URI | What |
|-----|------|
| `rondo://help` | Full API docs: Round/Task/Gate schemas, example round file, commands, config |

### Resource Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 016 | `rondo://help` resource MUST return the same data as `rondo --ai-help` (JSON with schemas + examples) | MUST |
| 017 | Resource MUST be discoverable via `ListMcpResourcesTool(server="rondo")` | MUST |
| 018 | Resource MUST include a complete, compilable example round file that AI can copy and modify | MUST |
