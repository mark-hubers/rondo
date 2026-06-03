# Rondo Audit — Findings (2026-06-03)

**Method:** 10-agent research workflow (`rondo-audit-2026-06`, run `wf_c08ff3ac-3a6`).
8 research agents fanned out across 3 phases + 1 synthesis agent. ~800K tokens, 7 min.
**Window mined:** 2026-04-08 → 2026-06-03 (8 weeks).
**Raw structured output:** preserved verbatim in `RAW-SYNTHESIS.json` (this dir).

> ⚠️ **Trust note:** P1 (usage mining) is grounded in real git/runtime data and is high-confidence.
> P2/P3 (Claude Code features + competitive) are **web-sourced** — some URLs look low-quality and
> some claims are marketing-flavored. Treat P2/P3 as leads to verify, NOT facts. See "Verification" below.

---

## Verification (Claude read the live code — DO NOT skip this)

Per "checked ≠ correct" — I verified the report's code-level claims against `anthropic_api.py`
and the adapter dir directly. Results:

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Fix #0: HTTP error body swallowed | ✅ **REAL** | `anthropic_api.py:175` uses `exc.reason` only; never `exc.read()` |
| `temperature` sent unconditionally | ✅ **REAL** | `anthropic_api.py:92` — always in payload (default 0.2) |
| Opus 4.8 rejects temperature when thinking on | ✅ **REAL** (web-confirmed, multiple sources) | This is the likely 400 root cause |
| `effort` wired on CLI but not API path | ✅ **REAL** | No `effort`/`output_config` anywhere in `anthropic_api.py` payload |
| `anthropic-version: 2023-06-01` stale | ⚠️ **MIXED** | Lines 100/205 — BUT P2 web scan says 2023-06-01 is still current. Verify before bumping. |
| `models()` doesn't list 4.8 | ✅ **REAL** | Line 220 lists `claude-opus-4-6`, no 4-8 |
| **"Gemini + Anthropic adapters have NO retry/breaker" (Finding #234)** | ❌ **FALSE / STALE** | All 3 adapters have `retry_http` (4×) + `get_circuit_breaker` (2×). Finding was fixed since logged. |

**Lesson:** the synthesis ranked "implement retry/breaker parity" as a P1 stability action — but it's
**already done**. Don't spec/build it. This is exactly why agent findings get verified against code
before they become work.

---

## P1 — Usage Mining (HIGH confidence, real data)

### What worked (keep doing)
- **Example/docs overhaul** (RONDO-240→285) — real-dispatch examples, GETTING-STARTED, 62-example index. Unblocked real workflows.
- **Finding→commit traceability** — 260+ findings mapped to sprints+commits. Disciplined closure.
- **Cost calibration** (RONDO-295) — replaced flat $0.60 heuristic with per-provider pricing (9× tighter on small prompts; now blocks 4×Opus-100K burns).
- **Audit trail** — two-phase INTENT/OUTCOME, atomic writes, `fcntl.flock`, secret scrubbing, request_id correlation, stuck-intent reconciliation. 1808 dispatch records.
- **Architecture refactor** — extracted 416-line `dispatch_routing.py`, shrank `mcp_dispatch.py` 27%.

### Real runtime health (from ~/.rondo/, 847 dispatches)
- **68.5% success** (580 done). **13.3% partial/malformed JSON** (113) — mostly subprocess "Not logged in". **5.2% blocked** (44) with zero diagnostics. **103 ERR_SUBPROCESS** with no stderr captured.
- **Retry queue is write-only** — 50 stale files, 60% ERR_SUBPROCESS_FOOTGUN (semantic blocks, not transient). No aging/cleanup.
- **Cost=$0 on every record** — Max-auth masks cloud-provider cost; error/timeout paths never capture cost or tokens.

### USH = voice of the customer (real research use)
- **Multi-provider cabinet review worked great** — 3 providers convergence-checked 8 citation gaps; all flagged the same hallucinated stat. Convergence = actionable.
- **Task-specific profiles** (`ush_medical`/`ush_writing`/`ush_deep`) — plain-English → provider sets.
- **Blockers:** Opus 4.8 HTTP 400 (the trigger for all this); effort not on API path; stale model names (gpt-4.1 retired Feb 2026) with no auto-refresh; silent provider drop-out (Mistral vanished, no error); `default_count=2` surprises `ush_deep` (4 providers).

### Top failures (real)
1. **auto_reconcile race** (Finding #257, flagged HIGH by Gemini+Grok) — INTENT/IN-FLIGHT/DONE not atomic across processes → valid in-flight marked "stuck" → duplicate re-dispatch.
2. **Subprocess auth fragility** — `claude -p` loses session mid-run → 13% malformed.
3. **Opus 4.8 400** — adapter built for 4.6 contract.
4. **Opaque errors** — ERR_SUBPROCESS/blocked records have no stderr/context.

---

## P2 — New Claude Code / Opus 4.8 (web-sourced, VERIFY before acting)

### Directly relevant to the 4.8 fix (high confidence — corroborated)
- **Adaptive thinking**: Opus 4.8 only supports `thinking: {type:'adaptive'}`. Manual `budget_tokens` → 400.
- **`output_config.effort`**: `low/medium/high/xhigh/max` replaces sampling control. Maps to Rondo's existing `RondoConfig.effort`.
- **temperature/top_p/top_k rejected entirely** on 4.8 → must STRIP, not just clamp.
- **Structured outputs**: `output_config.format = {type:'json', schema:{…}}` — stable, no beta header.

### Opportunities (rank later)
- **Batch API** — 50% cost cut for overnight (async, <1hr). Strong fit for Rondo's overnight niche.
- **Prompt caching** — 5-min TTL (won't survive overnight gaps; good for interactive multi-provider where same context → N providers).
- **1M context** — no premium; map effort→context budget.
- **Agent teams / subagents / Dynamic Workflows** — overlaps Rondo's job (see P3).

> Some P2 claims (e.g. "Dynamic Workflows rewrote Bun Zig→Rust", "Agent SDK billing split June 15") are
> marketing/speculative and from weak sources. Do not cite as fact.

---

## P3 — Competitive landscape → Rondo's niche

**Rondo's defensible niche:** *structured, cost-aware, UNATTENDED multi-provider AI dispatch.*

| Competitor | They win at | Rondo wins at |
|------------|-------------|---------------|
| **Claude Agent SDK** | interactive MCP agents, session resume, native code-edit | provider-agnostic, $0 Max auth, zero-dep, overnight, audit/cost gating |
| **aider** | interactive git pair-programming, repo-map | unattended batch, retry/breaker, cost caps, scheduling, multi-provider compare |
| **LangGraph/CrewAI/AutoGen** | heavyweight graph orchestration, big tool ecosystems | zero-dep install, overnight watchdog+spool, MCP-first, operational simplicity |

**Honest weakness:** the niche is defensible but ecosystem lock-in is weak (features are copyable).
Growth = serve Mark's own research labs (USH, ACE, OB) extremely well — cost tracking + effort sweeps
for large AI experiments is the killer use case nobody else nails.

**Gaps worth borrowing (without bloating):** conditional/branching rounds (LangGraph edges),
optional distributed idempotency cache, blind-scoring + `--replicates=N` for experiments.

---

## Ranked recommendations (from synthesis — P0 verified, others need triage)

### P0 — stability/bugs (do first)
| # | Fix | Target spec | Effort | Verified? |
|---|-----|-------------|--------|-----------|
| 1 | **Opus 4.8: strip temperature/top_p/top_k for thinking models** | REQ-109 | M | ✅ real |
| 2 | **Surface HTTP error body** (`exc.read()`) — all adapters | STD-108 | S | ✅ real |
| 3 | **auto_reconcile distributed locking** (Finding #257) | STD-110 | L | ⚠️ verify lock isn't already partial |
| 4 | **Subprocess auth recovery** (13% "Not logged in") | IFS-100 | M | ✅ real (runtime data) |

### P1 — high value (unblocks research)
- Wire `effort` → `output_config.effort` into API adapters (REQ-109) — ✅ real gap
- Capture stderr/env in error records (STD-113) — ✅ real
- Cost on error/timeout paths (STD-105) — ✅ real
- Model registry auto-refresh + drift report (REQ-111) — ✅ real friction
- Structured logging adoption w/ correlation_id (STD-101) — verify how unused it really is
- Provider drop-out explicit failure mode (REQ-109) — ✅ real (Mistral silent)
- ~~Retry/breaker parity~~ — ❌ **ALREADY DONE, drop it**

### P2 — ecosystem polish (later)
Batch API routing, blind-scoring `--blind`, `--replicates=N`, pre-dispatch cost estimate,
JSONL→SQLite index, cyclic-import cleanup, Claude Code subagent integration.

### Quick wins (single-line-ish)
- Delete hardcoded `[:2000]` truncation in `mcp_dispatch.py` (Finding #258)
- `exc.read().decode()` in HTTPError handler (= P0 #2)
- request_id on error/blocked records
- Update RONDO-REFERENCE.md CLI count

---

## Proposed next step (NOT yet done — awaiting Mark)
1. **Spec the P0 fixes** into REQ-109 / STD-108 / STD-110 / IFS-100 (spec-first, the right way).
2. **File P0+P1 as OB findings** via `ace-sprint` so they're tracked work.
3. **Build Fix #2 first** (surface error body) → re-test 4.8 → confirm temperature theory empirically before the rest.
