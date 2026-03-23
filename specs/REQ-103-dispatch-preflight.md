# REQ-103: Dispatch Preflight

*Verify the dispatch environment before wasting API tokens. Claude installed? Key valid? Rate limit OK?*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-102 (Configuration), CORE-STD-010 (Error Resilience) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-113 (Preflight System) — adapted from session preflight to dispatch preflight
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:** Before Rondo dispatches any task to Claude Code, verify the environment can succeed. Is Claude Code installed? Is the API key valid? Is the rate limit in a good state? Is there enough disk space for worktrees? A failed preflight saves minutes of wasted dispatch time and dollars of wasted API tokens.

**IN scope:**
- Pre-dispatch environment checks
- Claude Code availability and version
- API key / auth validation
- Rate limit status check
- Disk space for worktrees
- Health status (GREEN/YELLOW/RED)
- Overnight batch pre-checks

**OUT of scope:**
- Task validation (CORE-STD-010 pre-dispatch validation)
- Model routing logic (REQ-100)
- Overnight scheduling (REQ-101)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo dispatches tasks to AI providers that cost money and take time. A dispatch that fails
because Claude isn't installed, the API key is expired, or the rate limit is exhausted wastes
both. Worse, overnight batch runs can burn through dozens of failed dispatches before anyone
notices. Preflight catches these failures before the first dollar is spent.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Preflight runs automatically before every `rondo run` command | MUST | Auto test |
| 002 | Preflight completes in <3 seconds | MUST | Performance test |
| 003 | Check: `claude` binary on PATH and executable | MUST | Binary test |
| 004 | Check: Claude Code version matches known-compatible versions (IFS-100 assumption A1) | SHOULD | Version test |
| 005 | Check: API key or Max plan auth available (per auth mode in config) | MUST | Auth test |
| 006 | Check: rate limit status — if `blocked`, abort with "Rate limited. Resets at: {time}" | MUST | Rate test |
| 007 | Check: if `isUsingOverage`, warn "Using overage capacity — costs may be higher" | SHOULD | Overage test |
| 008 | Check: disk space > 500MB free (worktrees need space) | SHOULD | Disk test |
| 009 | Check: git available (worktree operations need it) | SHOULD | Git test |
| 010 | Check: CLAUDECODE env var not set (prevents nested session error — ERR_NESTED_SESSION) | MUST | Env test |
| 011 | Check: config file exists and parses | MUST | Config test |
| 012 | Report health as GREEN (go), YELLOW (proceed with warnings), RED (abort) | MUST | Status test |
| 013 | RED status: abort with clear message and recovery steps | MUST | Abort test |
| 014 | For overnight batch: run preflight ONCE at start, not per-task. Cache result for batch duration. | SHOULD | Batch test |
| 015 | `rondo preflight` standalone command: check without dispatching | SHOULD | Standalone test |
| 016 | Preflight result included in OAResult metadata when OB-connected | SHOULD | Integration test |


### CLI Version Compatibility (F-28 — Architecture Audit Session 85)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 017 | Preflight MUST check that Claude Code CLI supports ALL flags used by Rondo dispatch: `--output-format stream-json`, `--model`, `--tools`, `--dangerously-skip-permissions`, `-p` | MUST | Flag test |
| 018 | Preflight MUST run a lightweight smoke test dispatch (`claude -p "test" --output-format stream-json`) and verify the output format matches expected JSON structure | MUST | Smoke test |
| 019 | Smoke test result (output format, flag support, response time) MUST be cached for batch duration — not re-run per task | SHOULD | Cache test |
| 020 | When Claude Code version changes (detected via `claude --version`), cached preflight results MUST be invalidated and smoke test re-run | MUST | Version change test |
| 021 | Preflight MUST maintain a version compatibility matrix: `{claude_version: {flags_tested: [...], last_tested: timestamp, result: pass/fail}}` | SHOULD | Matrix test |
| 022 | If smoke test detects changed output format (e.g., stream-json schema changed), preflight MUST return RED with "CLI output format changed — Rondo adapter update required" | MUST | Format change test |
| 023 | `CLAUDECODE` env var stripping (req 010) MUST be verified by smoke test — not just checked for presence but confirmed that the stripped subprocess does not trigger ERR_NESTED_SESSION | MUST | Nesting verify test |
| 024 | Preflight MUST log the Claude Code version, tested flags, and smoke test result to enable debugging when overnight runs fail silently | MUST | Debug log test |


---

## 4. Architecture / Design

### Check Order

```
1. Config parse        (~1ms)   → RED if invalid
2. Claude binary       (~10ms)  → RED if missing
3. CLAUDECODE env var  (~1ms)   → RED if set (nesting trap)
4. API key present     (~1ms)   → RED if missing
5. Claude version      (~50ms)  → YELLOW if unknown version
6. Rate limit status   (~100ms) → RED if blocked, YELLOW if overage
7. Git available       (~10ms)  → YELLOW if missing (no worktrees)
8. Disk space          (~10ms)  → YELLOW if low
                       --------
                       <200ms typical
```

### Rate Limit Check

