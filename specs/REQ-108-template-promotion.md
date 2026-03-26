# REQ-108: Task Template Promotion

*Useful twice = permanent template. Track one-off task definitions, promote the ones that stick.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail), REQ-107, OB-REQ-112 | **Used by:** REQ-101 (Automation)
**Cross-pollinated from:** OB-REQ-112 (Ad-Hoc Promotion) — adapted from methodology tool promotion to task template promotion
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 1. Purpose & Scope

**What this spec does:** Users create one-off task definitions for specific dispatches. Some are used once and forgotten. Others get reused 5, 10, 20 times — these are templates hiding in plain sight. This spec tracks usage and promotes popular task definitions to built-in templates, so proven patterns get reused instead of reinvented.

**IN scope:**
- Tracking unique task definitions by prompt_hash
- Promotion lifecycle (ADHOC → CANDIDATE → TEMPLATE → ARCHIVED)
- CLI for listing templates and candidates
- Morning report surfacing of promotion candidates
- Archive policy for unused templates

**OUT of scope:**
- Prompt engineering (how to write good prompts)
- Template marketplace / sharing (future)
- Model selection within templates (REQ-100 owns that)

---


## 2. The Problem

Without template promotion, good task definitions are invisible. A user creates a code
review prompt, refines it over 5 runs until it works well, then forgets where they saved
it. Next week they write a new one from scratch. Meanwhile, the proven prompt sits unused
in the audit trail. Template promotion surfaces these hidden patterns and makes them
reusable, reducing prompt reinvention and improving consistency.

---


## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Track every unique task definition by prompt_hash: first_used_at, last_used_at, usage_count | MUST | Tracking test |
| 002 | Promotion threshold: usage_count >= 2 in different sessions = promotion candidate | MUST | Threshold test |
| 003 | Promotion lifecycle: `ADHOC` (one-off) → `CANDIDATE` (used 2+) → `TEMPLATE` (promoted to built-in) → `ARCHIVED` (unused 90+ days) | MUST | Lifecycle test |
| 004 | `rondo templates` CLI: show all templates with usage count and last_used_at | SHOULD | CLI test |
| 005 | `rondo templates --candidates` CLI: show promotion candidates (used 2+ but not yet promoted) | SHOULD | Candidates test |
| 006 | Promotion: copy task definition to `~/.rondo/templates/` with a name. Available in `rondo run --template <name>`. | SHOULD | Promote test |
| 007 | Auto-surface candidates in morning report: "3 task definitions used 2+ times — consider promoting" | SHOULD | Report test |
| 008 | Template usage feeds back: promoted templates tracked for continued usage. If unused 90+ days → suggest archiving. | SHOULD | Archive test |
| 009 | When OB-connected: template promotion events included in OAResult metadata | SHOULD | Integration test |
| 010 | Derived from STD-113 audit trail (prompt_hash grouping) — no separate tracking DB needed | MUST | Source test |


---


## 4. Architecture / Design

```
STD-113 Audit Trail (rondo_audit.jsonl)
    │
    ▼
Promotion Engine
    ├── Group by prompt_hash
    ├── Count unique sessions per hash
    ├── Classify: ADHOC (<2) / CANDIDATE (2+) / TEMPLATE (promoted)
    └── Archive check: last_used_at > 90 days
    │
    ▼
~/.rondo/templates/
    ├── review-forward.yaml     # Promoted template
    ├── code-fix.yaml           # Promoted template
    └── ...
```

Templates are stored as YAML files with the full task definition (instruction, model hints,
done_when template). Running `rondo run --template review-forward` loads the template and
substitutes context variables.

---


## 5. Data Model

**Concurrency:** All template writes use file-level locking. Concurrent template promotion and YAML file updates are serialized to prevent corruption.

Template metadata is derived from STD-113 audit trail (no separate storage). Promoted
templates are stored as YAML files in `~/.rondo/templates/`.

| Field | Source | Purpose |
|-------|--------|---------|
| `prompt_hash` | SHA-256 of normalized prompt | Unique identifier for task definition |
| `first_used_at` | Min timestamp in audit group | When this pattern first appeared |
| `last_used_at` | Max timestamp in audit group | Most recent use |
| `usage_count` | Count of audit entries per hash | How often used |
| `session_count` | Count of distinct sessions per hash | Used in different sessions? |
| `lifecycle` | Derived from usage_count + promotion status | ADHOC/CANDIDATE/TEMPLATE/ARCHIVED |

---


## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Template files | YAML in `~/.rondo/templates/` | `rondo run --template <name>` |
| Candidate list | Terminal table / JSON | Mark (CLI, morning report) |
| Archive suggestions | Morning report section | Mark (cleanup decisions) |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Dispatch audit trail | JSONL | STD-113 |
| Promotion decisions | Manual CLI command | Mark |
| Template files | YAML | Previous promotions |

