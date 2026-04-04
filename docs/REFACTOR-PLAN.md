# Rondo Refactoring Plan — DRY + Module Split

**Date:** 2026-04-04 | **Session:** 97 | **Status:** PROPOSAL (needs review)
**Codebase:** 10,662 lines across 25 source files, 1,370+ tests

---

## Problem Statement

Rondo grew from 3 files (engine + dispatch + cli) to 25 files over 16 sprints.
Features were added fast, tests kept green, but module boundaries weren't
maintained. Two files exceed size limits, and 4 DRY violations are spreading.

**Convention failures:**
- `cli.py` (1,277 lines) — over 1,200 limit
- `mcp_server.py` (1,140 lines) — over 800 recommended
- `rondo_run_file()` complexity = 16 (limit 15)

**DRY violations (same logic in multiple places):**
- Adapter instantiation: 4+ places manually do `if provider == "gemini": GeminiAdapter(...)`
- Config TOML loading: 3 places each read `~/.rondo/config.toml` independently
- Provider URL map: `{"openai": "https://api.openai.com/v1", ...}` duplicated
- Error code strings: adapters hardcode `"ERR_AUTH"` instead of importing constants

---

## Proposed Changes

### Change 1: Adapter Factory — `get_adapter(provider, model)` in providers.py

**What:** Single function that returns a configured adapter for any provider.

**Before (duplicated in 4 places):**
```python
from rondo.adapters.auth import load_api_key
from rondo.adapters.gemini import GeminiAdapter
from rondo.adapters.chat_completions import ChatCompletionsAdapter
from rondo.adapters.anthropic_api import AnthropicAPIAdapter

key = load_api_key(provider)
if provider == "gemini":
    adapter = GeminiAdapter(api_key=key)
elif provider in ("openai", "grok", "mistral"):
    urls = {"openai": "https://api.openai.com/v1", ...}
    adapter = ChatCompletionsAdapter(provider_name=provider, base_url=urls[provider], ...)
elif provider == "anthropic":
    adapter = AnthropicAPIAdapter(api_key=key)
```

**After (one call):**
```python
from rondo.providers import get_adapter_for_dispatch

adapter = get_adapter_for_dispatch("gemini", "gemini-2.5-flash")
# Returns configured GeminiAdapter with key loaded, or None if no key
```

**Files changed:** `providers.py` (add function), `health.py` (use it), `cli.py` (use it in review), `test_cloud_full.py` (use it)
**Risk:** Low — new function, callers opt in. No behavior change.
**Test:** Existing adapter tests + new factory test.

### Change 2: Single Config Reader — `get_rondo_config()` 

**What:** One function to load and cache `~/.rondo/config.toml`. Currently 3 places read it independently.

**Before:**
```python
# In providers.py
config_path = Path.home() / ".rondo" / "config.toml"
if config_path.is_file():
    with open(config_path, "rb") as f:
        data = tomllib.load(f)

# In health.py — SAME CODE
# In cli.py _get_review_profile_providers — SAME CODE
```

**After:**
```python
from rondo.config import get_rondo_config

cfg = get_rondo_config()  # Cached, loaded once
providers = cfg.get("providers", {})
```

**Files changed:** `config.py` (add function), `providers.py` (use it), `health.py` (use it), `cli.py` (use it)
**Risk:** Low — consolidation, not behavior change. Cache is the same one-shot pattern.
**Test:** Existing config tests cover loading. New test for cache behavior.

### Change 3: Provider URL Registry in Config

**What:** Move provider base URLs from hardcoded dicts to config.toml `[providers.X]` section.

**Before:**
```python
urls = {
    "openai": "https://api.openai.com/v1",
    "grok": "https://api.x.ai/v1", 
    "mistral": "https://api.mistral.ai/v1",
}
```

**After:** Read from config:
```toml
[providers.openai]
base_url = "https://api.openai.com/v1"
```
Fallback to hardcoded defaults if config missing.

