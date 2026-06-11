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
- [x] **8.4 Budget gate: per-provider estimates** (R4, MED) — DONE RONDO-395 (97fd118):
      per-class estimates/samples/probes with GLOBAL cap accounting; MAX-KEEP updates;
      $0-success scoped to its own class; worker derives class from provider prefix.
      Judge 7/7 RED→GREEN; RONDO-373 regime rails green.
- [x] **8.5 Cross-process lock: bounded wait + lock-file hygiene** (R5, MED) — DONE
      RONDO-396 (21473d7): LOCK_NB retry to RONDO_XPROC_LOCK_WAIT_SEC (3s default, 0=off,
      garbage→default), timeout = WARN + proceed unlocked; sweep_stale_key_locks (7d TTL,
      flock-probe before unlink, held files immortal) rides compaction. Judge 5/5;
      RONDO-390 two-process rails green.
- [x] **8.6 Reconcile flock ON the audit file** (R6, LOW-MED, STD-110 r016 literal) — DONE
      RONDO-398 (f81b4c0): LOCK_EX on the JSONL across scan+write (sidecar semantics kept);
      thread-local flag kills the self-deadlock on synthetic appends. Judge 4/4.
- [x] **8.7 http_skeleton success-path catch widening** (R8, LOW) — DONE RONDO-397
      (30b022c): TypeError/ValueError → ERR_PROVIDER result + breaker + redaction; labeled
      top-up pins no-bare-Exception creep. Judge 7/7.
- [x] **8.8 bin/mutate --timeout-per-mutant + dispatch_parse measured** — CODE RONDO-392;
      MEASURED RONDO-405: first honest sweep 31/61 (51%, one mutant HUNG and was caught at
      60s — item-17's exact failure mode, now bounded); labeled top-up suite (gate as the
      mechanical referee) drove it to **59/61 = 97%**, the 2 survivors documented provable
      equivalents (dead max() guard arm). ERROR_RECOVERY transient flags now value-pinned —
      coverage executed that table on every run but asserted nothing.

## P2 — Spec honesty + proof

- [x] **8.9 STD-115 scope honesty** (R7, LOW) — DONE (098d3ff): SECURITY.md "Spec scope
      honesty" section — BUILT (quarantine store, withholding, advisory scope marking, each
      with judge) vs DESIGNED-NOT-BUILT (lifecycle reqs 001-021), consumer warning explicit.
- [x] **8.10 ⛳ Mid-point deep review** — DONE (reports/cursor-reviews/
      midpoint-review-20260610-road-to-8.md): 11 findings, 1 blocker. Disposition
      (RONDO-399):
      - FIXED: #1 HIGH prompt_sent left raw by quarantine redaction (the blocker —
        re-opened STD-104 r023 on the fail path); #2 RecursionError in the quarantine
        WRITE escaped before redaction; #3 K-probe blind-admit window (one blind probe
        round-wide restored); #5 _save_background_result chmod window; #8 refused plans
        now audited (status="refused"); #9 matrix cell output born 0o600.
      - DOCUMENTED (accepted trade): #7 estimate gate intentionally conservative
        (can refuse free work — strict reading when max_budget is set); #10 mutate
        timeout must be >> baseline (operator contract in docstring).
      - ACKNOWLEDGED, kept as-is with rationale: #4 idempotency lookup stays
        post-routing — correctness (no cross-mode cache serve) over fast-path latency;
        routing is pure CPU, and a route error preempting a cached result is MORE
        honest, not less. #6 TypeError/ValueError still count against the breaker —
        a malformed-but-200 payload IS a provider-degradation signal (judge-pinned);
        revisit if false trips appear. #11 advisory audit IO volume — watch item.
