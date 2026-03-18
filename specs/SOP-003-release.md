# SOP-010: Release Procedure

*How to ship a new version of Rondo.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-SOP-010, Caliber-SOP-010, Rondo-SOP-010

---

## 1. Pre-Release Checklist

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

## 2. Version Bump

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

## 3. Changelog Update

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

## 4. Tag Creation

1. Format: `rondo-vX.Y.Z` (product prefix for monorepo)
   ```bash
   git tag -a rondo-vX.Y.Z -m "Rondo vX.Y.Z: brief description"
   ```

2. Push tag:
   ```bash
   git push origin rondo-vX.Y.Z
   ```

---

## 5. Build Artifact

Rondo produces:
- **Python package:** `pip install -e .` (editable, monorepo) or `pip install .` (standalone)
- **CLI tool:** `rondo` command (registered via `[project.scripts]` in pyproject.toml)
- **No PyPI upload** at this stage — Rondo is distributed via git clone

Future: Rondo is planned to become its own standalone repository. At that point, PyPI publishing may apply.

---

## 6. Post-Release

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

## 7. Rollback

If critical issues found after release:

1. Revert to previous tag:
   ```bash
   git checkout rondo-vPREVIOUS
   ```
2. Fix forward (preferred) or revert commits
3. Create patch release (X.Y.Z+1)

---

## 8. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal SOP-010 for Rondo. |
