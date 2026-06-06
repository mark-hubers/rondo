# Hostile Re-Review — SOP-106 Rubric — 2026-06-06

**Sprint:** RONDO-339 (measure only — no code changed)
**Method:** ONE hostile prompt + verified evidence dossier → 3 external AIs via
`rondo_multi_review` (gemini:gemini-2.5-flash, openai:gpt-4.1, grok:grok-3).
Reviewers instructed: assume overhyped, cite dossier evidence for every score,
absence of evidence = absent, do not round up.
**Cost:** ~$0.028 actual (gemini $0.0015 + gpt-4.1 $0.0158 + grok-3 $0.0106),
logged in ~/.rondo/audit/. Cap was $0.50.
**Gate (SOP-106):** panel mean ≥ 8.5 AND no dimension below 7.5.

---

## TL;DR

| Metric | Result |
|--------|--------|
| Panel mean | **3.13 / 10** (gemini 2.6 · openai 3.3 · grok 3.5) |
| Gate | **FAIL** — mean and floor both |
| Dimensions under 7.5 (any AI) | **ALL 10** |
| Unanimous verdict | Not public = not installable = dims 1/6/7/8 score near zero |

The panel scored far below the internal ~6.5 estimate because the rubric
measures a STRANGER's reality: a private, unpublished, macOS-only repo cannot
score on install, portability, packaging, or community no matter how good the
engineering is. Dims 1, 6, 7, 8, 9 are blocked on Mark's open decisions
(GitHub go, PyPI name, LICENSE), not on engineering.

---

## Results: dimension × AI

| # | Dimension | Gemini | OpenAI | Grok | Dim mean | <7.5? |
|---|-----------|--------|--------|------|----------|-------|
| 1 | Install | 0 | 0 | 2 | 0.67 | ⚠ ALL |
| 2 | First hour | 3 | 5 | 5 | 4.33 | ⚠ ALL |
| 3 | Security/trust | 5 | 5 | 6 | 5.33 | ⚠ ALL |
| 4 | Error UX | 4 | 6 | 4 | 4.67 | ⚠ ALL |
| 5 | Docs for strangers | 6 | 7 | 9 | 7.33 | ⚠ gemini, openai |
| 6 | Portability | 0 | 0 | 0 | 0.00 | ⚠ ALL |
| 7 | Packaging | 0 | 1 | 0 | 0.33 | ⚠ ALL |
| 8 | Community/support | 3 | 1 | 1 | 1.67 | ⚠ ALL |
| 9 | API stability | 0 | 2 | 2 | 1.33 | ⚠ ALL |
| 10 | Operational trust | 5 | 6 | 6 | 5.67 | ⚠ ALL |
| | **AI mean** | **2.6** | **3.3** | **3.5** | **3.13** | |

Every dimension was scored under 7.5 by at least one AI. Dimension 5 (docs)
is the only one whose mean clears 7.5 — and only because Grok gave it a 9
("strong but irrelevant until install and portability exist").

---

## Evidence cited per dimension (panel consensus)

| # | Dimension | Evidence the panel cited |
|---|-----------|--------------------------|
| 1 | Install | Private repo, not on PyPI — clone + local venv is the only path; pipx impossible |
| 2 | First hour | docs/GOLDEN-FIVE.md + 58 examples exist, BUT a stranger can't install to reach them; RONDO-335 error-UX completion not marked |
| 3 | Security/trust | SECURITY.md present; public-cut mechanism (PUBLIC_BUILD) per reports/NIGHT-SHIFT-2026-06-05.md; BUT the "verify auth=max refused" check needs CI that doesn't exist |
| 4 | Error UX | docs/ERROR-ENVELOPE-CONTRACT.md documented; BUT RONDO-335 (zero raw tracebacks, exit codes in --help) only PLANNED in specs/Rondo-SOP-106 — no completion mark |
| 5 | Docs | 20 docs/ files, 58 runnable examples, examples/generate_index.py --check PASSES, docs-drift PASSES — strongest dimension |
| 6 | Portability | NO .github/workflows, never tested Linux/Windows, ~/.rondo not XDG, macOS-only — all three scored 0 |
| 7 | Packaging | pyproject license="MIT" but NO LICENSE file; PyPI name "rondo" TAKEN; not published; no CHANGELOG; no SemVer/deprecation doc |
| 8 | Community | SECURITY.md + CONTRIBUTING.md exist; NO LICENSE, NO CODE_OF_CONDUCT, NO issue templates, NO public repo |
| 9 | API stability | 0.7.0 pre-1.0; no declared stable surface; no deprecation policy |
| 10 | Operational trust | watchdog implemented but NOT ARMED; canary/auto-tier/audit/cost-tracking live; rondo doctor 6/6 today |

---

## Per-AI verdicts (verbatim)

**Gemini (mean 2.6):** "The project fails the 8.5 mean gate and has all
dimensions below 7.5, primarily due to its complete lack of public readiness
and installability."

**OpenAI (mean 3.3):** "Fails the 8.5 gate; the single biggest reason is total
lack of installability and portability for strangers (private, macOS-only,
not on PyPI, no CI)."

**Grok (mean 3.5):** "Fails the 8.5 gate because packaging, portability, CI,
and public availability are entirely absent."

---

## Top 3 fixes by score movement

| # | Fix | Dims moved | Est. mean gain |
|---|-----|-----------|----------------|
| 1 | **Publish bundle** — Mark's go: public repo + PyPI under chosen name (rondo-ai / rondo-dispatch) + LICENSE file + CHANGELOG. Pure decision + ~1 day labor | 1: 0.67→~8 · 7: 0.33→~8 · 8: 1.67→~8 (also lifts 2, 5) | **~+2.0** |
| 2 | **CI matrix** — GitHub Actions Linux/macOS/Windows × py3.12-3.14, plus XDG data dirs. Also unblocks dim 3's public-cut verify check | 6: 0→~7.5 · 3: 5.33→~7.5 | **~+1.0** |
| 3 | **Paper the maturity** — declare stable API surface + deprecation policy (dim 9); arm the watchdog (dim 10); mark RONDO-335 error-UX sweep VERIFIED in SOP-106 with evidence (dim 4) | 9: 1.33→~7 · 10: 5.67→~8 · 4: 4.67→~7.5 | **~+0.9** |

All three together: ~3.13 → ~7.0-7.5. Matches SOP-106's own Phase B-gated
analysis — the gap is decisions + packaging labor, not research risk.

**Note on the internal ~6.5 estimate:** the panel doesn't contradict the
engineering quality (dims 3, 4, 5, 10 evidence was accepted as real). It
contradicts the WEIGHTING — five of ten dimensions cannot score above ~2
while the repo is private. The rubric is a release gate, and the release
hasn't happened. That is the honest reading.

---

## Raw dossier facts fed to the panel (all verified 2026-06-06)

- 2,210 tests pass, own venv; 34 conventions-lock tests green in 1.0s
- 58 runnable examples, index check PASS; docs-drift PASS; 20 docs/ files
- rondo doctor 6/6 PASS; 5 provider keys loadable
- PRESENT: SECURITY.md, CONTRIBUTING.md
- MISSING: LICENSE (despite pyproject license="MIT"), CHANGELOG.md,
  .github/workflows, CODE_OF_CONDUCT.md, issue templates
- Not on PyPI; "rondo" name taken; watchdog not armed; macOS-only; pre-1.0
