# START HERE — Rondo standalone repo

**Updated:** 2026-06-06 (post RONDO-339/340) | **State:** independent + green

## Where this repo came from

Split from `~/git/mhubers/ace2/rondo/` with **full history preserved**
(611+ commits). The ace2 copy is FROZEN (see its POINTER.md). Backups:
3 verified git bundles (internal + BKUP_DATA_A + BKUP_DATA_B).

## Current health (verified 2026-06-06)

| Check | Result |
|-------|--------|
| Full suite, own venv, zero ace2 ties | 2,218 passed, 0 failed |
| Own 6-gate build (`bin/build`) | green (see git log) |
| `rondo doctor` from installed tool | 6/6 PASS |
| Docs drift + examples index | clean |
| Conventions locks (incl. new API-stability lock) | 39 green |

## What Rondo is right now (the 25-sprint campaign, RONDO-313→337)

Self-watching multi-provider dispatch: nightly watchdog, model canary +
auto-tiers, docs-drift scanner, per-task learned routing, experiment matrix
with blind sealing + judge scoring, artifact-level secrets guarantee,
round-file trust gate, public-cut mechanism, error-envelope contract,
guided failures, dead-flag lock. Full record:
`reports/NIGHT-SHIFT-2026-06-05.md` (morning report at top).

## Mark's release bar — and the measured position

**Nothing ships under 7.5/10; target 8.5** — scored by the 10-dimension
hostile-review rubric in `specs/Rondo-SOP-106-road-to-8.5.md`.

**Measured 2026-06-06 (RONDO-339):** 3-AI hostile panel scored **3.13 mean,
all 10 dimensions under the 7.5 floor** — full evidence in
`reports/hostile-review-2026-06-06.md`. The engineering evidence was
accepted; the score is floored because 5 of 10 dimensions cannot rise
while the repo is private and unpublished.

**Banked since the review (RONDO-340, fix #3 of the report):**
- `docs/API-STABILITY.md` — stable surface declared (24 CLI commands,
  25 MCP tools, config keys) + deprecation policy, drift-locked by
  `tests/conventions/test_api_stability.py` (dim 9)
- RONDO-335 error-UX sweep LIVE-VERIFIED and marked in SOP-106 (dim 4)
- LICENSE file (MIT) — fixes the pyproject contradiction (dim 8, partial)
- **Watchdog ARMED 2026-06-06** (Mark's go): launchd job
  `com.rondo.nightly-watchdog`, daily 3:00 AM, verified loaded + canary
  sweep run live (dim 10). First sweep ALERTED: 7d reliability 85% < 95%
  target (62 dispatches) — open item below.

## What's next — ALL gated on Mark's decisions

Nothing left on the score is self-serve. Each row needs Mark's word first:

| Decision | Unlocks (dim) | Panel-estimated gain |
|----------|---------------|----------------------|
| Publish go (public repo + PyPI) | 1 Install, 7 Packaging, 8 Community | ~+2.0 mean |
| PyPI name (`rondo` TAKEN; rondo-ai / rondo-dispatch free) | 7 | part of above |
| CHANGELOG + SemVer adoption at publish | 7, 9 | part of above |
| CI matrix: GitHub Actions Linux/macOS/Windows × py3.12-3.14 | 6 Portability, 3 public-cut verify | ~+1.0 mean |
| req 606 auto-apply (3 questions in `specs/Rondo-DESIGN-registry-auto-apply.md`) | `learn` exits experimental | — |

**Open item (found by the armed watchdog, first sweep):** 7-day dispatch
reliability is 85% vs the 95% target (62 dispatches). Triage via
`rondo audit --failed` — dim 10's "reliability scoreboard honest" means
fixing the rate, not the meter.

Deferred-by-evidence (unchanged): chunked streaming (needs a 2nd ~1800s
forensic), context-limits table refresh (needs verified numbers),
CORE-spec vendoring with drift check (before public).

After the gated work lands: re-run the RONDO-339 panel (same prompt frame,
`reports/hostile-review-2026-06-06.md` documents the method) — that re-score
is the real 8.5 measurement.

## Working in this repo

Read `CLAUDE.md` (the rules) and `CONTRIBUTING.md` (the locks as policy).
Sprint tracking stays in ace2's Flight Control via `ace-sprint` (in ~/bin).
