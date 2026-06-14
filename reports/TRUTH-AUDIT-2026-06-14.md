# Truth Audit — front-door docs + specs (2026-06-14, RONDO-432)

**Goal (Mark's):** "make rondo a lot more better and truthful ... fix code and docs
and spec and remove any writing we said we have but not really in rondo."

**Method — three roles, no single party certifies its own work:**
1. **Author (Claude)** — inventory claims, fix code/docs/specs.
2. **Jury (gemini:high + grok:grok-4.3 via rondo)** — independently review; a DIFFERENT
   vendor than the author. Dogfoods rondo's own thesis (`docs/CROSS-VENDOR-JURY.md`) on rondo.
3. **Independent deep pass (Cursor)** — STAGED for 6/15 (quota); explores the repo on its
   own, priority target REQ-114 (Claude's own-work bias).

Every claim → locate ground truth (module / CLI flag / test) → classify → fix code-or-prose →
`bin/build` green + (for judgment calls) a different-vendor verdict → commit.

## What was found and fixed

### Batch 1 — stale numbers in front-door docs (commit 38c0253)
Two read-only scouts inventoried every checkable claim. Corrected against authoritative
sources (the code, NOT a reviewer's guess — several scout numbers were themselves wrong):

| Claim | Was | Truth | Authority |
|-------|-----|-------|-----------|
| examples | 85 / 92 / 107 | **101** | `generate_index.py --check` (lock) |
| tests | 1,404 / 2,610 / 2,798 | **2,817** | pytest collect |
| MCP tools | 23 | **27** | `@mcp.tool` count |
| CLI subcommands | 24 | **25** | api-stability lock regex |
| conventions classes | 43 | **29** | grep tests/conventions |
| commits | 694 | **743** | git rev-list |

`RONDO-REFERENCE.md` was a 2-month-old exhibit (dated 2026-04-05) → refreshed.
Where possible, prose now cites the lock-checked source so numbers can't re-drift.

**Verified NOT stale (scouts flagged, code disproved — left intact):** Opus-class thinking
+ streamed dispatch + event watchdog (`parse_stream_json_events`, `_run_with_watchdog` exist);
13 MCP examples (13 files); `verify-examples.sh` exists.

### Batch 2 — two capability overclaims in specs (commit 64c70e7)
- **REQ-114 req 032** named `examples/pipelines/release-notes.yaml` as "the proving
  pipeline" — that file does NOT exist. But the MUST (a runnable flagship ships with the
  feature) IS met by `claude-builder.yaml`. Pointed the spec at the real flagship; demoted
  release-notes.yaml to an explicitly NOT-BUILT "next pipeline" note.
- **REQ-108 template-promotion** described a full ADHOC→CANDIDATE→TEMPLATE→ARCHIVED
  lifecycle — NONE built (only a static `rondo_templates()` list; no `templates` CLI
  subcommand). Added a PARTIAL/NOT-BUILT banner naming exactly which reqs are design-only.

### Batch 3 — 22 stale spec Status fields (commit da7e255)
The "~45 unfinished specs" was a status-field lie. Per `SPEC-STATUS-TRUTH-2026-06-14.md`
(verified against modules/CLI/tests), flipped 21 specs DESIGNED/DRAFT/STUB → **BUILT
(verified 2026-06-14)** and 1 → PARTIAL — each gated by confirming the cited module exists
(zero skips, all 18 modules present). Untouched: the honestly-bannered NOT-BUILT/PARTIAL
specs + standards/SOP docs.

### Batch 4 — cross-vendor jury pass on the now-current docs (commit 2855929)
gemini + grok hostile-reviewed the edited README + START-HERE (author-bias check). Both
objected; triage:
- **REJECTED** (verified false): "Opus 4.8 hallucinated" (it's real; but made phrasing
  version-agnostic to dodge the doubt + drift), "CI claims nonexistent CI" (already under
  a "gated on Mark's decisions / NO git remote yet" table), "2026 dates are future" (grok's
  clock is stale).
- **ACCEPTED** (real): the watchdog "Open item" showed a week-old 85% as if current →
  refreshed to the live all-time rate **81.4% (2,453/3,015)**, date-stamped, noted most
  failures are transient/external (rate-limit 255, provider-down 101, subprocess 104), and
  told the reader to re-check with `rondo metrics`.

**Jury lesson:** its value was forcing a LOOK, not being right — 2 of 3 objections did not
survive verification, 1 did. A juror that objects is not automatically correct; it is a
reason to go check.

## Residual / open
- **Cursor independent deep pass** — 6/15 (quota). The one auditor that is neither Claude
  nor a doc-only reviewer; explores the repo itself. Priority: REQ-114 (Claude bias).
- Genuinely-NOT-BUILT set unchanged (~6: multi-account, signed-receipts, ob-integration,
  quarantine-lifecycle, prompt-protection; oscillation is minimal). All honestly bannered.
- Numbers that are NOT lock-verified (test count, commit count) live only inside dated
  "verified <date>" snapshots — honest, but will need the date bumped on edits.

**Bottom line:** the say-do gap was almost entirely (a) stale numbers and (b) stale status
fields — not fabricated capabilities. The thesis cores (jury, verify, envelope, sanitize,
audit, pipeline) are real and tested. Two genuine capability overclaims existed (REQ-114
file name, REQ-108 lifecycle); both corrected. The docs now lead with claims that survive
a hostile check.
