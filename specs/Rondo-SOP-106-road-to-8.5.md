# Rondo-SOP-106: The Road to a Stable 8.5 — Execution Plan

**Product:** Rondo
**Category:** SOP (execution plan; the roadmap itself is SOP-105)
**Created:** 2026-06-06 (Mark's bar: "nothing under 7.5 releases; everything should be 8.5")
**Status:** ACTIVE
**Version:** 0.1
**Owner:** Mark G. Hubers
**Depends on:** Rondo-SOP-105 (roadmap + P-items), VER-100 (verification map)

---

## 1. What 8.5 MEANS — the scoring instrument

A score without a fixed rubric is vibes. The instrument:

**Panel:** Cursor hostile review + 3 independent AIs (the SOP-105 method that
produced the original 4.5) — same prompt frame, blind to prior scores.

**Rubric — 10 dimensions, each 0-10, evenly weighted:**

| # | Dimension | 8.5 looks like |
|---|-----------|----------------|
| 1 | Install (stranger, 3 OSes) | pipx → first run < 10 min, no surprises |
| 2 | First hour | Golden five works verbatim; failures explain themselves |
| 3 | Security/trust | No silent code exec; secrets provably can't leak; public cut verified |
| 4 | Error UX | Contract envelope everywhere; zero raw tracebacks; stable exit codes |
| 5 | Docs for strangers | Terms defined at first use; examples ARE docs and all run |
| 6 | Portability | CI green Linux/macOS/Windows; XDG; no mac-only assumptions |
| 7 | Packaging | PyPI, versioned, SemVer + CHANGELOG, name resolved |
| 8 | Community/support | LICENSE, SECURITY.md, CONTRIBUTING, issue templates, doctor --bundle |
| 9 | API stability | Stable surfaces declared; deprecation policy |
| 10 | Operational trust | Watchdog/canary/drift live; reliability scoreboard honest |

**Release gate:** panel mean ≥ 8.5 AND no dimension below 7.5
(Mark's floor applies per-dimension — one rotten leg fails the chair).

## 2. Current honest position (2026-06-06)

~6.5 mean. Strong: 3, 4, 10 (likely 8+ already). Weak: 6, 7, 8 (≤4 — they
mostly don't exist yet, and CANNOT exist without the repo move).

## 3. The gap plan — every item with its verification

### Phase C-now (no repo move needed; self-serve)

| Item | Sprint | Dim | Verification |
|------|--------|-----|--------------|
| Dead-flag standing lock | RONDO-333 ✓ | 4 | tests/conventions/test_dead_flags.py (first run caught --no-refresh) |
| Auto-retry ×1 on ERR_STREAM_DISCONNECT | RONDO-334 | 10 | hermetic retry test + forensics record of the retry |
| Error-UX sweep: zero raw tracebacks on user errors, exit codes documented in --help epilog | RONDO-335 | 4 | a conventions test greps every `except` print-path; manual sweep of run/live/overnight/matrix CLI errors |
| P2-3 stranger docs pass: define round/matrix/smart-return/COALESCE at first use; kill insider jargon | RONDO-336 | 5 | docs-drift stays green + a fresh-eyes AI read-through scores ≥8 on "could a stranger follow this" |
| SECURITY.md + CONTRIBUTING.md + trust-model doc drafts | RONDO-337 | 8 | files exist, cross-linked from README; LICENSE row stays Mark-only |
| Split-brain honesty doc (P1-10): API-only vs subprocess-only table | RONDO-337 | 5 | one table in README/REFERENCE, verified against code |

### Phase B-gated (needs Mark's decisions + repo move)

| Item | Needs | Dim |
|------|-------|-----|
| Repo move to git/mhubers/rondo (backup bundle FIRST) | Mark's go | — |
| GitHub Actions: Linux/macOS/Windows × py3.12-3.14 | repo | 6 |
| PyPI publish under chosen name (`rondo` TAKEN; rondo-ai / rondo-dispatch free) | Mark's name pick | 7 |
| LICENSE | Mark's pick | 8 |
| SemVer + CHANGELOG + deprecation policy | repo | 7, 9 |
| Public-cut wheel build with PUBLIC_BUILD=True + verify auth=max refused | repo CI | 3 |
| **Hostile re-review with the rubric above** | all of the above | gate |

### Explicitly deferred (not blocking 8.5)

req 606 auto-apply (awaiting Mark's 3 answers) · chunked streaming (needs a
second ~1800s forensic) · context-limits table (verified numbers needed) ·
project-local rondo.toml merge.

## 4. Honest estimate

Phase C-now: ~4 sprints of real TDD work. Phase B-gated: ~2-3 days of
packaging/CI labor once decisions land. The re-review is cheap (~$0.15,
the SOP-105 panel method). Nothing here is research-risk; it's discipline
labor — the kind this codebase has been eating for breakfast.

## 5. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-06-06 | Initial: the 10-dimension rubric (8.5 mean + 7.5 per-dimension floor), gap plan C-now vs B-gated, honest current position ~6.5. |
