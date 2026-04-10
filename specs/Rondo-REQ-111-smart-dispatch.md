# Rondo-REQ-111: Smart Dispatch — Do, Process, Return

*Say what you want. Rondo handles the prompt engineering. Get structured data back.*

**Created:** 2026-04-09 (Session 100)
**Status:** DRAFT
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Depends on:** REQ-100 (Core — three-field contract, dispatch, extract_json), REQ-106 (Structured Input — context_data), REQ-109 (Provider Adapters — routing, health, scoring), STD-113 (Audit Trail)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Adds three things to Rondo that make it usable without Python knowledge:
1. Simple CLI — `rondo "do this"` (no subcommands, no round files)
2. YAML/JSON input — language-agnostic task definitions
3. Smart return — Rondo injects per-provider prompt engineering so the AI returns structured JSON by default

**The DPR Pattern:**
- **Do** — what you want (plain English or YAML/JSON)
- **Process** — Rondo handles routing, prompt engineering, budget, audit (invisible to user)
- **Return** — structured JSON with smart defaults (scriptable, pipeable)

**IN scope:** Simple CLI, YAML/JSON loader, smart return prompts, per-provider return templates, auto-rating, learning loop.

**OUT of scope:** Engine changes (REQ-100), structured input (REQ-106), provider adapters (REQ-109), audit trail (STD-113), DAG orchestration (future), HITL (future).

**What this spec does NOT redefine:**
- Three-field contract → REQ-100 req 003
- Structured JSON from Claude → REQ-100 reqs 029-031
- extract_json fallback → REQ-100 req U-26
- context_data / file context → REQ-106 reqs 001-010
- Provider routing → REQ-109 reqs 011-028
- Prompt size limits → REQ-100 req 003 (500KB cap)

---

## 2. Requirements

### Simple CLI (new entry point)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 400 | `rondo "prompt"` (positional argument) MUST create an inline Round and dispatch to the default provider (config `[routing.default]`, fallback "sonnet"). | MUST | CLI test |
| 401 | `rondo "prompt" --model gemini:flash` MUST route to specified provider. | MUST | CLI test |
| 402 | `--json` forces JSON output (default). `--text` forces plain text (skips return prompt injection). | MUST | Output test |
| 403 | Stdin pipe: `echo "data" \| rondo "analyze this"` MUST append stdin to prompt as context. Uses REQ-106 context_data mechanism. Max stdin: 1MB (extends REQ-100 req 003 cap). | MUST | Pipe test |
| 404 | File context: `rondo "review" ./file.py` MUST read file as context. Uses REQ-100 req 003 context_files with existing path validation (no traversal, no symlinks). | MUST | File test |
| 405 | When both `--return` and `--field` provided, `--return` takes full precedence. `--field` is ignored. | MUST | Precedence test |

### YAML/JSON Round Loader (new input formats)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 410 | `rondo run round.yaml` MUST parse YAML into Round/Task objects using existing Task fields from REQ-100 req 002. | MUST | Loader test |
| 411 | `rondo run round.json` MUST parse JSON into Round/Task objects. Same schema as YAML. | MUST | Loader test |
| 412 | File type by extension: `.yaml`/`.yml` → YAML, `.json` → JSON, `.py` → Python (existing). | MUST | Detection test |
| 413 | Existing Python round files MUST work unchanged (backward compat). | MUST | Compat test |
| 414 | YAML/JSON MUST be validated against Task field schema at load time. Unknown fields rejected with clear error. No `eval()`, no arbitrary code execution from YAML. Uses `yaml.safe_load()` only. | MUST | Security test |

