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
| 00:4x | models --verify canary 15 tiers (RONDO-316) | $0.0007 | $0.1007 |
| 00:5x | (wheel redeployed; installed rondo models verified live) | $0 | $0.1007 |
| 01:3x | judge-demo matrix: 4 cells + 4 judge dispatches, 3 providers (RONDO-317) | $0.0025 | $0.1032 |

## TASK QUEUE (work top-down; update status as you go)
| # | Task | Status | Sprint |
|---|------|--------|--------|
| 0 | Recover Cold Witness outputs | DONE (audit recovery; finding #302 on return shape) | — |
| 1 | Cursor roadmap retry | DONE (reports/cursor-productization-roadmap-2026-06-06.md; empty-output cause: --mode plan suppressed print) | — |
| 2 | SOP-105 public-release roadmap | DONE v0.2 (4-AI synthesis, committed) | RONDO-312 ✓ |
| 3 | CI-able corpora | DONE (17 fixtures, dual-source gates, fake-HOME proven, finding #301 fixed) | RONDO-313 ✓ |
| 4 | Nightly watchdog | DONE (committed, wheel deployed, live ALERT verified, finding #285 fixed) | RONDO-314 ✓ |
| 5 | Per-task affinity | DONE (full chain live-verified, finding #297 fixed, example 07-task-affinity, INDEX 87) | RONDO-315 ✓ |
| 6 | Auto-tiers + canary | DONE (15/15 PASS $0.0007; 606 auto-apply -> work request; non-chat filter from live run) | RONDO-316 ✓ |
| 7 | Matrix judge scoring | DONE (judge field was DEAD — now wired; live 4-cell run, judge col 8.0(n=2)×2 groups, $0.0025) | RONDO-317 ✓ |
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
- RONDO-317 ✓ matrix judge (req 051): judge_rubric required at load, _judge_cell costed into SAME budget, crash-isolated, report judge column. Dead-field made real (Cursor's dead-flag class). Live: gpt-5.4-mini judged haiku+gemini cells.
- RONDO-316 ✓ auto-tiers+canary: derive_auto_tiers/resolve_model/verify_models/registry_mode + rondo models CLI. Live lessons: 'geMINI' substring trap -> token matching; catalogs mix non-chat models -> exclusion list. Canary 15/15 PASS $0.0007. req 606 auto-apply = work request, honestly NOT claimed.
- RONDO-315 ✓ per-task affinity: task_type Task→AuditRecord→scoring→recommend_model. Live round proof in audit. Note: `rondo run` inside CC needs env -u CLAUDECODE (preflight RED otherwise). Subprocess dispatches = Max plan tokens, NOT API ledger.
- RONDO-314 ✓ nightly watchdog: live runs caught 2 mock-blind bugs (get_rondo_config returns DICT; drift entries carry 'state' NOT 'status') → 2 unmocked contract tests added. First real sweep: ALERT, 7d 94% < 95% (47 dispatches — tonight's torture tests count). Plist NOT installed — Mark's call: `rondo schedule --cmd nightly --interval daily --name nightly-watchdog --install`. uv lock: don't run two installs.
- RONDO-313 ✓ CI corpus fixtures: build_corpus_fixtures.py (redact+verify+leak-abort), 12 parser + 5 auth (1 prod + 4 synthetic labeled), gates pass with AND without local corpus. Gotcha: 33 auth records = 1 distinct variant; auth fixture syntax: finding-update ID fix --sprint X.
- RONDO-312 ✓ SOP-105 v0.1→v0.2 (4-AI synthesis). Panel recovered from audit (~$0.10). Findings #302. Cursor lesson: --mode plan suppresses -p output; omit it for printable runs.
