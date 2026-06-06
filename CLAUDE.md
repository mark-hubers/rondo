# Rondo — Claude Code Instructions (standalone repo)

**Rondo** = scripted AI dispatch: multi-provider, budgeted, audited, self-watching.
Split from the ace2 monorepo 2026-06-06 with full history (611+ commits).
Owner: Mark Hubers. **Nothing goes public/GitHub without Mark's explicit word.**

## When Mark says "rondo" (session start)
1. Read `START-HERE.md` — current state, where things are, what's next
2. Run `rondo doctor` (free) — is the install healthy
3. ASK what to work on. Do not start building unsolicited.

## Build & test (this repo is self-contained)
| Task | Command |
|------|---------|
| Full 6-gate build (run before EVERY commit) | `bin/build` |
| Full suite | `.venv/bin/pytest tests/ -q` |
| Conventions locks only (fast, run often) | `.venv/bin/pytest tests/conventions/ -q` |
| Lint/format | `.venv/bin/ruff check src/rondo/ tests/` / `ruff format` |
| Docs freshness | `rondo models --docs-drift` |
| Examples index | `python3 examples/generate_index.py --check` (regen: `--write` + bump count) |

## Sprint tracking (still lives in ace2 — by design)
- `ace-sprint register RONDO-NNN --layer FIX --orbit 5 --round 9` → `start` →
  activities (`--loop write_tests/implement/verify --cat test_write/code_edit/test_fix`)
  → `done --force` (the --type register flag is broken; --force at done is the accepted path)
- Tools in `~/bin/`; Flight Control DB in `~/git/mhubers/ace2/db/` — works from anywhere

## The non-negotiables (machinery-enforced; see CONTRIBUTING.md)
1. **TDD** — failing test first, always
2. **Conventions locks** (`tests/conventions/`): dead-flag lock (every CLI flag
   tested), complexity ≤15 (extract, never exempt), import layering, signatures
   (`~/bin/orbit-sign sign <file>` for new files), SPDX headers, VER-001 refs in tests
3. **Examples ARE docs** — a feature without a runnable example isn't done
4. **Honesty engineering** — error envelope everywhere, never fake data, partial
   results preserved, zero-collected tests = hard build failure
5. **Mocked seams get one UNMOCKED contract test** pinning the real shape
6. **Live-verify features** — run the real command/dispatch before claiming done
   (tiny canaries ~\$0.0001 are encouraged; log costs)
7. **Mark decides** — never suggest ending the session; ask before public actions

## Key docs (discovery map)
| What | Where |
|------|-------|
| Current state + next steps | `START-HERE.md` |
| The 8.5 release plan + scoring rubric | `specs/Rondo-SOP-106-road-to-8.5.md` |
| Public-release roadmap | `specs/Rondo-SOP-105-public-release.md` |
| Threat model | `SECURITY.md` |
| The rules as policy | `CONTRIBUTING.md` |
| Stranger first hour | `docs/GOLDEN-FIVE.md` |
| The 25-sprint campaign record | `reports/NIGHT-SHIFT-2026-06-05.md` |
| Verification map | `specs/Rondo-VER-100-verification.md` |

## Mark (accessibility — CRITICAL)
- Usher Syndrome Type 2: legally blind + deaf. **No blue links** — use
  `→ LINK: url` in code blocks. High contrast. Short paragraphs. Terminal over GUI.
- Types fast, spelling suffers: read intent, show "Got it:" + clean version, never
  slow him down. Plain-English parentheses after jargon.
- The frozen original lives at `~/git/mhubers/ace2/rondo/` (POINTER.md there).
