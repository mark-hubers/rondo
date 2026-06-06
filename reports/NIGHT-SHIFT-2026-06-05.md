# NIGHT SHIFT — 2026-06-05/06 (16h autonomous, Mark's directive)

## ☀ MORNING REPORT (read this first)

**TL;DR: 10 sprints closed (RONDO-313 → 322), every feature live-tested, full suite 2165/2165 GREEN, $0.10 of your $6.00 spent.**

| # | What Rondo gained tonight | Proof it works |
|---|---------------------------|----------------|
| 1 | **Nightly watchdog** — `rondo nightly`: drift + retryq + 7d reliability in ONE schedulable sweep, macOS alert on failure | First real run honestly flagged ALERT: 7d success 94% < 95% target |
| 2 | **CI-able corpus gates** — 17 sanitized fixtures in the repo; parser/auth gates now run on ANY machine | Proven with fake-HOME: 2 passed where they used to skip |
| 3 | **Per-task affinity** — tasks carry `task_type`; Rondo learns which model is best at WHICH job | Live round: classify/code-review/summarize all landed in the audit trail |
| 4 | **Auto-tiers + canary** — `rondo models --tiers` (derived low/mid/high) + `--verify` (live canary) | 15/15 tier models answered, $0.0007 total |
| 5 | **Matrix judge scoring** — the dead `judge:` field is real; one external model scores every cell | Live: gpt-5.4-mini judged haiku+gemini cells, judge column in report |
| 6 | **Config `[timeouts]`** — per model-class × effort, COALESCE, in config-template | Live resolve: 120 / 600 / 900 |
| 7 | **STD-102→109 merge** — finding #298 closed, 20 refs repointed, 102 archived | Residual grep clean |
| 8 | **`rondo doctor`** — install diagnosis + redacted support bundle (the first command support asks a stranger to run) | Live: 6/6 PASS on your machine; bundle leak-scan clean |
| 10 | **Convention sweep** — full 25-min suite caught 8 reds the build gate missed (signatures, layering, complexity, doc sync, corpus). All fixed; gate-coverage finding filed | 298 tests green across all 8 areas |
| 9 | **Redaction GUARANTEE** — plant realistic secrets, sweep every written file. Found+fixed 2 REAL holes: Google AIza keys had NO scrub pattern; notify wrote errors verbatim to log + macOS banner | 50/50 green; security finding filed |

**Also:** SOP-105 v0.2 (public-release roadmap, 4 AIs synthesized) · 4 new live examples (INDEX = 89) · findings #285 #297 #298 #301 fixed · ~8 commits, all through ace-build gates.

**Two real bugs the mocks missed, caught by live runs** (and now pinned by unmocked contract tests): config returns a dict not an object; drift entries carry `state` not `status`. Plus: "geMINI" substring classified every Gemini model as low-tier — token matching fixed it.

**YOUR DECISION (one-liner, when you want the watchdog armed):**
```
rondo schedule --cmd nightly --interval daily --name nightly-watchdog --install
launchctl load ~/Library/LaunchAgents/com.rondo.nightly-watchdog.plist
```
I did NOT install it — a recurring background job on your Mac is your call.

**Note on the 94% reliability alert:** tonight's own torture tests count against the 7d window. Not a regression — the watchdog telling the truth.

