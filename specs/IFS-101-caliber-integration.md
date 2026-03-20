# IFS-101: Caliber Integration Contract

*How Rondo receives and executes tasks from Caliber — AI review, AI fix, rule contradiction checks.*

**Created:** 2026-03-19 | **Status:** DESIGNED
**Classification:** open
**Clearance:** not-cleared
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-108 (Error Handling)
**Connects to:** Caliber-IFS-103 (Caliber's side of this integration)
**References:** NAMING-MAP.md, INTEGRATION-ARCHITECTURE.md

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

---

## 3. Requirements

### Task Types Accepted from Caliber

1. **Review tasks** — Caliber sends code + rules, Rondo dispatches to AI reviewer
   - Forward review: "Does this code work? Read top-down."
   - Reverse review: "Walk bottom-up. Are assumptions guarded?"
   - Sideways review: "Compare against conventions and other files."
2. **Fix tasks** — Caliber sends finding + code, Rondo dispatches to AI fixer
   - Instruction: "Fix this specific issue: {finding.message}"
   - Context: file content + rules that were violated
   - done_when: "Fixed code passes the check that found the issue"
3. **Contradiction check tasks** — Caliber sends full ruleset, Rondo dispatches to AI analyzer
   - Instruction: "Find logical contradictions between these rules"
   - done_when: "Zero contradictions found OR conflicts documented"

### Task Input Format

4. Rondo accepts Caliber tasks as standard Rondo Task objects — no special format
5. Task.instruction contains Caliber's prompt (review question, fix instruction, or contradiction query)
6. Task.context_files contains the code and rules to review/fix
7. Task.done_when contains Caliber's success criteria
8. Task.model hints which AI to use (Caliber decides based on task type)

### Result Format Returned

9. Rondo returns standard TaskResult to Caliber:
   - `status`: done/partial/error
   - `parsed_result`: JSON with findings array (file, line, severity, message, reviewer)
   - `raw_output`: full AI response
   - `duration_sec`: wall clock
10. For review tasks: `parsed_result.findings[]` matches Caliber's Finding format
11. For fix tasks: `parsed_result.fixed_code` contains the corrected code
12. For contradiction tasks: `parsed_result.contradictions[]` lists conflicting rule pairs
13. DispatchUsage attached: model, tokens_in, tokens_out, cost_usd, duration_ms

### Multi-AI Dispatch

14. Caliber requests specific models per task type via Task.model field
15. Rondo dispatches to whatever model Caliber requests — no overriding
16. Parallel dispatch: if Caliber sends 2 review tasks (Claude reverse + Gemini forward), Rondo can run both in parallel when workers > 1
17. Rondo returns separate TaskResult per AI — Caliber handles merging

### Transport

18. **Python API (primary):** Caliber imports Rondo client — `from rondo import run_round`
19. **CLI fallback:** `rondo run task.json` for when Caliber can't import directly
20. Same transport as any other Rondo consumer — no Caliber-specific protocol

### Standalone Behavior

21. Rondo works without Caliber — it's a general dispatch framework
22. Nothing in Rondo's code references Caliber specifically
23. Caliber is just another consumer that sends Task objects and reads TaskResults
24. If Caliber is not installed, Rondo doesn't know or care

### Error Handling

25. Caliber sends malformed task → Rondo returns TaskResult with status="error", error_message explains what's wrong
26. AI model unavailable → Rondo returns status="error" with model name and reason
27. AI timeout → Rondo respects task timeout, returns partial results if available
28. Cost budget exceeded → Rondo checks budget before dispatch, returns status="skipped" if over budget

---

## 10. Rules & Constraints

1. Rondo treats Caliber like any other consumer — no special handling
2. Task format is standard Rondo Task — Caliber-specific semantics are in the instruction text
3. Rondo never interprets finding severity — that's Caliber's job
4. Rondo never merges multi-AI results — that's Caliber's job (Caliber-IFS-103 reqs 29-31)

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
| D2 | Python API primary, CLI fallback | 2026-03-19 | Matches Caliber-IFS-004 transport choice |
| D3 | Rondo doesn't merge multi-AI | 2026-03-19 | Merging is a quality decision, not a dispatch decision. Caliber owns quality. |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-19 | Initial spec. 28 requirements. Fixes SPR-021, SPR-028. Session 80. |
