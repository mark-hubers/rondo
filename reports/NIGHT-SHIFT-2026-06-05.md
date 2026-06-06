# NIGHT SHIFT — 2026-06-05/06 (16h autonomous, Mark's directive)

**Mandate (Mark, verbatim intent):** spec + code the big missing features Rondo
really needs; make real working examples of new features and more usage examples;
run real tests/ideas up to **$6.00 AI budget**; do it right and hard; gap-check
everything; keep going without help.

**Rules in force:** autonomous mode (no permission waits) · externalize ALL state
HERE after every sprint · OB tools every sprint (register→loops→gate→commit→done)
· TDD · claims verified before written · budget logged per dispatch.

## BUDGET LEDGER (cap $6.00)
| When | What | Cost | Running |
|------|------|------|---------|
| 23:5x | Cold Witness panel (3 providers, tier high) | ~$0.10 | $0.10 |

## TASK QUEUE (work top-down; update status as you go)
| # | Task | Status | Sprint |
|---|------|--------|--------|
| 0 | Recover Cold Witness outputs from ~/.rondo/audit (wrong key in my print; DO NOT redispatch) | TODO | — |
| 1 | Retry Cursor productization roadmap (output came back empty; earlier hostile review worked — maybe drop --mode plan or retry as-is) | TODO | — |
| 2 | Synthesize Cursor hostile review + roadmap + panel → **Rondo-SOP-105-public-release.md** (the "usable by a stranger" definition of done + phased work list) | TODO | RONDO-312 |
| 3 | **CI-able corpora** (answers Cursor's "local-only gates" indictment): sanitize a sample of the 80-parser + 33-auth corpus records into repo fixtures (tests/fixtures/corpus/), corpus tests run BOTH repo fixtures (always) and full local corpus (when present) | TODO | RONDO-313 |
| 4 | **Nightly alert wiring** (#285 residual — top weakness "nobody's watching"): `rondo schedule` daily job → providers --refresh --drift + retryq sweep + metrics 7d; FAILURE/STALE → macOS notification (notify support exists). Real working example of `rondo schedule` while at it | TODO | RONDO-314 |
| 5 | **#297 per-task affinity:** add task_type to AuditRecord (+dispatch pass-through), scoring groups by (model, task_type), recommend_model uses task-level learned BEFORE global learned | TODO | RONDO-315 |
| 6 | **REQ-111 604-610 auto-tiers + `rondo models --verify`** canary CLI (cheap live canary per tier ≈ $0.05/run; do one real run as the example) | TODO | RONDO-316 |
| 7 | **REQ-113 req 051 judge scoring** for matrix (judge: provider:model + rubric; budget-counted) + extend matrix example; real run ≈ $0.30 | TODO | RONDO-317 |
| 8 | **REQ-109 req 212 config [timeouts] matrix** (per model-class × effort, COALESCE) | TODO | RONDO-318 |
| 9 | **#298 STD-102→109 merge pass** (fold unique reqs, repoint 8 refs, archive 102) | TODO | RONDO-319 |
| 10 | More real examples: matrix-with-judge, schedule/alerting, per-task affinity demo; INDEX regen --write + count bump each time | TODO | with each |
| 11 | Final: full suite + cloud_full + update CONTEXT-SNAPSHOT + VER-100 + morning report for Mark | TODO | — |

## CONSTANTS / GOTCHAS (relearn after compaction)
- Repo: /Users/markhubers/git/mhubers/ace2 (rondo/ inside). cwd DRIFTS — always cd first.
- venv: ace2/.venv (../.venv from rondo/). Installed tool: uv; reinstall needs
  `/opt/homebrew/bin/uv tool install --force --reinstall --from .../ace2/rondo rondo`
  + SYMBOL-VERIFY grep (uv reuses cached wheels — finding #288). `uv` alias is broken (usage-value.sh).
- Caliber safe path open: rondo/src/rondo/ (session a7b6bc5d). Scanner false-positives:
  substring _AUTH/_circuit_breaker etc — known, finding #284, don't churn.
- ace-sprint: register --layer FIX --type WIRE --orbit 5 --round 9; loops write_tests/implement/verify
  with --cat test_write/code_edit/test_fix; then done.
- generate_index.py needs **--write** + EXPECTED_EXAMPLE_COUNT bump.
- Historical text: NEVER blanket-replace model IDs over narrative ("grok-3 retired" stays!).
- Gates: ace-build full before every commit. Full rondo suite ~23min — use targeted + background.
- Budget: log EVERY paid dispatch here. STOP paid work at $6.00.

## SPRINT LOG (append after each)
(empty — night starting)
