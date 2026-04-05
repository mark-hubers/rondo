# Rondo A+ Improvement Plan

**Date:** 2026-04-05 | **Session:** 98
**Source:** 3-provider AI body review (Gemini 2.5 Flash + Grok-3 + Mistral Large)
**Status:** DRAFT — awaiting Cursor review before building

---

## Current Grades (AI Body Review Consensus)

| # | Area | Grade | Target |
|---|------|-------|--------|
| 1 | Code Architecture | A- | A+ |
| 2 | Test Quality | B+ | A+ |
| 3 | Error Handling | C | A |
| 4 | Security | C- | A |
| 5 | Configuration | B | A+ |
| 6 | Documentation | B- | A |
| 7 | Observability | B | A |
| 8 | API Design | C+ | A |
| 9 | Operational Readiness | A- | A+ |
| 10 | Process Maturity | A- | A+ |

---

## FIX-1: Structured Error Payloads (Error Handling C → A)

**Problem:** Errors lose context through the dispatch→runner→overnight→report chain. User-facing messages are inconsistent — sometimes raw stack traces, sometimes generic "error". No recovery guidance. The FIX-663 bug (0 errors when tasks fail) was a symptom of this.

**What all 3 reviewers said:**
- Gemini: "Cannot differentiate transient vs permanent failures"
- Grok: "Absence of centralized error aggregator"
- Mistral: "Enforce structured error payloads with recovery paths"

**Proposed approach:**

1. Define `ErrorPayload` dataclass in engine.py:
```python
@dataclass
class ErrorPayload:
    code: str           # ERR_SUBPROCESS, ERR_AUTH, etc.
    message: str        # Human-readable explanation
    context: dict       # {provider, model, task_name, ...}
    recovery: str       # "Run rondo preflight" or "Check API key"
    transient: bool     # True = worth retrying
    layer: str          # "dispatch", "runner", "overnight", "report"
```

2. Every error path in dispatch.py, runner.py, overnight.py creates an ErrorPayload
3. The report chain preserves the full payload — no more "0 errors" when tasks fail
4. TaskResult.error_payload replaces the flat error_code + error_message fields
5. Morning report renders recovery suggestions from the payload
6. Notification messages include recovery guidance

**Files changed:** engine.py, dispatch.py, dispatch_parse.py, runner.py, overnight.py, report.py, notify.py, + tests
**Risk:** Breaking change to TaskResult shape. All consumers need updating.
**Spec impact:** New req in REQ-100 (error payload contract), update STD-108 (error handling standard)
**Estimated sprints:** 2-3

**Questions for Cursor:**
- Is ErrorPayload the right shape? Should `context` be typed more strictly?
- Should we keep backward compat (old error_code field) or clean break?
- Are there error paths we're missing that need payloads?

---

## FIX-2: Security Hardening (Security C- → A)

**Problem:** Subprocess execution uses basic safety (list args, no shell=True, stdin piping) but lacks defense-in-depth. Key management has EnvBackend which could leak in logs. Config files aren't permission-checked on all platforms.

**What all 3 reviewers said:**
- Gemini: "Piecemeal sanitization approach — no centralized input validation"
- Grok: "EnvBackend exposes keys in debug logs, no rotation policy"
- Mistral: "Replace raw subprocess with hardened wrapper"

**Proposed approach:**

1. **Subprocess hardening** — `_run_subprocess()` in dispatch.py already:
   - Uses list args (not shell=True) ✓
   - Pipes prompt via stdin (not CLI arg, ARG_MAX safe) ✓
   - Has SIGTERM-first kill sequence ✓
   - Strips CLAUDECODE env var ✓
   
   What's missing:
   - Output validation: verify subprocess output matches expected schema before parsing
   - Timeout enforcement: already exists (watchdog) but should also limit output size
   - Resource limits: `ulimit` or `resource` module caps on child process

2. **Key management hardening:**
   - EnvBackend: filter `RONDO_*` and `*_API_KEY` from debug/error logs
   - Add log scrubbing function to sanitize.py
   - KeychainBackend already good (macOS Keychain)
   - Config: enforce file permissions (0600) on `~/.rondo/config.toml` — already done in FIX-656 req 090

3. **Pre-commit protection:**
   - Add `.env` pattern to `.gitignore` (if not already)
   - Convention test: no hardcoded API keys in source

**Files changed:** dispatch.py (subprocess wrapper), sanitize.py (log scrubbing), config.py (permission check), + tests
**Risk:** Resource limits could break legitimate long-running dispatches.
**Spec impact:** Update REQ-100 (subprocess safety), update STD-108 (security rules)
**Estimated sprints:** 2

