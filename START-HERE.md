# START HERE — Rondo standalone repo

**Updated:** 2026-06-06 (split day) | **State:** independent + green

## Where this repo came from

Split from `~/git/mhubers/ace2/rondo/` with **full history preserved**
(611+ commits). The ace2 copy is FROZEN (see its POINTER.md). Backups:
3 verified git bundles (internal + BKUP_DATA_A + BKUP_DATA_B).

## Proven on split day

| Check | Result |
|-------|--------|
| Full suite, own venv, zero ace2 ties | 2,210 passed, 0 failed |
| Own 6-gate build (`bin/build`) | green (see git log) |
| `rondo doctor` from installed tool | 6/6 PASS |
| Docs drift | clean |

## What Rondo is right now (the 25-sprint campaign, RONDO-313→337)

Self-watching multi-provider dispatch: nightly watchdog, model canary +
auto-tiers, docs-drift scanner, per-task learned routing, experiment matrix
with blind sealing + judge scoring, artifact-level secrets guarantee,
round-file trust gate, public-cut mechanism, error-envelope contract,
guided failures, dead-flag lock. Full record:
`reports/NIGHT-SHIFT-2026-06-05.md` (morning report at top).

## Mark's release bar

**Nothing ships under 7.5/10; target 8.5** — scored by the 10-dimension
hostile-review rubric in `specs/Rondo-SOP-106-road-to-8.5.md`.
Honest current position: ~6.5-7.

## What's next (in order)

1. **CI** — GitHub Actions matrix (Linux/macOS/Windows × py3.12-3.14):
   blocked on Mark's GitHub decision (gold rule: nothing public without his word)
2. **Hostile re-review** against the SOP-106 rubric (the real 8.5 measurement)
3. Mark's open decisions: PyPI name (`rondo` TAKEN; `rondo-ai`/`rondo-dispatch`
   free) · LICENSE · arm the watchdog · req 606 auto-apply design (3 questions in
   `specs/Rondo-DESIGN-registry-auto-apply.md`)
4. Deferred-by-evidence: chunked streaming (needs a 2nd ~1800s forensic),
   context-limits table refresh (needs verified numbers), CORE-spec vendoring
   with drift check (before public)

## Working in this repo

Read `CLAUDE.md` (the rules) and `CONTRIBUTING.md` (the locks as policy).
Sprint tracking stays in ace2's Flight Control via `ace-sprint` (in ~/bin).
