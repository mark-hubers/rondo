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
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-008 (Security), CORE-STD-010 (Error Resilience — credential scrubbing) | **Used by:** STD-113 (Audit Trail), IFS-102 (OB Integration), REQ-101 (Automation)
**Cross-pollinated from:** ACE R17 (Privacy & Redaction) — adapted from knowledge-base redaction to dispatch-output sanitization

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
- ACE-level knowledge redaction (ACE R17 — broader scope)

---

## 3. Requirements

### Detection

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Scan all AI output (stdout, parsed_result, files_created content) for secret patterns before storing | MUST | Scan test |
| 2 | Default patterns: `api_key`, `password`, `secret`, `bearer`, `token`, AWS access keys (`AKIA...`), base64 strings >40 chars, private key markers (`-----BEGIN`) | MUST | Pattern test |
| 3 | Confidence scoring: exact pattern match = 0.9+, heuristic match (entropy-based) = 0.5-0.8 | SHOULD | Confidence test |
| 4 | Custom patterns configurable in `.rondo/config.toml [sanitization.patterns]` | SHOULD | Config test |

### Scrubbing

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 5 | Replace detected secrets with `[REDACTED:{pattern_name}]` placeholder | MUST | Scrub test |
| 6 | Scrub BEFORE writing to: audit files (STD-113), result files, OAResult JSON, morning reports | MUST | Order test |
| 7 | Raw unscrubbed output preserved in memory for current dispatch processing — scrubbed only at storage boundary | MUST | Boundary test |
| 8 | Environment variable patterns (`${VAR}`, `$HOME`, `~/.env`) stripped from all stored output | MUST | Env test |
| 9 | File paths in reports: truncate to basename, hide home directory | SHOULD | Path test |

### Audit

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 10 | Log scrubbing events: timestamp, dispatch_id, pattern_matched, confidence, line_number. NEVER log the actual secret. | MUST | Audit test |
| 11 | Scrubbing count included in dispatch result metadata: `secrets_scrubbed: 3` | MUST | Count test |
| 12 | If 0 secrets scrubbed: don't log (no noise for clean output) | SHOULD | Quiet test |

### False Positive Management

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 13 | `rondo sanitize allow <pattern> <value_hash>` — mark a specific match as non-secret (e.g., "base64_encoded" that's actually just a test fixture) | SHOULD | Allow test |
| 14 | Allowed patterns tracked in config, not in code. Feeds back to reduce false positives over time. | SHOULD | Feedback test |
| 15 | CORE-STD-011 (Self-Correction) applied: track scrubbing accuracy (was it really a secret?) to improve patterns | SHOULD | Correction test |

---

## 10. Rules & Constraints

1. **Scrub at storage boundary.** In-memory processing uses raw output. Scrubbing happens when writing to disk/DB/network. Violation ID: `STD114-BOUNDARY`
2. **Never log the secret.** Log that scrubbing happened (pattern name, line number). Never log what was scrubbed. Violation ID: `STD114-NEVER-LOG-SECRET`
3. **Over-scrub > under-scrub.** Missing a real secret is worse than redacting a false positive. Default to scrub. Violation ID: `STD114-CONSERVATIVE`
4. **Patterns are configurable.** Different projects have different secret formats. Users can add custom patterns. Violation ID: `STD114-CONFIGURABLE`

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

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | API key in AI output → scrubbed before audit file | Scrub test |
| 2 | No secrets in any audit file, result file, or report | Security scan |
| 3 | Scrubbing event logged with pattern name (not content) | Audit test |
| 4 | False positive → `rondo sanitize allow` → not scrubbed next time | Allow test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from ACE R17. 15 requirements. Adapted from knowledge-base redaction to dispatch output. |
