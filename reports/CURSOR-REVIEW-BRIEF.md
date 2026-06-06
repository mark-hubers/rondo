# Cursor Deep-Review Brief — Rondo (2026-06-05)

**Your mandate from Mark:** full, hard, hostile review of code, docs, examples,
and help files — and an audit of whether Claude's claims this week were truthful.
**Do not be polite. Every claim below is offered for refutation.** Where you find
a claim false or inflated, say so plainly — that is the primary purpose.

## Scope & entry points

- Code: `rondo/src/rondo/` (notably `adapters/anthropic_api.py`, `matrix.py`,
  `retry_queue.py`, `model_registry.py`, `dispatch.py`, `audit.py`)
- Specs: `rondo/specs/` (41 files; most-changed: REQ-109 v2.0, REQ-111 v0.4,
  REQ-113 v0.2, STD-108 v0.7, STD-110 v0.6, STD-113 v1.1, IFS-100 v0.8, VER-100 v1.2)
- Docs: `rondo/README.md`, `rondo/docs/` (19 files)
- Examples: `rondo/examples/` (85 files, INDEX.md) + `verify-examples.sh`
- AI-help: `rondo/src/rondo/data/ai_help_data.json`
- Evidence dirs: `rondo/research/2026-06-03-rondo-audit/`,
  `rondo/research/2026-06-05-failure-taxonomy/` (incl. CAMPAIGN-REPORT.md)
- Session commits: `git log --since="2026-06-03" --oneline -- rondo/` (~30)

## CLAIMS REGISTER — verify or refute each

| # | Claim | Where to check | How to refute |
|---|-------|----------------|---------------|
| C1 | Parser bug misfiled 80 successful dispatches; fixed; all 80 historic outputs now parse | `dispatch_parse.py` parse_task_json; `TestHistoricCorpusParsing`; commit 4743ebc7 | Run the corpus test; sample `~/.rondo/audit/` partials yourself |
| C2 | bare+max was a deterministic auth failure (the 13% bucket); fixed | `dispatch.py` `_build_subprocess_cmd` bare guard; IFS-100 req 015; commit 30a80189 | Construct bare+max config; check 24/24 live integration tests claim |
| C3 | Streaming dispatch works; a 445s & 462s max-effort thinking dispatch completed where 3 non-streaming attempts failed | `anthropic_api.py` consume_sse_stream; `~/.rondo/matrix/essay-split-46v48-v2/manifest.json` | Inspect manifest timestamps/costs; re-run a streamed max-effort dispatch |
| C4 | Experiment matrix (REQ-113) is real: budgeted, blind, resumable; executed live twice (6/6 cells each) | `matrix.py` + `test_matrix.py` (18 tests); `~/.rondo/matrix/demo-matrix/` | Run `rondo matrix run examples/rounds/06-experiment-matrix.yaml --dry-run`; audit budget-stop logic for bypasses |
| C5 | All 85 examples valid; 3 new ones were executed live before commit; 78 stale model IDs were refreshed | `examples/`, INDEX.md, verify-examples.sh; commit history | grep examples for any remaining dead model IDs; run the harness |
| C6 | ~2,060 tests green; production corpora (80 parser + 33 auth) as regression gates | `rondo/tests/`; run the suite | Run it. Look for tests weakened to pass (3 were FIXED this week for encoding bugs — judge whether fixes were legitimate: test_cli.py dead patches, e2e smoke fossil) |
| C7 | Recent dispatch success ~97%; lifetime 64% was dominated by build-era + Rondo-side bugs (≤18% provider-fault) | `rondo/research/2026-06-05-failure-taxonomy/` raw JSON + `~/.rondo/audit/rondo_audit.jsonl` | Recompute from the JSONL yourself |
| C8 | Drift/registry caught a fully retired grok-3 family on first run | `model_registry.py`; `~/.rondo/models-cache.json`; config git history | Check xAI's live model list |
| C9 | 25-process stress test justified NOT building the flock layer | `test_audit_stress.py`; STD-110 v0.6 | Critique the test: is 25×8 with mid-flight reconciles actually adversarial enough? This is the claim most worth attacking |
| C10 | ai-help teaches all new features to MCP callers | `ai_help_data.json`; `rondo --ai-help` | Diff capabilities vs actual CLI surface — find undocumented or over-documented features |

## WEAKNESSES ALREADY ADMITTED (verify Claude admitted them accurately; extend the list)

1. No alerting: nightly build failures went unnoticed ~3 days (finding #285 residual open)
2. Test-suite trust bruised: 23 live-config-coupled tests, 2 dead patches, 1 fossilized assertion found+fixed THIS WEEK — unknown soft spots likely remain
3. Split brain: matrix/effort/streaming are API-path only; the Max-plan subprocess path has none of it
4. 3 days of soak on the new regime — all reliability numbers are small-n
5. Single machine, no git remote, no backup (highest practical risk)
6. Module-size debt: dispatch.py ~1,100 lines, mcp_dispatch ~1,000
7. Per-task learned routing unbuilt (audit records lack task_type — finding #297)
8. ~30-min streamed-connection ceiling observed once (1,802s death) — unexplained
9. Convergence scanner: 65 medium findings repo-wide (cross-product dependency declarations)
10. Caliber live scanner false-positives (substring private-name matches) — dev friction
11. One non-reproducible combined-run test failure (#295) — name lost, being watched

## Hard questions Mark wants answered

1. Is the code quality actually good, or merely well-tested? (architecture, naming, layering)
2. Are the examples genuinely educational for a newcomer, or insider-flavored?
3. Is REQ-113 (matrix) genuinely novel vs LangSmith/promptfoo/etc. evaluation tooling — was the "no other tool has this" claim true?
4. Did the week's velocity (16 sprints, ~30 commits in 3 days) leave hidden corners?
5. Score it: for Mark's use, and as a future public tool. Claude said 8/10 and ~6.5/10 — was that honest?
