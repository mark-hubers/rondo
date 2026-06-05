# Rondo-REQ-113: Experiment Matrix — model × effort × context, scored honestly

*One command runs the whole grid. Replicates beat noise. Blind scoring beats bias.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-06-05 (Session 104) | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Depends on:** REQ-100 (Core), REQ-109 (Provider Adapters — tiers, effort, cost), REQ-111 (Smart Dispatch — normalization), STD-105 (cost), STD-113 (Audit), STD-114 (Sanitization)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):** Mark runs model-comparison experiments
(which AI is best for THIS job, at WHAT effort, with HOW MUCH context). Today
that is done by hand: N prompts × M models, manually tracked, manually scored,
n=1 per cell, self-ratings trusted at peril. (Evidence: USH essay-split
experiment 2026-06-03 — `PROTOCOL.md`, `RESULTS-batch1.md`, `FINDINGS.md` — and
its explicit wish-list: replicates, blind scoring, context variants,
compare-to-baseline.) This spec makes the whole grid ONE resumable, budgeted,
audited command. **No other dispatch tool has this** (competitive scan
2026-06-03) — it is Rondo's signature capability.

**IN scope:** matrix definition, grid execution, replicates + noise floor,
blind scoring workflow, baseline comparison hooks, cost gating, resume, report.
**OUT of scope:** semantic judging of outputs (a matrix CELL may dispatch a
judge, but judging quality is the caller's rubric); UI; cross-machine runs.

---

## 2. Requirements

### Matrix Definition

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | A matrix is defined in YAML (`rondo matrix run exp.yaml`): `prompt` (or `prompt_file`), `models: []` (provider:model or provider:tier), `efforts: []` (optional), `contexts: {name: file\|inline\|none}` (optional), `replicates: N` (default 1), `budget_usd`, `name`. | MUST | Loader test |
| 002 | The grid = models × efforts × contexts × replicates. Axes default to single-element when omitted (a plain model sweep is the degenerate case). | MUST | Grid test |
| 003 | YAML is `safe_load` only; schema-validated at load; unknown fields rejected with a clear error (REQ-111 req 414 idiom). | MUST | Security test |
| 005 | `inputs: {name: path}` (optional): each named file is read and substituted into the prompt at `{{name}}` placeholders BEFORE dispatch. Unresolved `{{...}}` placeholders in the final prompt ABORT the run with a clear error — a template must never be dispatched as if it were content. (First real-use lesson: the 4.6v4.8 run dispatched a paste-here placeholder; all 6 cells correctly refused.) | MUST | Inputs test |
| 004 | `effort` applies only to effort-capable paths (REQ-109 reqs 204-205). For models without effort support the cell records `effort: "n/a"` and runs ONCE per effort axis value collapse — never errors, never silently duplicates spend. | MUST | Effort-collapse test |

### Cost Gating (the axis multiplier makes this MANDATORY)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 010 | Before ANY dispatch: full-grid cost estimate (REQ-109 req 053 estimator per cell, summed). Estimate + cell count shown; run ABORTS if estimate > `budget_usd`. | MUST | Estimate test |
| 011 | `--dry-run` prints the grid table (every cell: model/effort/context/replicate + est. cost) and exits without dispatching. | MUST | Dry-run test |
| 012 | Running total tracked during execution; if actual spend reaches `budget_usd`, remaining cells are SKIPPED with status `budget_exhausted` (partial results preserved — STD-108 rule 3 spirit). | MUST | Budget-stop test |

### Execution

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 020 | Cells dispatch via the normal pipeline (audit INTENT/OUTCOME per cell, sanitize, history — STD-113; no bypass, REQ-109 req 029). Audit `project` field = `matrix:{name}`. | MUST | Pipeline test |
| 021 | Cell concurrency reuses the cloud dispatch pool (REQ-109 req 052); per-provider serialization respects rate limits. | MUST | Concurrency test |
| 022 | A matrix run is RESUMABLE: the manifest records per-cell status; re-running the same YAML skips `done` cells (idempotent by cell key = model+effort+context+replicate). | MUST | Resume test |
| 023 | One cell's failure NEVER aborts the run (STD-108 rule 6). Failed cells carry error_code + forensics (STD-113 reqs 021-022). | MUST | Isolation test |

### Output & Manifest

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 030 | Results land in `~/.rondo/matrix/{name}/`: one result file per cell + `manifest.json` (grid, statuses, costs, timings, dispatch_ids). | MUST | Layout test |
| 031 | `rondo matrix report {name}`: summary table — per cell: status, cost, latency, output length, self-rating (if smart-return), replicate mean±stdev for numeric fields. | MUST | Report test |
| 032 | Replicates (N>1): numeric self-ratings and latency report mean, stdev, range; a `noisy` flag marks cells where stdev exceeds 25% of mean (the n=1-is-noisy lesson, FINDINGS.md). | MUST | Noise test |
| 033 | Self-ratings are reported but NEVER ranked on — they are uncalibrated (FINDINGS.md: all models self-rated 7-10 regardless of quality). Report labels them "self (uncalibrated)". | MUST | Label test |

### Blind Scoring (bias control)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 040 | `blind: true`: result files are written under anonymized cell codes (`cell-A`, `cell-B`…); the code→cell mapping is stored ONLY in `manifest.sealed.json` (0600). | MUST | Blind test |
| 041 | `rondo matrix reveal {name}`: prints the mapping and stamps `revealed_at` into the manifest. Until reveal, `report` shows codes only. | MUST | Reveal test |
| 042 | Sealed mapping is tamper-evident: manifest stores a SHA-256 of the mapping at creation; reveal verifies it. | SHOULD | Integrity test |

### Baseline Comparison

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 050 | `baseline: path` (optional): report includes per-cell mechanical deltas vs baseline — length ratio, structural similarity (shared headings/keys). Cheap, local, no dispatch. | SHOULD | Baseline test |
| 051 | `judge: provider:model` (optional, costed into the budget): each cell's output is scored against the baseline by a judge dispatch using a caller-supplied rubric prompt. Judge cells are ordinary audited dispatches. | MAY | Judge test |

### CLI

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 060 | `rondo matrix run exp.yaml` / `status {name}` / `report {name}` / `reveal {name}`. | MUST | CLI test |
| 061 | Re-running at a NEW model generation: same YAML + new `name` reproduces the experiment (the "re-run at every release" goal, PROTOCOL.md). Manifest records model IDs actually used (tier-resolved) for honest cross-run comparison. | MUST | Repro test |

---

## 3. Worked Example (Mark's essay-split protocol, as YAML)

```yaml
name: essay-split-jun26
prompt_file: research/experiments/essay-split/SPLIT-PROMPT.md
models: [anthropic:high, openai:gpt-5.5, gemini:gemini-pro-latest, grok:grok-4.3, mistral:mistral-large-latest]
efforts: [low, high, max]          # applied where supported, n/a elsewhere
contexts:
  blind: none                       # task only
  informed: research/experiments/essay-split/STYLE-CONTEXT.md
replicates: 3
blind: true
baseline: research/experiments/essay-split/SPLIT-PLAN.md
budget_usd: 5.00
```

Grid: 5 models × 3 efforts × 2 contexts × 3 replicates = 90 cells (effort
collapses to 1 for non-effort models → fewer). Estimated before run; resumable;
blind-coded; reported with noise floors. Today this is a week of hand-work.

---

## 4. Rules & Constraints

1. **Budget is a hard ceiling** — estimate-abort before, running-stop during. Violation ID: `REQ113-BUDGET-HARD`
2. **Every cell is audited** — no side-channel dispatch. Violation ID: `REQ113-AUDIT-ALL`
3. **Self-ratings never rank** — uncalibrated by evidence. Violation ID: `REQ113-NO-SELF-RANK`
4. **Blind stays blind until reveal** — report cannot leak the mapping. Violation ID: `REQ113-SEAL`

---

## 5. Version History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.2 | 2026-06-05 | Req 005 inputs interpolation + unresolved-placeholder guard — from the FIRST real matrix run (template dispatched, every model honestly flagged it). Learn-by-use working as intended. |
| 0.1 | 2026-06-05 | Initial spec from USH essay-split learnings (PROTOCOL/RESULTS/FINDINGS 2026-06-03) + competitive-scan conclusion that no other tool has this. 24 requirements. RONDO-307 follow-on; build = next sprint. |