**Questions for Cursor:**
- Is output size limiting needed? claude -p output can be large for legitimate reasons.
- Should we sandbox with firejail/nsjail? (Probably overkill for single-user local tool.)
- Are there any actual CVEs in the current subprocess pattern?

---

## FIX-3: API Consistency + MCP Versioning (API Design C+ → A)

**Problem:** 22 MCP tools + 15 CLI commands create cognitive overload. No versioning strategy for MCP tools — adding/changing tools could break Claude Code integrations.

**What all 3 reviewers said:**
- Grok: "No unified schema or versioning strategy for MCP tools"
- Mistral: "Surface area too broad — consolidate CLI commands"
- Gemini: "Missing external-facing API reference"

**Proposed approach:**

1. **MCP tool versioning:**
   - Add `version` field to each MCP tool's return schema
   - Define stability levels: `stable`, `beta`, `experimental`
   - Document in ai_help_data.json which tools are which

2. **CLI consolidation review:**
   - Audit which CLI commands are actually used (check shell history)
   - Identify overlap (e.g., `rondo metrics` vs `rondo audit --cost`)
   - Don't remove — deprecate with clear migration paths

3. **API consistency:**
   - All MCP tools should return `{status, data, error}` shape
   - All CLI commands should support `--json` flag
   - Unified error codes across MCP and CLI

**Files changed:** mcp_server.py, mcp_tools.py, mcp_dispatch.py, mcp_compose.py, ai_help_data.json
**Risk:** Changing MCP tool return shapes could break existing Claude Code usage.
**Spec impact:** New STD (API stability contract), update IFS-104 (MCP server)
**Estimated sprints:** 2

**Questions for Cursor:**
- How aggressive should CLI consolidation be? Mark uses all 15 commands.
- Is semantic versioning (semver) the right model for MCP tools?
- Should deprecated tools still appear in ai_help or be hidden?

---

## FIX-4: Property-Based Testing (Test Quality B+ → A)

**Problem:** 1,376 tests with 0 failures, but no property-based testing, no mutation testing, no fuzzing. Edge cases are manually identified.

**What all 3 reviewers said:**
- Grok: "No mutation testing or explicit edge case coverage"
- Mistral: "No hypothesis for fuzzing adapters"
- Gemini: "Test rigor needs to move beyond volume"

**Proposed approach:**

1. **Add hypothesis to test dependencies:**
   - Property tests for: adapter input parsing, config validation, engine state transitions
   - Fuzz: malformed JSON responses, oversized payloads, unicode edge cases

2. **Mutation testing (mutmut):**
   - Run on core modules (engine.py, dispatch_parse.py, config.py)
   - Target: >90% mutation kill rate
   - Add to nightly build (too slow for regular builds)

3. **Flaky test detection improvement:**
   - Rondo already has FlakyEngine — but it's for dispatch results, not pytest
   - Add `pytest-rerunfailures` for CI detection
   - Feed flaky pytest results into the same FlakyEngine

**Files changed:** pyproject.toml (deps), new test files, nightly build config
**Risk:** hypothesis tests can be slow — need timeout limits.
**Spec impact:** Update VER-001 (test strategy)
**Estimated sprints:** 1-2

**Questions for Cursor:**
- Which modules benefit most from property testing?
- Is mutmut worth the CI time for a single-user project?
- Are there specific adapter edge cases that need fuzzing?

---

## FIX-5: Real-Time Alerting (Observability B → A)

**Problem:** Observability is passive — morning reports, JSONL logs, on-demand metrics. No real-time alerting when things go wrong during overnight runs.

**What all 3 reviewers said:**
- Gemini: "Lack of real-time, threshold-based alerting"
- Grok: "No anomaly detection for metric thresholds"
- Mistral: "Morning reports lack actionable RCA hooks"

**Proposed approach:**

1. **Threshold alerting in notify.py:**
   - Already has `notify_budget_threshold()` (50%, 75%, 90%)
   - Add: latency threshold (task takes >2x average)
   - Add: error rate threshold (>50% failures in a phase)
   - Add: cost spike (>3x average cost per task)

2. **RCA hooks in morning report:**
   - When errors occur, correlate with: recent code changes (git log), provider status, config changes
   - Add "Probable Cause" column to action items

3. **No Prometheus/Grafana** — overkill for single-user. The notification channels (terminal, file, macOS) are sufficient with smarter triggers.

**Files changed:** notify.py, report.py, overnight.py, metrics.py
**Risk:** False positive alerts could create noise. Thresholds need tuning.
**Spec impact:** New reqs in REQ-105 (notification triggers), update REQ-101 (morning report)
**Estimated sprints:** 1

