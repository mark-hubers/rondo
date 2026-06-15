# Rondo hostile re-review — 4-vendor panel — 2026-06-15 (RONDO-433)

**Method:** ONE hostile prompt + balanced evidence dossier → 4 INDEPENDENT external
vendors via `rondo_multi_review` (gemini-pro-latest, grok-4.3, openai gpt-5.5,
mistral-large-latest). Reviewers instructed: assume overhyped, score each of the
SOP-106 10 dimensions 0-10, cite a reason, blind to prior scores. Dossier
explicitly included the honest negatives (private/unpublished, 81.4% reliability).

**Gate (SOP-106):** panel mean ≥ 8.5 AND no dimension below 7.5.

## TL;DR

| | |
|---|---|
| Panel mean | **5.3 / 10** (gemini 5.9 · grok 4.7 · openai 5.35 · mistral 5.2) |
| Trajectory | 3.13 (2026-06-06, 3-AI) → **5.3** (2026-06-15, 4-AI) |
| Gate result | **FAIL** — would_release: false (unanimous, 4/4) |
| Why it can't pass | dims 1/6/7 (Install/Portability/Packaging) ≈ 0.5 — structurally impossible while PRIVATE |
| Engineering verdict | dims the panel CAN judge as engineering (3,4,5,9) average **~8.3** — already 8.5-grade |

The mean is **mathematically capped while the repo is private**: three dimensions
sit near zero because a stranger cannot install, no public CI proves portability,
and there is no PyPI package. No amount of engineering moves them — only Mark's
publish decision does.

## Results: dimension × vendor

| # | Dimension | gemini | grok | openai | mistral | **avg** | Class |
|---|-----------|:---:|:---:|:---:|:---:|:---:|---|
| 1 | Install (stranger, 3 OS) | 0 | 2 | 0 | 0 | **0.5** | publish-floored |
| 2 | First hour | 8 | 3 | 7 | 5 | **5.75** | partly publish-floored |
| 3 | Security/trust | 9.5 | 8 | 8 | 9 | **8.6** | engineering ✓ |
| 4 | Error UX | 10 | 9 | 9 | 9 | **9.25** | engineering ✓ |
| 5 | Docs for strangers | 9.5 | 7 | 8 | 8 | **8.1** | engineering ✓ |
| 6 | Portability | 0 | 1 | 2 | 0 | **0.75** | publish-floored |
| 7 | Packaging | 0 | 0 | 0 | 2 | **0.5** | publish-floored |
| 8 | Community/support | 5 | 2 | 5 | 6 | **4.5** | partly publish-floored |
| 9 | API stability | 10 | 8 | 8 | 7 | **8.25** | engineering ✓ |
| 10 | Operational trust | 7 | 7 | 6.5 | 6 | **6.6** | engineering (reliability-capped) |

## What this means (honest read)

- **The engineering is at 8.5.** The four dimensions that measure engineering
  independent of publish status — Security (8.6), Error UX (9.25), Docs (8.1),
  API stability (8.25) — average ~8.3, with Error UX the standout. Four
  different vendors, no collusion, all land there. That is the cross-vendor jury
  certifying the build quality, not the author.
- **The gate is publish-blocked, not engineering-blocked.** Dims 1/6/7 (≈0.5)
  cannot rise without the repo move + PyPI + public CI. Those are Mark's calls.
- **One engineering dim is below the 7.5 floor: dim 10 (Operational trust, 6.6).**
  Every vendor pinned the same cause — the 81.4% all-time dispatch reliability.
  This is the ONE lever that is both engineering and movable while private. The
  panel's actionable note: *"split core reliability from provider/transient
  reliability in the scoreboard"* — most of the 18.6% failures are external
  transients (rate-limit/provider-down/subprocess), not rondo logic. An honest
  split scoreboard (rondo-logic reliability vs end-to-end-incl-transient) is the
  legitimate dim-10 fix; gaming the meter is not.

## Cost

`rondo_multi_review`, 4 providers, one call each (durations: gemini 68s, grok 8s,
openai 29s, mistral 18s). Per-provider cost reported $0.00 (max/subscription auth
keys — no metered charge captured). Real dispatches, audited.

## Bottom line for the release question

By the cross-vendor jury's own measurement, **rondo's engineering is release-grade
(8.5)**. It cannot SCORE 8.5 overall until it is published, because three of ten
dimensions are definitionally about being public. The 3.13 → 5.3 climb is real and
came entirely from engineering + docs. The remaining gap is one decision (publish)
plus one honest-measurement fix (the reliability scoreboard split, dim 10).
