# Rondo-REQ-115: Verified Execution — rondo checks the work itself

*The model reports; rondo verifies. A claim with observable effects is never
taken on faith: rondo hashes the files and runs the checker with its own
hands. This is the anti-lying layer.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-06-11 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Depends on:** REQ-114 (pipelines), STD-113 (audit — open status vocabulary), STD-114 (sanitization)
**Author:** Mark Hubers — HubersTech
**Driver:** independent hostile review 2026-06-11 (reports/inline-control-review-2026-06-11.md): the inline path's execution is honor-system — "the LLM can hallucinate tool outputs and append the token." The reviewer's three hardening paths (loop-close verify call, state verification over token-grepping, challenge that requires real execution) are unified here into ONE mechanism: plan-declared, rondo-executed verification.

---

## 1. Purpose & Scope

**The trust inversion (plain English):** today, an inline plan ends with the
host session SAYING it did the work (token echo = saying it loudly). After
this spec, a plan can DECLARE what the world must look like afterwards —
files that must exist, a command that must exit 0 — and `rondo_verify` checks
those claims ITSELF, in rondo's own process, recording a `verified` or
`failed_verification` audit outcome. The model's honesty stops being the
load-bearing wall for anything observable.

**Who writes the verify block matters:** the LOCAL plan/pipeline author (the
user), never the model. The model cannot weaken its own checker.

**IN scope:** verify blocks on inline plans and pipeline steps; the
`rondo_verify` API/MCP surface; engine-side verification of pipeline steps
(defense in depth over the passed-flag); new audit statuses; evidence
recording. **OUT of scope (v1):** verifying pure-text answers (impossible by
construction — declared, not faked); cryptographic attestation of the host's
tool calls; cross-machine verification.

---

## 2. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### The verify block — **BUILT 2026-06-11 (RONDO-409)**

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 001 | A pipeline step (and an inline `rondo_run` call via a `verify` argument) may declare a verify block: `files` (list of paths that must exist after execution), `cmd` (argv LIST — never a shell string — run with cwd = the step's add_dir/workspace), `expect_exit` (default 0), `within_sec` (cmd timeout, default 120) | MUST | Loader/API test |
| 002 | The verify block is authored LOCALLY (YAML/caller arg). It is persisted at plan-issuance time in the dispatch's audit result record so `rondo_verify(dispatch_id)` later runs EXACTLY what was declared — the model never sees a way to alter it | MUST | Tamper test |
| 003 | `cmd` rejects shell strings: a string instead of a list is a definition error (`shell=False` execution only, REQ-100 subprocess hygiene) | MUST | Safety test |

### rondo_verify — the loop closer — **DESIGNED, not yet built** (next sprint; engine-side verification landed first)

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 010 | `rondo_verify(dispatch_id)` (Python API + MCP tool): loads the persisted verify block for that dispatch, checks every declared file EXISTS (recording size + sha256), runs `cmd` with shell=False capturing exit code + stdout tail (capped 2000 chars, SANITIZED per STD-114 before persistence) | MUST | API test |
| 011 | Outcome recorded as a NEW audit record paired to the same dispatch_id: status `verified` (all checks passed) or `failed_verification` (any miss — missing file, wrong exit, timeout), with the evidence in the record | MUST | Audit test |
| 012 | A dispatch with NO persisted verify block → `rondo_verify` returns status `unverifiable` honestly (and records nothing false); verifying the same dispatch twice appends a second record (re-verification is legal — state may change) | MUST | Honesty test |
| 013 | Verification evidence includes a `verified_at` timestamp and the hashes — so a LATER reviewer can detect post-verification tampering by re-hashing | SHOULD | Evidence test |

### Engine integration (pipelines stop trusting self-reports alone) — **BUILT 2026-06-11 (RONDO-409)**

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 020 | A pipeline step WITH a verify block: after the dispatch returns (and the passed-flag/contract gates pass), the ENGINE runs the verification itself; a verification failure FAILS the step (retryable per `retries`, on_fail semantics unchanged) — the model's passed=true cannot override rondo's own observation | MUST | Engine test |
| 021 | The step record carries `verification`: {checked_files, cmd, exit_code, ok} so the envelope shows BOTH the model's claim and rondo's observation | MUST | Envelope test |
| 022 | Steps WITHOUT a verify block behave exactly as v1.1 (no regression; verification is opt-in per step) | MUST | Rail test |

### Spec honesty — req 030 pending with rondo_verify; req 031 BUILT

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 030 | STD-113 §8 gains `verified` / `failed_verification` in the status table | MUST | Spec pin |
| 031 | Documentation states the honest limit: only observable effects are verifiable; free-text answers remain advisory (guarantees_scope unchanged for them) | MUST | Doc pin |

---

## 3. What this kills and what it cannot

| Lie | Before | After |
|-----|--------|-------|
| "I wrote the file" (didn't) | token echo accepted | `failed_verification`: file missing, recorded |
| "tests pass" (they don't) | token echo accepted | rondo runs pytest itself: exit 1 recorded |
| "I did it" with wrong content | undetected | hash + verify-cmd catch any observable wrongness |
| A wrong ANSWER in free text | undetected | STILL undetected — declared honestly (req 031) |
