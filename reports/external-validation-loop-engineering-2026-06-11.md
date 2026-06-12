# External validation: "loop engineering" — Boris Cherny, head of Claude Code

**Captured:** 2026-06-11 | **Source:** The New Stack, 2026-06-10
("The Anthropic leader who built Claude Code says he ditched prompting — now
he just writes loops"). Body fetched via search snippets (article gated).

## The quote

> "I don't prompt Claude anymore. I have loops running that prompt Claude and
> figuring out what to do." — Boris Cherny, head of Claude Code, Anthropic

## "Loop engineering" components named, vs what rondo already has

| Cherny's component | rondo |
|--------------------|-------|
| Loops that prompt Claude (not manual prompting) | conductor (`examples/api/conductor_if_else.py`) + pipelines (REQ-114) |
| Verification and routines | REQ-115 verified execution — rondo checks the work itself (RONDO-409/410) |
| Context management | scope guard (REQ-116) + per-step `add_dir`/tool scoping |
| Safety guardrails | budget ceiling, audit trail (STD-113), sanitize (STD-114), quarantine (STD-115) |
| Automated sequences on schedules (cron) | `rondo schedule` (launchd plists) |

## Honesty notes

- This is CONVERGENCE, not derivation: rondo's pipeline/verify/scope campaign
  PREDATES reading this article (commits 12ac2e0..3ee4151 on 2026-06-10/11; the
  fetch was 2026-06-11 after the work). Two independent parties — Anthropic's
  Claude Code lead and the rondo author — reached the same conclusion.
- The article DESCRIBES the practice; rondo is an independent, scriptable,
  audited, self-verifying ENGINE for it. The one thing rondo adds that the
  description implies but does not claim: machine-verification that a loop's
  work was actually done (not just that the loop ran).
- Article body was gated; this captures the verifiable quote + named
  components only, no fabricated specifics.

## Relevance to 8.12 (publish)

The most credible source in the space publicly validated the loop thesis the
day before rondo's verification layer landed. A real tailwind for the publish
decision — which remains Mark's alone.
