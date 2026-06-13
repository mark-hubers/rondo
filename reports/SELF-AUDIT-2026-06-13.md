# Rondo Self-Audit — spec→code→test, verify it yourself (2026-06-13)

**Why this exists:** Mark said he can't trust Claude's claims that the specs are
"built to the ideas." That distrust is earned — see the confirmed overclaim
below. The fix is not more assertions; it's making every claim **checkable by
you**, and surfacing gaps honestly. This is rondo's own thesis turned on me.

**How to read it:** every row has a real path and a command YOU can run. I am not
asking you to believe me — run the commands. Where a claimed thing was NOT backed,
it says so.

---

## 0. Confirmed overclaim this session (the real one)

`RONDO-418` commit `8dc9d37`: an earlier docstring + the RONDO-417 commit messages
claimed `_default_dispatch`'s mutants were "exercised by tests/integration/
test_live.py". That file tests `rondo.live`, a different module — it never touched
`_default_dispatch`. **That was false and it was committed.** I found it later and
built the real test (`tests/unit/test_default_dispatch_contract.py`). Verify:
```
grep -n "_default_dispatch\|rondo_run_file" tests/integration/test_live.py   # -> nothing
git show 8dc9d37 --stat                                                       # the fix
```
This is why an audit is warranted, not just my word.

## 1. REQ-115 (verified execution — the anti-lying core) — AUDITED

**Code is real** (run it):
```
grep -n "def run_verification\|def rondo_verify\|def validate_verify_block\|def _check_cmd\|def _check_content" src/rondo/verify.py
```
**Tests pass live** (run it — 70 tests, ground truth not claim):
```
.venv/bin/python -m pytest tests/unit/test_verify_mutation_kills.py tests/unit/test_lie_traps.py \
  tests/unit/test_rondo_verify_cursor.py tests/unit/test_content_assertions_cursor.py \
  tests/unit/test_inline_loop_control_cursor.py tests/unit/test_verified_execution_cursor.py \
  tests/unit/test_verifyspec_tamper.py -q
```

| Req | Claim | Backed by (verify yourself) | Status |
|-----|-------|------------------------------|--------|
| 001 | verify block (files/cmd/expect_exit/within_sec) | `test_verify_mutation_kills.py::test_valid_block_normalizes_defaults` | ✅ tested |
| 002 | block persisted at issuance; model can't alter | **`test_verifyspec_tamper.py`** | ⚠️→✅ **was a GAP, now closed** |
| 003 | cmd rejects shell string | `test_verify_mutation_kills.py::test_cmd_shell_string_rejected` | ✅ tested |
| 010-012 | rondo_verify loads spec / records / `unverifiable` | `test_rondo_verify_cursor.py::test_r012_unverifiable_honest` | ✅ tested |
| 013 | evidence has verified_at + sha256 | `test_rondo_verify_cursor.py:115 assert "verified_at" in text` | ✅ tested |
| 020-022 | engine runs verify; envelope carries it; opt-in | `test_content_assertions_cursor.py`, pipeline kill-tests | ✅ tested |
| 040-043 | contains / min_bytes content assertions | `test_content_assertions_cursor.py` | ✅ tested |

**The one gap the audit found:** req 002 was marked MUST with verification
"Tamper test" but **had no dedicated test** — persistence was only indirectly
exercised. That is exactly the kind of conformance overclaim Mark feared. It is
now closed (`test_verifyspec_tamper.py`, 4 tests: persisted-spec is the only
source, world-change → failed_verification, path-traversal dispatch_id blocked).

## 1b. STD-114 (output sanitization — the secrets scrubber) — AUDITED 2026-06-13

Status: **core BUILT + tested; 3 reqs DEFERRED; spec hygiene fixed.** Cross-vendor
finder = gemini:high (independent; agreed the split is fair, passed=true).

- reqs 001-012 (detection, AWS/base64 patterns, confidence, custom patterns,
  [REDACTED] replace, scrub-before-write, raw-in-memory boundary, env-var strip,
  path basename, count, quiet-when-zero): **BUILT, 85 tests green live**:
  ```
  .venv/bin/python -m pytest tests/unit/test_sanitize.py tests/unit/test_sanitize_entropy_cursor.py \
    tests/unit/test_sanitize_homoglyph.py tests/unit/test_redaction_guarantee.py \
    tests/unit/test_scrub_dict_cursor.py tests/unit/test_scrub_set_complete_cursor.py -q
  ```