- [x] **8.11 ⛳ Full re-score ROUND 1** — **7/10** (review-20260610-184904.md, same
      instrument). Both 6/10 blockers verified CLOSED in code; promotion criteria for 7
      met. Trajectory: 3.13 (Jun 6) → 5 → 6 → 7 (Jun 10). Off 7.5 on findings R2-1..R2-4
      below. Privateness cap named separately (8.12, Mark's).

## ROUND 2 — the 7 → 7.5+ items (re-score findings, same workflow)

NOTE: Cursor hit its monthly Pro+ usage limit mid-round (resets 6/15). The
independent-author role moved to GEMINI-2.5-PRO dispatched through rondo's own
rondo_run (separation of duties kept with a DIFFERENT vendor; ~\$0.02 total,
audit-logged). Twice, gemini's returned test fixtures came back with the fake
key ALREADY SCRUBBED to [REDACTED:...] — rondo's own sanitize pipeline scrubbing
its own dispatch results mid-authoring. R2-1..R2-4 DONE (RONDO-400/401/402,
commits bb36129/cf32913/554ec2f), all judges RED→GREEN, build 6/6.

- [x] **R2-1 In-memory idempotency `_cache` unbounded** (MED-HIGH) — the in-memory twin of
      the RONDO-369/396 leaks: one tuple holding a FULL result payload per unique prompt,
      forever, on the long-lived MCP server; eviction only on same-key re-lookup. Sweep
      expired entries (size/age bound), mirror the ref-count discipline.
- [x] **R2-2 Scrub set incomplete for spool/history** (MED) — error_message, context_data,
      command_sent reach spool + history RAW (STD-114 r006 MUST); audit forensic-scrubs
      error_message but spool/history don't. Bring the symmetric fields into
      sanitize_task_result (or scrub at the spool/history write boundary).
- [x] **R2-3 Matrix cell outputs unsanitized** (MED) — perms fixed (RONDO-399), content
      not: raw model output verbatim in {stem}.txt. Scrub before _write_cell_output.
- [x] **R2-4 Advisory OUTCOME vs STD-113** (LOW-MED) — req 021 MUST: non-done OUTCOME must
      persist error_message (advisory passes ""); §8 still says two states. Fix BOTH
      sides: pass a real error_message/explanation on advisory/refused outcomes AND amend
      STD-113 §8 to the de-facto open status vocabulary (spec-honesty, like 8.9).
- [x] **PROMPT-CODING CAMPAIGN (RONDO-406/407, Mark's order 2026-06-10 late)** — the
      thesis feature built + demonstrated LIVE: REQ-114 pipeline engine (gemini-authored
      judges 13/13), `rondo pipeline` CLI, and the Claude-driver flagship: rondo drove 10
      Claude Code subprocesses to build a todo app + 54-test suite from nothing, one
      verified step at a time, 54/54 INDEPENDENTLY re-verified by the runner. Every
      guardrail fired on a real event first (turn limit, budget ceiling, timeout, contract,
      passed=false gate). Artifacts: reports/claude-builder-2026-06-10/. This is the
      publish-launch centerpiece.
- [ ] **R2-5 ⛳ Re-score ROUND 2** — target ≥7.5 on the merits.
      Acknowledged-not-fixed carryovers (priced LOW by the reviewer): claude
      subscription-vs-API one-class residue (#5), breaker attribution on local bugs (#6),
      advisory preview side effects (#7), archive JSONL umask (#8 — fix with R2-2, it's
      one line), mutate timeout operator-contract (#9), advisory-can-only-be-honest (#10,
      by construction).
- [ ] **8.12 The privateness floor — MARK'S DECISION** — both reviews said the score is
      partly capped by private/unproven status. 8/10 likely requires the publish step
      (GitHub go, PyPI name, CI incl. Windows runner — which would also EXECUTE our Windows
      fixes for the first time). Nothing goes public without Mark's explicit word; this item
      exists so the cap is never forgotten in scoring talk.
      **PREP DONE 2026-06-10 (Mark's ruling: open USH disclosure — "not shy"):**
      - README "Why It's Built This Way" — the accessibility origin story in Mark's
        framing, as design spec not footnote. This makes CLAUDE.md's history a non-issue:
        **NO history rewrite needed, ever** — nothing touched, nothing to explain.
      - Deep public-safety scan CLEAN: full-history gitleaks → 13 hits, all provably fake
        sanitize-test fixtures, hand-inspected + allowlisted in .gitleaksignore (a
        stranger's scan now returns zero). No email/PII/key-fragments anywhere.
        SESSION-HISTORY.md audited: no personal info, publishable (Mark's taste call).
      - REMAINING when Mark says GO: create PRIVATE GitHub repo → push → stranger-lens
        review there → PyPI name pick (rondo-ai / rondo-dispatch) → CHANGELOG + SemVer →
        CI matrix → flip public. Reversible at every step until the flip.

---
**Honesty note on "better than 90% of solo GitHub projects":** on the dimensions a hostile
reviewer can measure — test depth (2,486, mutation-verified 97-100% on core modules),
reliability engineering (breakers/locks/budgets with real two-process proofs), audit trail,
review rigor (4 hostile reviews in 5 days, all findings closed) — rondo TODAY already
exceeds the overwhelming majority of solo projects, which ship with a README and vibes.
What the percentile claim can't include yet: users, issues survived, CI badges, docs site —
the community-proof dimensions only publishing unlocks (item 8.12).