**Questions for Cursor:**
- Are the threshold values right? (2x latency, 50% error rate, 3x cost)
- Should alerts be configurable per-provider?
- Is git log correlation for RCA hooks worth the complexity?

---

## FIX-6: Documentation Cookbook (Documentation B- → A)

**Problem:** Docs are comprehensive for specs but lack real-world usage scenarios. Golden-path covers the happy path only.

**What all 3 reviewers said:**
- Grok: "Lacks real-world usage examples beyond golden path"
- Gemini: "Missing external-facing API reference"
- Mistral: "Static diagrams don't scale for onboarding"

**Proposed approach:**

1. **Cookbook section** (docs/COOKBOOK.md):
   - Provider-specific scenarios (Gemini review, Ollama batch, multi-provider consensus)
   - Failure recovery (what to do when provider is DOWN, rate limited, auth fails)
   - Integration patterns (overnight + spool + morning report end-to-end)
   - Cost optimization (which provider for which task type)

2. **Auto-generated API docs:**
   - Use pdoc3 or mkdocstrings to generate from docstrings
   - Publish to `docs/api/` as markdown (not a web server)
   - Add to nightly build to prevent doc rot

3. **Runnable examples:**
   - `examples/` already has round files — add more with comments
   - Each example should be independently runnable with `--dry-run`

**Files changed:** docs/COOKBOOK.md (new), examples/ (expand), pyproject.toml (pdoc dep)
**Risk:** Doc maintenance burden. Solution: convention test that examples are parseable.
**Spec impact:** Update SOP-100 (spec onboarding)
**Estimated sprints:** 1

**Questions for Cursor:**
- Is auto-generated API docs worth maintaining for a single-user tool?
- Which provider scenarios are most valuable?
- Should the cookbook be one file or split by topic?

---

## FIX-7: Architecture Formalization (Architecture A- → A+)

**Problem:** Import layering is enforced but architecture isn't formally defined. No Protocol interfaces between layers.

**What all 3 reviewers said:**
- Gemini: "No explicit architectural style documented"
- Grok: "Implicit coupling via shared data models"
- Mistral: "Factory pattern violates Open/Closed — no plugin system"

**Proposed approach:**

1. **Protocol interfaces:**
   - `ProviderAdapter(Protocol)` — already partially exists, formalize with `@runtime_checkable`
   - `DispatchTarget(Protocol)` — interface between runner and dispatch
   - Add `isinstance` checks in factory for type safety

2. **Architecture diagram in RONDO-REFERENCE.md:**
   - Already exists! But add: formal layer names, dependency arrows, Protocol boundaries
   - Convention test: verify diagram layer names match actual import rules

3. **Plugin system (deferred):**
   - `entry_points` for third-party adapters is elegant but premature
   - Mark is the only user. When a second user arrives, add it.

**Files changed:** adapters/__init__.py (Protocol), providers.py (type checks), RONDO-REFERENCE.md
**Risk:** Over-engineering for a single-user tool. Keep it simple.
**Spec impact:** Update REQ-109 (adapter contract)
**Estimated sprints:** 1

**Questions for Cursor:**
- Is `@runtime_checkable Protocol` worth the complexity or just ABC?
- Should we enforce the adapter interface in the factory or trust convention tests?
- Is a plugin system premature or future-proofing?

---

## Cursor Review (2026-04-05)

Cursor reviewed all 7 FIX items + answered the 6 meta-questions. Key corrections:

### Grade Corrections
- **Error Handling C → B-** post-FIX-663 (skipped status tracking fixed the worst symptom)
- **Security C-** is plausible for local/trusted-user context — don't inflate to A with log scrubbing alone
- **Operational Readiness A-** is generous unless deploy/runbook exists — B+ without
- **Test Quality B+** may be under-rated — 1,376 tests with TDD discipline is solid

### Missing Gaps (3 reviewers missed)
- **Agent ergonomics:** `rondo_review_file` path-native MCP tool — bigger felt win than tool semver
- **Health semantics:** `rondo_health` should split `api_healthy` vs `run_quality` — two fields, large perceived gain
- **Round files as code execution:** Security must address untrusted rounds if ever shared
- **Cross-session UX:** dry_run prompt truncation vs real dispatch — document or fix
- **macOS-first honesty:** If not cross-platform, say so — avoids false "ops A" claims

