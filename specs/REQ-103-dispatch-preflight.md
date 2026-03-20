# REQ-103: Dispatch Preflight

*Verify the dispatch environment before wasting API tokens. Claude installed? Key valid? Rate limit OK?*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-102 (Configuration), CORE-STD-010 (Error Resilience) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-113 (Preflight System) — adapted from session preflight to dispatch preflight

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

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Preflight runs automatically before every `rondo run` command | MUST | Auto test |
| 2 | Preflight completes in <3 seconds | MUST | Performance test |
| 3 | Check: `claude` binary on PATH and executable | MUST | Binary test |
| 4 | Check: Claude Code version matches known-compatible versions (IFS-100 assumption A1) | SHOULD | Version test |
| 5 | Check: API key or Max plan auth available (per auth mode in config) | MUST | Auth test |
| 6 | Check: rate limit status — if `blocked`, abort with "Rate limited. Resets at: {time}" | MUST | Rate test |
| 7 | Check: if `isUsingOverage`, warn "Using overage capacity — costs may be higher" | SHOULD | Overage test |
| 8 | Check: disk space > 500MB free (worktrees need space) | SHOULD | Disk test |
| 9 | Check: git available (worktree operations need it) | SHOULD | Git test |
| 10 | Check: CLAUDECODE env var not set (prevents nested session error — ERR_NESTED_SESSION) | MUST | Env test |
| 11 | Check: config file exists and parses | MUST | Config test |
| 12 | Report health as GREEN (go), YELLOW (proceed with warnings), RED (abort) | MUST | Status test |
| 13 | RED status: abort with clear message and recovery steps | MUST | Abort test |
| 14 | For overnight batch: run preflight ONCE at start, not per-task. Cache result for batch duration. | SHOULD | Batch test |
| 15 | `rondo preflight` standalone command: check without dispatching | SHOULD | Standalone test |
| 16 | Preflight result included in OAResult metadata when OB-connected | SHOULD | Integration test |

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

---

## 10. Rules & Constraints

1. **Fast.** <3 seconds. If a check is slow, cache it. Violation ID: `REQ103-FAST`
2. **Actionable.** Every RED/YELLOW tells you what to do. "Claude not found. Install: brew install claude" not "Preflight failed." Violation ID: `REQ103-ACTIONABLE`
3. **Don't burn tokens.** Rate limit check should use cached data when possible, not a fresh API call. Violation ID: `REQ103-NO-WASTE`
4. **Nested session trap.** CLAUDECODE env var detection is CRITICAL — Session 78 lesson: hung subprocess for 2 minutes. Violation ID: `REQ103-NESTING`

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

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-113. 16 requirements. |
