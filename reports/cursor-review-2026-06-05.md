## (1) Claims verdicts C1–C10 (hostile table)

| Claim | Verdict | What’s actually true (with evidence) | What’s inflated / false |
|---|---|---|---|
| **C1** Parser bug misfiled 80 successes; fixed; **all 80** now parse | **PARTIAL** | Parser is **actually fixed**: accepts both `status` and smart-return `passed`, and uses a real JSON scanner (`raw_decode`) instead of the broken flat regex. | “**All 80 historic outputs now parse**” is **not proven or gated in-repo**: the “historic corpus” test reads **your local** `~/.rondo/audit/` and **skips** if absent; it also asserts **≥95%**, not 100%. So “all 80” + “permanent regression corpus” is marketing. |
| **C2** bare+max was deterministic auth failure (13% bucket); fixed | **MOSTLY TRUE** | Code now **drops `--bare` under `auth=max` and warns**, which directly prevents the deterministic “Not logged in” combo. The campaign report’s “33 records” is consistent with the taxonomy dataset. | The “**13% bucket**” phrasing is plausible but depends on one dataset; also “24/24 live integration tests” is not verifiable from code alone. |
| **C3** Streaming dispatch works; 445s/462s success via streaming where non-streaming failed | **PARTIAL** | **Streaming SSE consumption exists** and is used for “thinking” Anthropic models; watchdog becomes “per-event silence” (not total duration). | The specific “445s/462s” story depends on a manifest in `~/.rondo/...` **not in this repo**. Not verifiable here. Also this is **API adapter** streaming, not Claude CLI subprocess streaming. |
| **C4** Matrix (REQ-113) is real: budgeted, blind, resumable; executed live twice | **TRUE (feature)** / **UNVERIFIED (history)** | The matrix implementation is real: **estimate-abort**, **hard running ceiling**, **manifest.json + resume**, **blind sealing + SHA-256**, report/reveal/status all implemented and unit-tested. | “Executed live twice (6/6 cells)” is an anecdote you can’t prove from repo state. |
| **C5** All **85 examples** valid; 3 new executed live; 78 stale model IDs refreshed | **FALSE / INFLATED** | There *is* an example metadata system that expects **85** example files. Some example categories are covered by tests (round files + “API example runs”). | The shipped `examples/INDEX.md` is **out of sync** (it lists **76**, not 85). `verify-examples.sh` is a **tiny smoke script**, not “re-validating 85/90 examples.” The “API examples run” test explicitly allows exit code **1**, so examples can fail and still “pass.” “78 refreshed IDs” is unsubstantiated. |
| **C6** ~2,060 tests green; production corpora as regression gates | **PARTIAL** | There are **~1961** `def test_` functions in `rondo/tests/`; with parametrization it could plausibly execute “~2,060.” | “Production corpora as regression gates” is **not true as a repo guarantee**: the corpus tests read `~/.rondo/audit/...` and **skip** without it, i.e., not a CI gate unless CI has your personal audit data mounted. |
| **C7** Recent success ~97%; lifetime 64%; ≤18% provider fault | **SUPPORTED (by repo dataset)** | The repo’s `taxonomy-raw.json` directly supports ~64% done-rate for outcomes and ~97% in May/Jun windows; provider-fault share ≤18% is consistent depending on what you count as provider fault (timeouts included or not). | Still small-n for “recent” (May: 98 outcomes; Jun: 39). Don’t oversell it. |
| **C8** Drift/registry caught retired grok-3 family on first run | **CAPABILITY TRUE / HISTORICAL CLAIM UNVERIFIED** | The drift checker is real: it fetches live model lists and flags configured tiers as **STALE**; tests explicitly simulate “grok-3 is dead.” | Whether xAI actually retired grok-3 “on first run” requires live external verification at that time; repo can’t prove it. Also **docs/ai-help still tell users to use grok-3** in places, which undermines the whole narrative. |
| **C9** 25-process stress test justified not building flock layer | **WEAK CLAIM** | Test exists; it checks “no torn JSONL lines,” “no false-stuck,” and “no duplicate outcomes.” | The test is **not very adversarial**: it calls `reconcile_stuck_intents()` immediately while using a **300s in-flight threshold**, which *by design* prevents false-stuck. This isn’t a justification; it’s a sanity check. |
| **C10** ai-help teaches all new features to MCP callers | **PARTIAL** | `--ai-help` exists, and MCP exposes `rondo://help`; dynamic command list is generated from the CLI parser. | The ai-help content is **not truth-aligned**: it contains stale model IDs (e.g., grok-3) and hard claims like “no other dispatch tool has it.” That’s not “teaching”; that’s shipping misinformation. |

