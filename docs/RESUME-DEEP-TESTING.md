# Resume Runbook — Rondo Deep Testing (post RONDO-209)

**Created:** 2026-04-08
**Last sprint:** RONDO-209 (closed)
**Last commit:** `868d71a6` — Validate partial-write resilience
**Current state:** 1658 tests passing, pylint 9.67/10, build 22s, zero open HIGH findings

---

## How to resume

When you're ready to do the deep testing pass, just say:

> **"Resume Rondo deep testing — read RESUME-DEEP-TESTING.md"**

That's the trigger. Claude will read this file and have full context.

---

## Where you left off

You completed RONDO-204 through RONDO-209 (5 sprint clusters, ~50 commits over 2 sessions).
The Rondo dispatch engine is now production-ready for your specific use case (macOS,
multi-session Claude Code MCP). All HIGH severity findings are closed.

The remaining work is **VALIDATION** — proving every closed finding is genuinely fixed
via 4 phases of deep testing.

---

## What's in flight (READ THIS FIRST)

- **No active sprint.** RONDO-209 is closed. Start a new sprint (RONDO-210?) before any code changes.
- **Branch:** `main` (no feature branch)
- **Last build:** PASS, 1658 tests, 22s
- **Last commit:** `868d71a6` — `RONDO-209: validate partial-write resilience`
- **Working tree:** clean (no uncommitted changes)

---

## The 4 deep testing phases

### Phase A — fast verification (free, no external deps, ~5 min)

1. **Full default build** — proves test suite still green:
   ```bash
   cd ~/git/mhubers/ace2
   ace-build full --product rondo
   ```
   Expected: 1658 tests pass, pylint ≥9.67/10, ~22s

2. **Pylint full report** — shows current code quality:
   ```bash
   .venv/bin/python -m pylint rondo/src/rondo/ 2>&1 | tail -30
   ```
   Expected: 9.67/10, 0 broad-exception-caught violations in critical paths

3. **Per-finding traceability audit** — the most important verification.
   No script exists yet. NEEDS TO BE WRITTEN. The script should:
   - Query `audit_findings` for status='fixed' AND id BETWEEN 200 AND 260
   - For each finding, find the commit that closed it (via `git log --grep="#NNN"`)
   - For each commit, identify the test file(s) modified
   - Run those tests in isolation and verify they pass
   - Report any finding that has NO matching commit or NO test
   - Output: `rondo/reports/finding-traceability-YYYY-MM-DD.md`

   This is the highest-value missing piece. It catches the OB-bug class (silent
   no-op closures). When you resume, ASK Claude to write this script first.

### Phase B — real-API verification (~$0.50 cost, ~5 min)

4. **Cloud tests:**
   ```bash
   cd ~/git/mhubers/ace2
   .venv/bin/python -m pytest rondo/tests/ -m cloud -v
   ```
   This will burn ~$0.10-0.30 in real API calls across gemini, openai, grok, mistral, anthropic.
   Verifies every adapter actually works against real APIs.

5. **Multi-provider review (dogfood):**
   ```python
   # -- Direct call (bypasses MCP server cache):
   cd ~/git/mhubers/ace2
   .venv/bin/python -c "
   import sys; sys.path.insert(0, 'rondo/src')
   from rondo.mcp_compose import rondo_multi_review
   import json
   r = json.loads(rondo_multi_review(
       prompt='Final stability check — find any remaining issues',
       providers='[\"gemini:gemini-pro-latest\", \"openai:gpt-5.5\", \"grok:grok-4.3\"]',
       dry_run=False,
   ))
   for p in r['per_provider']:
       print(f'{p[\"provider\"]}: {p[\"status\"]}, dur={p.get(\"duration_sec\",0):.1f}s')
       print(p.get('output', '')[:500])
   "
   ```

### Phase C — concurrent stress test (~$1, ~10 min)

6. **Real concurrent stress test (NEW — needs writing):**
   No test exists yet. Create `rondo/tests/integration/test_stress_real_dispatch.py` with:
   - Spawn 5 `subprocess.Popen` workers
   - Each calls `rondo_run_file()` with a real prompt against gemini-flash
   - Run for 60 seconds
   - Verify: zero corrupted audit JSONL lines, zero lost idempotency entries,
     zero race-condition errors in logs
   - Cost: ~$0.50-1.00 in real API calls

7. **Long-running stability run:**
   Just keep `pytest rondo/tests/ --tb=line -x` running for 5+ minutes in a loop
   to catch slow leaks (file descriptors, memory, etc.)