```python
def check_rate_limit() -> PrefllightResult:
    """Quick rate limit probe without burning a dispatch."""
    # Use cached rate_limit_event from last dispatch if <5min old
    # Otherwise: lightweight claude -p "hi" --output-format stream-json
    # Parse rate_limit_event from stream
    if status == "blocked":
        return RED(f"Rate limited. Resets at: {resets_at}")
    if is_using_overage:
        return YELLOW("Using overage capacity")
    return GREEN()
```

### Preflight Result Object

```python
@dataclass
class PreflightResult:
    status: str           # GREEN / YELLOW / RED
    checks: list[Check]   # Individual check results
    summary: str          # Human-readable one-liner
    cached: bool          # True if reusing batch-cached result
```

---

## 5. Data Model

Preflight results are ephemeral — not persisted to a database. When OB-connected,
the preflight summary is included in OAResult metadata. The audit trail (STD-113)
records preflight status as part of the dispatch event.

| Field | Type | Purpose |
|-------|------|---------|
| `status` | str | GREEN/YELLOW/RED |
| `checks[]` | list | Individual check name + result + message |
| `duration_ms` | int | Total preflight time |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| PreflightResult | Python dataclass | Dispatch engine (go/no-go) |
| Preflight summary | String | OAResult metadata (when OB-connected) |
| Preflight status line | Terminal output | `rondo preflight` CLI |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Config file | TOML | `.rondo/config.toml` |
| Claude binary | Filesystem | `which claude` |
| Rate limit cache | JSON | Last dispatch result |
| Disk space | OS API | `shutil.disk_usage()` |

---

## 7. MCP / API Interface

Not applicable for initial release. Future: an MCP tool per CORE-IFS-005 could expose
preflight status so AI agents can check environment health before requesting dispatch.

---

## 8. States & Modes

**Directionality:** Forward-only per evaluation — GREEN → YELLOW → RED. Each preflight starts fresh (no persistent state).

| State | Meaning | Action |
|-------|---------|--------|
| **GREEN** | All checks pass | Dispatch proceeds |
| **YELLOW** | Warnings present, but dispatchable | Dispatch proceeds with warnings logged |
| **RED** | Critical failure | Dispatch aborted with recovery instructions |

Transitions: Every preflight starts fresh. No persistent state between preflights.
Batch mode caches a GREEN/YELLOW result for the batch duration.

---

## 9. Configuration

Preflight behavior is configured in `.rondo/config.toml`:

```toml
[preflight]
auto_run = true                   # Run before every dispatch
cache_duration_sec = 300          # Cache result for 5 min in batch mode
disk_min_mb = 500                 # Minimum free disk space
compatible_versions = ["1.0.*"]   # Known-good Claude Code versions
```

---

## 10. Rules & Constraints

1. **Fast.** <3 seconds. If a check is slow, cache it. Violation ID: `REQ103-FAST`
2. **Actionable.** Every RED/YELLOW tells you what to do. "Claude not found. Install: brew install claude" not "Preflight failed." Violation ID: `REQ103-ACTIONABLE`
3. **Don't burn tokens.** Rate limit check should use cached data when possible, not a fresh API call. Violation ID: `REQ103-NO-WASTE`
4. **Nested session trap.** CLAUDECODE env var detection is CRITICAL — Session 78 lesson: hung subprocess for 2 minutes. Violation ID: `REQ103-NESTING`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Speed | <200ms typical, <3s worst case | Must not add noticeable delay to dispatch |
| Reliability | No false REDs — preflight must not block valid dispatches | False RED = wasted opportunity |
| Actionability | Every failure includes recovery steps | Mark shouldn't have to guess what to fix |
| Cacheability | Batch mode reuses result for 5 minutes | Don't re-check 50 times in overnight batch |

---

## 12. Shared Patterns

- **Traffic light status:** GREEN/YELLOW/RED is the same pattern used in OB-REQ-113
  (session preflight) and Rondo provider health (REQ-109).
- **Check-and-continue:** YELLOW checks log warnings but don't block. Only RED blocks.
- **Cache-with-TTL:** Rate limit status cached for 5 minutes. Stale cache = re-check.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Dispatch engine | REQ-100 | Internal | Preflight → go/no-go signal |
| Provider health | REQ-109 | Internal | Per-provider health check |
| OB integration | IFS-102 | Outbound | Preflight summary in OAResult |
| Overnight batch | REQ-101 | Internal | Cache preflight for batch duration |
| Notifications | REQ-105 | Internal | RED preflight triggers notification |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-010 (Error Resilience) | Preflight failure is graceful, not a crash |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Preflight events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for environment health queries |

---

## 15. Self-Correction

- If preflight reports GREEN but dispatch immediately fails (Claude binary moved between
  check and dispatch), the dispatch error handler re-runs preflight and updates the cache.
- If rate limit cache is stale (provider changed state since last check), the next dispatch
  failure triggers a fresh rate limit probe and cache update.
- False YELLOW on version check (new Claude version not yet in compatible list) is self-
  correcting: after 3 successful dispatches on the unknown version, it's auto-added.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `which claude` is reliable for detecting Claude binary | May need explicit config path |