---

## (2) NEW weaknesses Claude missed (actual, not vibes)

- **“Permanent regression corpora” is a lie-by-implementation**: the “production corpora” tests are local-only and skip without `~/.rondo/audit/`—so they’re not gates for anyone except Mark on his machine.  
- **Examples system is internally inconsistent**:
  - generator expects **85** examples,
  - `examples/INDEX.md` currently lists **76**,
  - README claims **90** “dispatch-verified” examples,
  - verification script checks almost nothing.
- **The “API examples are validated” claim is hollow**: the test harness explicitly treats example exit code **1** as acceptable, meaning examples can fail to run real dispatch and still “pass.”
- **Docs / ai-help contain stale model guidance (grok-3) even while bragging the drift tool caught grok-3 retirement**. That’s operationally embarrassing: the tool “caught it” but the docs keep telling newcomers to step on the rake.
- **Admitted-weakness #3 (“effort is API-only”) is simply wrong**: the subprocess Claude path supports `--effort`. That’s not a small slip; it’s evidence the self-audit was sloppy.
- **The flock-layer “verification” test is rigged toward passing**: with a 300s in-flight threshold, your immediate reconcile calls can’t realistically produce false-stuck unless timestamps are missing/broken—so you’re not testing the hard case.
- **Security posture is under-discussed**:
  - round files are arbitrary Python (execution risk),
  - MCP server has no authN/authZ (it only guards “don’t run interactively”),
  - audit reset is one flag away from erasing evidence.

---

## (3) Code quality assessment (is it good, or just well-tested?)

- **Architecture/layering**: Better than most solo tools. There’s a real separation between engine types, subprocess dispatch, API adapters, MCP registration, parsing, and audit. The split of `dispatch.py` into `dispatch_parse.py` etc. is a real quality move.
- **Naming/intent**: Generally clear; “COALESCE / ALWAYS-ON / Dual-Path-With-Alerting” is consistently used as design language, which reduces ambiguity.
- **Where it’s objectively not “good”**:
  - **Two different worlds**: Claude CLI subprocess vs provider HTTP adapters still behave differently (and matrix v1 is API-only by design). That’s a structural tax you will keep paying.
  - **Evidence gating is performative in places** (local-only corpora, “examples validated” while allowing failure).
  - **Some “reliability proofs” are spec prose + a non-adversarial test**, not strong verification.

Verdict: **This is a competent, unusually disciplined solo codebase—but it still contains multiple “truth gaps” where tests/docs claim stronger guarantees than the code enforces.**

---

## (4) Docs/examples assessment (newcomer vs insider)

- **Newcomer value**: Good entry points exist (Golden Path / Getting Started). The CLI surface is coherent and the MCP tool set is discoverable via `rondo://help`.
- **Insider-flavored failure**: The docs are **not consistently maintained** relative to reality:
  - model examples still mention grok-3 in places,
  - “no streaming support” appears in docs while the Anthropic adapter literally uses SSE streaming,
  - “90 dispatch-verified examples” is not backed by automation; the shipped index is out of sync.
- **Examples are plentiful but not reliably “educational truth”** unless you enforce a hard “examples must run” policy (you currently don’t).

Verdict: **Docs read confident; reality is messier. Newcomers will copy/paste stale provider IDs and hit failures that docs claim Rondo prevents.**

---

## (5) Truthfulness audit verdict (Claude’s honesty)

**Verdict: NOT fully honest.** Not “malicious lying,” but a consistent pattern of upgrading “code exists” into “verified, gated, and proven.”

Concrete failures:
- “All 80 historic outputs now parse” is asserted in narrative while the test is local-only + allows 5% failure.
- “Production corpora as regression gates” is not a repo-level gate.
- “All 85 examples valid / dispatch-verified” is not enforced; tests allow failure.
- Admitted-weakness list contains at least one **factually wrong** item (effort support).

Net: Claude’s brief is **~70% engineering truth, ~30% marketing inflation**.

---

## (6) Scores vs Claude (8/10 for Mark, 6.5/10 public)

