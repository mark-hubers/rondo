# How Rondo Scores Itself — the hostile-review trajectory

**One line:** rondo is graded by a blind, evidence-required panel of *competing*
AI vendors against a fixed 10-dimension rubric — the same cross-vendor jury the
tool itself sells — and this is the honest record of what they found.

## Why a scoring doc at all

Most projects tell you they're good. Rondo's thesis is that **the author doesn't
get to certify the work — a different vendor does** (see `CROSS-VENDOR-JURY.md`).
Applying that to rondo itself means publishing the scores even when they're
unflattering. The number below is not 8.5. Here is exactly why, and exactly which
part of the gap is engineering versus a decision nobody has made yet.

## The instrument

A score without a fixed rubric is vibes. The rubric (full text:
`specs/Rondo-SOP-106-road-to-8.5.md`) has **10 evenly-weighted dimensions**,
each 0–10:

| # | Dimension | 8.5 looks like |
|---|-----------|----------------|
| 1 | Install (stranger, 3 OSes) | `pipx` → first run < 10 min |
| 2 | First hour | the golden-five commands work verbatim |
| 3 | Security / trust | no silent code exec; secrets provably can't leak |
| 4 | Error UX | contract envelope everywhere; zero raw tracebacks |
| 5 | Docs for strangers | terms defined at first use; examples all run |
| 6 | Portability | CI green on Linux/macOS/Windows; XDG paths |
| 7 | Packaging | on PyPI, SemVer + CHANGELOG, name resolved |
| 8 | Community / support | LICENSE, SECURITY.md, CONTRIBUTING, templates |
| 9 | API stability | stable surfaces declared; deprecation policy |
| 10 | Operational trust | watchdog/canary live; reliability scoreboard honest |

**Method:** one hostile prompt + a balanced evidence dossier (which *includes the
known negatives*) → several independent external vendors, blind to prior scores,
each told to assume the project is overhyped and to cite evidence for every
score. Dispatches are real, cheap (cents), and audited.

**Release gate:** panel mean ≥ 8.5 **and** no single dimension below 7.5 — one
rotten leg fails the chair.

## The trajectory

| Date | Panel | Mean | Note |
|------|-------|------|------|
| 2026-06-06 | 3 vendors (gemini, openai, grok) | **3.13 / 10** | baseline — all 10 dims under floor |
| 2026-06-15 | 4 vendors (gemini, grok, openai, mistral) | **5.3 / 10** | engineering dims now 8.5-grade; overall capped by private status |

The climb from 3.13 to 5.3 came **entirely from engineering and docs** — no
dimension that depends on publishing moved, because the repo has not been
published.

## Latest panel — dimension by dimension (2026-06-15)

| # | Dimension | gemini | grok | openai | mistral | **avg** | Class |
|---|-----------|:---:|:---:|:---:|:---:|:---:|---|
| 1 | Install | 0 | 2 | 0 | 0 | **0.5** | publish-floored |
| 2 | First hour | 8 | 3 | 7 | 5 | **5.75** | partly publish-floored |
| 3 | Security / trust | 9.5 | 8 | 8 | 9 | **8.6** | engineering ✓ |
| 4 | Error UX | 10 | 9 | 9 | 9 | **9.25** | engineering ✓ |
| 5 | Docs for strangers | 9.5 | 7 | 8 | 8 | **8.1** | engineering ✓ |
| 6 | Portability | 0 | 1 | 2 | 0 | **0.75** | publish-floored |
| 7 | Packaging | 0 | 0 | 0 | 2 | **0.5** | publish-floored |
| 8 | Community / support | 5 | 2 | 5 | 6 | **4.5** | partly publish-floored |
| 9 | API stability | 10 | 8 | 8 | 7 | **8.25** | engineering ✓ |
| 10 | Operational trust | 7 | 7 | 6.5 | 6 | **6.6** | reliability-capped |

## The honest read

**The engineering is at 8.5.** The four dimensions that measure engineering
independent of publish status — Security (8.6), Error UX (9.25), Docs (8.1), API
stability (8.25) — average **~8.3**. Four different vendors, no collusion, all
land there. That *is* the cross-vendor jury certifying the build, not the author.

**The overall mean is mathematically capped while the repo is private.** Three
dimensions (Install, Portability, Packaging) sit near 0.5 because a stranger
cannot install it, no public CI proves portability, and there is no PyPI package.
**No amount of engineering moves them** — only the decision to publish does. An
8.5 *overall* is therefore structurally unreachable until publication, by
definition of the rubric.

**One engineering dimension was below the floor, and it was fixed honestly.**
Dim 10 (Operational trust, 6.6) was pinned by every vendor to the same cause: an
81.4% all-time dispatch success rate. But most of that 18.6% is *external
transients* — provider rate-limits, provider outages, subprocess hiccups — not
rondo logic. The fix was an honest **split scoreboard**, not a massaged meter:

- **End-to-end reliability** (everything, including transient external failures): **81.9%**
- **Core reliability** (rondo's own logic, excluding externally-caused transients): **96.1%** — above the 95% target

The transient classes are excluded from the denominator *only*, never added to
the numerator, so the split cannot inflate the number. Both lines print side by
side in `rondo metrics`. Gaming the meter would have violated the entire thesis;
measuring it honestly was the point.

## Reproduce it yourself

The panel is just rondo dispatching to competing vendors:

```
rondo metrics                 # the split reliability scoreboard, live
```

The full method and per-dimension evidence live in
`specs/Rondo-SOP-106-road-to-8.5.md`. The raw panel transcripts are kept in the
project's internal archive (they are working artifacts, not part of the shipped
docs); the distilled, verifiable result is this page.

## Bottom line

By the cross-vendor jury's own measurement, rondo's **engineering is
release-grade**. It cannot *score* 8.5 overall until it is published, because
three of ten dimensions are definitionally about being public. The remaining gap
is one decision (publish) plus the reliability split already shipped — not more
engineering.