- req 010 (NEVER log the actual secret — the scariest MUST): genuinely tested —
  `test_redaction_guarantee.py` plants secrets, asserts they never reach disk /
  audit artifacts / notification logs. Not a gap.
- **GAP FOUND + FIXED (spec hygiene, not a code lie):** reqs 013-015 (`rondo
  sanitize allow` CLI + self-correction) are DESIGNED-not-built; the req table
  left them unmarked (gemini called this "a severe audit problem"). Now marked
  ❌ NOT BUILT.
- **LIMIT DOCUMENTED (honest, was silent):** a secret split across a line break
  is not caught (regex is line-oriented); contiguous tokens ARE. Added to §20
  failure modes. Low practical risk (split tokens are non-functional); residual
  risk is multi-line PEM.
- No code or MUST-test gap found in STD-114.

## 1c. STD-113 (dispatch audit trail) — AUDITED 2026-06-13

Status: **built + tested; one SHOULD overclaim corrected.** 112 audit tests green:
```
.venv/bin/python -m pytest tests/unit/test_audit.py tests/unit/test_audit_mutation_kills.py \
  tests/unit/test_advisory_outcome_std113_cursor.py tests/unit/test_mcp_run_status.py \
  tests/unit/test_reconcile_audit_flock_cursor.py -q
```
- reqs 001-010 (intent/outcome records, prompt+result files, append-only JSONL,
  scrub-before-write, immutability), 014-027 (morning-report ids, reconcile_stuck
  + age threshold + stuck_after_sec, run_status 2000-char truncate, forensic
  fields error_message/stderr/blocked_reason/project, append-only schema): BUILT,
  tested. The `rondo audit` CLI (012 detail, 013 --cost) is REAL (cli.py:151).
- **OVERCLAIM corrected:** req 011 claimed query "by date range, task name, model,
  status" — the CLI has only `--failed` + detail, none of those filters. Marked
  PARTIAL in the spec (mechanically certain from the parser args).
- No MUST gap. (Mutation residual 103/133 = documented rails+equivalents, RONDO-418.)

## 1d. REQ-114 (prompt pipelines — the engine) — AUDITED 2026-06-13

Status: **built + tested, NO overclaim found** (the honest good news — not
everything is a gap). 78 pipeline tests green live; mutation 149/160 (RONDO-417,
the residual documented). 
- CLI `rondo pipeline [--plan]` REAL (cli.py:83). Plan-mode purity (011/012)
  tested (`test_plan_only_preview_pure_cursor.py`). Flagship examples ship
  (`examples/pipelines/claude-builder.yaml`, `code-refine.yaml` — req 032).
- reqs 001-005 (YAML safe_load, field validation, placeholders, forward-ref
  reject, expect contract), 010 (budget ceiling), 020-025 (sequential guarded
  dispatch, on_fail, retries, envelope, explicit wiring, injectable dispatch):
  all have req-mapped kill-tests written this session.
- **Bias caveat (honest):** this is the spec I worked on MOST this session, so my
  "clean" verdict could be over-confident. It gets the Cursor independent
  third-pass on 6/15 specifically to counter that bias.

## 1e. REQ-116 (scope guard) — AUDITED 2026-06-13

Status: **built + tested; one gap found + closed.** 12 scope tests green;
scope.py mutation 10/10.
- reqs 001-003 (scope_score shape, deterministic, scoring), 010-012/014
  (allow_broad, strict_scope blocks, default warns, no regression): tested
  (`test_scope_guard_cursor.py` + `test_scope_mutation_kills.py`).