**Files changed:** `providers.py` (read base_url from config), `examples/config.toml` (add base_url)
**Risk:** Low — COALESCE pattern (config > hardcoded default). Existing configs work unchanged.
**Test:** Existing routing tests + new config override test.

### Change 4: Split cli.py → cli.py + cli_commands.py

**What:** Move command handler functions out of `cli.py` into `cli_commands.py`.

**Before:** cli.py = parser (145 lines) + common flags + main() + 16 _cmd_* handlers = 1,277 lines

**After:**
- `cli.py` — parser, build_parser(), main(), command dispatch (~300 lines)
- `cli_commands.py` — all _cmd_* functions (~900 lines)

**Files changed:** Split existing file, no new logic.
**Risk:** Medium — import paths change. Tests reference `cli.py` functions. Need to update test imports.
**Test:** All existing CLI tests must pass unchanged (behavior doesn't change).

### Change 5: Split mcp_server.py → mcp_server.py + mcp_dispatch.py

**What:** Move composition tools (multi_review, cloud, chain, benchmark, explain, summarize) out of registration file.

**Before:** mcp_server.py = tool registration + 6 composition functions + run_file inline dispatch = 1,140 lines

**After:**
- `mcp_server.py` — create_mcp_server(), tool registration, resource (~400 lines)
- `mcp_dispatch.py` — rondo_run_file, rondo_multi_review, rondo_chain, rondo_benchmark, rondo_cloud, rondo_explain, rondo_summarize (~700 lines)

**Files changed:** Split existing file.
**Risk:** Medium — `rondo_multi_review` and `rondo_run_file` are imported by CLI review command and tests. Need to update import paths.
**Test:** All MCP tests must pass. Import test for new module.

### Change 6: Error Code Imports

**What:** Adapters import error constants from `engine.py` instead of hardcoding strings.

**Before:**
```python
error_code = "ERR_AUTH"  # string literal in adapter
```

**After:**
```python
from rondo.engine import ERR_AUTH
error_code = ERR_AUTH
```

**Files changed:** All 4 adapter files.
**Risk:** Very low — same strings, just imported. Typo protection.
**Test:** Existing error code tests pass (same values).

---

## Execution Order

| Order | Change | Why this order |
|-------|--------|---------------|
| 1 | **Adapter Factory** (#1) | Highest value DRY fix. Enables changes 3-5. |
| 2 | **Config Reader** (#2) | Second highest DRY fix. Used by factory. |
| 3 | **URL Registry** (#3) | Depends on config reader. |
| 4 | **Error Imports** (#6) | Standalone, low risk, do anytime. |
| 5 | **Split cli.py** (#4) | Depends on factory being done (review command uses it). |
| 6 | **Split mcp_server.py** (#5) | Last — biggest risk, most import path changes. |

---

## What NOT to Refactor

- **dispatch.py** (803 lines) — complex but cohesive. Splitting prompt building from subprocess would create artificial coupling.
- **engine.py** (532 lines) — data model. Stable, well-tested, don't touch.
- **ai_help.py** (575 lines) — hardcoded dict. Ugly but harmless. Refactor when it becomes config-driven.

---

## Success Criteria

1. All 1,370+ existing tests pass (zero behavior change)
2. `cli.py` under 400 lines
3. `mcp_server.py` under 500 lines
4. Convention tests: 21/21 pass (complexity + import layering fixed)
5. No duplicated adapter instantiation code
6. One config reader, one adapter factory
7. `ace-build full --product rondo` GREEN

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Import path breakage | Medium | High (tests fail) | Do one split at a time, run tests after each |
| Circular imports | Low | High | Factory in providers.py, lazy imports |
| Behavior regression | Low | Medium | No logic changes, just moves + consolidation |
| Merge conflicts | Low | Low | Do in one sprint session |

---

*Prepared for AI body review + Cursor review before execution.*