---

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
| 8 | Config [timeouts] matrix | DONE (resolve_read_timeout COALESCE, adapter wired, template documented, live-verified 120/600/900) | RONDO-318 ✓ |
| 9 | STD-102→109 merge | DONE (6 reqs folded w/ Origin column, 20 refs repointed in 7 specs, 102 ARCHIVED, #298 fixed) | RONDO-319 ✓ |
| 10 | More real examples: matrix-with-judge, schedule/alerting, per-task affinity demo; INDEX regen --write + count bump each time | TODO | with each |
| 11 | Final wrap | DONE — full suite **2165 passed, 0 failed** (24:11) after RONDO-322 sweep; morning report ✓, CONTEXT-SNAPSHOT ✓, VER-100 v1.3 ✓ | — |
| 12 | BONUS: `rondo doctor` (SOP-105 P2-0) | DONE (REQ-103 v1.4 reqs 030-036; live 6/6 PASS; bundle leak-scan clean) | RONDO-320 ✓ |
| 13 | BONUS: P1-7 redaction guarantee | DONE (2 real holes fixed: AIza pattern missing, notify verbatim; artifact-level permanent gate) | RONDO-321 ✓ |
| 14 | BONUS: convention sweep (8 suite reds) | DONE (signed, VER refs, layering, comments, 5 complexity extractions, doc sync, corpus refinement; gate-coverage finding) | RONDO-322 ✓ |

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
- RONDO-322 ✓ convention sweep: full suite (25min) found 8 reds ace-build had passed — gate selection investigation filed. Complexity surgery on 5 hot functions verified by 298 tests. Corpus gate now distinguishes misfiled-success from true-partial.
- RONDO-321 ✓ redaction guarantee: artifact-level tests caught what function-level missed for months. AIza pattern + notify choke-point sanitize. High-severity security finding filed.
- RONDO-320 ✓ rondo doctor: 6 checks + fix hints + redacted bundle (leak = abort). Lessons: example `|| true` masked stale wheel (redeployed, reran honestly); found+killed 4.5h ZOMBIE chain from pre-compaction — its REQ-111 req 611 edit NEVER landed despite 'done' claim → truth-repaired + finding filed (verify file state, not task intent).
- RONDO-319 ✓ STD-102→109 merge: Explore agent mapped uniques/covered/refs (research-only, allowed); fold has Origin traceability; round-def reqs → REQ-100; 2 contradictions dropped openly.
- RONDO-318 ✓ config timeouts (req 212): adapters/timeouts.py, per-dispatch→config→defaults, unknown thinking effort floors 600. Gotcha: adapter class is AnthropicAPIAdapter not AnthropicAdapter.
- RONDO-317 ✓ matrix judge (req 051): judge_rubric required at load, _judge_cell costed into SAME budget, crash-isolated, report judge column. Dead-field made real (Cursor's dead-flag class). Live: gpt-5.4-mini judged haiku+gemini cells.
- RONDO-316 ✓ auto-tiers+canary: derive_auto_tiers/resolve_model/verify_models/registry_mode + rondo models CLI. Live lessons: 'geMINI' substring trap -> token matching; catalogs mix non-chat models -> exclusion list. Canary 15/15 PASS $0.0007. req 606 auto-apply = work request, honestly NOT claimed.
- RONDO-315 ✓ per-task affinity: task_type Task→AuditRecord→scoring→recommend_model. Live round proof in audit. Note: `rondo run` inside CC needs env -u CLAUDECODE (preflight RED otherwise). Subprocess dispatches = Max plan tokens, NOT API ledger.
- RONDO-314 ✓ nightly watchdog: live runs caught 2 mock-blind bugs (get_rondo_config returns DICT; drift entries carry 'state' NOT 'status') → 2 unmocked contract tests added. First real sweep: ALERT, 7d 94% < 95% (47 dispatches — tonight's torture tests count). Plist NOT installed — Mark's call: `rondo schedule --cmd nightly --interval daily --name nightly-watchdog --install`. uv lock: don't run two installs.
- RONDO-313 ✓ CI corpus fixtures: build_corpus_fixtures.py (redact+verify+leak-abort), 12 parser + 5 auth (1 prod + 4 synthetic labeled), gates pass with AND without local corpus. Gotcha: 33 auth records = 1 distinct variant; auth fixture syntax: finding-update ID fix --sprint X.
- RONDO-312 ✓ SOP-105 v0.1→v0.2 (4-AI synthesis). Panel recovered from audit (~$0.10). Findings #302. Cursor lesson: --mode plan suppresses -p output; omit it for printable runs.
