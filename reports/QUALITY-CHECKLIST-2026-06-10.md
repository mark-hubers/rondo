# Rondo Quality Burn-Down Checklist — 2026-06-10

Source: Cursor holistic review (`reports/cursor-reviews/review-20260610-063557.md`, scored **5/10**),
mutation-gate sweep, DRY scan, and session findings. Workflow per item: **Cursor authors the RED
test → Claude fixes → Cursor's test judges → build → commit** (one sprint per item).

Legend: `[ ]` open · `[x]` done · severity from the hostile review · ✓v = claim verified in code by Claude

---

## P0 — Release blockers (Cursor would block on these)

- [x] **1. Budget gate fails in production regimes** (cursor #1, HIGH, ✓v) — `parallel.py`
      (a) probe wait 30s < real dispatch latency → all waiters fall through with est=0.0 → overrun;
      (b) `settle()` samples only `cost > 0` — Claude max-auth path costs 0 → `_have_sample` never
      flips → round silently serializes one-task-at-a-time. The RONDO-366 test used instant $1 mocks
      so it lies about this. Fix: sample on EVERY settle (cost>=0); probe wait must not fall back to
      est=0 (block or re-probe); Cursor test must cover slow + zero-cost regimes.
      DONE 2026-06-10 (RONDO-373, 532ea62): no-fallthrough wait + settle(ok) sampling ($0 success IS
      a sample). Cursor regime tests 2 RED → 3 GREEN; 40 regression green; twin-grep clean.
- [x] **2. Breaker `_save_state` crashes Windows** (cursor #2, HIGH, ✓v) — `retry.py:286`
      unguarded `import fcntl` before try; `except` lacks ImportError. First breaker transition on
      Windows = hard crash in adapter error path. EXACT twin of the RONDO-367 audit fix. STD-110 r019.
      DONE 2026-06-10 (RONDO-372): guarded import + single-writer `_persist_payload` fallback; Cursor
      test 3 RED → 3 GREEN. **Twin-grep found a THIRD twin Cursor missed: `audit.py rotate()`** —
      also fixed (guarded `_fcntl`, conditional lock), Cursor rotate test stash-proven 2 RED → 2 GREEN.
      Committed: RONDO-372 (1a7f716), build 2304 green.

## P1 — High-value correctness

- [x] **3. MCP server stops crash-forensics after startup** (cursor #3, MED-HIGH, ✓v by design review)
      — `audit.py` RONDO-371 gate is once-per-PROCESS; long-lived MCP server never reconciles again.
      Fix: time-based re-claim (e.g. once per N minutes) or per-round gate, not process-lifetime.
      DONE 2026-06-10 (RONDO-374, 0c5494e): time-based re-claim (_AUTO_RECONCILE_INTERVAL_SEC=300, monotonic); storm rail held. Cursor test 1 RED -> 2 GREEN.
- [x] **4. anthropic health lies on dead key** (cursor #4, MED, ✓v) — `anthropic_api.py:428` returns
      healthy on 401/403. RONDO-357 fixed chat_completions only — twin missed. Align + one test per adapter.
      DONE 2026-06-10 (RONDO-375, fa64091): mirrors RONDO-357 contract (401/403 unhealthy; 404/405/429 reachable). Cursor test 4 RED -> 14 GREEN.
- [x] **5. Silent double-spend re-attempt** (cursor #5, MED, ✓v; nuance: logged but not "by choice")
      — `anthropic_api.py:285` disconnect → silent second `retry_http` (up to 5 attempts) vs
      REQ-109 r213 MUST "never silent spend". Fix: config-gate it (default off or single attempt),
      surface in result envelope.
      DONE 2026-06-10 (RONDO-378, b73a71a + fixup): opt-in stream_reattempt (default OFF per r213), surfaced via metrics. Cursor test 2 RED -> 3 GREEN. Old RONDO-334 tests updated — they pinned the violation.
- [x] **6. Parallel round dies on unlisted exception type** (cursor #8, MED, ✓v) — `parallel.py:187`
      collector catches (OSError, ValueError, RuntimeError) only; worker KeyError/TypeError kills the
      whole round, violating REQ-101 r8 isolation. Fix: catch Exception in collector (log + error result).
      DONE 2026-06-10 (RONDO-376, 5df8e21): collector catches Exception (KI/SystemExit stay fatal). Cursor test 2 RED -> 3 GREEN.

## P2 — Correctness, smaller blast radius

- [x] **7. Breaker load-path signature TOCTOU** (cursor #7, MED, ✓v) — `retry.py:437` `_record_mtime()`
      stats AFTER `read_text`; peer write between them makes sig describe unread bytes → missed reload.
      Fix: stat before read, or derive sig from the read bytes.
      DONE 2026-06-10 (RONDO-379, e3595f6): signature captured BEFORE read; mid-window peer write now forces one converging reload. Cursor test 1 RED -> 2 GREEN.
- [x] **8. Gemini thinking-token cost undercount** (cursor #9, LOW-MED, ✓v) — `gemini.py:156` ignores
      `thoughtsTokenCount` → budget gate fed low numbers on exactly the expensive runs.
      DONE 2026-06-10 (RONDO-380, 3ecf58b): output = candidates + thoughts. Cursor test 1 RED -> 2 GREEN. No twins (OpenAI/Anthropic totals already include reasoning).
- [x] **9. `_scrub_dict` nested scrub untested** (mutation gate, security-reachable, ✓v) —
      `sanitize.py:521-526` return-None mutants survive; every task's parsed_result flows through it.
      Cursor test: nested dict/list secret actually scrubbed.
      DONE 2026-06-10 (RONDO-377, f9a5690): Cursor test 4/4; bin/mutate 27/36 -> 30/36, all four _scrub_dict survivors killed.
- [x] **10. open_until docstring says monotonic, code is wall-clock** (cursor #10, LOW, known/accepted)
      — fix the docstring (cheap honesty win), don't re-litigate the design.
      DONE 2026-06-10 (RONDO-374 rider): comment now states wall-clock + NTP trade-off.

## P3 — DRY / architecture debt

- [x] **11. Adapter dispatch() triplication** (cursor #6 — REFUTED my gemini↔ollama read) —
      gemini/chat_completions/anthropic triplicate the dispatch skeleton + HTTPError→breaker block;
      drift bugs #4 and the redaction gap (gemini redacts body, chat_completions doesn't) came from it.
      Extract shared skeleton into ProviderAdapter/factory. BIG refactor — do AFTER P0-P2 (locks green).
      DONE 2026-06-10 (RONDO-381, 67404d8): http_skeleton.py — one 10-step pipeline, 4 adapters ported, dup blocks 7 -> 2, key-redaction unified. 174/174 adapter+judge tests.
- [x] **12. ollama adapter missing reliability primitives** (cursor #6b) — no retry_http, no breaker,
      no cost. Local = free, but breaker/retry still apply (ollama can hang/die). Wire it into the
      shared skeleton from #11.
      DONE 2026-06-10 (RONDO-381): ollama wired through the skeleton (+3 lines = breaker + retry + empty gate). Cursor judge 4 RED -> 5 GREEN.
- [x] **13. Smaller dup pairs** (pylint R0801): runner↔parallel, mcp_server↔mcp_dispatch,
      dispatch↔dispatch_parse — assess each: extract or document why distinct.
      DONE 2026-06-10 (RONDO-382, 520c9ee): pre-gate contract shared via engine helper; dataclasses.replace at both usage sites; MCP pass-through KEPT (front-door signature). Dup scan 7 -> 1.

## P4 — Lying-test burn-down (mutation sweep, scoped scores = LOWER bounds)

- [x] **14. spool.py — 24/58 caught (41%)** — re-check 34 survivors vs full suite; Cursor authors
      tests for real gaps.
      DONE 2026-06-10 (RONDO-384): 22/58 -> 56/58 (97%). 44 Cursor tests + 2 Claude missing-dir. 2 accepted equivalents documented.
- [x] **15. envelope.py — 23/44 (52%)** — same treatment; envelope is the public contract surface.
      DONE 2026-06-10 (RONDO-386): 23/44 -> 43/44 (98%), 61 Cursor tests; 1 hand-proven equivalent accepted.
- [x] **16. history.py — 17/25 (68%)** — same treatment.
      DONE 2026-06-10 (RONDO-386): 14/25 -> 25/25 (100%) — first perfect module. Cursor tests + labeled Claude residue top-up.
- [ ] **17. dispatch_parse.py — sweep pending** (fill in when done)
- [x] **18. engine.py — sweep pending** (fill in when done)
      MEASURED 2026-06-10: engine.py 30/94 caught (32%) vs test_engine.py scoped — survivor triage queued with items 14-16.
- [x] **19. sanitize.py residue** — entropy calc + extra_patterns boolop survivors (beyond item 9).
      DONE 2026-06-10 (RONDO-387): 28/36 -> 35/36 (97%); 12 Cursor entropy/extra-patterns tests; lone survivor = repr=False cosmetic (documented).
- [x] **19b. bin/mutate wart** — `ast.unparse` mutants strip SPDX/signature comments, so conventions/
      builds running mid-sweep see false failures. Either re-prepend the original header onto mutants,
      or document "never run build during a sweep" in bin/mutate usage.
      DONE 2026-06-10: pyc-staleness FIXED (RONDO-385 purge); header-strip + mid-sweep rules documented in bin/mutate header (read via git show; never build mid-sweep; hand-replicate surprising verdicts).

## P5 — Structural (known, unscored by Cursor for honesty; bigger design calls — Mark decides scope)

- [ ] **20. Fail-open sanitizer** — scrub exception still spools/saves UNsanitized result
      (`dispatch.py:811-814`). Fail-closed option: on scrub failure, redact whole payload.
      MARK RULED 2026-06-10: FAIL-OPEN + LOUD — keep the data (golden rule: never lose data), but escalate: -WARNING- log + metrics flag + visible marking on the result. Implement as RONDO-388.
- [ ] **21. Idempotency PIPE_BUF claim false for multi-KB results** (`idempotency.py:134`) — large
      JSONL appends are not atomic; torn-line guard exists on read, but fix the claim + consider chunk guard.
      MARK RULED 2026-06-10: ADD WRITE LOCK — flock around large idempotency JSONL appends for true atomicity. Implement as RONDO-389.
- [ ] **22. Cross-process idempotency still check-then-act** — documented limitation; decide: accept
      (document loudly) or build file-lock single-flight.
      MARK RULED 2026-06-10: BUILD IT — cross-process per-key file-lock single-flight (lock lifecycle + stale-lock recovery). Implement as RONDO-390.

## P6 — Showcase

- [x] **23. New example: budget-guarded parallel round** — showcases RONDO-366 gate (cap honored, probe,
      ERR_BUDGET_EXCEEDED surfacing). Runs hermetically in build like all examples.
      DONE 2026-06-10 (RONDO-383): budget_guarded_parallel.py — RONDO-373 gate demo, hermetic 3/3.
- [x] **24. New example: resilience tour** — breaker trip → cooldown → recovery + retry/Retry-After +
      idempotency dedup in one runnable story. The "why rondo" demo.
      DONE 2026-06-10 (RONDO-383): resilience_tour.py — live-verified -PASS-; exposed+fixed the Retry-After 'exactly' comment lie (it's a floor).

## Done this session
- [x] **0. cursor-review wrapper lied -PASS- on empty review** — empty-body guard added (~/bin/cursor-review).

---
**The meta-lesson driving items 2/4 (and the review's bottom line):** fixes land at one call site and
miss their twin. Burn-down rule: every fix MUST grep for its twins across all adapters/modules before
the sprint closes.
