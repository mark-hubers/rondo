# Rondo Quality Burn-Down Checklist — 2026-06-10

Source: Cursor holistic review (`reports/cursor-reviews/review-20260610-063557.md`, scored **5/10**),
mutation-gate sweep, DRY scan, and session findings. Workflow per item: **Cursor authors the RED
test → Claude fixes → Cursor's test judges → build → commit** (one sprint per item).

Legend: `[ ]` open · `[x]` done · severity from the hostile review · ✓v = claim verified in code by Claude

---

## P0 — Release blockers (Cursor would block on these)

- [ ] **1. Budget gate fails in production regimes** (cursor #1, HIGH, ✓v) — `parallel.py`
      (a) probe wait 30s < real dispatch latency → all waiters fall through with est=0.0 → overrun;
      (b) `settle()` samples only `cost > 0` — Claude max-auth path costs 0 → `_have_sample` never
      flips → round silently serializes one-task-at-a-time. The RONDO-366 test used instant $1 mocks
      so it lies about this. Fix: sample on EVERY settle (cost>=0); probe wait must not fall back to
      est=0 (block or re-probe); Cursor test must cover slow + zero-cost regimes.
- [x] **2. Breaker `_save_state` crashes Windows** (cursor #2, HIGH, ✓v) — `retry.py:286`
      unguarded `import fcntl` before try; `except` lacks ImportError. First breaker transition on
      Windows = hard crash in adapter error path. EXACT twin of the RONDO-367 audit fix. STD-110 r019.
      DONE 2026-06-10 (RONDO-372): guarded import + single-writer `_persist_payload` fallback; Cursor
      test 3 RED → 3 GREEN. **Twin-grep found a THIRD twin Cursor missed: `audit.py rotate()`** —
      also fixed (guarded `_fcntl`, conditional lock), Cursor rotate test stash-proven 2 RED → 2 GREEN.
      Awaiting full build (held until mutation sweep releases the tree) + commit.

## P1 — High-value correctness

- [ ] **3. MCP server stops crash-forensics after startup** (cursor #3, MED-HIGH, ✓v by design review)
      — `audit.py` RONDO-371 gate is once-per-PROCESS; long-lived MCP server never reconciles again.
      Fix: time-based re-claim (e.g. once per N minutes) or per-round gate, not process-lifetime.
- [ ] **4. anthropic health lies on dead key** (cursor #4, MED, ✓v) — `anthropic_api.py:428` returns
      healthy on 401/403. RONDO-357 fixed chat_completions only — twin missed. Align + one test per adapter.
- [ ] **5. Silent double-spend re-attempt** (cursor #5, MED, ✓v; nuance: logged but not "by choice")
      — `anthropic_api.py:285` disconnect → silent second `retry_http` (up to 5 attempts) vs
      REQ-109 r213 MUST "never silent spend". Fix: config-gate it (default off or single attempt),
      surface in result envelope.
- [ ] **6. Parallel round dies on unlisted exception type** (cursor #8, MED, ✓v) — `parallel.py:187`
      collector catches (OSError, ValueError, RuntimeError) only; worker KeyError/TypeError kills the
      whole round, violating REQ-101 r8 isolation. Fix: catch Exception in collector (log + error result).

## P2 — Correctness, smaller blast radius

- [ ] **7. Breaker load-path signature TOCTOU** (cursor #7, MED, ✓v) — `retry.py:437` `_record_mtime()`
      stats AFTER `read_text`; peer write between them makes sig describe unread bytes → missed reload.
      Fix: stat before read, or derive sig from the read bytes.
- [ ] **8. Gemini thinking-token cost undercount** (cursor #9, LOW-MED, ✓v) — `gemini.py:156` ignores
      `thoughtsTokenCount` → budget gate fed low numbers on exactly the expensive runs.
- [ ] **9. `_scrub_dict` nested scrub untested** (mutation gate, security-reachable, ✓v) —
      `sanitize.py:521-526` return-None mutants survive; every task's parsed_result flows through it.
      Cursor test: nested dict/list secret actually scrubbed.
- [ ] **10. open_until docstring says monotonic, code is wall-clock** (cursor #10, LOW, known/accepted)
      — fix the docstring (cheap honesty win), don't re-litigate the design.

## P3 — DRY / architecture debt

- [ ] **11. Adapter dispatch() triplication** (cursor #6 — REFUTED my gemini↔ollama read) —
      gemini/chat_completions/anthropic triplicate the dispatch skeleton + HTTPError→breaker block;
      drift bugs #4 and the redaction gap (gemini redacts body, chat_completions doesn't) came from it.
      Extract shared skeleton into ProviderAdapter/factory. BIG refactor — do AFTER P0-P2 (locks green).
- [ ] **12. ollama adapter missing reliability primitives** (cursor #6b) — no retry_http, no breaker,
      no cost. Local = free, but breaker/retry still apply (ollama can hang/die). Wire it into the
      shared skeleton from #11.
- [ ] **13. Smaller dup pairs** (pylint R0801): runner↔parallel, mcp_server↔mcp_dispatch,
      dispatch↔dispatch_parse — assess each: extract or document why distinct.

## P4 — Lying-test burn-down (mutation sweep, scoped scores = LOWER bounds)

- [ ] **14. spool.py — 24/58 caught (41%)** — re-check 34 survivors vs full suite; Cursor authors
      tests for real gaps.
- [ ] **15. envelope.py — 23/44 (52%)** — same treatment; envelope is the public contract surface.
- [ ] **16. history.py — 17/25 (68%)** — same treatment.
- [ ] **17. dispatch_parse.py — sweep pending** (fill in when done)
- [ ] **18. engine.py — sweep pending** (fill in when done)
- [ ] **19. sanitize.py residue** — entropy calc + extra_patterns boolop survivors (beyond item 9).
- [ ] **19b. bin/mutate wart** — `ast.unparse` mutants strip SPDX/signature comments, so conventions/
      builds running mid-sweep see false failures. Either re-prepend the original header onto mutants,
      or document "never run build during a sweep" in bin/mutate usage.

## P5 — Structural (known, unscored by Cursor for honesty; bigger design calls — Mark decides scope)

- [ ] **20. Fail-open sanitizer** — scrub exception still spools/saves UNsanitized result
      (`dispatch.py:811-814`). Fail-closed option: on scrub failure, redact whole payload.
- [ ] **21. Idempotency PIPE_BUF claim false for multi-KB results** (`idempotency.py:134`) — large
      JSONL appends are not atomic; torn-line guard exists on read, but fix the claim + consider chunk guard.
- [ ] **22. Cross-process idempotency still check-then-act** — documented limitation; decide: accept
      (document loudly) or build file-lock single-flight.

## P6 — Showcase

- [ ] **23. New example: budget-guarded parallel round** — showcases RONDO-366 gate (cap honored, probe,
      ERR_BUDGET_EXCEEDED surfacing). Runs hermetically in build like all examples.
- [ ] **24. New example: resilience tour** — breaker trip → cooldown → recovery + retry/Retry-After +
      idempotency dedup in one runnable story. The "why rondo" demo.

## Done this session
- [x] **0. cursor-review wrapper lied -PASS- on empty review** — empty-body guard added (~/bin/cursor-review).

---
**The meta-lesson driving items 2/4 (and the review's bottom line):** fixes land at one call site and
miss their twin. Burn-down rule: every fix MUST grep for its twins across all adapters/modules before
the sprint closes.