| A2 | Rate limit status is queryable without burning tokens | May need a dedicated health endpoint |
| A3 | CLAUDECODE env var is the definitive nesting signal | If Anthropic changes the var name, check breaks |
| A4 | 500MB disk minimum is sufficient for worktrees | Large repos may need more; make configurable |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Missing Claude binary → RED with install instructions | Binary test |
| 2 | Rate limited → RED with reset time | Rate test |
| 3 | CLAUDECODE set → RED with "strip env var" message | Nesting test |
| 4 | All checks pass → GREEN, dispatch proceeds | Happy path test |
| 5 | Overnight batch → preflight once, not per-task | Batch test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Check implementations (8 checks) | 1 day |
| PreflightResult dataclass + formatting | 0.5 day |
| Batch caching | 0.5 day |
| CLI command (`rondo preflight`) | 0.5 day |
| OAResult metadata integration | 0.5 day |
| Tests | 1 day |
| Total | ~4 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Each individual check (8 checks × pass/fail) | 16 |
| Integration | Full preflight → dispatch flow | 4 |
| Performance | Preflight completes <3s | 2 |
| Caching | Batch mode reuses cached result | 3 |
| CLI | `rondo preflight` standalone output | 2 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| False RED (Claude present but check fails) | Dispatch blocked unnecessarily | Allow `--skip-preflight` override |
| Stale cache (rate limit changed after cache) | Dispatch fails despite GREEN | Re-check on first dispatch failure |
| Slow rate limit probe (>3s) | Preflight exceeds time budget | Use cached data, skip live probe |
| Preflight itself crashes | Dispatch blocked | Catch all exceptions, default to YELLOW |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework |
| STD-102 | Configuration loading |
| CORE-STD-010 | Error resilience patterns |

| Used By | Why |
|---------|-----|
| REQ-101 | Automation uses cached preflight for overnight batch |
| IFS-102 | OB integration includes preflight in OAResult metadata |
| REQ-109 | Provider adapters extend preflight with per-provider health |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Auto-run before every dispatch | 2026-03-20 | Catch problems early, save money |
| D2 | Cache for batch mode | 2026-03-20 | Don't re-check 50 times overnight |
| D3 | CLAUDECODE env var check is RED (not YELLOW) | 2026-03-20 | Session 78: nested session hung for 2 minutes, total blocker |
| D4 | <3s time budget | 2026-03-20 | Preflight must not be the bottleneck |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should preflight check network connectivity to AI providers? | Additional RED check vs slower preflight | OPEN |
| Q2 | Should preflight report be saved to a log file for overnight debugging? | Useful for post-mortem, adds disk I/O | OPEN |
| Q3 | Should `--skip-preflight` be allowed, and if so, should it be logged as a warning? | Escape hatch vs safety | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Preflight** | Pre-dispatch environment verification — all checks before first API call |
| **GREEN** | All checks pass, dispatch is safe to proceed |
| **YELLOW** | Warnings present but dispatch can proceed with caveats |
| **RED** | Critical failure, dispatch must not proceed |
| **Nesting trap** | CLAUDECODE env var set → subprocess will fail with ERR_NESTED_SESSION |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False RED blocks valid dispatch | Low | Wasted opportunity | `--skip-preflight` escape hatch |
| Rate limit probe burns tokens | Low | Wasted money | Cache-first approach |
| New Claude version flagged as YELLOW | Medium | Noisy warnings | Auto-whitelist after 3 successes |

---

## 26. External Scan

Cross-pollinated from OB-REQ-113 (session preflight). Similar patterns exist in CI/CD:
Jenkins agent health checks, GitHub Actions runner readiness checks, Docker healthchecks.
The traffic-light pattern (GREEN/YELLOW/RED) is universal in operations monitoring.

---

## 27. Security Considerations

- Preflight checks API key presence, not API key content. Keys are never logged or displayed.
- Rate limit probe uses minimal token expenditure (cached when possible).
- CLAUDECODE env var check prevents session nesting, which is both a reliability and
  security concern (nested sessions could inherit unexpected permissions).

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Total preflight time | <200ms typical | Most checks are local filesystem/env |
| Rate limit probe | <100ms (cached) or <1s (live) | Live probe only when cache is stale |
| Memory | Negligible | PreflightResult is a small dataclass |
| Disk I/O | Minimal | Config file read + disk space check |

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

Not yet populated. Will be filled during first build sprint implementing preflight.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- The CLAUDECODE env var check (req 10) is the single highest-value check in this spec.
  Session 78 lost 2 minutes to a hung nested subprocess. This check prevents that entirely.
- Cross-pollinated from OB-REQ-113 which handles session-level preflight. REQ-103 handles
  dispatch-level preflight — same pattern, different scope.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Dispatch preflight checks | THEORY | Specced for pre-dispatch validation | Phase 1 build |
| Model availability check | THEORY | Specced for verifying model access | Phase 1 build |
| Budget validation | THEORY | Specced for token budget pre-check | Phase 1 build |
| Context size validation | THEORY | Specced for ensuring prompt fits model window | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-113. 16 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