### Approach Corrections
- **FIX-1:** Additive migration (ErrorPayload alongside old fields), not big-bang TaskResult replacement
- **FIX-2:** Lead with documented threat model. Subprocess is not the main risk — round files are.
- **FIX-3:** Stability labels + server version BEFORE unified `{status,data,error}` everywhere
- **FIX-4:** Hypothesis yes, mutmut optional nightly. Cap test runtime with `--hypothesis-profile`.
- **FIX-5:** Thresholds need min sample size + hysteresis. Git RCA deferred.
- **FIX-6:** Cookbook > pdoc for solo. Runnable examples highest leverage.
- **FIX-7:** Don't duplicate ABC with Protocol — pick one, delete the other.

### Scope: A vs A+
**A (credible, maintainable):** Structured errors where users look (report, MCP JSON), key/log hygiene, cookbook, MCP stability labels, hypothesis on parsers.

**A+ (portfolio/OSS bar):** Full TaskResult migration, unified API envelope, mutation testing, rich alerting, plugins, full cross-platform — pick two, not all.

---

## MASTER BUILD LIST — Post-Cursor (Final)

**Reordered per Cursor recommendation: cheap wins first, breaking changes last.**

### Phase 1: Quick Wins (1 session, ~3 sprints)

| Sprint | What | Impact |
|--------|------|--------|
| FIX-670 | **Cookbook + Runnable Examples** — "RED but providers green" scenario, multi-provider review, auth failure recovery, cost optimization | Docs B- → A |
| FIX-671 | **Health Semantics Split** — `rondo_health` returns `api_healthy` + `run_quality` separately. Convention test: MCP tool count + CLI command count matches reference doc. | API C+ → B+, doc rot prevention |
| FIX-672 | **Agent Path Tool** — `rondo_review_file` accepts file path natively (not just inline prompt) | Agent UX improvement |

### Phase 2: Error + Security Foundation (1-2 sessions, ~4 sprints)

| Sprint | What | Impact |
|--------|------|--------|
| FIX-673 | **Threat Model Doc** — document what Rondo trusts (round files, config, Claude binary), what it doesn't (AI output, provider responses), macOS-first disclosure | Security C- → B |
| FIX-674 | **Error Payloads (report + notify only)** — ErrorPayload dataclass, additive on TaskResult (`error_payload: ErrorPayload | None`), morning report renders recovery suggestions. Legacy fields preserved. | Error Handling B- → A- |
| FIX-675 | **Key/Log Hygiene** — scrub `*_API_KEY` from error messages + debug logs, enforce chmod 600 on TOML, convention test for no hardcoded keys in source | Security B → A- |
| FIX-676 | **MCP Stability Labels** — each tool tagged `stable`/`beta`/`experimental` in ai_help_data.json, server version in `rondo_dispatch_info`, deprecated tools shown with replacement | API B+ → A |

### Phase 3: Depth (1-2 sessions, ~3 sprints)

| Sprint | What | Impact |
|--------|------|--------|
| FIX-677 | **Property-Based Testing** — hypothesis for dispatch_parse, config validation, parse_model, adapter response mapping. `--hypothesis-profile` for CI timeout. | Tests B+ → A |
| FIX-678 | **Threshold Alerting** — latency/error-rate/cost thresholds in notify.py with min sample size + hysteresis. Per-provider for cost/latency. No git RCA. | Observability B → A- |
| FIX-679 | **Architecture: Protocol or ABC** — pick one (ABC, already exists), delete the other path, formalize adapter contract in REQ-109 | Architecture A- → A |

### Deferred (A+ only, not needed for A)

| Item | Why defer |
|------|----------|
| Full TaskResult migration (remove legacy fields) | Breaking change, needs versioned release |
| Unified `{status, data, error}` MCP envelope | Same risk as above — do after stability labels prove out |
| Mutation testing (mutmut) | CI cost >> benefit for solo dev |
| Plugin system (entry_points) | Premature — no second user |
| Real-time Grafana dashboard | Overkill for single-user |
| Cross-platform (Windows/Linux) | macOS-first is honest |

---

## Target Grades After All 3 Phases

| Area | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|------|---------|--------------|---------------|---------------|
| Architecture | A- | A- | A- | **A** |
| Test Quality | B+ | B+ | B+ | **A** |
| Error Handling | B- | B- | **A-** | A- |
| Security | C- | C- | **A-** | A- |
| Configuration | B | B | B+ | B+ |
| Documentation | B- | **A** | A | A |
| Observability | B | B | B+ | **A-** |
| API Design | C+ | **B+** | B+ | **A** |
| Operational Readiness | A- | A- | A- | A- |
| Process Maturity | A- | A- | A- | A- |

**Honest final grade: A across 7 of 10, A- on the remaining 3.**
**That's an A. Not A+, but a real, defensible A.**

---

*Original AI body review (Gemini + Grok + Mistral) above. Cursor review merged 2026-04-05.*
