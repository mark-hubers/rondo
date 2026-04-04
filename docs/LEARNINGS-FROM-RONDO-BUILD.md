# Learnings from Rondo Build — What OB + Caliber Need

**Sessions:** 91-97 | **Date:** 2026-04-04
**Context:** 16 sprints of Rondo building exposed gaps in OB and Caliber that we need to fix.

---

## Caliber Gaps (Things Caliber Should Have Caught)

### Already Filed (Spike Backlog)

Check `caliber/docs/SPIKE-BACKLOG.md` for existing S1-S17.

### NEW Spikes (from Rondo build Sessions 91-97)

| Spike | What it catches | How we found it | Priority |
|-------|----------------|-----------------|----------|
| **S18: DRY detector** | Same 5+ line block in 2+ files (adapter instantiation was in 4 places) | Manual grep during refactoring plan | High |
| **S19: Module growth alert** | "cli.py grew 150 lines this sprint" — warn before hitting size limit | Hit 1277 lines, only caught by convention test after the fact | High |
| **S20: Import fan-out** | "cli.py imports from 8+ modules" — coupling indicator | Review command imported adapters directly, broke import layer convention | Medium |
| **S21: Factory pattern enforcer** | "You're calling GeminiAdapter() directly — use get_adapter()" | Cursor found adapter instantiation duplication | Medium |
| **S22: Config drift detector** | "config.toml says gemini-2.0-flash-lite but code says gemini:flash" | cloud_full test caught 2 bad model IDs — should be a Caliber check | High |
| **S23: Dead config detector** | "`trust` field in config but never read by code" | Cursor found trust is documentation-only | Medium |
| **S24: Startup wiring check** | "load_providers_config() exists but no caller from main()" | Cursor found the #1 production bug — config never loaded | High |
| **S25: Model ID validator** | "gemini:flash is not a valid API model — should be gemini-2.5-flash" | 39 hardcoded wrong model IDs, only caught by real API call | High |

### How Caliber Could Implement These

| Spike | Implementation approach |
|-------|----------------------|
| S18 (DRY) | AST hash of function bodies → compare across files. Or simpler: 5+ identical lines across 2+ files = block. |
| S19 (Growth) | Compare file LOC before/after edit. If delta > 50 in one Edit, warn. If total > 1000, block. |
| S20 (Fan-out) | Count `from X import` sources per file. > 8 = warn. |
| S21 (Factory) | Grep for specific class constructors (e.g., `GeminiAdapter(`) outside approved modules. |
| S22 (Config drift) | Parse config.toml + grep source for model strings → compare. Run in `ace-build`. |
| S23 (Dead config) | Parse config.toml keys → grep source for usage → report unused keys. |
| S24 (Startup wiring) | For each `def load_*()` function, verify it's called from at least one entry point (main, create_server). |
| S25 (Model ID) | Optionally call provider health endpoint during `ace-build full --product rondo` to verify model names. |

---

## OB Gaps (Things OB Should Track)

### Metrics OB Should Capture Per Build

| Metric | What | Why | Where |
|--------|------|-----|-------|
| **Per-file LOC** | Size of each source file | Catch "cli.py growing from 800 → 1277" trend | `quality_snapshots` |
| **Max complexity** | Highest cyclomatic complexity function | Catch "rondo_run_file went 12 → 16" | `quality_snapshots` |
| **Import fan-out** | Max imports per file | Coupling indicator | New column |
| **DRY score** | % duplicated code (e.g., via `ruff` or `jscpd`) | "Duplication crept from 2% to 5%" | New column |
| **Convention pass rate** | 19/21, 20/21, 21/21 per build | "We've been at 19/21 for 3 sprints — fix it" | Build telemetry |

### Process Improvements

| What OB should enforce | What happened without it |
|-----------------------|------------------------|
| **Spec before code** | 3 sprints coded first, speced after (I had to be told) |
| **Product-scoped builds** | ACE failures blocked Rondo work for weeks |
| **Config validation in build** | gemini:flash was wrong for weeks — no test caught it |
| **Convention gate on sprint close** | 2 pre-existing convention failures tolerated indefinitely |
| **Cursor review cadence** | Cursor found production bugs Claude missed (3 reviews, all valuable) |

