# DESIGN: Registry Auto-Apply Mode — REQ-111 req 606

**Status:** PROPOSAL — needs Mark's decision before any code
**Created:** 2026-06-06 (night shift, RONDO-327 parallel work)
**Driver:** req 606 is MUST but unbuilt; `registry_mode()` currently downgrades
`auto` to `suggest` with a warning (RONDO-316 — honest gap, work request filed).
**Why a design doc:** auto mode WRITES to your config. That crosses the
Session 81 rule ("detection automated, fix manual — Rondo never edits config").
The spec carves an exception; the carve needs your sign-off on the mechanics.

---

## TL;DR

Auto mode maintains ONE Rondo-owned file (`~/.rondo/auto-tiers.toml`) and never
touches `config.toml`. Your file stays yours; the COALESCE makes the auto file
visible but always lower priority than anything you pinned.

## The core question you need to decide

Req 606 says auto mode modifies "auto-tier profiles." Two ways to build that:

| Option | How | Risk |
|--------|-----|------|
| **A. Separate file (RECOMMENDED)** | Rondo writes ONLY `~/.rondo/auto-tiers.toml` (regenerated on each refresh). `config.toml` is NEVER opened for write. Resolution: manual pin → auto-tiers file → collapse ladder (already built, req 610). | Near zero — your file untouchable by construction |
| B. In-place sections | Rondo edits `[profiles.auto_low/mid/high]` blocks inside `config.toml`, fenced by markers | TOML round-trip can mangle comments/format; one bug away from breaking the Session 81 rule |

Option A makes "never modifies user config" a STRUCTURAL guarantee instead of a
promise. Recommendation: A.

## Mechanics under Option A

1. `[registry] mode = "auto"` in config.toml (you opt in by hand — flipping this line is itself manual)
2. Each `rondo providers --refresh` (or nightly watchdog with refresh) re-derives
   auto-tiers (req 607 derivation already built + tested) and atomically rewrites
   `~/.rondo/auto-tiers.toml` with a header: generated-by, timestamp, source cache
3. Every change (old → new per tier) appended to the audit trail as a
   `registry_auto_change` record + surfaced in the morning report (req 606)
4. Dispatch resolution (already shipped as `resolve_model`, req 610):
   manual pin → auto-tier → collapse. Manual ALWAYS wins — unchanged
5. `rondo models --tiers` shows BOTH derived values and what the auto file
   currently holds, flagging any divergence

## What stays forbidden (hard guarantees)

- `config.toml` is never opened for writing by any Rondo code path
- User profiles (`ush_*` etc.) and `[providers.*]` pins are never consulted for writes
- A failed derivation NEVER clears the auto file (stale-but-working beats empty)
- Auto file failures degrade to suggest mode with a warning — never block dispatch

## Test plan (when approved)

- Structural: no `open(config_path, "w")` anywhere — a conventions lock greps for it
- Atomic write + header round-trip; failed refresh preserves prior file
- Audit record emitted per tier change; morning report line present
- COALESCE precedence: pin beats auto file beats ladder (extends test_auto_tiers.py)

## Your decision

1. Option A (separate file) vs B (in-place sections)?
2. Should the nightly watchdog auto-refresh the auto file, or only explicit `--refresh`?
3. Want a `rondo models --apply` manual middle ground (prints diff, asks nothing, writes the auto file once) before full auto?
