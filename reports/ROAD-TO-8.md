# Road to 8/10 — tracked task list (started 2026-06-10)

Baseline: **6/10** (reports/cursor-reviews/review-20260610-164750.md — all RONDO-359..390
fixes verified real). Target: **8/10**, same instrument, same hostility. Mark's order:
"do all that needed... very clear trackable task list... cursor help on the way and deep
review as you go."

Workflow per item (unchanged, proven over 36 commits): Cursor authors the RED judge →
Claude implements → judge GREEN → twin-grep → verdict-read-then-commit → tick here.
Deep re-reviews at the two milestones marked ⛳.

Legend: `[ ]` open · `[x]` done · (R#) = re-score finding number

---

## P0 — The two named block-ons for 7

- [x] **8.1 Quarantine on scrub failure** (R1, HIGH, STD-114 r006 MUST) — DONE RONDO-391:
      `_quarantine_scrub_failure` in dispatch.py (mkstemp → 0o600, RONDO_TEST_DIR-aware,
      redact-in-place wins even if the quarantine write fails); except widened to Exception;
      twin fixed in mcp_dispatch.py defensive sanitize (was narrow + leaked parsed/stderr);
      judge tests/unit/test_sanitize_quarantine_cursor.py 5/5 RED→GREEN; RONDO-388's
      persist-raw pin reconciled with documented amendment.
      RULING AMENDMENT (Mark 2026-06-10 "do all that needed to get to 8"): fail-open+loud
      becomes QUARANTINE — still never-lose-data, but a failed-scrub result goes to a
      locked-down quarantine store (~/.rondo/quarantine/, dir+files 0o600-family) and is
      WITHHELD from audit/result/spool/history; the envelope carries status+quarantined
      marker so the caller knows where it went. Widen the except to Exception — the narrow
      (TypeError, AttributeError) let RecursionError (deep parsed_result) and re.error (bad
      custom pattern) crash finalize or sail through WITH raw data. This also lays the first
      real bricks of STD-115 (PENDING state). Mark may VETO the amendment → revert to loud
      fail-open and accept the 7-ceiling.
- [x] **8.2 Inline/agent path under the machinery** (R2, HIGH, the soft center) — DONE
      RONDO-394, design Cursor-reviewed first (design-review-20260610-item82.md): audit
      INTENT + advisory OUTCOME at the choke point, dispatch_id in the plan (Caliber
      correlation), sanitize-on-persist-only, guarantees_scope on ALL builders
      (advisory/guarded) + not_covered floor, schema 2→3, estimate-gated budget at
      issuance, fail-open+loud. BONUS pre-existing bug fixed: raw-execution idempotency
      key could serve a cached subprocess result to an inline caller (lookup moved below
      advisory return). Judge 9/9 RED→GREEN. Declined: plans-per-minute limiter.

## P1 — MUSTs + holes that compound (the 7→8 meat)

- [x] **8.3 Audit artifacts 0o600** (R3, MED-HIGH, STD-110 r012 MUST) — DONE RONDO-393:
      atomic_write→mkstemp; _append_jsonl O_CREAT 0o600; save_result mkstemp (chmod window
      killed); twins fixed: history append, idempotency append+compaction (deduped into
      _rewrite_compacted), retry-queue dead-letter. Breaker persist triaged non-sensitive.
      Judge 6/6 (Cursor, incl. no-op-chmod mechanism pin).
- [ ] **8.4 Budget gate: per-provider estimates** (R4, MED) — one global estimate
      under-enforces mixed free+paid rounds (free sample drives est to 0, paid tasks admit
      uncapped). Estimate map keyed by provider/auth-class; admission uses the estimate for
      THE TASK being admitted; estimate updates keep a per-class max-decay, not last-write.
- [ ] **8.5 Cross-process lock: bounded wait + lock-file hygiene** (R5, MED) — blocking
      acquire can stall an interactive caller for a peer's 30-min dispatch: bounded
      LOCK_NB retry window (~2-5s default, configurable), on timeout proceed WITHOUT the
      cross-process lock + WARN (in-process single-flight still holds; worst case = the old
      rare double-pay, never a stalled server). Lock-dir hygiene: TTL sweep of stale lock
      FILES during idempotency compaction using flock-probe (only unlink files we can
      LOCK_NB → provably unheld → safe against the unlink-inode race).
- [ ] **8.6 Reconcile flock ON the audit file** (R6, LOW-MED, STD-110 r016 literal) —
      scan+write under the same lock _append_jsonl uses, replacing/augmenting the sidecar.
- [ ] **8.7 http_skeleton success-path catch widening** (R8, LOW) — TypeError/ValueError
      from token math on a successful response → error result, all callers, not just the
      parallel collector.
- [~] **8.8 bin/mutate --timeout-per-mutant** (item-17 debt) — CODE DONE RONDO-392 (hang =
      CAUGHT; TDD 4 RED→GREEN incl. real-hang contract test). REMAINING: re-measure
      dispatch_parse with --timeout-per-mutant in an idle window (sweeps own the tree).

## P2 — Spec honesty + proof

- [ ] **8.9 STD-115 scope honesty** (R7, LOW) — 8.1 builds the quarantine bricks; document
      which STD-115 MUSTs are now real vs still DESIGNED-NOT-BUILT (scope-honesty section in
      SECURITY.md). No silent spec-vs-code gaps.
- [ ] **8.10 ⛳ Mid-point deep review** — Cursor hostile pass over 8.1-8.5 diffs
      specifically (fresh eyes on the new quarantine + lock code BEFORE the re-score).
- [ ] **8.11 ⛳ Full re-score** (same instrument/prompt lineage) — target ≥7.5. Record.
- [ ] **8.12 The privateness floor — MARK'S DECISION** — both reviews said the score is
      partly capped by private/unproven status. 8/10 likely requires the publish step
      (GitHub go, PyPI name, CI incl. Windows runner — which would also EXECUTE our Windows
      fixes for the first time). Nothing goes public without Mark's explicit word; this item
      exists so the cap is never forgotten in scoring talk.

---
**Honesty note on "better than 90% of solo GitHub projects":** on the dimensions a hostile
reviewer can measure — test depth (2,486, mutation-verified 97-100% on core modules),
reliability engineering (breakers/locks/budgets with real two-process proofs), audit trail,
review rigor (4 hostile reviews in 5 days, all findings closed) — rondo TODAY already
exceeds the overwhelming majority of solo projects, which ship with a README and vibes.
What the percentile claim can't include yet: users, issues survived, CI badges, docs site —
the community-proof dimensions only publishing unlocks (item 8.12).