- **GAP FOUND + CLOSED:** req 013 (plan surfaces each step's scope score) was
  code-only (pipeline.py:309) with NO test — same pattern as req-002. Closed:
  `test_pipeline_mutation_kills.py::test_plan_surfaces_scope_score_per_step`.

## 1f. REQ-115 — already audited (§1); req-002 gap closed (`test_verifyspec_tamper.py`).

## 2. Remaining

- **REQ-117** (signed receipts) — DRAFT only, NOT built (honestly labeled; not a gap).
- **Cursor independent third pass** — queued for 6/15 (counters my own-work bias,
  esp. on REQ-114).

## 3. Tally — gaps found by this audit (every one a real overclaim, now fixed)

| Spec | Overclaim found | Fix |
|------|-----------------|-----|
| REQ-115 | req 002 "Tamper test" claimed, no test existed | `test_verifyspec_tamper.py` (RONDO-421) |
| STD-114 | reqs 013-015 unmarked but NOT built; multiline limit silent | marked NOT BUILT + limit documented (RONDO-422) |
| STD-113 | req 011 claimed query filters the CLI lacks | marked PARTIAL (RONDO-423) |
| REQ-116 | req 013 code-only, untested | `test_plan_surfaces_scope_score_per_step` (RONDO-424) |
| REQ-114 | none found (worked on most; Cursor 6/15 to counter bias) | — |
| REQ-112 | none found — error-envelope honesty contract real | 70 tests green; req 507 fallback + 508 ERR_TIMEOUT both tested |
| STD-115 | DESIGNED spec ~95% NOT BUILT, unmarked; name-collides with scrub-failure quarantine | NOT-BUILT banner added (RONDO-427) |

### REQ-112 (error envelope — "never fake data") + STD-115 (quarantine) — AUDITED 2026-06-13
- **REQ-112: CLEAN.** `envelope.py` real; 70 tests green. req 507 (every error_code
  gets a remediation message) guaranteed by the `_resolve_error_message` fallback
  AND tested (`test_unknown_code_gets_generic_help`, `test_empty_message_resolves_to_fallback`);
  req 508 ERR_TIMEOUT tested. The honesty contract holds.
- **STD-115: DESIGNED, NOT BUILT.** The result trust-lifecycle (PENDING/VERIFIED/
  TRUSTED state machine, auto-approval, review queue — reqs 001-021) has NO code.
  Honest at spec level (status DESIGNED) but the req table was unmarked and the
  word "quarantine" collides with the unrelated, shipped scrub-failure quarantine
  (RONDO-391). Added a prominent NOT-BUILT + name-collision banner.

Pattern: the overclaims were SHOULD-level CLI/feature reqs and missing
conformance tests — NOT fake core functionality. The MUST cores (scrub, audit,
verify, pipeline) are real and tested. Every gap above is now closed or honestly
labeled, with a runnable command.

Until each is traced req-by-req, treat "built to spec" for them as **claimed, not
audited**. I will run the same trace on them next, same method, same honesty about
gaps.

## 3. Whole-suite ground truth (run it)

```
bin/build           # 6 gates; full suite green is the floor for every commit
bin/mutate src/rondo/verify.py --tests "tests/unit/test_verify_mutation_kills.py ..."   # proves the tests BITE
```
The mutation gate (RONDO-363) is the independent referee: it proves a test fails
when the code is broken, so "green" isn't a green mock. Numbers in any report can
be re-measured with `bin/mutate`; do not take them on faith.

## 3b. Cursor independent third pass — staged for 6/15 (quota-gated today)

Cursor (and `cursor-review`) need the cursor-agent quota, which resets 6/15. When
it's back, run from the repo root:
```
cursor-review "Audit spec->code->test conformance for REQ-114/115/116 + STD-113/114.
For each requirement: is there a real test, or is it claimed-only? Flag overclaims.
PRIORITY: REQ-114 — Claude wrote most of its tests this session, so check that hardest."
```
Why Cursor specifically: it reads the actual code independently (a third party, not
Claude self-grading, not a summary-only cross-vendor read). It is the bias-counter
on REQ-114. File its findings as §1g here.

## 4. Standing commitment

- Every "built/verified/tested" claim gets a path + a runnable command, or it
  doesn't get made.
- Gaps get surfaced (like req 002), not smoothed over.
- The next work: trace REQ-114 / 116 / STD-113 / STD-114 the same way and file
  the findings here.
