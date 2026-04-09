# Rondo-REQ-111: Smart Dispatch — Do, Process, Return

*Say what you want. Rondo handles the prompt engineering. Get structured data back.*

**Created:** 2026-04-09 (Session 100)
**Status:** DRAFT
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Depends on:** REQ-100 (Core), REQ-109 (Provider Adapters), STD-113 (Audit Trail)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Makes Rondo dead simple: you say what to do, Rondo does the prompt engineering,
you get structured JSON back. No prompt expertise needed. The tool learns which
AI returns the best data and how to ask each one.

**The DPR Pattern:**
- **Do** — what you want (plain English)
- **Process** — Rondo handles routing, prompt engineering, budget, audit (invisible)
- **Return** — structured JSON with smart defaults (scriptable, pipeable)

**IN scope:**
- Simple CLI: `rondo "do this"` with no subcommands
- YAML/JSON round file input (language-agnostic)
- Smart default return format (JSON with standard fields)
- User-defined return fields (`--field`, `--return`)
- Per-provider return prompt templates
- AI self-rating in response metadata
- Auto-rating (JSON validity, field completeness)
- Learning loop (which provider returns best structured data)
- Stdin pipe support (`git diff | rondo "review this"`)

**OUT of scope:**
- DAG workflow orchestration (future spec)
- Human-in-the-loop steps (future spec)
- New provider adapters (REQ-109)

---

## 2. The Problem

Today, using Rondo requires:
1. Writing a Python Round file with imports and dataclasses
2. Knowing prompt engineering to get structured output
3. Parsing text blobs to extract useful data
4. Manually tuning prompts per provider

**What users actually want:**
```bash
rondo "review this code for bugs"
```
→ get back JSON they can script with. Done.

**What gets lost today:**
- AI confidence in its own answer
- What it reviewed vs what it skipped
- Metadata (language detected, frameworks, line count)
- Whether the response was complete or partial
- Self-assessed limitations

All of this data is FREE (costs pennies in extra tokens) but nobody asks for it.

---

## 3. Requirements

### Simple CLI (Do)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 400 | `rondo "prompt"` (positional argument) MUST dispatch the prompt to the default provider and return JSON to stdout. No subcommands needed. | MUST | CLI test |
| 401 | `rondo "prompt" --model gemini:flash` MUST route to specified provider. | MUST | CLI test |
| 402 | `rondo "prompt" --json` MUST force JSON output. `--text` MUST force plain text. Default: JSON. | MUST | Output test |
| 403 | Stdin pipe: `echo "data" \| rondo "analyze this"` MUST append stdin content to the prompt as context. | MUST | Pipe test |
| 404 | File context: `rondo "review this" ./src/file.py` MUST read the file and include as context. | SHOULD | File test |

### YAML/JSON Input (Do — file mode)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 410 | `rondo run round.yaml` MUST parse YAML task definitions into Round/Task objects. | MUST | Loader test |
| 411 | `rondo run round.json` MUST parse JSON task definitions into Round/Task objects. | MUST | Loader test |
| 412 | YAML/JSON task schema: `{name, instruction, model?, done_when?, return_format?, context_files?, depends_on?, only_if?}` | MUST | Schema test |
| 413 | Existing Python round files (`.py`) MUST continue to work unchanged. | MUST | Compat test |
| 414 | File type detected by extension: `.yaml`/`.yml` → YAML, `.json` → JSON, `.py` → Python. | MUST | Detection test |

### Smart Default Return (Return)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 420 | When no return_format specified, Rondo MUST inject a default return prompt instructing the AI to return JSON with standard fields. | MUST | Default test |
| 421 | Standard fields: `passed` (bool), `confidence` (float 0-1), `result` (str — main answer), `issues` (list), `suggestions` (list), `metadata` (object). | MUST | Schema test |
| 422 | AI self-rating fields in `_meta`: `quality` (1-10), `complete` (bool), `limitations` (str). These are requested in the return prompt at near-zero extra cost. | MUST | Self-rate test |
| 423 | `--field <name>` flag MUST tell Rondo to instruct the AI to put its main answer in a named field. E.g., `--field bugs` → response has a `bugs` field. | MUST | Field test |
| 424 | `--return '<json_schema>'` flag MUST let user specify exact return schema. Overrides smart defaults. | SHOULD | Custom test |
| 425 | COALESCE for return format: `user --return → user --field → smart defaults`. First non-null wins. | MUST | COALESCE test |
| 426 | Plain text mode (`--text`): skip JSON return prompt entirely. AI responds naturally. | MUST | Text test |

