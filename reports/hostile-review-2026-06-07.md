# Hostile Re-Review — SOP-106 Rubric — 2026-06-07

**Sprint:** RONDO-346 (measure only) | **Method:** same as RONDO-339 — one
hostile prompt + verified dossier → 3 AIs via `rondo_multi_review`
(gemini-2.5-flash, gpt-4.1, grok-3). Cost ~$0.03.
**Prior:** 3.13 mean (RONDO-339, 2026-06-06).

---

## TL;DR

| Metric | 2026-06-06 | 2026-06-07 |
|--------|-----------|-----------|
| Panel mean | 3.13 | **~3.5** (gemini 3.55 · openai 3.50 · grok: no numeric, "still below, multiple <7.5") |
| Gate | FAIL | FAIL |
| Verdict (unanimous) | publish-gated | **still publish-gated** |

The mean moved **+0.4** — small, exactly as predicted. Engineering moved the
dimensions it *could*; five dimensions stay floored because the repo is
private/unpublished, and those dominate the average.

---

## Per-dimension (the two AIs that scored numerically)

| # | Dimension | 06-06 | Gemini | OpenAI | Move |
|---|-----------|-------|--------|--------|------|
| 1 | Install | 0.67 | 0 | 0 | flat (private) |
| 2 | First hour | 4.33 | 6.0 | 2 | mixed |
| 3 | Security | 5.33 | 1 | 4 | down (no CI to verify public-cut) |
| 4 | Error UX | 4.67 | 6.5 | 7 | **UP** |
| 5 | Docs | 7.33 | 0 | 3 | down — see note |
| 6 | Portability | 0.00 | 3 | 3 | **UP** (Linux proof; CI caps it) |
| 7 | Packaging | 0.33 | 0 | 0 | flat (not on PyPI) |
| 8 | Community | 1.67 | 3 | 2 | slight up (LICENSE) |
| 9 | **API stability** | 1.33 | **10** | **8** | **+~7.7 — the big win** |
| 10 | Operational | 5.67 | 6 | 6 | slight up |

## What this proves

- **Engineering CAN move the needle.** Dim 9 went 1.33 → ~9 — RONDO-340's
  API-STABILITY.md + lock + deprecation policy landed exactly as intended.
  Dims 4 and 6 also rose on real work (error-UX honesty, Linux proof).
- **But the mean is publish-gated.** Dims 1, 5, 7, 8 (and 3's verification)
  cannot rise while private. They drag the average to ~3.5 no matter how
  good the engineering. This is not a contradiction — it's the rubric
  measuring a *stranger's* reality, and the release hasn't happened.
- **All three AIs independently flagged the Mistral 429 gap** (dim 10) — the
  9 lost votes from the live panel. That's the one purely-engineering item
  on the board → RONDO-347 next.

## Honesty notes

- **Grok returned no per-dimension scores this run** (only issues/verdict) —
  the panel mean is from gemini+openai. Recorded, not hidden.
- **Dim 5 (Docs) dropped 7.33 → 0-3** despite docs IMPROVING. This is a
  grader-stance shift: this round they scored "private repo = strangers
  can't read the docs = absent," where RONDO-339 graded doc quality. Not a
  regression — a reminder the rubric is stranger-relative.

## The honest position

~3.5 measured. Engineering work is paying off where it's allowed to
(API stability proves it). The path to 7.5+ is now unambiguous and almost
entirely **Mark's publish decisions**: public repo + PyPI name + CI matrix +
CHANGELOG. One pure-engineering item remains (Mistral retry, RONDO-347).