### Smart Return Prompt Injection (new — the core feature)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 420 | When output mode is JSON (default), Rondo MUST append a return-format instruction to the prompt BEFORE dispatch. This extends REQ-100 req 029 (structured JSON) with richer default fields. | MUST | Injection test |
| 421 | Default return fields (appended to every JSON-mode dispatch): `passed` (bool), `confidence` (float 0-1), `result` (str), `issues` (list), `suggestions` (list), `metadata` (object), `_meta` (object: quality 1-10, complete bool, limitations str). | MUST | Schema test |
| 422 | `--field <name>` MUST instruct AI to put its main answer in the named field, alongside the standard fields. E.g., `--field bugs` → `{"bugs": [...], "passed": false, ...}`. | MUST | Field test |
| 423 | `--return '<schema>'` MUST let user define exact return schema. Overrides smart defaults entirely. Schema string validated as well-formed JSON at parse time. | SHOULD | Custom test |
| 424 | COALESCE: `--return → --field + defaults → defaults only`. | MUST | COALESCE test |
| 425 | `--text` mode: no return prompt injected. AI responds naturally. | MUST | Text test |

### Per-Provider Return Templates (new)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 430 | `~/.rondo/config.toml` MAY define `[return_prompts.<provider>]` with provider-specific return instructions. | MUST | Config test |
| 431 | COALESCE: provider-specific template → default template. | MUST | COALESCE test |
| 432 | Templates MUST NOT include user prompt content — only formatting instructions. Appended at dispatch time. | MUST | Security test |
| 433 | Default templates SHOULD be tuned per known provider (gemini, grok, mistral, openai, local). Simpler templates for smaller models (ollama 8B). | SHOULD | Provider test |

### Auto-Rating + Learning (new)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 440 | After every JSON-mode dispatch, Rondo MUST validate: (a) valid JSON? (b) standard fields present? Stored in audit OUTCOME (extends STD-113 req 003). | MUST | Validation test |
| 441 | If AI returns invalid JSON, use existing REQ-100 U-26 extract_json. If extraction fails, return `{"passed": null, "result": "<raw>", "_parse_error": true}`. | MUST | Fallback test |
| 442 | `rondo learn` CLI command MUST compute per-provider scores from last 7 days of audit data: json_success_rate, fields_complete_rate, avg_self_quality, avg_cost, avg_latency, sample_count. | MUST | Compute test |
| 443 | Scores cached in `~/.rondo/learned/provider_scores.json`. Rebuilt from audit JSONL on demand (no separate data store, per REQ-003 never-lose-data). | MUST | Cache test |
| 444 | `rondo providers --scores` MUST show per-provider scores table. | SHOULD | CLI test |
| 445 | json_success_rate feeds into REQ-109 (Adaptive Provider Scoring section) adaptive scoring (req 301 formula) as an additional quality signal. | SHOULD | Integration test |

### Response Normalization (new — common format regardless of provider)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 470 | `normalize_response(raw, provider)` MUST produce a common JSON shape regardless of which provider answered. Users MUST NOT need to know which provider handled their request. | MUST | Normalization test |
| 471 | Normalization MUST: strip markdown fences (```json...```), hoist nested `_meta` to top level, ensure all 7 standard fields present (fill missing with defaults), preserve any extra fields the provider added. | MUST | Field test |
| 472 | Standard field defaults when missing: `passed=null`, `confidence=0.0`, `result=""`, `issues=[]`, `suggestions=[]`, `metadata={}`, `_meta={"quality":0,"complete":false,"limitations":"not provided"}`. | MUST | Default test |
| 473 | Normalization runs AFTER `validate_return_json` and BEFORE output to user. Pipeline: raw → extract_json → validate → normalize → output. | MUST | Order test |
| 474 | Provider-specific quirk handling: Grok nests `_meta` inside `metadata` → hoist out. Mistral wraps in markdown fences → strip. Others: pass through. New providers added as discovered. | SHOULD | Quirk test |
| 475 | Extra fields beyond the 7 standard fields MUST be preserved (not stripped). Provider may return useful data we didn't ask for. | MUST | Preservation test |

