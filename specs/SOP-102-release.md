# SOP-102: Release Procedure

*How to ship a new version of Rondo.*

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-SOP-003, SOP-102 (Caliber), SOP-102 (Rondo)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)
**Depends on:** SOP-101

---

## 1. Purpose & Scope

**What this SOP does:** Step-by-step procedure for releasing a new version of Rondo.
Covers pre-release checks, version bumping, changelog, tagging, artifact creation,
post-release verification, and rollback.

**IN scope:**
- Pre-release checklist (all build gates pass)
- Semantic versioning
- Changelog format
- Git tag creation
- Build artifact
- Post-release verification
- Rollback procedure

**OUT scope:**
- Build process details (SOP-101 owns that)
- PyPI publishing (future — Rondo is git-distributed for now)
- OB integration testing (IFS-102 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without a release procedure, versions are ad hoc, changelogs are missing, tags are
inconsistent, and rollback is panic-driven. This SOP ensures every release is
reproducible, documented, and reversible.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | All 6 build gates pass before release | MUST |
| 002 | Semantic versioning (MAJOR.MINOR.PATCH) enforced | MUST |
| 003 | Changelog updated with every release | MUST |
| 004 | Git tag with product prefix (rondo-vX.Y.Z) | MUST |
| 005 | Post-release smoke test passes | MUST |
| 006 | Rollback procedure documented and tested | SHOULD |


---

## 4. Architecture / Design

### Release Pipeline

```
Pre-release checklist (SOP-101 build gates)
    │
    ▼
Version bump (pyproject.toml)
    │
    ▼
Changelog update (CHANGELOG.md)
    │
    ▼
Git tag (rondo-vX.Y.Z)
    │
    ▼
Push tag to remote
    │
    ▼
Post-release smoke test
    │
    ▼
DONE (or rollback if smoke fails)
```

---

## 5. Data Model

Not applicable — this is a release procedure. Version metadata lives in `pyproject.toml`.

---

## 6. Data Boundary

### Pre-Release Checklist

All items must be true before proceeding:

- [ ] `ruff format --check src/ tests/` passes
- [ ] `ruff check src/ tests/` passes
- [ ] `bandit -r src/rondo/ --skip B404,B603` passes
- [ ] `mypy src/rondo/` passes
- [ ] `pytest tests/ --cov=rondo` passes with >= 90% coverage
- [ ] No BLOCK findings open in OB (if Tier 3 connected)
- [ ] All task examples in `examples/` run successfully (smoke test)
- [ ] Overnight mode tested with at least one batch

---

## 7. MCP / API Interface

Not applicable for this SOP. Future: CORE-STD-021 MCP tools could trigger release
automation and report release status.

---

## 8. States & Modes

### Version Bump

1. Version lives in `rondo/pyproject.toml`:
   ```toml
   [project]
   version = "X.Y.Z"
   ```

2. Bump following semver:
   - **MAJOR** (X): Breaking changes to task API, config format, or CLI interface
   - **MINOR** (Y): New dispatch modes, new report formats, new engine features
   - **PATCH** (Z): Bug fixes, documentation, internal improvements

3. Update the version:
   ```bash
   # Edit rondo/pyproject.toml version field
   ```

---

## 9. Configuration

### Changelog Update

1. Changelog format in `rondo/CHANGELOG.md` (create if first release):
   ```markdown
   ## [X.Y.Z] — YYYY-MM-DD

   ### Added
   - New dispatch mode or feature

   ### Changed
   - Changed task API or behavior

   ### Fixed
   - Bug fix description
   ```

2. Include: spike references, spec references, breaking changes prominently marked.

---

## 10. Rules & Constraints

1. **All gates pass.** No release with failing build gates. No exceptions. Violation ID: `SOP102-GATES-PASS`
2. **Semver is strict.** Breaking changes = MAJOR bump. No hiding breaks in MINOR. Violation ID: `SOP102-SEMVER-STRICT`
3. **Tag prefix required.** `rondo-vX.Y.Z` (not `vX.Y.Z`) for monorepo clarity. Violation ID: `SOP102-TAG-PREFIX`
4. **Changelog before tag.** Changelog must be committed before tag creation. Violation ID: `SOP102-CHANGELOG-FIRST`

### Tag Creation

1. Format: `rondo-vX.Y.Z` (product prefix for monorepo)
   ```bash
   git tag -a rondo-vX.Y.Z -m "Rondo vX.Y.Z: brief description"
   ```

2. Push tag:
   ```bash
   git push origin rondo-vX.Y.Z
   ```

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Reproducibility | Same tag = same code = same behavior | Releases must be deterministic |
| Reversibility | Rollback in <5 minutes | Mistakes happen — fast recovery is critical |
| Traceability | Tag → changelog → specs → sprint | Every release traceable to requirements |
| Reliability | Post-release smoke test passes | Release must actually work |

### Build Artifact

Rondo produces:
- **Python package:** `pip install -e .` (editable, monorepo) or `pip install .` (standalone)
- **CLI tool:** `rondo` command (registered via `[project.scripts]` in pyproject.toml)
- **No PyPI upload** at this stage — Rondo is distributed via git clone

Future: Rondo is planned to become its own standalone repository. At that point, PyPI publishing may apply.

---

## 12. Shared Patterns

### Post-Release

1. Run the example tasks to confirm release works:
   ```bash
   cd rondo/examples
   rondo run example_task.py
   ```
2. If Tier 3: OB records the release
3. Update `rondo/reports/` with release metrics
4. Verify the tag:
   ```bash
   git log --oneline -1 rondo-vX.Y.Z
   ```

---

## 13. Integration Points

| Integration | What | Notes |
|-------------|------|-------|
| SOP-101 | Build gates must pass before release | Pre-release dependency |
| OB (Tier 3) | OB records release event | If OB-connected |
| Git remote | Tag pushed to origin | Release artifact |

### Rollback

If critical issues found after release:

1. Revert to previous tag:
   ```bash
   git checkout rondo-vPREVIOUS
   ```
2. Fix forward (preferred) or revert commits
3. Create patch release (X.Y.Z+1)

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-003 (Quality) | All build gates pass before release |
| CORE-STD-012 (Requirement Readiness) | Release only includes ready requirements |
| CORE-STD-013 (TrackerData) | Release events logged as trackerdata entries |
| CORE-STD-021 (MCP Standard) | Future MCP tool for release automation |
| DEC-017 | Universal SOP numbering |

---

## 15. Self-Correction

- If post-release smoke test fails, immediately rollback (do not investigate while broken
  code is live). Fix forward in a patch release.
- If a release is tagged but the changelog is missing, delete the tag, add the changelog,
  and re-tag. Never ship without a changelog.
- If semver was applied incorrectly (MINOR instead of MAJOR for a breaking change),
  issue a corrective MAJOR release immediately with a note in the changelog.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Git tags are sufficient for release tracking | May need release branches for hotfixes |
| A2 | Git clone is the distribution method | May need PyPI for standalone Rondo |
| A3 | Single-machine release process | May need CI/CD pipeline for team releases |
| A4 | Monorepo tag prefix is enough for disambiguation | May need separate repos per product |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Tag exists and points to correct commit | `git log --oneline -1 rondo-vX.Y.Z` |
| 2 | Changelog includes all changes since last release | Manual review |
| 3 | Post-release smoke test passes | Run example tasks |
| 4 | Rollback restores previous version in <5 minutes | Timed test |

---

## 18. Build Notes / Estimate

Release procedure takes ~30 minutes when all build gates already pass.

| Step | Time |
|------|------|
| Pre-release checklist | 5 min (if build already clean) |
| Version bump + changelog | 10 min |
| Tag + push | 2 min |
| Post-release smoke test | 10 min |
| Total | ~30 min |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Pre-release | All 6 build gates | 6 |
| Smoke | Post-release example tasks | 3 |
| Rollback | Revert to previous tag + verify | 1 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Build gate fails during pre-release | Release blocked | Fix before releasing |
| Tag pushed but smoke fails | Broken release in the wild | Immediate rollback + patch release |
| Changelog forgotten | Untraceable release | Pre-tag checklist enforces changelog |
| Wrong semver (MINOR vs MAJOR) | Consumer breakage | Corrective MAJOR release immediately |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| SOP-101 | Build gates must pass (pre-release checklist) |
| CORE-SOP-003 | Universal release procedure template |
| DEC-017 | Universal SOP numbering |

| Used By | Why |
|---------|-----|
| All Rondo consumers | Release is how they get updates |
| OB (Tier 3) | Records release events for tracking |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Semver for versioning | 2026-03-18 | Industry standard, clear breaking change signal |
| D2 | `rondo-vX.Y.Z` tag format | 2026-03-18 | Monorepo requires product prefix |
| D3 | No PyPI in v1 | 2026-03-18 | Git clone is sufficient for current distribution |
| D4 | Fix forward preferred over revert | 2026-03-18 | Reverts can lose unrelated commits |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should there be a release branch strategy? | Hotfix isolation | OPEN — not needed yet |
| Q2 | When should Rondo move to PyPI distribution? | Broader distribution | OPEN — when standalone repo exists |
| Q3 | Should release notes be auto-generated from commit messages? | Automation vs quality | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Semver** | Semantic versioning — MAJOR.MINOR.PATCH |
| **MAJOR** | Breaking change to public API |
| **MINOR** | New feature, backward compatible |
| **PATCH** | Bug fix, backward compatible |
| **Smoke test** | Quick post-release verification that basic functionality works |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Release breaks overnight automation | Low | Lost overnight run | Post-release smoke includes overnight test |
| Tag points to wrong commit | Low | Wrong code released | Verify with `git log` before push |
| Rollback loses recent commits | Low | Lost work | Fix forward preferred, rollback only for emergencies |

---

## 26. External Scan

Release procedure follows Python packaging best practices. Similar to Poetry release
workflow and pip-tools release cycle. Tag prefix pattern borrowed from monorepo conventions
(Lerna, Nx). Changelog format follows Keep a Changelog (keepachangelog.com).

---

## 27. Security Considerations

- Releases should be tagged with signed commits (`git tag -s`) when GPG is configured.
- No credentials included in release artifacts.
- Pre-release security scan (bandit) ensures no new vulnerabilities ship.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Release time | <30 minutes | From "ready to release" to "done" |
| Rollback time | <5 minutes | Git checkout + pip install |
| Post-release smoke | <10 minutes | Example tasks with mock providers |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not applicable — this is a release procedure SOP.

---

## 31. AI Went Wrong

Not applicable — this is a release procedure SOP.

---

## 32. AI Assumptions

Not applicable — this is a release procedure SOP.

---

## 33. AI Cost

Not applicable — this is a release procedure SOP.

---

## 34. Notes

- The "fix forward" preference (D4) is critical. Reverting commits in a shared repo can
  lose unrelated work. A patch release (X.Y.Z+1) that fixes the specific issue is safer.
- Rondo's eventual move to a standalone repo will change this procedure: PyPI publishing,
  separate CI/CD, release branches. This SOP will be updated when that happens.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Release procedure | THEORY | Specced but Rondo not yet released | Phase 2 build |
| Version bump protocol | THEORY | Specced for semantic versioning | Phase 2 build |
| Release checklist | THEORY | Specced for pre-release verification | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal CORE-SOP-003 for Rondo. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