### Per-Provider Return Prompts (Process)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 430 | `~/.rondo/config.toml` MAY define `[return_prompts.<provider>]` with provider-specific JSON instruction text. | MUST | Config test |
| 431 | COALESCE: provider-specific return prompt → default return prompt. | MUST | COALESCE test |
| 432 | Default return prompt MUST be tuned for each provider as they are added. Initial set: gemini, grok, mistral, openai, local (ollama). | SHOULD | Provider test |
| 433 | Provider return prompts MUST NOT include the user's actual prompt — only the "how to format your response" instructions. Appended to user prompt at dispatch time. | MUST | Security test |

### Auto-Rating (Process — free)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 440 | After every dispatch, Rondo MUST check: (a) is the response valid JSON? (b) does it contain all required standard fields? | MUST | Validation test |
| 441 | Auto-rating stored in audit OUTCOME record: `json_valid` (bool), `fields_complete` (bool), `return_prompt_version` (str). | MUST | Audit test |
| 442 | If AI returns invalid JSON, Rondo MUST attempt to extract JSON from the response (balanced-brace extraction — already in TaskResult.extract_json). | MUST | Fallback test |
| 443 | If JSON extraction fails, return `{"passed": null, "result": "<raw text>", "parse_error": true}` so scripts don't crash. | MUST | Graceful test |

### Learning Loop (Process — overnight)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 450 | Overnight job (or `rondo learn`) MUST compute per-provider scores from last 7 days of dispatch data. | MUST | Compute test |
| 451 | Score includes: `json_success_rate` (% valid JSON returns), `fields_complete_rate`, `avg_self_quality`, `avg_cost`, `avg_latency`, `sample_count`. | MUST | Score test |
| 452 | Scores cached in `~/.rondo/learned/provider_scores.json`. Recomputed nightly or on demand. | MUST | Cache test |
| 453 | `rondo providers --scores` CLI MUST show per-provider scores with breakdown. | SHOULD | CLI test |
| 454 | Adaptive routing (REQ-109-addendum) uses `json_success_rate` as an input to provider scoring. | SHOULD | Routing test |
| 455 | Learning data is read-only derived from audit trail (STD-113). No separate data store. Rebuildable from JSONL at any time. | MUST | Rebuild test |

### Task Chaining (Return → next Do)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 460 | YAML/JSON tasks MAY specify `depends_on: <task_name>` — task only runs after dependency completes. | SHOULD | Dependency test |
| 461 | YAML/JSON tasks MAY specify `only_if: "<expression>"` — Python expression evaluated against previous task results. | SHOULD | Condition test |
| 462 | Template variables: `{{task_name.field}}` in instruction text MUST be replaced with the named field from the named task's result. | SHOULD | Template test |
| 463 | Circular dependencies MUST be detected at load time and rejected with clear error. | MUST | Cycle test |

---

## 4. Architecture

### Dispatch Flow (with smart returns)

```
User: rondo "review this" --field bugs

  ┌─────────────────────────────────────────────┐
  │ CLI: parse positional prompt + flags         │
  │   prompt = "review this"                     │
  │   field = "bugs"                             │
  │   output = json (default)                    │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │ Prompt Builder: inject return instructions   │
  │   provider = resolve (COALESCE routing)      │
  │   return_prompt = provider-specific template  │
  │   full_prompt = user_prompt + return_prompt   │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │ Dispatch: send to provider (existing path)   │
  │   audit INTENT, budget check, hooks          │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │ Response Handler: parse + validate + rate     │
  │   parse JSON (or extract from text)          │
  │   check fields_complete                      │
  │   record auto-rating in audit OUTCOME        │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │ Output: JSON to stdout                       │
  │   {"passed": false, "bugs": [...],           │
  │    "confidence": 0.95, "_meta": {...}}       │
  └──────────────────────────────────────────────┘
```

