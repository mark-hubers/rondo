# Rondo — Session History

Newest at top. Per-repo session log (see `~/.claude/on-demand/session-save-procedure.md`).

---

## 2026-06-10 EVENING — ROAD-TO-8: 6/10 → 7/10 measured, every engineering item closed (RONDO-391→405)

**TL;DR:** Mark's order: "do all that needed to get this to a 8/10... clear trackable task
list... deep review as you go." Built `reports/ROAD-TO-8.md` and closed ALL of it — rounds
1 AND 2 — in one evening: ~15 sprints, ~25 commits, every fix judge-tested RED→GREEN,
build green before every commit. **Re-scored 7/10** (same hostile instrument; trajectory
3.13 → 5 → 6 → 7 in four days). Suite 2,486 → 2,610 collected.

### Round 1 (8.1-8.11): quarantine-on-scrub-failure (391; prompt_sent + RecursionError twins
caught by the mid-point review and fixed); advisory path under the machinery — audit
INTENT/advisory OUTCOME, dispatch_id correlation, guarantees_scope/not_covered on every
plan builder, schema 3, estimate-gated budget at issuance (394; design Cursor-reviewed
BEFORE code — found a real pre-existing cache-collision bug); artifacts born 0o600
everywhere incl. 4 twin-grep finds (393); per-class budget estimates (395); bounded
cross-process lock + flock-probe TTL sweep (396); reconcile under the audit file's own
flock with thread-local re-entrancy (398); adapter catch widening with a no-bare-Exception
pin (397); mutate --timeout-per-mutant, hang=caught (392); STD-115 scope honesty in
SECURITY.md; mid-point hostile review (11 findings: 6 fixed, 2 documented, 3 acknowledged).

### Round 2 (R2-1..R2-8): bounded in-memory idempotency cache (400); complete scrub set —
error_message/context_data/command_sent + archive 0o600 (401); matrix output scrubbed +
advisory OUTCOME req-021 + STD-113 §8 amended to the open status vocabulary (402);
claude-max/claude-api auth-class split + PURE plan_only previews (403); mutation-gate
baseline guard — red-on-clean aborts, tight timeout warns (404); dispatch_parse MEASURED
31/61 honest → kill suite → **59/61 = 97%**, 2 survivors documented provable equivalents;
the timeout flag caught a genuinely hanging mutant in production use (405).

### The day's defining event: Cursor died mid-round (Pro+ monthly limit, resets 6/15).
The independent-author role moved to **gemini-2.5-pro dispatched through rondo itself**
(rondo_run, ~$0.03 total, separation of duties kept with a DIFFERENT vendor). Twice,
gemini's test fixtures came back with the fake AWS key ALREADY SCRUBBED — rondo's own
sanitize pipeline scrubbing its own dispatch results mid-authoring. Every gemini harness
guess was RED-replicated before trust (caught one vacuously-passing test); every re-point
documented in module docstrings, never silent. Authoring prompts preserved in
reports/authoring-prompts/2026-06-10/.

