# STD-114: Output Sanitization

*AI output may contain secrets from the code it read. Detect and scrub before storing or reporting.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-008 (Security), CORE-STD-010 (Error Resilience — credential scrubbing), CORE-STD-012, CORE-STD-011, CORE-STD-021, CORE-STD-013, STD-107 | **Used by:** STD-113 (Audit Trail), IFS-102 (OB Integration), REQ-101 (Automation)
**Cross-pollinated from:** ACE-REQ-017 (Privacy & Redaction) — adapted from knowledge-base redaction to dispatch-output sanitization

---

## 1. Purpose & Scope

**What this spec does:** Rondo dispatches prompts that include source code. That source code may contain secrets: API keys in config files, passwords in test fixtures, tokens in environment examples. The AI reads them, and may echo them in its output. This spec defines detection and scrubbing of secrets in AI output before it reaches audit files, reports, or OB integration.

**IN scope:**
- Pattern-based secret detection in AI output (stdout, parsed results)
- Confidence-scored detection (exact match vs heuristic)
- Scrubbing before storage (audit files, result files, OAResult)
- Non-destructive audit (log THAT scrubbing happened, not WHAT was scrubbed)
- False positive management (user override for non-secrets)

**OUT of scope:**
- Preventing secrets from entering prompts (that's the caller's job — Caliber, OB)
- Secret management (CORE-STD-008)
- General error resilience (CORE-STD-010)
- ACE-level knowledge redaction (ACE-REQ-017 — broader scope)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified STD correct (Session 86) -->

## 2. The Problem

AI reads source code that contains secrets: API keys in config files, passwords in test fixtures, tokens in `.env.example`. The AI may echo these secrets in its output. Without sanitization, secrets end up in audit files, reports, and OB's database — persisted and potentially exposed. Rondo is the last gate before AI output reaches storage.

---

## 3. Requirements

### Detection


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Scan all AI output (stdout, parsed_result, files_created content) for secret patterns before storing | MUST | Scan test |
| 002 | Default patterns: `api_key`, `password`, `secret`, `bearer`, `token`, AWS access keys (`AKIA...`), base64 strings >40 chars, private key markers (`-----BEGIN`) | MUST | Pattern test |
| 003 | Confidence scoring: exact pattern match = 0.9+, heuristic match (entropy-based) = 0.5-0.8 | SHOULD | Confidence test |
| 004 | Custom patterns configurable in `.rondo/config.toml [sanitization.patterns]` | SHOULD | Config test |


### Scrubbing

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 005 | Replace detected secrets with `[REDACTED:{pattern_name}]` placeholder | MUST | Scrub test |
| 006 | Scrub BEFORE writing to: audit files (STD-113), result files, OAResult JSON, morning reports | MUST | Order test |
| 007 | Raw unscrubbed output preserved in memory for current dispatch processing — scrubbed only at storage boundary | MUST | Boundary test |
| 008 | Environment variable patterns (`${VAR}`, `$HOME`, `~/.env`) stripped from all stored output | MUST | Env test |
| 009 | File paths in reports: truncate to basename, hide home directory | SHOULD | Path test |


### Audit

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 010 | Log scrubbing events: timestamp, dispatch_id, pattern_matched, confidence, line_number. NEVER log the actual secret. | MUST | Audit test |
| 011 | Scrubbing count included in dispatch result metadata: `secrets_scrubbed: 3` | MUST | Count test |
| 012 | If 0 secrets scrubbed: don't log (no noise for clean output) | SHOULD | Quiet test |


