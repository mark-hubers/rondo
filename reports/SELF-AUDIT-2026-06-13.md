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

## 2. NOT yet audited this way (honest scope — do NOT assume these are verified)

REQ-115 and STD-114 are traced. STILL claimed-but-not-req-by-req-audited:

- **STD-113** (audit trail) — `src/rondo/audit.py`, mutation 103/133 (RONDO-418)
- **REQ-114** (pipeline) — `src/rondo/pipeline.py`, mutation 149/160 (RONDO-417)
- **REQ-116** (scope guard) — `src/rondo/scope.py`, mutation 10/10
- **REQ-117** (signed receipts) — DRAFT only, NOT built (honestly labeled)

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

## 4. Standing commitment

- Every "built/verified/tested" claim gets a path + a runnable command, or it
  doesn't get made.
- Gaps get surfaced (like req 002), not smoothed over.
- The next work: trace REQ-114 / 116 / STD-113 / STD-114 the same way and file
  the findings here.