- **For Mark’s use (local-first power tool)**: **7/10**  
  Strong core, good safety instincts, decent observability. But truth gaps (docs/examples/corpora) and split-brain behavior are real drag and will waste time.

- **As a future public tool**: **4.5/10**  
  The code could be open-sourced, but the public-facing story is currently too inconsistent (stale docs, example validation theater, local-machine assumptions, macOS bias, implicit configs). You’d bleed credibility fast.

Claude’s 8/10 and 6.5/10 are **too generous** given the documented overclaims and the “verification” that isn’t actually a gate.

---

## High-signal evidence excerpts

```44:93:/Users/markhubers/git/mhubers/ace2/rondo/src/rondo/dispatch_parse.py
def _is_result_dict(parsed: Any) -> bool:
    ...
    return isinstance(parsed, dict) and ("status" in parsed or "passed" in parsed)

def parse_task_json(text: str) -> dict[str, Any] | None:
    ...
    # -- Bare JSON objects: scan every '{' with raw_decode (req 124)
    decoder = json.JSONDecoder()
    ...
    while True:
        start = text.find("{", idx)
        ...
        parsed, end = decoder.raw_decode(text, start)
        ...
        if _is_result_dict(parsed):
            last_match = parsed
```

```2357:2387:/Users/markhubers/git/mhubers/ace2/rondo/tests/unit/test_dispatch.py
class TestHistoricCorpusParsing:
    def test_historic_partials_parse(self) -> None:
        audit = Path.home() / ".rondo" / "audit"
        log = audit / "rondo_audit.jsonl"
        if not log.exists():
            pytest.skip("no local audit corpus on this machine")
        ...
        # -- ≥95%: allow a handful of genuinely-malformed outputs in old data
        assert failures <= candidates * 0.05
```

```803:868:/Users/markhubers/git/mhubers/ace2/rondo/src/rondo/dispatch.py
def _build_subprocess_cmd(...):
    ...
    if config.effort:
        cmd.extend(["--effort", config.effort])
    ...
    if use_bare and config.auth == "max":
        logger.warning(
            "-WARNING- --bare requires ANTHROPIC_API_KEY but auth=max strips it. "
            "Running NON-bare on Max auth (hooks active). Use auth=api for --bare."
        )
        use_bare = False
```

```1:84:/Users/markhubers/git/mhubers/ace2/rondo/research/2026-06-05-failure-taxonomy/taxonomy-raw.json
{
 "outcomes": 1816,
 "status": {
  "INTENT": 908,
  "blocked": 44,
  "error": 164,
  "done": 584,
  "stuck": 3,
  "partial": 113
 },
 "error_codes": {
  "ERR_SUBPROCESS": 103,
  "ERR_TIMEOUT": 13,
  "ERR_PROVIDER": 17,
  "ERR_PROVIDER_DOWN": 28,
  "ERR_AUTH": 3,
  "ERR_RECONCILED_STUCK": 3,
  "ERR_MALFORMED_JSON": 113
 },
 ...
}
```

```17:36:/Users/markhubers/git/mhubers/ace2/rondo/examples/generate_index.py
EXPECTED_EXAMPLE_COUNT = 85  # -- RONDO-311: +matrix yaml, +matrix cli, +fleet-health cli
...
def _collect_example_files(examples_dir: Path) -> list[Path]:
    ...
```

```51:75:/Users/markhubers/git/mhubers/ace2/rondo/tests/integration/test_api_examples.py
def test_example_main_runs(self, example_file: Path) -> None:
    ...
    try:
        module.main()
    except SystemExit as exc:
        # -- Examples return 0 (success) or 1 (findings/warnings) — both are OK
        if exc.code not in (0, 1, None):
            raise
```

```72:77:/Users/markhubers/git/mhubers/ace2/rondo/docs/WHY-RONDO.md
3. **No streaming support.** Rondo waits for the full response. No token-by-token streaming to the user.
```

```499:503:/Users/markhubers/git/mhubers/ace2/rondo/src/rondo/data/ai_help_data.json
"routing": "Use provider:model syntax — 'gemini:gemini-2.5-flash', 'grok:grok-3', 'mistral:large'; OpenAI optional",
...
"multi_provider": "rondo_cloud() dispatches sequentially to N providers; default trio preference Gemini + Grok (+ Mistral for security)",
```