### False Positive Management

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 013 | `rondo sanitize allow <pattern> <value_hash>` — mark a specific match as non-secret (e.g., "base64_encoded" that's actually just a test fixture) | SHOULD | Allow test |
| 014 | Allowed patterns tracked in config, not in code. Feeds back to reduce false positives over time. | SHOULD | Feedback test |
| 015 | CORE-STD-011 (Self-Correction) applied: track scrubbing accuracy (was it really a secret?) to improve patterns | SHOULD | Correction test |


---

## 4. Architecture / Design

Sanitization runs as a pipeline stage between dispatch completion and storage: raw output → pattern scanner → confidence scorer → scrubber → scrubbed output → storage. The scanner runs all patterns (default + custom) against every output field. Scrubbing replaces matches with `[REDACTED:{pattern}]`. The pipeline is synchronous and adds minimal latency.

---

## 5. Data Model

**Concurrency:** File-level append locking on JSONL spool files (STD-113).

Scrubbing event: `{timestamp, dispatch_id, pattern_matched, confidence, line_number, action: "SCRUBBED"|"ALLOWED"}`. No secret content in the event. Scrub summary: `{dispatch_id, secrets_scrubbed: int, patterns_triggered: list[str]}`. Attached to DispatchUsage metadata.

---

## 6. Data Boundary

Sanitization happens at the storage boundary. In-memory processing uses raw (unscrubbed) output. Scrubbing triggers when writing to: audit files (STD-113), spool files (STD-104), OAResult JSON (IFS-102), and morning reports (REQ-101). The boundary is write-to-disk/write-to-network.

---

## 7. MCP / API Interface

No MCP interface for sanitization. Sanitization is an internal pipeline stage. CORE-STD-021 MCP tools receive already-scrubbed data — they never see raw output. The `rondo sanitize allow` CLI manages the false positive allowlist locally.

---

## 8. States & Modes

Sanitization is always enabled by default. `sanitization.enabled = false` disables it (for debugging only — logs a WARNING). Confidence threshold is configurable: matches below the threshold are logged but not scrubbed. Two modes: conservative (scrub everything >= 0.5) and relaxed (scrub only >= 0.9).

---

## 9. Configuration

```toml
[sanitization]
enabled = true
confidence_threshold = 0.5          # Scrub if confidence >= this
log_scrubbing_events = true

[sanitization.patterns]
# Additional patterns beyond defaults
custom_1 = "ACME_SECRET_[A-Z0-9]{32}"
custom_2 = "ghp_[A-Za-z0-9]{36}"
```

---

## 10. Rules & Constraints

1. **Scrub at storage boundary.** In-memory processing uses raw output. Scrubbing happens when writing to disk/DB/network. Violation ID: `STD114-BOUNDARY`
2. **Never log the secret.** Log that scrubbing happened (pattern name, line number). Never log what was scrubbed. Violation ID: `STD114-NEVER-LOG-SECRET`
3. **Over-scrub > under-scrub.** Missing a real secret is worse than redacting a false positive. Default to scrub. Violation ID: `STD114-CONSERVATIVE`
4. **Patterns are configurable.** Different projects have different secret formats. Users can add custom patterns. Violation ID: `STD114-CONFIGURABLE`

---

## 11. Quality Attributes

- **Conservative by default:** Over-scrub rather than under-scrub. Missing a real secret is worse than redacting a false positive.
- **Non-destructive:** Raw output preserved in memory for current dispatch. Scrubbing only at storage boundary.
- **Auditable:** Every scrubbing event logged (what pattern, what line — never what content).

---

## 12. Shared Patterns

- **Storage boundary scrubbing:** Same pattern as CORE-STD-010 credential scrubbing rules.
- **Confidence scoring:** Exact match (0.9+) vs heuristic (0.5-0.8). Same approach as STD-115 auto-approval confidence.
- **False positive allowlist:** User-managed exceptions. Same pattern as security tool suppressions.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| STD-114 → STD-113 | Scrubbed output in audit files | CORE-STD-010 rules 19-22 |
| STD-114 → IFS-102 | Scrubbed OAResult for OB | No secrets cross product boundary |
| STD-114 → REQ-101 | Scrubbed morning reports | No secrets in reports |
| STD-114 → CORE-STD-013 | Scrubbing events as TrackerData | Append-only event format |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-008 | Security — output sanitization prevents secret persistence |
| CORE-STD-010 | Error resilience — credential scrubbing rules (reqs 19-22) |
| CORE-STD-012 | Requirement readiness — sanitization pipeline must be active |
| CORE-STD-013 | TrackerData — scrubbing events are trackable |
| CORE-STD-021 | MCP standard — MCP tools receive scrubbed data only |

---

## 15. Self-Correction

CORE-STD-011 applied: track scrubbing accuracy over time. Was the scrubbed content really a secret? False positive rate feeds pattern refinement. The `rondo sanitize allow` command is the human feedback loop — Mark corrects false positives, patterns improve.

---

## 16. Assumptions

1. Secret patterns are detectable by regex (API key formats, private key markers).
2. Entropy-based heuristic detection catches novel secret formats at lower confidence.
3. False positive rate is acceptable (better to over-scrub than miss a real secret).
4. Consumers tolerate `[REDACTED:...]` placeholders in results without breaking.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | API key in AI output → scrubbed before audit file | Scrub test |
| 2 | No secrets in any audit file, result file, or report | Security scan |
| 3 | Scrubbing event logged with pattern name (not content) | Audit test |
| 4 | False positive → `rondo sanitize allow` → not scrubbed next time | Allow test |

---

## 18. Build Notes / Estimate

Pattern scanner: 3 hours (regex engine, default patterns, custom pattern loading). Confidence scorer: 2 hours (exact match scoring, entropy calculation). Scrubber: 1 hour (replace with placeholder, preserve structure). Audit integration: 1 hour. CLI (`rondo sanitize allow`): 2 hours. Total: ~9 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Pattern tests | Default patterns detect known secret formats |
| Confidence tests | Exact match scores 0.9+, heuristic scores 0.5-0.8 |
| Scrub boundary tests | Scrubbing happens at write, not during processing |
| False positive tests | Allowed patterns are not scrubbed |
| Audit tests | Scrubbing events logged without secret content |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Pattern misses a secret format | Secret persisted in audit/spool | Conservative threshold + entropy fallback |
| Over-scrubbing breaks result parsing | Consumer cannot use result | `[REDACTED:...]` placeholder preserves JSON structure |
| Allowlist too permissive | Real secrets slip through | Review allowlist periodically |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-008 | Security requirements for secret handling |
| Depends on | CORE-STD-010 | Credential scrubbing rules (reqs 19-22) |
| Depends on | CORE-STD-012 | Readiness — sanitization pipeline must be active |
| Used by | STD-113 | Audit trail stores scrubbed output |
| Used by | IFS-102 | OB integration receives scrubbed results |
| Used by | REQ-101 | Morning reports use scrubbed content |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Scrub at storage boundary, not at capture | In-memory processing needs raw output for accurate parsing | 2026-03-20 |
| D2: Conservative default (0.5 threshold) | Missing a real secret is worse than false positive | 2026-03-20 |
| D3: User-managed allowlist | Only humans can decide what is not a secret | 2026-03-20 |

---

## 23. Open Questions

1. Should scrubbing extend to file contents that AI creates in worktrees?
2. Should entropy threshold be auto-tuned based on false positive history?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Sanitization** | Detecting and replacing secrets in AI output before storage |
| **Confidence score** | 0.0-1.0 rating of how likely a match is a real secret |
| **Storage boundary** | The point where data moves from memory to disk/network |
| **Allowlist** | User-managed list of known false positives to skip |

---

## 25. Risk / Criticality

**HIGH.** Output sanitization is the last defense against secret persistence. A missed secret in an audit file is a permanent exposure. The conservative scrubbing threshold and entropy fallback are the primary mitigations.

---

## 26. External Scan

Gitleaks and truffleHog use similar pattern-based secret detection for git commits. Rondo adapts these patterns for AI output (different context, same threat). Entropy-based detection follows the approach from truffleHog v3. No novel detection method — proven patterns applied to a new surface.

---

## 27. Security Considerations

This IS a security spec (extends STD-107). Sanitization prevents the specific threat of AI echoing secrets from source code. Cross-references: STD-107 (rule 12, output sanitization), CORE-STD-010 (reqs 19-22, credential scrubbing), STD-113 (audit file protection).

---

## 28. Performance / Resource

Pattern scanning: ~5ms per dispatch output (regex engine over ~10KB text). Entropy calculation: ~2ms for heuristic candidates. Total sanitization overhead: <10ms per dispatch — negligible compared to dispatch duration. Memory: raw output held in memory during dispatch, released after scrubbed write.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) requires the sanitization pipeline to be active before dispatches can proceed. CORE-STD-013 (TrackerData) records scrubbing events for trend analysis (are secrets appearing more frequently?). CORE-STD-021 MCP tools always receive scrubbed data — sanitization is transparent to MCP consumers.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Output sanitization rules | THEORY | Specced for cleaning AI-generated output | Phase 1 build |
| PII detection | THEORY | Specced for removing personal data from outputs | Phase 1 build |
| Format normalization | THEORY | Specced for consistent output formatting | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from ACE-REQ-017. 15 requirements. Adapted from knowledge-base redaction to dispatch output. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
