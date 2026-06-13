# The Cross-Vendor Jury — Rondo's thesis

**One line:** the AI that writes the code does not get to certify it; a *different
vendor* does, and disagreements are the signal.

## Why this is the moat (and not "another agent loop")

Every serious coding tool now runs tests in a loop — Claude Code, Cursor, Copilot
Workspace, aider, OpenHands, mini-swe-agent. "Verified loop" is table stakes, and
the incumbents will ship it natively. So a loop alone is not a differentiator.

The one thing a **single-vendor** tool structurally will not build: a jury where a
**competitor's model** judges its own model's work. Anthropic won't have Gemini
grade Claude. Cursor won't route to Grok to veto its Composer. That reluctance is
structural, not technical — and it is exactly the gap rondo fills.

```
accept = rondo_verifies(work) AND a DIFFERENT vendor agrees
```

Two independent layers, neither of which the author model controls:
1. **Mechanical truth** — rondo runs the test itself, hashes the file, checks the
   exit code. The model's `passed=true` cannot override rondo's own observation.
2. **Cross-vendor judgment** — a different vendor reviews the actual output; the
   step is accepted only if it also agrees. The *disagreement* is the product:
   it's the bug nobody else would have caught.

## The proof (run it)

`examples/api/controlled_review_loop.py` — live:
- Scenario 1: Claude builds `mean()`; rondo runs pytest itself (green); Gemini +
  Grok concur → ACCEPT.
- Scenario 2: `days_in_month` hard-coded to `return 30` **passes its shallow
  test** — a single-vendor "tests pass" loop ships it — but both jurors read the
  logic and **OBJECT** → REJECT. The jury caught a bug green tests would ship.

That second scenario is the whole argument in one run.

## Honest competitive position

- rondo's verification (the model can't grade its own observable work) is real vs
  the popular agents — aider feeds test output back to the model to "read and
  fix"; OpenHands trusts the agent-server's self-report. But that alone is not the
  moat (they could close it).
- The niche IS contested: bernstein (HMAC-signed audit chains), Conductor
  (Microsoft), Hive (YC), Symphony (OpenAI) are all in scriptable orchestration.
- An independent cross-vendor panel rated rondo **3-4/10 as it was positioned**
  ("another loop") and **~7/10 reframed around the jury** + published proof. This
  doc is that reframe. Full analysis: `reports/competitive/LANDSCAPE-2026-06-13.md`.

## What rondo is NOT claiming

- Not "we invented the loop" (we didn't; the loop is everywhere).
- Not "we're more mature than aider/OpenHands" (we aren't; they're battle-tested).
- Not "the model can never lie" (it can — see `reports/SELF-AUDIT-2026-06-13.md`,
  where rondo's own self-audit found and fixed real overclaims). The claim is
  narrower and verifiable: *the model is never the sole judge of its own work.*