### Input Format Support

```
.py   → load_round_file() (existing Python loader)
.yaml → load_round_yaml() (NEW — parse to Round/Task)
.json → load_round_json() (NEW — parse to Round/Task)
stdin → inline prompt (existing prompt= path)
```

### Learning Data Flow

```
Every dispatch:
  response → auto_rate(json_valid, fields_complete) → audit OUTCOME

Nightly (or rondo learn):
  audit JSONL → aggregate 7 days → provider_scores.json cache

Next dispatch:
  read cache → pick best provider for task_type → dispatch
```

---

## 5. Examples

### Simplest possible use
```bash
$ rondo "what is kubernetes"
{"passed": true, "confidence": 0.99, "result": "Kubernetes is a container orchestration platform...", "issues": [], "suggestions": [], "metadata": {"topic": "infrastructure"}, "_meta": {"quality": 9, "complete": true, "limitations": ""}}
```

### With named field
```bash
$ rondo "find bugs in this code" --field bugs < myfile.py
{"passed": false, "confidence": 0.92, "bugs": ["SQL injection line 42", "XSS line 88"], "issues": [{"severity": "critical", "line": 42, "type": "sql-injection"}], "suggestions": ["Use parameterized queries"], "metadata": {"language": "python", "lines": 150}, "_meta": {"quality": 8, "complete": true, "limitations": "Only static analysis, no runtime check"}}
```

### Piped chain
```bash
$ rondo "find bugs" --field bugs < src/app.py | \
  jq '.bugs[]' | \
  rondo "fix each of these bugs" --field fixes
```

### YAML round file
```yaml
# review-and-fix.yaml
name: review-and-fix
tasks:
  - name: review
    instruction: "Review this code for security issues"
    context_files: ["src/login.py"]
    return_format: {"passed": "bool", "bugs": "list"}

  - name: fix
    instruction: "Fix these bugs: {{review.bugs}}"
    depends_on: review
    only_if: "not review.passed"
    return_format: {"fixed": "list", "files_changed": "list"}
```

```bash
$ rondo run review-and-fix.yaml
{"tasks": [{"name": "review", "passed": false, "bugs": [...]}, {"name": "fix", "fixed": [...]}], "status": "done"}
```

### Provider scores
```bash
$ rondo providers --scores
  Provider        JSON OK  Fields  Quality  Cost     Latency  Score  Samples
  ──────────────  ───────  ──────  ───────  ───────  ───────  ─────  ───────
  gemini:flash    98%      96%     8.2      $0.003   2.1s     0.87   147
  grok:grok-3     94%      91%     7.8      $0.008   3.4s     0.68   89
  mistral:large   96%      94%     8.0      $0.005   2.8s     0.78   53
  local:qwen32b   82%      70%     6.5      $0.000   4.2s     0.52   210
```

---

## 6. Risk

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AI ignores return prompt, returns text blob | Medium | Medium | Req 442: extract_json fallback. Req 443: graceful degradation. |
| Small models (8B) can't follow JSON format | High | Low | Simpler return prompt for local models (req 432). |
| Self-rating is unreliable | Medium | Low | Cross-check with auto-rating (Layer 1). Self-rating is advisory. |
| Learning loop creates feedback loop | Medium | Medium | 10% exploration rate (REQ-109-addendum req 322). |
| YAML parser adds attack surface | Low | Medium | Validate schema strictly. No arbitrary Python eval from YAML. |
| Template injection via {{}} | Low | High | Only allow `{{task_name.field}}` — no arbitrary expressions. |

---

## 7. Version History

| Ver | Date | Changes |
|-----|------|---------|
| 0.1 | 2026-04-09 | Initial. Session 100: designed in live conversation. DPR pattern, smart returns, per-provider prompts, three-layer rating, learning loop, YAML input, task chaining. |