---

## Symbols System (F25) — Why It's Critical

### What Symbols Enables

| Without symbols | With symbols |
|----------------|-------------|
| "grep for GeminiAdapter" → hope you found all | "symbols query: who instantiates GeminiAdapter" → complete list |
| Manual refactoring plan (2 hours) | "symbols impact: move rondo_run_file to mcp_dispatch.py" → auto-generated change list |
| "I think nothing calls this function" | "symbols callers: _cmd_old_thing → 0 callers → safe to delete" |
| Caliber can't check call patterns | Caliber queries symbols: "is this function called from main()?" |

### What Symbols Needs (Minimum Viable)

| Component | What it stores | How it's built |
|-----------|---------------|---------------|
| **Function table** | name, file, line, return_type, params | AST parse of all .py files |
| **Call graph** | caller_func → callee_func | AST parse of function bodies |
| **Import graph** | file → imported_modules | AST parse of imports |
| **Class table** | name, file, methods, bases | AST parse |

**Build trigger:** Run after every `ace-build full`. Store in `round-tracking.db` (existing) or separate `symbols.db`.

**Query interface:** 
```bash
ace-symbols callers rondo_run_file        # who calls this?
ace-symbols imports cli.py                # what does this file import?
ace-symbols impact move rondo_run_file    # what breaks if I move this?
ace-symbols unused                        # functions with 0 callers
ace-symbols duplicates                    # same function body in 2+ places
```

### Symbols → Caliber Integration

Once symbols exist, Caliber can:
```
S24 (Startup wiring): symbols callers load_providers_config → must include main()
S21 (Factory pattern): symbols callers GeminiAdapter.__init__ → must only be in providers.py
S18 (DRY): symbols duplicates → block if count > 1
```

---

## Cross-Product Learnings (Rondo → OB → Caliber → ACE)

| Lesson | Source | Impact |
|--------|--------|--------|
| "Tests pass but production is broken" | load_providers_config never called | Tests manually inject config — production doesn't |
| "Dry-run tests miss real API bugs" | gemini:flash → 404 | Need cloud_full test mode |
| "Convention tests are vacuously true" | ACE spec count = 0 specs found | Glob pattern was wrong — test checked 0 files |
| "Build RED normalized" | 8 failures ignored for weeks | Product-scoped builds needed |
| "Cursor finds things Claude misses" | 3 Cursor reviews, all productive | Schedule periodic cross-AI reviews |
| "Config without wiring = dead code" | TOML file existed, load function existed, tests passed | Nobody called it from startup |
| "Model IDs drift silently" | config.toml had wrong IDs | Need cloud_full validation or Caliber check |
| "Docs lie faster than code changes" | README said 18 tools, had 21. Said gemini:flash, was wrong. | Living doc must be verified against code |
| "Agents bypass Caliber" | Session 91 agent rewrote 3 files | Agents have no hooks — research only |
| "One AI is not enough" | Claude built it, Cursor reviewed it, 3 AI bodies validated | Multi-AI review catches different things |

---

## Action Items

| Item | System | Priority | Sprint? |
|------|--------|----------|---------|
| Add S18-S25 to Caliber spike backlog | Caliber | High | Update SPIKE-BACKLOG.md |
| Add per-file LOC + complexity to ace-build | OB | High | OB sprint |
| Build symbols MVP (function + call graph + import graph) | F25 | High | Multi-sprint |
| Add convention gate to ace-sprint done | OB | Medium | OB sprint |
| Schedule weekly Cursor review of hot paths | Process | Medium | Calendar |
| Add cloud_full to nightly build | Rondo | Medium | Config change |
| Product-scoped ace-build in nightly | OB | Medium | Config change |

---

*This document captures what we learned. Update SPIKE-BACKLOG.md and ACE-TASKS.md accordingly.*
