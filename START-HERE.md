# START HERE — Rondo standalone repo

**Updated:** 2026-06-14 (RONDO-419→431) | **State:** independent + green (2,817 tests)

**Thesis:** the cross-vendor jury — the AI that writes the code doesn't certify it,
a *different* vendor does (`docs/CROSS-VENDOR-JURY.md`, live: `examples/api/controlled_review_loop.py`).

**Honest rating:** an independent cross-vendor panel scored it **3-4/10 as it was
positioned ("another agent loop"), ~7/10 reframed around the jury + published proof**
(`reports/competitive/LANDSCAPE-2026-06-13.md`). The earlier "7/10 hostile-verified"
was an internal score; the external read is lower until the reframe lands. A
spec→code→test self-audit (`reports/SELF-AUDIT-2026-06-13.md`) found + fixed 4 real
conformance overclaims — the MUST cores (scrub/audit/verify/pipeline) are real and
tested; some SHOULD-level CLI reqs are honestly marked NOT BUILT / PARTIAL.

## Where this repo came from

Split from `~/git/mhubers/ace2/rondo/` with **full history preserved**
(611+ commits). The ace2 copy is FROZEN (see its POINTER.md). Backups:
3 verified git bundles (internal + BKUP_DATA_A + BKUP_DATA_B).

## Current health (verified 2026-06-14)

| Check | Result |
|-------|--------|
| Full suite, own venv, zero ace2 ties | 2,817 tests collected, build green |
| Own 6-gate build (`bin/build`) | green before every commit (743 commits) |
| `rondo doctor` from installed tool | 6/6 PASS |
| Docs drift + examples index (101) | clean (`generate_index.py --check`) |
| Conventions locks | 30 classes green |
| Mutation kill-rates (reproduce: `bin/mutate <module>`) | from the RONDO-416→418 hardening — spool 97 / envelope 98 / history 100 / sanitize 97 / dispatch_parse 97% (see `reports/LIVE-TESTING-2026-06-12.md`) |

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

**Trajectory (same hostile instrument, fixes verified in code each time):**
3.13 (panel, Jun 6) → 5 → 6 → **7/10** (Jun 10, `reports/cursor-reviews/
review-20260610-184904.md`). The four-day climb is the ROAD-TO-8 campaign:
`reports/ROAD-TO-8.md` — every engineering item CLOSED (rounds 1 + 2,
RONDO-391→405): quarantine-on-scrub-failure, advisory path under the
machinery with scope honesty, every artifact born 0o600, per-class +
auth-class budget estimates, bounded cross-process locks with TTL hygiene,
reconcile under the audit file's own flock, complete scrub set, bounded
in-memory cache, pure plan_only previews, mutation-gate baseline guard.
The score remains floored by private/unpublished status — ~5 of 10 panel
dimensions cannot rise until the publish decision (Mark's alone).

**Banked since the review (RONDO-340, fix #3 of the report):**
- `docs/API-STABILITY.md` — stable surface declared (25 CLI commands,
  27 MCP tools, config keys) + deprecation policy, drift-locked by
  `tests/conventions/test_api_stability.py` (dim 9)
- RONDO-335 error-UX sweep LIVE-VERIFIED and marked in SOP-106 (dim 4)
- LICENSE file (MIT) — fixes the pyproject contradiction (dim 8, partial)
- **Watchdog ARMED 2026-06-06** (Mark's go): launchd job
  `com.rondo.nightly-watchdog`, daily 3:00 AM, verified loaded + canary
  sweep run live (dim 10). First sweep ALERTED: 7d reliability 85% < 95%
  target (62 dispatches) — open item below.

## What's next — ALL gated on Mark's decisions

Self-serve engineering is DONE (ROAD-TO-8 rounds 1+2 closed 2026-06-10).
Open: the round-2 re-score needs an instrument (Cursor quota resets 6/15;
alternatives: a Cursor spend limit, or a rondo cloud panel with an
instrument-change note). NOTE: this repo has NO git remote yet — creating
one is part of the publish decision below. Each row needs Mark's word first:

| Decision | Unlocks (dim) | Panel-estimated gain |
|----------|---------------|----------------------|
| Publish go (public repo + PyPI) | 1 Install, 7 Packaging, 8 Community | ~+2.0 mean |
| PyPI name (`rondo` TAKEN; rondo-ai / rondo-dispatch free) | 7 | part of above |
| CHANGELOG + SemVer adoption at publish | 7, 9 | part of above |
| CI matrix: GitHub Actions Linux/macOS/Windows × py3.12-3.14 | 6 Portability, 3 public-cut verify | ~+1.0 mean |
| req 606 auto-apply (3 questions in `specs/Rondo-DESIGN-registry-auto-apply.md`) | `learn` exits experimental | — |

**Open item (armed watchdog; first flagged 2026-06-06):** dispatch reliability
sits below the 95% target. As of 2026-06-14 the all-time success rate is **81.4%
(2,453/3,015 dispatches)** — but most failures are transient/external, not rondo
logic: `ERR_RATE_LIMIT` (255), `ERR_PROVIDER_DOWN` (101), `ERR_SUBPROCESS` (104).
Triage via `rondo audit --failed`; dim 10's "reliability scoreboard honest" means
fixing the rate (retry/backoff coverage of the transient classes), not the meter.
Re-check the live number with `rondo metrics` — do not trust this snapshot.

Deferred-by-evidence (unchanged): chunked streaming (needs a 2nd ~1800s
forensic), context-limits table refresh (needs verified numbers),
CORE-spec vendoring with drift check (before public).

After the gated work lands: re-run the RONDO-339 panel (same prompt frame,
`reports/hostile-review-2026-06-06.md` documents the method) — that re-score
is the real 8.5 measurement.

## Working in this repo

Read `CLAUDE.md` (the rules) and `CONTRIBUTING.md` (the locks as policy).
Sprint tracking stays in ace2's Flight Control via `ace-sprint` (in ~/bin).
