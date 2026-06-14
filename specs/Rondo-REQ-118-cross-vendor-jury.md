# Rondo-REQ-118: Cross-Vendor Jury

*The model that wrote the artifact does not get to certify it. A DIFFERENT vendor
does — and disagreement is the signal. The one moat a single-vendor tool can't copy.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-06-14 | **Status:** BUILT (minimal) | **Owner:** Mark G. Hubers
**Depends on:** REQ-109 (provider adapters), REQ-112 (error envelope), STD-114 (sanitize)
**Driver:** the competitive reality check (reports/competitive/LANDSCAPE-2026-06-13.md):
every tool runs tests; the one thing Anthropic/Cursor/Copilot structurally WON'T
build is a competitor's model judging their own. That is rondo's defensible wedge.
Full thesis: docs/CROSS-VENDOR-JURY.md.

---

## 1. Purpose

Make the cross-vendor adversarial review a first-class, reusable capability —
`jury_review()` (`src/rondo/jury.py`) + an MCP tool — not a hand-wired example.
A panel of DIFFERENT vendors independently judges an artifact; the step is
accepted only if at least one juror is reached AND every reached juror agrees;
the disagreement (objecting jurors) is surfaced as the product.

## 2. Requirements (all BUILT — `tests/unit/test_jury.py`, mutation 22/22)

| # | Requirement | Priority | Verification |
|---|-------------|----------|--------------|
| 001 | `jury_review(artifact, question, jurors, dispatch)` convenes N DIFFERENT-vendor jurors on the artifact | MUST | `test_unanimous_pass_is_accepted` |
| 002 | Accepted ONLY if >=1 juror reached AND every reached juror agrees (passed) | MUST | `test_one_objection_blocks_and_is_surfaced` |
| 003 | The DISAGREEMENT (objecting jurors + reasons) is returned, not hidden | MUST | `test_one_objection_blocks_and_is_surfaced` |
| 004 | Verdict channel = the smart-return `passed` field (normalized across vendors); a custom key is unreliable | MUST | `test_verdict_uses_passed_channel_not_a_custom_key` |
| 005 | A juror that errors OR returns no parseable verdict is INCONCLUSIVE (reached=False), never a silent no-vote | MUST | `test_unreachable_juror_is_inconclusive_not_a_no_vote`, `test_valid_json_without_passed_key_is_inconclusive` |
| 006 | Zero jurors reached → NOT accepted (cannot certify on no verdicts) | MUST | `test_all_unreachable_is_not_accepted` |
| 007 | Each juror's prompt carries the real artifact + question | MUST | `test_each_juror_gets_the_artifact_and_question` |
| 008 | Injectable dispatch seam (hermetic tests; production default = guarded rondo_run_file) | MUST | the dispatch= param + `test_default_dispatch_normalizes_a_real_envelope` |
| 010 | MCP tool `rondo_jury` exposes the jury for live use in Claude Code | SHOULD | MCP registration |

## 3. Honest limits

- It verifies what a reviewer can JUDGE from the artifact; it does not run the
  code (that's REQ-115 verify — the two compose: mechanical verify AND the jury).
- Cross-vendor cost = N dispatches per review. Jurors default to gemini:high +
  grok:grok-4.3; configurable.
- A unanimous-wrong jury is still possible (all vendors miss the same bug) — the
  jury raises the bar, it is not infallible. Compose with REQ-115 mechanical verify.
