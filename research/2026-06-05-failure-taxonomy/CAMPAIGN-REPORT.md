# Rondo Reliability Campaign — Full Report (2026-06-03 → 2026-06-05)

**Sprints:** RONDO-296 → RONDO-301 (6 closed, full OB process artifacts)
**Commits:** dfe2aae8, ca30ea24, 61b8cfba, b2bdb9fc, d0db2aba, 4743ebc7, 30a80189, 751ab445
**Findings filed:** #284-#295 (12)
**Specs updated:** REQ-100 v1.4, REQ-109 v1.9, REQ-111 v0.3, IFS-100 v0.8, STD-101 v0.3, STD-108 v0.6, STD-110 v0.5, STD-113 v1.1
**Evidence dirs:** `rondo/research/2026-06-03-rondo-audit/`, `rondo/research/2026-06-05-failure-taxonomy/`

## Three root causes found and killed

1. **Parser threw away good work (#290, CRITICAL).** `parse_task_json` demanded a
   `status` key (rejecting Rondo's own smart-return `passed` schema) and used a
   flat regex that could not read nested JSON. **80 successful dispatches were
   misfiled as failures.** Fixed with dual-schema + raw_decode scanner; all 80
   historic outputs now parse (kept as a permanent regression corpus).

2. **bare+max = deterministic "Not logged in" (#293, CRITICAL).** `--bare`
   disables OAuth/keychain; `auth=max` strips ANTHROPIC_API_KEY; `config.bare`
   defaulted True. Every bare+max dispatch failed auth BY CONSTRUCTION — the
   entire historic 13.3% auth bucket (33 records). Fixed: drop --bare under max
   + WARN. Side effect: **in-session subprocess dispatch works** — the "known
   impossible" that spawned the Agent-path workaround was this bug.

3. **Audit trail dropped all diagnostics (#291).** error_message/stderr were
   never persisted — 467 failures said "(no message)". Forensics pack: every
   failure now carries message + stderr + blocked_reason + project.

## Fossilized-bug archaeology (bugs that taught the codebase wrong lessons)

- e2e smoke test ASSERTED "subprocess WILL fail in-session" — the #293 bug as doctrine
- 2 CLI tests patched a dead re-export, passing only because #293 made dispatch fail
- 9 e2e tests red because the wheel silently shipped without data files (#294, fixed)
- 23 unit tests were coupled to the LIVE user config (#292, hermetic fixture fixed)

## Corrected health numbers

| | Believed | True |
|---|---|---|
| Lifetime success | 68.5% | 64% raw, but April was 72% (80 recovered) |
| Recent (May/Jun) | unknown | **97%** |
| Provider-fault share of failures | "the AIs problem" | **≤18%** |

## Provider fleet (all canary-verified live)

openai gpt-5.4-nano/5.4-mini/5.5 · gemini -latest aliases ×3 · grok-4.3 ×3
(grok-3 family was RETIRED — found by the drift-check prototype on first run)
· mistral -latest ×3 · anthropic haiku-dated/sonnet-4-6/**opus-4-8** (unblocked)

## Verification

- chaos 15 / pat 133 / unit 1,365 / integration 364 / e2e 114 — all green
- 24/24 live integration tests dispatch REAL work (was 13/24)
- Production-data regression corpora: 80 parser outputs + 33 auth outputs
- ace-build full PASSED (after fixing its own zsh word-split bug — nightlies
  had been silently red since 06-02)
- Deployed via uv with cache-clean + symbol-verify (#288 protocol)

## Next wave (specced, not built)

STD-108 015-018 retry lifecycle · STD-101 240-242 windowed scoreboard ·
REQ-111 600-610 model registry · #289 init-template packaging ·
STD-110 016-020 flock layer (verify-first via ≥20-concurrent stress test) ·
#295 single combined-run flake (watch via REQ-107)