### State at save
- All committed through RONDO-405; bin/build 6/6 green; no git remote exists (publish = 8.12).
- OPEN: round-2 re-score (instrument = Cursor, quota-dead till 6/15; alternatives: spend
  limit, or rondo cloud panel with an instrument-change note); 8.12 publish fork (MARK'S).

---

## 2026-06-10 — The 24-item quality burn-down: 5/10 review → everything fixed (20 sprints, RONDO-372→390)

**TL;DR:** Cursor's hostile holistic review scored rondo **5/10** with 10 findings (2 release
blockers). By end of day: ALL 24 checklist items resolved — every finding fixed with a
Cursor-authored RED→GREEN test, the adapter architecture unified, mutation coverage driven to
97–100% on four modules, Mark's three design rulings implemented (incl. two real cross-process
locks), and the live tool reinstalled. **33 commits**, suite 2,337 → **2,486 tests**, every commit
build-green + gitleaks-clean. Re-score pending (Cursor service was flaky at day's end).

### The checklist (reports/QUALITY-CHECKLIST-2026-06-10.md — all 24 resolved)
- **P0–P2 (Cursor's 10 findings):** budget gate production regimes (RONDO-373: no-fallthrough
  probe wait + $0-success-is-a-sample), Windows fcntl crashes ×3 twins (372: breaker persist +
  audit rotate; twin-grep found the 3rd that Cursor itself missed), MCP forensics re-claim
  interval (374), anthropic health 401-honesty twin (375), opt-in surfaced stream re-attempt
  (378+fixup — old RONDO-334 tests had pinned the spec violation), round isolation vs
  KeyError (376), breaker load-sig order (379), gemini thoughtsTokenCount cost (380),
  `_scrub_dict` security pin (377, mutation-proven), docstring truth (374 rider).
- **P3 architecture (381/382):** `adapters/http_skeleton.py` — ONE 10-step reliability pipeline,
  4 adapters ported (ollama gained breaker/retry/empty-gate for +3 lines), key-redaction
  unified, dup blocks 7→1; pre-gate contract shared via engine helper; dataclasses.replace.
- **P4 lying tests (384/386/387):** mutation-caught spool 38→97%, envelope 52→98%,
  history 56→**100%**, sanitize 75→97%. All Cursor-authored suites + labeled Claude top-ups;
  equivalents documented, never tautology-tested. dispatch_parse measurement (item 17) ran last.
- **P5 Mark's rulings (388/389/390):** sanitize crash = fail-open + LOUD (warning/metric/marking;
  bonus: _attach_metrics clobber fixed); idempotency appends under flock (PIPE_BUF lie retired);
  **cross_process_key_lock** — per-key flock single-flight, two-real-process race test proves
  one payment, kernel-managed release (no stale-lock code).
- **P6 showcase (383):** `resilience_tour.py` (exposed + fixed the "Retry-After exactly" comment
  lie — it's a floor) and `budget_guarded_parallel.py`. Examples 90→92.

### The verification system caught ITSELF lying five times — each became a rule
1. Cursor missed the 3rd fcntl twin → **twin-grep before every sprint close**.
2. I committed 378/379 on a RED build (chained grep+commit) → **verify and commit are NEVER one
   command** (memory: feedback-verify-build-before-commit-separate-steps).
3. Mutation gate emitted no-op return-None mutants (RONDO-364).
4. Mutation gate ran stale .pyc bytecode — same-size/same-second mutants (RONDO-385); caught by
   HAND-REPLICATION → **surprising gate verdicts get one hand-replication before belief**;
   sanitize score honestly corrected 30/36→28/36.
5. Mid-sweep the working tree IS a mutant → **read source via `git show HEAD:`, never build
   mid-sweep** (rules now in bin/mutate header; nearly triaged a live mutant of spool.py).

### Key decisions
- Mark: "go now" on the adapter refactor; "keep grinding, no lazy"; P5 rulings as above.
- Re-score with the SAME instrument (cursor holistic) before the publish decision — 2 attempts
  failed on Cursor-service connection blips (honest -ERROR-, no fake pass); retry queued.
- Worktree discipline: reinstall + re-score ran from `git worktree` at HEAD because the live
  tree was mid-mutation (a reinstall would have baked a MUTANT into the production binary).

### State at save
- Branch clean through `af900fa` (+ item-17/19b checklist ticks pending the measurement).
- Live tool = today's code (`rondo doctor` 0 FAIL/0 WARN).
- IN FLIGHT: dispatch_parse mutation measurement (item 17, background); re-score retry queued
  on its completion. Worktree at /tmp/rondo-clean-head to clean up after.

### What's next
1. Record item 17's number; commit final checklist state; `git worktree remove /tmp/rondo-clean-head`.
2. Re-score (Cursor, same rubric) → fresh number vs the 7.5/8.5 release bar.
3. MARK'S FORK (his call alone): publish-prep (GitHub go, PyPI name rondo-ai/rondo-dispatch,
   CHANGELOG/SemVer, CI matrix incl. Windows) vs more hardening (Windows CI, watchdog 85%<95%
   triage) vs live USH campaigns.

---

## 2026-06-09 — Concurrency hardening + the anti-lie test workflow (13 sprints, RONDO-359→371)

**TL;DR:** Fixed a batch of concurrency/reliability bugs, built a mutation gate, then ran an
independent-AI (Cursor) review that found **10 real bugs in code I'd just called "done"** — and
fixed every one with a **Cursor-authored test** judging my fix (separation of duties). 13 sprints,
all `bin/build` green (ended at 2299 tests, pylint 9.33), gitleaks clean, every sprint closed.