### Phase D — external validation (~$0.50, ~5 min)

8. **Round 4 AI review** — final dogfood pass:
   Use the multi_review snippet from Phase B step 5 with this prompt:
   > "After RONDO-204 through RONDO-209 (8 commits in RONDO-209: idempotency JSONL,
   > audit fcntl.flock, multi_review error surfacing, broad-except narrowing,
   > provider ABC extraction, mcp cycle break, crash recovery test, partial-write
   > resilience tests). Tests: 1658 passing including 9 multi-process. Pylint 9.67.
   > Find any REMAINING bug class or risk that could bite in production. Be brutal."

---

## Key file locations

| What | Where |
|------|-------|
| **Open findings DB** | `~/git/mhubers/ace2/db/round-tracking.db` (table: `audit_findings`) |
| **Closed RONDO-209 findings** | #246, #247, #248, #250, #251, #252, #254 (7 fixed) |
| **Open findings (low severity)** | #245 (OB tooling), #249 (won't fix), #253 (MCP cache) |
| **Test inventory** | `rondo/docs/TEST-INVENTORY.md` (auto-generated) |
| **Test strategy ADR** | `rondo/docs/ADR-001-test-strategy.md` |
| **Test layer guide** | `rondo/tests/README.md` |
| **Multi-process tests** | `rondo/tests/integration/test_integration_multiprocess.py` (9 tests) |
| **Reliability integration** | `rondo/tests/integration/test_integration_reliability.py` (10 tests) |
| **Master integration flow** | `rondo/tests/integration/test_integration_flow.py` (11 tests) |
| **Build script** | `~/bin/ace-build` (has finding #245 — wrong pylint dir) |
| **Sprint CLI** | `~/bin/ace-sprint` |

---

## Finding state at session end

```
#245 OPEN   medium  ace-build pylint runs on src/ace2/ instead of rondo/src/rondo/
#246 FIXED  high    JSON race in idempotency.py — switched to append-only JSONL
#247 FIXED  medium  multi_review max_tokens too low — bumped to 8K
#248 FIXED  medium  multi_review error_code/error_message now surfaced
#249 OPEN   low     Unicode homoglyphs (won't fix — contrived attack vector)
#250 FIXED  medium  Serial retry on ERR_PROVIDER_DOWN/ERR_RATE_LIMIT
#251 FIXED  high    Audit rotation race — added fcntl.flock cross-process lock
#252 FIXED  medium  Crash recovery test — SIGKILL subprocess + reconcile
#253 OPEN   low     MCP server caches code, requires Claude Code restart
#254 (cluster) FIXED — 5 broad-except narrowed in retry/health/mcp_tools/preflight/_version
```

---

## Last 8 commits in RONDO-209 (for git log reference)

```
868d71a6 RONDO-209: validate partial-write resilience (round-3 review concern)
0d963672 RONDO-209 #254: narrow broad-except handlers — kill silent-failure bite class
d462621f RONDO-209: fix #252 — multi-process crash recovery test
69b7ae79 RONDO-209 pylint: break mcp family cyclic imports
548205c5 RONDO-209 pylint: extract ProviderAdapter ABC to break adapter↔providers cycles
fb0aaff9 RONDO-209: fix #248/#250 multi_review observability + serial retry
5601d70e RONDO-209: fix #251 audit rotation cross-process race + multi-process rotation test
aa1d08ed RONDO-209: fix #246 (JSON race) + #247 (truncation) + multi-process tests
```

---

## What NOT to do when resuming

- **Don't** run `ace-build pylint` and trust the score — it's wrong (pylints `src/ace2/` instead of `rondo/src/rondo/`). Use the direct command in Phase A item 2.
- **Don't** trust the MCP `mcp__rondo__rondo_multi_review` tool — it's cached old code. Use the direct Python snippet.
- **Don't** skip the traceability audit (Phase A item 3). It's the highest value piece.
- **Don't** start fixing things without an active sprint. Run `ace-sprint register RONDO-210 ...` first.

---

## Quick smoke test you can run RIGHT NOW (10 seconds)

```bash
cd ~/git/mhubers/ace2 && ace-build full --product rondo 2>&1 | tail -5
```

Expected output:
```
✓ All 1658 tests passed
✓ Pylint score: 9.89/10  (NOTE: this is the buggy ace-build score; real is 9.67)
✓ FULL BUILD PASSED (22s)
```

If this fails, something has regressed since `868d71a6` — check git status and `git log --oneline -5`.