### Config Template Management (new — product-ready config)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 480 | Code `_PROVIDER_TEMPLATES` dict = factory defaults. ALWAYS available. Used when no config.toml entry exists for a provider. | MUST | Fallback test |
| 481 | `~/.rondo/config.toml` `[return_prompts.<provider>]` = user overrides. When present, WINS over code defaults (COALESCE). | MUST | Override test |
| 482 | `rondo init --config` template MUST include a generic `[return_prompts.default]` section. Provider-specific templates (gemini, grok, etc.) go in `examples/provider-templates.toml`, NOT in the shipped template. | MUST | Template test |
| 483 | `rondo init --config --update` MUST add NEW settings from the template to user's config WITHOUT overwriting existing user edits. New sections appended with `## NEW IN vX.Y` markers. | SHOULD | Update test |
| 484 | Provider-specific templates in code (gemini, grok, mistral, openai, local) are tuned from live testing. They are the RECOMMENDED defaults, not the only option. Users can override any provider in their config.toml. | MUST | Doc |
| 485 | `examples/provider-templates.toml` MUST contain copy-paste-ready sections for each supported provider with comments explaining why each template is tuned that way (quirks documented). | MUST | Example test |

### Task Chaining in YAML/JSON (new — simple subset only)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 450 | `depends_on: <task_name>` — task runs only after dependency completes. | SHOULD | Dependency test |
| 451 | `only_if: "<condition>"` — restricted comparisons ONLY. Allowed: `task.field == value`, `not task.passed`, `task.confidence > N`. NO arbitrary Python. NO eval(). Parsed by Rondo, not Python interpreter. | SHOULD | Condition test |
| 452 | Template variables: `{{task_name.field}}` in instruction — replaced with field value from named task's result. Only dot-separated `name.field` allowed — no nested expressions, no function calls. Validated at parse time. | SHOULD | Template test |
| 453 | Circular dependencies MUST be detected at load time and rejected. | MUST | Cycle test |

---

## 3. Architecture

```
User: rondo "review this" --field bugs

  CLI → parse prompt + flags
    ↓
  Prompt Builder → append per-provider return template
    ↓
  Dispatch (existing REQ-100 pipeline: hooks, budget, audit)
    ↓
  Response → validate JSON, auto-rate, extract if needed
    ↓
  stdout → {"passed": false, "bugs": [...], "_meta": {...}}
```

No new modules needed for core path. Adds:
- `round_yaml.py` — YAML/JSON loader (new, small)
- Return template injection in `dispatch_prompt.py` (existing module)
- Auto-rating fields in `dispatch.py` finalize path (existing)
- `rondo learn` CLI command (new subcommand)

---

## 4. Cross-Reference Map

| REQ-111 Feature | Depends On | Extends |
|---|---|---|
| Simple CLI | REQ-100 inline prompt path | New entry point |
| File context | REQ-100 req 003 (context_files) | Reuses existing |
| Stdin context | REQ-106 (context_data) | Reuses existing |
| JSON return parsing | REQ-100 reqs 029-031, U-26 | Adds smart defaults |
| Prompt size limits | REQ-100 req 003 (500KB) | Extends to stdin |
| Provider routing | REQ-109 reqs 011-028 | Adds return_prompt |
| Adaptive scoring | REQ-109 (Adaptive Provider Scoring section) reqs 300-324 | Adds json_success_rate |
| Audit fields | STD-113 req 003 | Adds json_valid, fields_complete |

---

## 5. Risk

| Risk | Mitigation |
|------|------------|
| AI ignores return prompt | Req 441: extract_json fallback + graceful degradation |
| Small models can't do JSON | Req 433: simpler templates for small models |
| `only_if` code injection | Req 451: NO eval(). Restricted comparator only. |
| Template `{{}}` injection | Req 452: whitelist `name.field` only. Validated at parse. |
| Stdin too large | Req 403: 1MB cap |
| YAML arbitrary code | Req 414: yaml.safe_load() only. No eval. |

---

## 6. Version History

| Ver | Date | Changes |
|-----|------|---------|
| 0.1 | 2026-04-09 | Initial draft from Session 100 conversation. |
| 0.2 | 2026-04-09 | Removed 3 duplicate req blocks (JSON return, file context, extract_json). Added cross-reference map. Fixed security: only_if restricted to comparisons (no eval), template whitelist, stdin size cap, YAML safe_load. Reduced from 63 to 46 reqs. |
