# Rondo-STD-107 Addendum: Security Hardening — Path to 9/10

**Parent:** Rondo-STD-107-security.md
**Created:** 2026-03-31
**Origin:** Session 93 — Cursor security review for 9/10 target
**Status:** APPROVED

---

## Background TTL + Limits (RONDO-92, Finding #190)

| # | Requirement | Priority |
|---|-------------|----------|
| H-01 | `_background_results` MUST have max 100 entries. Evict oldest completed when full. | MUST |
| H-02 | Entries older than 24h MUST be eligible for eviction on next access. | MUST |
| H-03 | `rondo_run_status` MUST return `"expired"` for evicted dispatch_ids. | MUST |

## MCP Trust Levels (RONDO-95)

| # | Requirement | Priority |
|---|-------------|----------|
| H-04 | MCP tools classified: LOW (read-only), MEDIUM (preview), HIGH (mutation). | MUST |
| H-05 | HIGH tools (run dry_run=False, retry, spool_consume, schedule_create) MUST check `RONDO_ALLOW_MUTATIONS` env var. Default: allowed. | SHOULD |
| H-06 | When mutations disabled: return `{"status":"error","error":"mutating tools disabled","code":"ERR_MUTATIONS_DISABLED"}`. | MUST |

## MCP Input Validation (RONDO-95)

| # | Requirement | Priority |
|---|-------------|----------|
| H-07 | `rondo_run` prompt MUST be capped at 500KB. | MUST |
| H-08 | `rondo_chain` steps MUST be capped at 20. | MUST |
| H-09 | `rondo_benchmark` models MUST be capped at 10. | MUST |
| H-10 | `rondo_summarize` dispatch_json MUST be capped at 1MB. | MUST |
| H-11 | Violations return `{"status":"error","code":"ERR_INPUT_TOO_LARGE"}`. | MUST |

## Schedule Safeguards (RONDO-97)

| # | Requirement | Priority |
|---|-------------|----------|
| H-12 | Minimum schedule interval: 1 hour (no sub-hour cron). | MUST |
| H-13 | Maximum active schedules: 20. | MUST |
| H-14 | Schedule plist files: permission 644, owned by user. | MUST |

## Uniform Error Codes (RONDO-96)

| # | Requirement | Priority |
|---|-------------|----------|
| H-15 | Canonical error codes: ERR_INVALID_INPUT, ERR_LIMIT_EXCEEDED, ERR_INTERNAL, ERR_TIMEOUT, ERR_CONFIG, ERR_PROVIDER, ERR_MUTATIONS_DISABLED, ERR_NESTED_SESSION, ERR_WATCHDOG_TIMEOUT. | MUST |
| H-16 | ALL MCP tools use these codes in error responses. | MUST |

## Threat Model (RONDO-96)

| # | Requirement | Priority |
|---|-------------|----------|
| H-17 | Document: "Rondo targets macOS/*nix, single-user, Claude Code stdio MCP." | MUST |
| H-18 | Document: "Not in scope: multi-tenant server, untrusted network, Windows." | MUST |
| H-19 | Document: "Rondo does not expose arbitrary shell or network primitives." | MUST |

## Secret Scrubbing Verification

| # | Requirement | Priority |
|---|-------------|----------|
| H-20 | Verify: audit prompt files, result files, spool payloads, history records ALL go through sanitize. | MUST |
| H-21 | Schedule parameters MUST NOT contain credentials. API keys via env only. | MUST |

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-03-31 | Initial — 21 requirements for security 9/10. Cursor-driven. |