### What we did (in order)
- **RONDO-359** serialize reconcile read-modify-write (STD-110 r016).
- **RONDO-360** single-flight idempotency — stop double-pay on concurrent identical dispatches
  (key_lock + `_dispatch_and_cache` re-check under lock).
- **RONDO-361** circuit breaker — peer-trip visibility (mtime reload) + read state under `state.lock`.
- **RONDO-362** hermetic tests — stub the two I/O seams (`_run_subprocess` + `urlopen`); **full suite
  1031s → 93s (11×)**, no live/paid AI in the build. Found the "live" example coverage was already
  fake (180s timeouts passing).
- **RONDO-363** AST **mutation gate** (`bin/mutate` + `src/rondo/mutate.py`) — proves a test FAILS
  when code is wrong; trusts no author. Self-tests: strong test catches all mutants, weak test leaves
  survivors.
- **RONDO-364** A-spike: ran the gate on idempotency.py → killed 6 real survivors (TTL boundaries,
  disk persistence, compaction), fixed a no-op-mutant bug in the gate itself. Measured **~35% real /
  ~65% equivalent-mutant noise** → an auto-gate must be advisory, not blocking.
- **RONDO-365…371** — the 9 real bugs from Cursor's hostile concurrency review
  (`reports/cursor-reviews/review-20260608-180758-concurrency.md`), each Cursor-test-first:
  - 365 breaker fail-OPEN clobber (`del` erased a peer's live cooldown) — MUST
  - 366 budget gate TOCTOU → W× overrun — MUST (reserve-then-settle + cold-start probe)
  - 367 reconcile Windows `ImportError` crash + NFS silent-skip — spec MUST (errno triage + fallback)
  - 368 duplicate-OUTCOME: `stuck_after_sec` 300→900 (> 600s cloud timeout) + torn-final-line skip
  - 369 breaker reload mtime-collision → (mtime, size) signature + `_sig_lock`
  - 370 unbounded `_key_locks` leak → ref-count + evict on zero users
  - 371 per-task reconcile O(T·N) → once-per-(process, file) auto-reconcile gate

### Key decisions / rationale
- **Separation of duties is the anti-lie mechanism.** Author ≠ test-writer ≠ reviewer. I implement;
  Cursor writes the RED-first test and reviews; the mutation gate + `bin/build` are mechanical
  referees; Mark approves scope. Order locked in by Mark: A (spike) → C (Cursor workflow) → B
  (auto-gate, deferred, must be advisory per the 35% noise finding).
- **"Green ≠ real."** Mark called out that I'd claimed tests were "real" from green runs. Proven true:
  mutation gate found half my survivors slipped; Cursor found 10 bugs green builds missed; mypy's
  incremental cache even masked a malformed `type: ignore` for 4 builds (RONDO-366, fixed in 371).
- **#8 was correctly NOT a bug** (a documented limitation) — didn't pad the count. 10 findings → 9
  fixes + 1 dismissed.
- Concurrency bugs are invisible to the mutation gate (value/logic only) — they need stress tests +
  adversarial review. That's why the Cursor lens caught what the gate couldn't.

### Files changed (committed)
- src: `audit.py`, `retry.py`, `parallel.py`, `idempotency.py`, `mcp_dispatch.py`, **new** `mutate.py`
- tests: `test_retry.py`, `test_idempotency.py`, `test_mutate.py`, `test_mcp_parallel_multi.py`,
  `test_api_examples.py`, + 6 **Cursor-authored** `*_cursor.py` regression tests
- tooling: **new** `bin/mutate`; `reports/cursor-reviews/review-20260608-180758-concurrency.md`

### What's next (open, Mark's call)
- **B**: wire `bin/mutate` into `bin/build` for changed files — **advisory only** (65% equivalent-mutant
  noise makes a hard block a nuisance generator).
- Consider a convention lock: any lock/shared-state change ships with a multi-thread stress test.
- Strategic (unstarted): public/GitHub go decision, PyPI name, the SOP-106 8.5 release rubric.

### Memory written (boot cache)
- `feedback-green-is-not-real-mutation-gate`, `feedback-hermetic-test-dispatch-seams` (in
  `~/.claude/projects/.../memory/`).
