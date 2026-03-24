# SOP-104: Migration / Upgrade

*How to upgrade between Rondo versions, migrate data, and handle breaking changes.*

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-SOP-005, SOP-104 (Caliber), SOP-104 (Rondo)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this SOP does:** Defines the procedure for upgrading Rondo between versions,
migrating configuration and audit data, handling breaking changes in task API or config
format, and ensuring OB/Caliber compatibility across version boundaries.

**IN scope:**
- Version upgrade procedure (PATCH, MINOR, MAJOR)
- Configuration migration
- Audit trail compatibility
- OAPayload/OAResult contract versioning
- Template migration
- Rollback after failed upgrade
- OB/Caliber cross-product compatibility

**OUT scope:**
- Release creation (SOP-102 owns that)
- Incident handling during upgrade (SOP-103 owns that)
- Build process (SOP-101 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo evolves: new config keys, new audit fields, new OAPayload/OAResult versions, new
template formats. Without a migration procedure, upgrades break overnight automation,
corrupt audit trails, or silently produce incompatible OAResults that OB can't parse.
This SOP ensures every upgrade is safe, tested, and reversible.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | PATCH upgrades require no manual intervention | MUST |
| 002 | MINOR upgrades may add new config keys with defaults (no breakage) | MUST |
| 003 | MAJOR upgrades provide migration script for breaking changes | MUST |
| 004 | Audit trail backward compatible — new versions can read old audit data | MUST |
| 005 | OAPayload/OAResult version negotiation between Rondo and OB | MUST |
| 006 | Template files compatible across MINOR versions | SHOULD |
| 007 | Pre-upgrade check validates current version and identifies migration steps | SHOULD |
| 008 | Rollback to previous version without data loss | MUST |
| 009 | Cross-product compatibility matrix maintained | SHOULD |
| 010 | Upgrade procedure completes in <15 minutes | SHOULD |


---

## 4. Architecture / Design

### Upgrade Decision Tree

```
Check current version → Check target version → Determine upgrade type
    │
    ├── PATCH (X.Y.Z → X.Y.Z+1)
    │   └── pip install -e . → done
    │
    ├── MINOR (X.Y.Z → X.Y+1.0)
    │   └── pip install -e . → check new config keys → add defaults if missing → done
    │
    └── MAJOR (X.Y.Z → X+1.0.0)
        └── backup → run migration script → pip install -e . → verify → done
```

### Migration Script Pattern

```bash
## rondo migrate --from 1.x --to 2.0
rondo migrate
```

The `rondo migrate` command:
1. Detects current version from installed package
2. Detects target version from code
3. Runs version-specific migration functions in order
4. Validates result

---

## 5. Data Model

**Concurrency:** All migration writes use database transactions with WAL mode. Concurrent schema changes are serialized to prevent data corruption.

Migration affects these data artifacts:

| Artifact | Location | Migration Strategy |
|----------|----------|-------------------|
| Config file | `.rondo/config.toml` | Add new keys with defaults, never remove old keys until MAJOR |
| Audit trail | `rondo_audit.jsonl` | Append-only, new fields have defaults, old fields preserved |
| Templates | `~/.rondo/templates/` | YAML format stable across MINOR, migration for MAJOR |
| OAPayload schema | `schemas/oa-payload-v*.json` | Versioned, multiple versions supported simultaneously |
| OAResult schema | `schemas/oa-result-v*.json` | Versioned, multiple versions supported simultaneously |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Migrated config | TOML | Rondo runtime |
| Migration log | Terminal output + audit trail | Mark, debugging |
| Compatibility matrix | Markdown table | Operators, OB/Caliber integrators |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Current config | TOML | Previous Rondo version |
| Current audit trail | JSONL | Previous Rondo version |
| Current templates | YAML | Previous Rondo version |
| Migration scripts | Python | Rondo source code |

---

## 7. MCP / API Interface

Future: an MCP tool per CORE-IFS-005 could check upgrade compatibility and suggest
migration steps, enabling AI-assisted upgrades.

---

## 8. States & Modes

### Upgrade Lifecycle

| State | Meaning | Next |
|-------|---------|------|
| **PRE-CHECK** | Validate current state, identify migration needs | BACKUP |
| **BACKUP** | Snapshot config, audit, templates | MIGRATE |
| **MIGRATE** | Run migration scripts (MAJOR only) | INSTALL |
| **INSTALL** | pip install new version | VERIFY |
| **VERIFY** | Run preflight + smoke test | DONE or ROLLBACK |
| **ROLLBACK** | Restore from backup | PRE-CHECK (retry) |

**State Machine Type:** FORWARD-ONLY (with rollback branch)
**Rationale:** Upgrade progresses PRE-CHECK → BACKUP → MIGRATE → INSTALL → VERIFY → DONE. ROLLBACK is a forward branch from VERIFY (failure) that returns to PRE-CHECK for a retry cycle, but each cycle is a new forward pass.
**Rollback:** ROLLBACK restores from backup and restarts the upgrade cycle from PRE-CHECK.

---

## 9. Configuration

### Config Migration Rules

| Change Type | Version | Procedure |
|-------------|---------|-----------|
| New optional key | MINOR | Auto-add with default value, log "Added key X = default" |
| Key renamed | MAJOR | Migration script renames, old key preserved as comment |
| Key removed | MAJOR | Migration script removes after backup, log warning |
| Value format changed | MAJOR | Migration script converts, old value logged |
| Section restructured | MAJOR | Migration script moves keys, old structure preserved as backup |

### COALESCE Handles Missing Keys

New config keys added in MINOR versions use the COALESCE pattern: if the key is missing
from config, the hardcoded default applies. No migration needed — just works.

---

## 10. Rules & Constraints

1. **PATCH = zero migration.** Install and go. No config changes, no data changes. Violation ID: `SOP104-PATCH-ZERO`
2. **MINOR = additive only.** New keys with defaults. Never remove or rename keys in MINOR. Violation ID: `SOP104-MINOR-ADDITIVE`
3. **MAJOR = migration script required.** Breaking changes must have an automated migration path. Violation ID: `SOP104-MAJOR-SCRIPT`
4. **Audit trail is append-only.** Migration never modifies existing audit entries. New entries may have new fields. Violation ID: `SOP104-AUDIT-IMMUTABLE`
5. **Backup before MAJOR.** Automated backup of config + audit + templates before any migration. Violation ID: `SOP104-BACKUP-FIRST`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Safety | Zero data loss during upgrade | Audit trail and config are critical |
| Speed | <15 minutes total | Minimize downtime |
| Reversibility | Rollback in <5 minutes | Failed upgrades must be recoverable |
| Transparency | Every migration step logged | Mark sees what changed |
| Compatibility | OB/Caliber work with new Rondo version | Cross-product stability |

---

## 12. Shared Patterns

- **COALESCE for new config keys:** Missing key → default value. No migration needed for
  MINOR additions. Same pattern as STD-109 config resolution.
- **Versioned contracts:** OAPayload/OAResult have `$version` fields. Multiple versions
  can be supported simultaneously. Same pattern as REST API versioning.
- **Backup-migrate-verify:** Standard database migration pattern (Rails, Django, Flyway).
  Backup before change, migrate, verify, rollback if verify fails.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| OB integration | IFS-102 | Bidirectional | OAPayload/OAResult version negotiation |
| Caliber integration | IFS-101 | Bidirectional | TaskResult format compatibility |
| Provider adapters | REQ-109 | Internal | Adapter interface stability |
| Config system | STD-109 | Internal | COALESCE handles missing keys |

### Cross-Product Compatibility Matrix

| Rondo Version | OB Version | Caliber Version | Notes |
|---------------|-----------|-----------------|-------|
| 1.0.x | Any OB2 | Any Caliber | Initial compatible set |
| 2.0.x | OB2 ≥ 2.1 | Caliber ≥ 1.2 | OAPayload v2.0 requires OB update |

This matrix is maintained in `rondo/COMPATIBILITY.md` and updated with every MAJOR release.

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-010 (Error Resilience) | Migration failures are recoverable via rollback |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Migration events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for upgrade compatibility checks |
| DEC-017 | Universal SOP numbering |

---

## 15. Self-Correction

- If `rondo migrate` detects an incomplete previous migration (interrupted), it resumes
  from the last completed step rather than restarting from scratch.
- If post-upgrade verification fails, the migration log shows exactly which check failed
  and suggests rollback or manual fix.
- If the compatibility matrix is stale (Rondo upgraded but matrix not updated), the
  preflight warns: "Compatibility matrix not updated for version X.Y.Z."

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Backup fits in available disk space | May need to warn if disk is low |
| A2 | Migration scripts are idempotent (safe to re-run) | Must ensure idempotency in implementation |
| A3 | OB and Caliber can be upgraded independently of Rondo | If tightly coupled, need coordinated upgrades |
| A4 | Audit trail size is manageable for backup (<1GB) | May need incremental backup for large trails |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | PATCH upgrade: install and go, no migration needed | Upgrade test |
| 2 | MINOR upgrade: new config keys auto-added with defaults | Config test |
| 3 | MAJOR upgrade: migration script runs, all data preserved | Migration test |
| 4 | Rollback restores previous state completely | Rollback test |
| 5 | Cross-product compatibility verified post-upgrade | Integration test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| `rondo migrate` CLI command | 1 day |
| Config migration engine | 1 day |
| Backup/restore mechanism | 1 day |
| Pre-upgrade checker | 0.5 day |
| Compatibility matrix tool | 0.5 day |
| Tests | 1.5 days |
| Total | ~5.5 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Config migration, audit compatibility, version parsing | 8 |
| Integration | Full upgrade cycle (backup → migrate → verify) | 4 |
| Rollback | Upgrade fails → rollback → verify original state | 3 |
| Cross-version | Old audit data readable by new version | 3 |
| Compatibility | OAPayload v1 ↔ v2 negotiation | 2 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Migration script crashes mid-run | Partially migrated state | Backup + idempotent migration (re-runnable) |
| Backup disk full | Can't create backup | Pre-check disk space before upgrade |
| Config format incompatible | Rondo won't start | Rollback from backup |
| Audit trail too large to backup | Backup takes too long | Incremental backup (config only, audit stays in place) |
| OB sends old OAPayload version | Rondo rejects | Version negotiation with clear error |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Migration guards (mandatory backup, sequential enforcement) can be overridden under DR mode with human approval to force-apply or skip migration steps.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| SOP-101 | Build procedure (pip install after migration) |
| SOP-102 | Release procedure (creates the versions being upgraded to) |
| STD-109 | Config system (COALESCE handles missing keys) |
| IFS-102 | OAPayload/OAResult versioning |

| Used By | Why |
|---------|-----|
| All Rondo operators | Entry point for version upgrades |
| OB integrators | Cross-product compatibility checks |
| Caliber integrators | Cross-product compatibility checks |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | PATCH = zero migration, always | 2026-03-22 | Patches must be frictionless |
| D2 | MINOR = additive only (COALESCE handles missing keys) | 2026-03-22 | No migration for non-breaking additions |
| D3 | MAJOR = migration script required | 2026-03-22 | Breaking changes need automated conversion |
| D4 | Audit trail never modified by migration | 2026-03-22 | Append-only is inviolate |
| D5 | Backup before MAJOR is automated | 2026-03-22 | Human forgets, script doesn't |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should there be a `rondo upgrade` wrapper that does backup + install + migrate + verify? | Single-command upgrade | OPEN |
| Q2 | Should multiple MAJOR versions be skippable (1.x → 3.x directly)? | Skip intermediate versions | OPEN — chain migrations for now |
| Q3 | Should the compatibility matrix be machine-readable (TOML/JSON)? | Automated compatibility checks | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Migration** | Automated conversion of data/config between incompatible versions |
| **COALESCE** | Config resolution pattern — missing key → default value |
| **Compatibility matrix** | Table showing which Rondo/OB/Caliber versions work together |
| **Idempotent** | Safe to run multiple times — same result whether run once or twice |
| **Version negotiation** | OAPayload/OAResult `$version` field enables format compatibility |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Migration corrupts config | Low | Rondo won't start | Backup + rollback |
| OB/Caliber incompatible after upgrade | Medium | Integration broken | Compatibility matrix + pre-upgrade check |
| Audit trail format change breaks history queries | Low | Lost historical data | Audit entries are never modified, new fields have defaults |
| Users skip MAJOR migration steps | Medium | Broken state | `rondo migrate` enforces steps |

---

## 26. External Scan

Migration patterns follow established practices: Django migrations (sequential, reversible),
Rails ActiveRecord migrations (up/down), Flyway (SQL versioned migrations). The COALESCE
pattern for MINOR upgrades is borrowed from Terraform provider config (new optional fields
have defaults). Version negotiation follows HTTP content negotiation patterns.

---

## 27. Security Considerations

- Backup files may contain config data (not keys — keys are in Keychain). Backup files
  should be permission-restricted (0600) and deleted after successful upgrade.
- Migration scripts should not require elevated privileges.
- Version negotiation errors should not reveal internal system details to external callers.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| PATCH upgrade | <2 minutes | pip install only |
| MINOR upgrade | <5 minutes | pip install + config check |
| MAJOR upgrade | <15 minutes | backup + migrate + install + verify |
| Rollback | <5 minutes | restore backup + pip install old version |
| Backup size | <100MB | Config + templates (audit stays in place) |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — built from stub, full 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not yet populated. Will be filled during first real version upgrade.

---

## 32. AI Assumptions

Not yet populated. Will capture assumptions during upgrade implementation.

---

## 33. AI Cost

Not yet populated. Will track cost of upgrade-related build sprints.

---

## 34. Notes

- This SOP was originally a stub (RESERVED status, Session 79). Session 84 built it out
  to full 35 sections with upgrade decision tree, config migration rules, and compatibility
  matrix pattern.
- The COALESCE pattern for MINOR upgrades is the key insight: new config keys with defaults
  means MINOR upgrades are zero-migration. Only MAJOR versions need migration scripts.
- The audit trail's append-only nature means it's inherently forward-compatible — new
  versions add fields with defaults, old entries remain readable.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Migration procedure | THEORY | Specced for version-to-version upgrades | Phase 2 build |
| Schema migration steps | THEORY | Specced for DB schema evolution | Phase 2 build |
| Rollback procedure | THEORY | Specced for failed migration recovery | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial stub. Reserved number. Session 79. |
| 0.2 | 2026-03-22 | Full build from stub. 10 requirements, upgrade decision tree, config migration rules, cross-product compatibility matrix. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
