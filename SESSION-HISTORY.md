# Rondo — Session History

Newest at top. Per-repo session log (see `~/.claude/on-demand/session-save-procedure.md`).

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
