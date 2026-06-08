# Deep Codebase Review — 3-AI panel — 2026-06-08

**Sprint:** RONDO-350 | **Tool:** `rondo_review_codebase` (rondo reviewing
itself — dogfood). 7 core modules, 3 batches, providers
gemini-2.5-flash / gpt-4.1 / grok-3. ~50 findings total.
**Files:** dispatch.py, dispatch_routing.py, retry.py, providers.py,
config.py, runner.py, mcp_dispatch.py.

> NOTE: findings below are the PANEL's claims. Credible ones are marked for
> adversarial verify-then-fix; likely false-positives are flagged. No fix
> ships without a failing test first (the rondo rule).

---

## What's genuinely GOOD (consensus praise)

- **Sanitize-before-audit pipeline** — secrets scrubbed before anything is
  written/logged; called out by name as strong.
- **Always-on finalize pipeline** — audit/sanitize/spool/history/metrics on
  EVERY path, success and error alike.
- **Immutable config + thorough validation + secure loading.**
- **Retry + circuit-breaker design** — solid reliability primitives.
- **Requirements traceability** (REQ-/RONDO- refs everywhere) — rare rigor.
- **Robust subprocess management** for the Claude path.

Gemini: "high degree of engineering rigor." OpenAI: "strong attention to
error handling, security, and architectural layering."

---

## What NEEDS HELP — ranked, credibility-tagged

| # | Theme | Where | Credible? | Why it matters |
|---|-------|-------|-----------|----------------|
| 1 | **Thread-safety on shared globals** — `_cc_version_cache`, circuit-breaker `_states`, `_background_results` mutated without locks | dispatch.py:140, retry.py, mcp_dispatch.py:86 | **YES** (grok+openai consensus) | rondo runs PARALLEL workers — unlocked global writes are a real race class |
| 2 | **`fcntl.flock` is Unix-only** — circuit-breaker persistence | retry.py:165 | **YES** | hard **Windows portability blocker** — ties directly to the CI/publish goal (dim 6) |
| 3 | **Budget overrun under concurrency** — running_cost locked, but dispatch happens outside the lock | mcp_dispatch.py:470 | **YES** | cost-control correctness — could overspend in parallel rounds |
| 4 | **Config permission-check ordering** — a world-writable config at an earlier path may be read before the perm check | config.py:470, providers.py:400 | **likely** | security: the trust-gate could be bypassed |
| 5 | **`_max_output_bytes` silent 1MB fallback** if MODEL_CONTEXT_LIMITS import fails | dispatch.py:85 | medium | could truncate large 1M-context responses silently |
| 6 | **mcp_dispatch.py 1112 lines + dispatch/dispatch_routing coupling** | architecture | **YES** (consensus) | the known "two front doors" weakness; biggest structural debt |

### Flagged as likely FALSE-POSITIVE (verify before trusting)
- "fork/multiprocessing breaks locks" — rondo uses **threads, not fork**;
  theoretical here.
- "circuit breaker per-round not shared across threads" — may be **by
  design** (per-round breaker). Needs a look at intent, not a reflexive fix.

---

## The honest headline

The panel's verdict matches our own: **the engineering is rigorous and the
security/reliability design is genuinely good** — but there's a real
**thread-safety debt on global mutable state** (rondo grew parallel workers
after some of those globals were written single-threaded), and **`fcntl` is
a Windows wall** that CI would expose the moment publishing starts. Neither
is a crisis today (single-user, macOS); both are real before public/CI.

## Recommended next sprints (verify-then-fix, TDD)

1. **RONDO-351** — lock the shared globals (version cache, breaker, bg
   results). Highest consensus, real race class.
2. **RONDO-352** — Windows-safe file locking (replace bare `fcntl` with a
   portable lock or graceful fallback). Unblocks dim 6 / Windows.
3. **RONDO-353** — budget accounting under the lock (cost correctness).
4. Then config-perm ordering + the output-cap fallback.

Architecture (mcp_dispatch split) is a larger, separate effort — worth it
before public, not urgent.
