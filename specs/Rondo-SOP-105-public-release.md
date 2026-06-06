# Rondo-SOP-105: Public Release — the road from 4.5 to 9

*The "usable by a stranger" definition of done that never existed — now it does.*

**Product:** Rondo
**Category:** SOP
**Created:** 2026-06-06 (night shift, Mark's directive: "usable for everyone")
**Status:** DESIGNED
**Version:** 0.3
**Owner:** Mark G. Hubers
**Sources synthesized:** Cursor hostile review (reports/cursor-review-2026-06-05.md, scored 7/10 owner · 4.5/10 public) + Cold Witness panel of 3 independent AIs (reports/cold-witness-public-release-2026-06-06.md: gemini-pro, gpt-5.5, mistral-large) + campaign findings #284-#301.

---

## 1. The one-sentence truth all four AIs agreed on

> "The biggest gap is not model-routing sophistication; it is **operational trust
> for unknown users, unknown machines, unknown keys, and hostile inputs**." (gpt-5.5)

The engine is confirmed good ("competent, unusually disciplined" — hostile reviewer).
Public-readiness is a **finite list of packaging/trust labor**, not redesign.

## 2. DEFINITION OF DONE: "Usable by a stranger"

A person who has never met Mark, on Linux or Windows, with only PyPI and the README:

1. `pipx install rondo` (or pip/uv) → `rondo init` → guided first run **< 10 minutes**
2. Adds ONE provider key via env var or wizard — no macOS Keychain required
3. Runs a golden example and gets structured JSON — without reading a spec
4. Cannot be harmed by a downloaded round file without an explicit, loud opt-in
5. Knows what version they have, what's stable, and where to report a bug
6. CI (not Mark's laptop) proves the suite green on 3 OSes before every release

Score target: independent hostile re-review ≥ 8/10 public.

## 3. THE PHASED WORK LIST

### P1 — FOUNDATION (blocks everything; all 4 AIs ranked these top)

| ID | Item | Effort | Consensus |
|----|------|--------|-----------|
| P1-1 | **Cross-platform credentials** — ✅ VERIFIED ALREADY BUILT (2026-06-06): env-first chain with all 5 standard names → Keychain → 1Password. Remaining: optional `keyring` lib for Win/Linux secure storage | M | 4/4 |
| P1-2 | **Cross-platform config**: XDG base dirs (`~/.config/rondo`), project-local `rondo.toml`, env overrides; `~/.rondo` honored as legacy | M | 3/4 |
| P1-3 | **Round-file trust model** — ✅ DONE (RONDO-330, 2026-06-06): `.py` rounds + phases files gated at the EXECUTOR; `--allow-python-rounds` or `[security] allow_python_rounds`; loud 3-option refusal; template ships deny-by-default; proven live on a config-less machine | M | 4/4 |
| P1-4 | **CI**: GitHub Actions matrix (Linux/macOS/Windows × Py 3.12+), repo-fixture corpus gates (NOT local-only — Cursor's indictment), release automation | M | 4/4 |
| P1-5 | **Packaging**: PyPI + pipx; console entry point already exists; name collision check ("rondo" on PyPI?) | M | 4/4 |
| P1-6 | **Public cut excludes**: the Max-plan `--auth max` subprocess pattern (Mark's standing concern) ships disabled/undocumented in public builds | S | brief |

### P1 additions (Cursor roadmap pass, 2026-06-06)

| ID | Item | Effort |
|----|------|--------|
| P1-7 | Secrets redaction GUARANTEE — ✅ CORE DONE (RONDO-321): artifact-level tests over audit+notify; 2 real holes fixed. Remaining: `rondo config --show` (doctor shows last-4 today) | M |
| P1-8 | Dependency policy: zero-dep core + optional extras (`rondo[openai]`…), documented | S |
| P1-9 | CLI contract: actionable errors (no raw tracebacks), stable exit codes, strict stdout/stderr split, `--json` never mixes logs | M |
| P1-10 | Split-brain documented honestly: what's API-only vs subprocess-only and why (matrix/streaming/effort) | S |
| P1-11 | Cost guardrails impossible to misunderstand: worst-case preview before run, caps on by default, cancellation + partial-results semantics | M |

### P2 — ONBOARDING (the first 10 minutes)

| ID | Item | Effort |
|----|------|--------|
| P2-0 | `rondo doctor`: validate config/keys(redacted)/network/models/MCP + emit redacted support bundle for issue reports | M |
| P2-1 | `rondo init` first-run wizard: create config, pick ONE provider, validate key, run a smoke dispatch, point at golden examples (gpt-5.5's "first-run command") | M |
| P2-2 | Golden path: curate 5 "first hour" examples (the 85 stay; strangers need a guided 5) — README already sketches this sequence | S |
| P2-3 | Docs-for-strangers pass: define bespoke terms at first use (round, experiment matrix, smart return, COALESCE); beginner quickstart that assumes nothing | M |
| P2-4 | CLI error UX: user errors get friendly messages, never raw tracebacks (gemini) | M |
| P2-5 | Windows/Linux path + notification fallbacks (osascript is macOS-only) | M |

### P3 — TRUST & SUPPORT (what makes strangers stay)

| ID | Item | Effort |
|----|------|--------|
| P3-1 | SemVer + CHANGELOG (Keep-a-Changelog) + deprecation policy | S |
| P3-2 | API stability contract: which surfaces are stable (CLI, MCP tools, envelope) vs internal | M |
| P3-3 | Community files: LICENSE (choose!), CONTRIBUTING, Code of Conduct, issue/PR templates | S |
| P3-4 | SECURITY.md + the trust model documented; secrets-handling statement; telemetry stance (none) | S |
| P3-5 | MCP server hardening notes (no authn today — document the local-only assumption loudly) | S |
| P3-6 | Independent hostile re-review gate before launch (this worked; institutionalize it) | S |

### P4 — GROWTH (post-launch)

| ID | Item | Effort |
|----|------|--------|
| P4-1 | Homebrew formula; maybe a container image | M |
| P4-2 | Signed/curated "recipe packs" if round-sharing becomes a thing (gpt-5.5) | L |
| P4-3 | Per-task affinity, judge scoring, and the rest of the internal queue — features keep landing through the same spec/TDD pipeline | ongoing |

## 4. Sequencing rule

P1 before any announcement. P2 before any stranger is invited. P3 before the repo
goes public. P4 after real outside users exist. **The standalone-repo move
(`git/mhubers/rondo`, history-preserving subtree split) happens at the START of P1**
— public work happens in the public-bound repo. Backup (remote/bundle) precedes the move.

## 5. The three solo-dev publicization mistakes (panel) — and our answers

1. **"Works on my machine" blindness** → P1-4 CI matrix is the cure, nothing else is
2. **Assuming insiders' context in docs** → P2-3 stranger pass + P2-2 golden five
3. **Shipping the sharp edges** (arbitrary code paths, raw tracebacks) → P1-3 trust model + P2-4 error UX

## 6. Version History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.3 | 2026-06-06 | P1 scoreboard truth: P1-1 verified already built; P1-3 DONE (RONDO-330); P1-7 core done (RONDO-321); P2-0 doctor DONE (RONDO-320); P2-2 golden five DONE (RONDO-328). Honest public score movement: ~4.5 → ~6. |
| 0.2 | 2026-06-06 | Folded Cursor productization pass: doctor+support-bundle, redaction guarantee+tests, dependency-extras policy, CLI exit-code/stream contract, cost-UX, split-brain documentation. |
| 0.1 | 2026-06-06 | Initial synthesis: Cursor hostile review + 3-AI Cold Witness panel + findings #284-#301. The first written "usable by a stranger" definition of done. |
