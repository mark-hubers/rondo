# Rondo — Claude Code Instructions

**Rondo** = scripted AI dispatch: multi-provider, budgeted, audited, self-watching.
Built with full history preserved (700+ commits). Maintainer: Mark Hubers.

## Session start
1. Read `README.md` and `docs/GETTING-STARTED.md` — what rondo is, how to run it
2. Run `rondo doctor` (free) — is the install healthy
3. Ask what to work on before making changes.

## Build & test (this repo is self-contained)
| Task | Command |
|------|---------|
| Full 6-gate build (run before EVERY commit) | `bin/build` |
| Full suite | `.venv/bin/pytest tests/ -q` |
| Conventions locks only (fast, run often) | `.venv/bin/pytest tests/conventions/ -q` |
| Lint/format | `.venv/bin/ruff check src/rondo/ tests/` / `ruff format` |
| Docs freshness | `rondo models --docs-drift` |
| Examples index | `python3 examples/generate_index.py --check` (regen: `--write` + bump count) |

## The non-negotiables (machinery-enforced; see CONTRIBUTING.md)
1. **TDD** — failing test first, always
2. **Conventions locks** (`tests/conventions/`): dead-flag lock (every CLI flag
   tested), complexity ≤15 (extract, never exempt), import layering, SPDX headers,
   spec-reference checks in tests
3. **Examples ARE docs** — a feature without a runnable example isn't done
4. **Honesty engineering** — error envelope everywhere, never fake data, partial
   results preserved, zero-collected tests = hard build failure
5. **Mocked seams get one UNMOCKED contract test** pinning the real shape
6. **Live-verify features** — run the real command/dispatch before claiming done
   (tiny canaries are encouraged; log costs)
7. **Maintainer decides** — ask before public-facing or irreversible actions

## Key docs (discovery map)
| What | Where |
|------|-------|
| Getting started | `docs/GETTING-STARTED.md` |
| The cross-vendor jury (the thesis) | `docs/CROSS-VENDOR-JURY.md` |
| How rondo scores itself | `docs/SCORING.md` |
| The 8.5 release rubric | `specs/Rondo-SOP-106-road-to-8.5.md` |
| Threat model | `SECURITY.md` |
| The rules as policy | `CONTRIBUTING.md` |
| Stranger's first hour | `docs/GOLDEN-FIVE.md` |
| Verification map | `specs/Rondo-VER-100-verification.md` |

## Accessibility (the maintainer's design spec, not a footnote)
- Mark has Usher Syndrome Type 2 (openly disclosed — see "Why It's Built This
  Way" in README.md). It drives rondo's terminal-first, no-surprises design.
- **No blue links** — use `→ LINK: url` in code blocks. High contrast. Short
  paragraphs. Terminal over GUI. Warn before anything opens a window.
- Plain-English parentheses after jargon.