---


## 7. MCP / API Interface

Future: an MCP tool per CORE-STD-021 could list templates and candidates, enabling AI
agents to discover and use proven task patterns. Example: "What templates do I have for
code review?" → returns list of promoted templates with usage stats.

---


## 8. States & Modes

Template lifecycle states:

| State | Condition | Transitions To |
|-------|-----------|---------------|
| **ADHOC** | Used <2 times or only in 1 session | CANDIDATE (when used 2+ in different sessions) |
| **CANDIDATE** | Used 2+ in different sessions, not promoted | TEMPLATE (manual promotion) |
| **TEMPLATE** | Promoted to `~/.rondo/templates/` | ARCHIVED (unused 90+ days) |
| **ARCHIVED** | Template unused for 90+ days | TEMPLATE (if used again) |

Promotion (CANDIDATE → TEMPLATE) is always manual. Archive suggestions are automatic
but archiving requires manual confirmation.

**State Machine Type:** CYCLIC
**Rationale:** Templates cycle: ADHOC → CANDIDATE → TEMPLATE → ARCHIVED → TEMPLATE (if reused). The ARCHIVED → TEMPLATE transition makes this cyclic — a dormant template can be reactivated by usage.
**Rollback:** Archived templates auto-reactivate on use. Manual demotion is not supported (delete and re-create instead).

---


## 9. Configuration

```toml
[templates]
dir = "~/.rondo/templates"         # Where promoted templates live
promotion_threshold = 2             # Minimum uses in different sessions
archive_days = 90                   # Suggest archive after N days unused
surface_candidates = true           # Show candidates in morning report
```

---


## 10. Rules & Constraints

1. **2 uses = candidate.** Not 1 (too aggressive), not 5 (too conservative). 2 in different sessions proves it wasn't a typo. Violation ID: `REQ108-TWO-USES`
2. **Promotion is manual.** Auto-surfacing is fine. Auto-promoting is not — Mark decides what becomes a template. Violation ID: `REQ108-MANUAL-PROMOTE`
3. **Archive, don't delete.** Unused templates might be seasonal. Archive preserves them. Violation ID: `REQ108-ARCHIVE`
4. **Derived from audit.** No separate tracking database. All data comes from STD-113. Violation ID: `REQ108-FROM-AUDIT`

---


## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Discovery | Candidates surfaced within 24 hours of meeting threshold | Don't wait a week to notice a reusable pattern |
| Simplicity | Promote with one CLI command | Low friction encourages template creation |
| Durability | Templates survive across Rondo upgrades | YAML files in user directory, not in package |
| Reuse rate | >50% of overnight dispatches use templates (target) | Proves the system is working |

---


## 12. Shared Patterns

- **Prompt-hash grouping:** Same mechanism as REQ-107 (flakiness). SHA-256 of normalized
  prompt text groups comparable task runs.
- **Lifecycle states:** ADHOC → CANDIDATE → TEMPLATE → ARCHIVED follows the same pattern
  as OB-REQ-112 (ad-hoc tool promotion) and is analogous to feature flags (off → canary →
  GA → deprecated).
- **Morning report surfacing:** Same pattern as REQ-105 (notifications) — surface actionable
  insights in the daily summary.

---


## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Audit trail | STD-113 | Inbound | JSONL audit records with prompt_hash |
| Morning report | REQ-101 | Outbound | Candidate surfacing section |
| Template runner | REQ-100 | Internal | `--template <name>` loads YAML |
| OB integration | Rondo-IFS-102 | Outbound | Promotion events in OAResult |

---


## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Promotion events logged as trackerdata entries |
| CORE-STD-021 (MCP Standard) | Future MCP tool for template discovery |

---


## 15. Self-Correction

- If a promoted template's flakiness score (REQ-107) exceeds 20%, the morning report
  flags it as "promoted but flaky — consider revising."
- If archived templates are re-used (ARCHIVED → TEMPLATE), the promotion engine notes
  the pattern as "seasonal" for future archive suggestions.
- If the 2-use threshold generates too many candidates (>20 per week), the morning report
  suggests increasing the threshold.

---


## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Prompt hash is stable across Rondo versions | Template expansion changes could invalidate hashes |
| A2 | 2 uses in different sessions indicates genuine reuse | May catch incidental reuse (typo correction runs) |
| A3 | YAML is a good format for template storage | May need more structured format for complex tasks |
| A4 | 90 days is the right archive window | Seasonal tasks may need 180+ days |

---


## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Task used 2x in different sessions → flagged as CANDIDATE | Threshold test |
| 2 | Promoted template loadable via `--template <name>` | Template run test |
| 3 | Morning report shows candidates | Report test |
| 4 | Template unused 90 days → archive suggestion | Archive test |
| 5 | Archived template re-used → auto-unarchived | Re-activation test |

---


## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Promotion engine (grouping, counting, lifecycle) | 1 day |
| Template YAML format + loader | 1 day |
| CLI commands (`rondo templates`, `--candidates`, `--promote`) | 1 day |
| Morning report integration | 0.5 day |
| Archive checker | 0.5 day |
| Tests | 1 day |
| Total | ~5 days |

---


## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Grouping, counting, lifecycle transitions | 8 |
| Integration | Audit → promotion engine → template file | 4 |
| CLI | Template listing, candidate listing, promotion | 6 |
| Lifecycle | ADHOC→CANDIDATE→TEMPLATE→ARCHIVED→TEMPLATE | 4 |
| Template | YAML loading, variable substitution, `--template` dispatch | 4 |

---


## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Template YAML malformed | `--template` fails to load | Validate on promotion, not on use |
| Prompt hash changes after Rondo update | Historical grouping broken | Version prompt normalization |
| Template directory permissions | Can't write promoted templates | Check permissions in preflight |
| Too many candidates (noisy) | Morning report cluttered | Configurable threshold + limit display |

---


## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework (defines Task, prompt_hash) |
| STD-113 | Audit trail (data source for usage tracking) |

| Used By | Why |
|---------|-----|
| REQ-101 | Automation uses templates for overnight dispatch patterns |

---


## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 2-use threshold (not 1, not 5) | 2026-03-20 | 1 is too aggressive (catches one-offs), 5 is too conservative (misses useful patterns) |
| D2 | Manual promotion only | 2026-03-20 | Auto-promotion could create unwanted templates. Mark decides. |
| D3 | YAML template format | 2026-03-20 | Human-readable, editable, simple |
| D4 | Archive, never delete | 2026-03-20 | Seasonal patterns may look unused. Archive is reversible. |

---


## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should templates support inheritance (base template + overrides)? | Template complexity vs reuse | OPEN |
| Q2 | Should templates include model preferences or just prompt text? | Scope of what a "template" captures | OPEN |
| Q3 | Should there be a template sharing mechanism (export/import)? | Multi-user, future scope | OPEN — not in v1 |

---


## 24. Glossary

| Term | Definition |
|------|-----------|
| **Template** | A promoted task definition available via `--template <name>` |
| **Candidate** | A task definition used 2+ times in different sessions, eligible for promotion |
| **Prompt hash** | SHA-256 of normalized prompt text, used to track unique task definitions |
| **Archive** | Soft-removal of unused templates (recoverable, not deleted) |

---


## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Template proliferation (too many) | Medium | Hard to find the right template | Categories/tags in future version |
| Stale templates used after model changes | Low | Poor results from outdated prompts | Flakiness detection (REQ-107) flags stale templates |
| Promotion threshold too low/high | Medium | Too many/few candidates | Configurable threshold |

---


## 26. External Scan

Cross-pollinated from OB-REQ-112 (Ad-Hoc Promotion). Industry analogues: GitHub Actions
reusable workflows (ad-hoc → composite action → marketplace), Terraform modules (inline →
local module → registry). The promotion lifecycle pattern is well-established in DevOps.

---


## 27. Security Considerations

- Template YAML files may contain prompt text that references project-specific code or rules.
  Store in user directory (`~/.rondo/templates/`), not in project repo, unless intentional.
- Templates should not contain API keys or credentials. Validation on promotion ensures
  no secrets in template content.
- Shared templates (future) would need content review before import.

---


## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Candidate detection | <500ms over audit trail | Group-by-hash computation |
| Template loading | <10ms | Read single YAML file |
| Template listing | <1s | Scan template directory + usage stats |
| Disk | <1MB for all templates | YAML files are small |

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

Not yet populated. Will be filled during first build sprint implementing template promotion.

---


## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---


## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---


## 34. Notes

- The "useful twice = permanent" principle is the single most important design choice.
  It's the minimum bar that separates signal from noise. One use could be experimental.
  Two uses in different sessions = real pattern.
- Template promotion is a quality-of-life feature, not a core requirement. It makes Rondo
  more ergonomic over time as proven patterns become one-command reusable.

---


### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Task template concept | THEORY | Specced for reusable task definitions | Phase 2 build |
| Ad-hoc to template promotion | THEORY | Specced for promoting successful tasks | Phase 2 build |
| Template versioning | THEORY | Specced for tracking template evolution | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-112. 10 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
