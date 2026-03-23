# IFS-101: Caliber Integration Contract

*How Rondo receives and executes tasks from Caliber — AI review, AI fix, rule contradiction checks.*

**Created:** 2026-03-19 | **Status:** DESIGNED
**Classification:** open
**Clearance:** not-cleared
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-108 (Error Handling)
**Connects to:** Caliber-IFS-103 (Caliber's side of this integration)
**References:** NAMING-MAP.md, INTEGRATION-ARCHITECTURE.md, CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:**
Defines how Rondo receives and executes tasks dispatched by Caliber. Caliber sends review, fix, and contradiction check tasks. Rondo dispatches to AI (Claude, Gemini), collects results, returns to Caliber. This is Rondo's side — Caliber-IFS-103 defines Caliber's side.

**IN scope:**
- Task types Rondo accepts from Caliber (review, fix, contradiction)
- Task format (instruction + context + done_when)
- Result format returned to Caliber (findings, fix results)
- Multi-AI dispatch (Claude for reverse, Gemini for forward)
- Transport (Python API primary, CLI fallback)
- Standalone behavior (Rondo works without Caliber)

**OUT scope:**
- How Caliber decides what to send (Caliber-IFS-103 owns that)
- How Caliber merges findings (Caliber-IFS-103 owns that)
- OB integration (Rondo-IFS-102 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Caliber performs multi-AI review and fix operations but has no execution engine of its own.
It needs a dispatch layer that can route tasks to different AI models, manage timeouts,
track costs, and return structured results. Without a formal contract between Caliber
and Rondo, task formats drift, error handling becomes ad hoc, and cost tracking is lost.
This spec formalizes the handshake so both products can evolve independently.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

*All requirements in this spec are MUST priority unless marked SHOULD.*
### Task Types Accepted from Caliber
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL **Review tasks** — Caliber sends code + rules, Rondo dispatches to AI reviewer | MUST |

   - Forward review: "Does this code work? Read top-down."
   - Reverse review: "Walk bottom-up. Are assumptions guarded?"
   - Sideways review: "Compare against conventions and other files."
| ID | Requirement | Priority |
|----|-------------|----------|
| 002 | System SHALL **Fix tasks** — Caliber sends finding + code, Rondo dispatches to AI fixer | MUST |

   - Instruction: "Fix this specific issue: {finding.message}"
   - Context: file content + rules that were violated
   - done_when: "Fixed code passes the check that found the issue"
| ID | Requirement | Priority |
|----|-------------|----------|
| 003 | System SHALL **Contradiction check tasks** — Caliber sends full ruleset, Rondo dispatches to AI analyzer | MUST |

   - Instruction: "Find logical contradictions between these rules"
   - done_when: "Zero contradictions found OR conflicts documented"
### Task Input Format
| ID | Requirement | Priority |
|----|-------------|----------|
| 004 | System SHALL rondo accepts Caliber tasks as standard Rondo Task objects — no special format | MUST |
| 005 | System SHALL task.instruction contains Caliber's prompt (review question, fix instruction, or contradiction query) | MUST |
| 006 | System SHALL task.context_files contains the code and rules to review/fix | MUST |
| 007 | System SHALL task.done_when contains Caliber's success criteria | MUST |
| 008 | System SHALL task.model hints which AI to use (Caliber decides based on task type) | MUST |

### Result Format Returned
| ID | Requirement | Priority |
|----|-------------|----------|
| 009 | System SHALL rondo returns standard TaskResult to Caliber: | MUST |

   - `status`: done/partial/error
   - `parsed_result`: JSON with findings array (file, line, severity, message, reviewer)
   - `raw_output`: full AI response
   - `duration_sec`: wall clock
| ID | Requirement | Priority |
|----|-------------|----------|
| 010 | System SHALL for review tasks: `parsed_result.findings[]` matches Caliber's Finding format | MUST |
| 011 | System SHALL for fix tasks: `parsed_result.fixed_code` contains the corrected code | MUST |
| 012 | System SHALL for contradiction tasks: `parsed_result.contradictions[]` lists conflicting rule pairs | MUST |
| 013 | System SHALL dispatchUsage attached: model, tokens_in, tokens_out, cost_usd, duration_ms | MUST |

### Multi-AI Dispatch
| ID | Requirement | Priority |
|----|-------------|----------|
| 014 | System SHALL caliber requests specific models per task type via Task.model field | MUST |
| 015 | System SHALL rondo dispatches to whatever model Caliber requests — no overriding | MUST |
| 016 | System SHALL parallel dispatch: if Caliber sends 2 review tasks (Claude reverse + Gemini forward), Rondo can run both in parallel when workers > 1 | MUST |
| 017 | System SHALL rondo returns separate TaskResult per AI — Caliber handles merging | MUST |

### Transport
| ID | Requirement | Priority |
|----|-------------|----------|
| 018 | System SHALL **Python API (primary):** Caliber imports Rondo client — `from rondo import run_round` | MUST |
| 019 | System SHALL **CLI fallback:** `rondo run task.json` for when Caliber can't import directly | MUST |
| 020 | System SHALL same transport as any other Rondo consumer — no Caliber-specific protocol | MUST |

### Standalone Behavior
| ID | Requirement | Priority |
|----|-------------|----------|
| 021 | System SHALL rondo works without Caliber — it's a general dispatch framework | MUST |
| 022 | System SHALL nothing in Rondo's code references Caliber specifically | MUST |
| 023 | System SHALL caliber is just another consumer that sends Task objects and reads TaskResults | MUST |
| 024 | System SHALL if Caliber is not installed, Rondo doesn't know or care | MUST |

### Error Handling
| ID | Requirement | Priority |
|----|-------------|----------|
| 025 | System SHALL caliber sends malformed task → Rondo returns TaskResult with status="error", error_message explains what's wrong | MUST |
| 026 | System SHALL aI model unavailable → Rondo returns status="error" with model name and reason | MUST |
| 027 | System SHALL aI timeout → Rondo respects task timeout, returns partial results if available | MUST |
| 028 | System SHALL cost budget exceeded → Rondo checks budget before dispatch, returns status="skipped" if over budget | MUST |

---
## 4. Architecture / Design

Caliber sits above Rondo in the stack. Caliber owns quality decisions (what to review, how to
merge findings, what severity means). Rondo owns execution (dispatch to AI, collect results,
track cost). The boundary is: Caliber sends a Task, Rondo returns a TaskResult.

```
Caliber (quality brain)
    │
    │  Task objects (standard Rondo format)
    ▼
Rondo (dispatch muscle)
    │
    │  claude -p / gemini API / ollama
    ▼
AI Providers (Claude, Gemini, Ollama)
```

No Caliber-specific adapters, routes, or branches exist inside Rondo.

---

## 5. Data Model

Rondo uses its standard dataclasses for Caliber interactions. No Caliber-specific models.

| Dataclass | Key Fields | Owner |
|-----------|-----------|-------|
| `Task` | instruction, context_files, done_when, model, timeout_sec | REQ-100 |
| `TaskResult` | status, parsed_result, raw_output, duration_sec | REQ-100 |
| `DispatchUsage` | model, tokens_in, tokens_out, cost_usd, duration_ms | REQ-100 |
| `Finding` | file, line, severity, message, reviewer | Caliber (Rondo passes through) |

Rondo does not persist Caliber-specific data. Caliber stores its own findings.

---

## 6. Data Boundary

**What Rondo produces for Caliber:**

| Output | Format | Consumer |
|--------|--------|----------|
| TaskResult per task | Python dataclass / JSON | Caliber finding merge |
| DispatchUsage per task | Python dataclass / JSON | Caliber cost tracking |
| Raw AI output | String in TaskResult.raw_output | Caliber for debugging |

**What Rondo consumes from Caliber:**

| Input | Format | Producer |
|-------|--------|----------|
| Task objects | Python dataclass / JSON | Caliber dispatch logic |
| Model hints | String in Task.model | Caliber task-type routing |

---

## 7. MCP / API Interface

Not applicable for initial release. Future: Caliber MAY invoke Rondo via MCP tool
calls per CORE-IFS-005, enabling on-demand dispatch from any MCP-capable client.
The MCP tool would accept the same Task JSON and return the same TaskResult JSON.

---

## 8. States & Modes

Rondo operates in the same mode regardless of whether the caller is Caliber or another consumer.

| Mode | Trigger | Behavior |
|------|---------|----------|
| Standalone | No `.ob/config.toml` | Accepts Task, dispatches, returns TaskResult |
| OB-connected | `.ob/config.toml` present | Same as standalone + OAPayload/OAResult wrapping |

Caliber tasks flow through whichever mode is active. Caliber does not control mode.

---

## 9. Configuration

No Caliber-specific configuration exists in Rondo. Caliber tasks use the same
provider routing, budget limits, and timeout settings as any other dispatch.
Caliber-side config (which models for which review type) is in Caliber's own config.

---

## 10. Rules & Constraints

1. Rondo treats Caliber like any other consumer — no special handling
2. Task format is standard Rondo Task — Caliber-specific semantics are in the instruction text
3. Rondo never interprets finding severity — that's Caliber's job
4. Rondo never merges multi-AI results — that's Caliber's job (Caliber-IFS-103 reqs 29-31)

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Latency | <2s overhead beyond AI response time | Rondo adds dispatch overhead, not AI latency |
| Throughput | Parallel dispatch when workers > 1 | Caliber sends multi-AI reviews concurrently |
| Reliability | Partial results on timeout, never silent failure | Caliber needs data even on partial success |
| Cost transparency | DispatchUsage on every result | Caliber tracks cost per review cycle |

---

## 12. Shared Patterns

- **3-field contract (Do, Read, Done):** Every Caliber task maps to Task.instruction (Do),
  Task.context_files (Read), Task.done_when (Done). Same pattern as all Rondo tasks.
- **COALESCE for model selection:** Task.model → routing table → provider default.
  Caliber sets Task.model; if empty, Rondo's routing table decides.
- **Error envelope:** All errors wrapped in TaskResult with status="error" and
  error_message field. Never raw exceptions across the boundary.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Caliber → Rondo | Caliber-IFS-103 | Inbound | Task objects |
| Rondo → AI providers | IFS-100, REQ-109 | Outbound | Provider adapter interface |
| Rondo → OB (if connected) | IFS-102 | Outbound | OAResult wrapping |
| Rondo ← config | STD-109 | Internal | TOML / COALESCE |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-010 (Error Resilience) | Task failure returns error TaskResult, never crashes Rondo |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Dispatch events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool interface for on-demand dispatch |
| STD-108 (Error Handling) | Error codes and structured error responses |
| STD-113 (Audit Trail) | Every Caliber dispatch recorded in audit log |

---

## 15. Self-Correction

- If Caliber sends a task with an unknown model name, Rondo returns an error result
  with suggested valid model names from the routing table.
- If repeated Caliber tasks fail on the same model, trend alerting (REQ-106) flags
  the model as degrading. Caliber can read this from the morning report.
- Cost overruns on Caliber-initiated tasks are tracked per-provider and surfaced in
  budget alerts (REQ-105) so Caliber review cycles don't silently drain funds.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Caliber sends well-formed Task objects | Rondo returns error TaskResult with validation details |
| A2 | Caliber handles its own finding deduplication | Duplicate findings from parallel AI may reach Caliber |
| A3 | Task.model is a valid Rondo provider/model name | Rondo returns error with supported model list |
| A4 | Caliber manages its own retry logic | Rondo does not retry failed Caliber tasks automatically |

---

## 17. Success Criteria

| Scenario | Expected Result | Verification |
|----------|----------------|-------------|
| Caliber sends review task | Rondo dispatches to AI, returns findings | Test |
| Caliber sends fix task | Rondo dispatches, returns fixed code | Test |
| Caliber sends contradiction check | Rondo dispatches, returns conflicts list | Test |
| Caliber sends 2 parallel review tasks | Both execute, both return results | Test |
| AI model unavailable | Rondo returns error with clear message | Test |
| Caliber not installed | Rondo works normally for other consumers | Test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Implementation effort | Low — Caliber uses existing Rondo Task/TaskResult, no new code |
| Test effort | Medium — need Caliber-shaped test fixtures for review/fix/contradiction |
| Integration test | Requires Caliber test harness to send realistic tasks |
| Risk | Low — Rondo is already generic; Caliber is just another caller |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Task validation, result formatting | 8 |
| Integration | Caliber → Rondo → mock AI → result | 6 |
| Contract | TaskResult matches Caliber Finding schema | 4 |
| Error | Malformed tasks, timeouts, budget exceeded | 6 |
| Parallel | Multi-AI concurrent dispatch | 3 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| AI timeout on review task | Caliber gets partial/no findings | Return partial results if available |
| Model unavailable | Caliber review cycle blocked | Fallback provider per REQ-109 |
| Budget exceeded mid-batch | Remaining Caliber tasks skipped | Return status="skipped" with budget info |
| Malformed finding JSON from AI | Caliber can't parse results | Raw output preserved for manual inspection |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework |
| STD-108 | Error handling patterns |
| IFS-100 | Claude CLI interface (how Rondo calls AI) |

| Used By | Why |
|---------|-----|
| Caliber-IFS-103 | Caliber's side of this integration |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | No Caliber-specific code in Rondo | 2026-03-19 | Rondo is generic. Caliber is just a consumer. |
| D2 | Python API primary, CLI fallback | 2026-03-19 | Matches Caliber-IFS-004 transport choice | <!-- REF: Caliber-IFS-004 not found — planned spec, not yet created -->
| D3 | Rondo doesn't merge multi-AI | 2026-03-19 | Merging is a quality decision, not a dispatch decision. Caliber owns quality. |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should Rondo validate that parsed_result.findings[] matches Caliber's schema? | Contract enforcement vs simplicity | OPEN |
| Q2 | Should Rondo expose a streaming interface for long-running Caliber reviews? | Caliber could show progress during multi-minute reviews | OPEN |
| Q3 | Will Caliber need batch task submission (send 10 review tasks at once)? | Affects queueing design | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Finding** | A quality issue discovered by AI review — file, line, severity, message |
| **Contradiction** | Two rules that logically conflict — both cannot be true |
| **Forward review** | Read code top-down, check if logic is correct |
| **Reverse review** | Read code bottom-up, check if assumptions are guarded |
| **Sideways review** | Compare code against conventions and peer files |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AI produces unparseable findings | Medium | Caliber can't use results | Raw output always preserved; Caliber can re-parse |
| Cost overrun on large review batches | Low | Budget alerts fire late | Pre-dispatch budget check (req 28) |
| Caliber-Rondo contract drift | Low | Silent data loss | NAMING-MAP.md as shared authority |

---

## 26. External Scan

No external products were found that formalize AI-dispatch-to-quality-tool contracts.
Caliber-Rondo integration is custom. Closest analogy: CI/CD systems dispatching to
linters/scanners, where the runner (Rondo) is generic and the tool (Caliber) owns semantics.

---

## 27. Security Considerations

- Caliber tasks may contain source code in context_files. Rondo transmits this to AI
  providers. API keys must be secured per REQ-109 (Keychain only).
- No Caliber credentials flow through Rondo. Caliber authenticates to Rondo via standard
  Python import or CLI invocation — no separate auth layer needed for local usage.
- HTTPS transport (future) requires mTLS per CORE-STD-005 rule 16.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Dispatch overhead | <500ms per task | Rondo adds prompt assembly + subprocess launch |
| Memory | <100MB per worker | Task objects are small; AI responses are streamed |
| Parallel capacity | Up to `workers` concurrent dispatches | Config-controlled, default 4 |
| Disk | Minimal — audit log only | No Caliber-specific persistence in Rondo |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not yet populated. Will be filled during first build sprint that implements this contract.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- This spec intentionally has zero Caliber-specific code paths in Rondo. If a future
  requirement needs Caliber-aware behavior, it should go through a plugin/hook mechanism
  rather than hardcoding Caliber references.
- Session 80 originally created this spec with 28 requirements. Session 84 added
  sections 2, 4-9, 11-16, 18-34 to reach 35-section compliance.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Caliber-to-Rondo contract | THEORY | Specced for AI review task submission | Phase 2 build |
| Review result format | THEORY | Specced for structured review output | Phase 2 build |
| Fix suggestion format | THEORY | Specced for actionable code fixes | Phase 2 build |
| Multi-directional review protocol | THEORY | Forward/reverse/sideways review specced | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-19 | Initial spec. 28 requirements. Fixes SPR-021, SPR-028. Session 80. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
