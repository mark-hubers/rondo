# Rondo Excellence Plan — Post-Refactoring Improvements

**Date:** 2026-04-04 | **Session:** 97
**Source:** Cursor review + Gemini + Grok + Mistral recommendations
**Status:** APPROVED for building

---

## Quick Wins (1 sprint)

| # | Change | What | Spec req? | Effort |
|---|--------|------|-----------|--------|
| 1 | **Type the adapter factory** | `get_adapter() -> ProviderAdapter | None` | No — code quality | 5 min |
| 2 | **Config file permission check** | Don't load world-readable config | REQ-109 req 039 (security) | 10 min |
| 3 | **Document cache strategy** | Health=5min, config=one-shot, keys=5min | REQ-109 reqs 018, 040 | 15 min |
| 4 | **Clarify load merge vs replace** | Docstring: toml_data merges, file loads once | Existing req 040 | 5 min |

## Structural Improvements (2-3 sprints)

| # | Change | What | Spec req? | Effort |
|---|--------|------|-----------|--------|
| 5 | **Config validation on load** | Reject bad types/ranges at startup | New req 089 | 1 sprint |
| 6 | **Move _DEFAULT_TASK_MODELS to config** | Hardcoded dict → config.toml [routing] | Existing req 028 (enforce) | 1 sprint |
| 7 | **Fix 3 convention failures** | VER-001, SpecReferences, Complexity | Convention fixes | 1 sprint |

## Deferred (Next Session)

| # | Change | Why defer |
|---|--------|----------|
| 8 | Singleton ProviderConfig class | Big refactor, needs design review |
| 9 | Subpackage splits (cli/commands/*) | Current sizes are acceptable at 1000 limit |
| 10 | Error message sanitization | Needs threat model review |

---

## Spec Updates Needed

### REQ-109 new reqs:
- req 089: Config validation — reject unknown keys, validate types (enabled=bool, *_model=string, trust=enum)
- req 090: Config file permissions — skip loading if world-readable (chmod 644 ok, 666 not)

### REQ-109 existing reqs to enforce:
- req 028: recommend_model MUST read TOML (currently has hardcoded fallback)
- req 039: Config security (add permission check)
- req 040: Key cache (document behavior explicitly)
