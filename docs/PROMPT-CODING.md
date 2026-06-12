<!-- SPDX-FileCopyrightText: 2026 Mark Hubers -->
<!-- SPDX-License-Identifier: MIT -->
<!-- AUTHOR: drafted by gemini-2.5-pro via rondo_run, edited by Claude (RONDO-407) -->

# Prompt Coding

Prompts are not chat; they are code. Rondo treats AI dispatches like
infrastructure. You define deterministic pipelines with explicit data wiring,
strict output contracts, and hard budgets. It's Terraform for prompts.

## The discipline

* **Plan:** `rondo pipeline file.yaml --plan` validates wiring, estimates
  per-step costs, and checks the total against the budget ceiling with zero
  dispatches and zero cost. Unresolved placeholders abort before any spend.
* **Apply:** Sequential execution. A failed step's output never silently
  flows onward.
* **Audit:** Every step records INTENT and OUTCOME. Outputs are sanitized,
  partials preserved, and actual costs strictly enforced against the budget.
  Full per-step results and costs are saved in the envelope.

## A pipeline is a program

```yaml
name: summarize-and-translate
budget_usd: 0.05
steps:
  - name: extract
    model: openai:high
    prompt: "Extract key themes as JSON: {{inputs.source_text}}"
    expect: {required: ["themes"]}
    retries: 1
    on_fail: stop
  - name: translate
    model: mistral:default
    prompt: "Translate these themes to French as JSON: {{steps.extract.output}}"
    expect: {required: ["french_themes"]}
```

## Run it

```bash
# Plan (zero cost)
rondo pipeline pipe.yaml --plan --input source_text=@doc.txt
# Apply
rondo pipeline pipe.yaml --input source_text="Raw text"
```

```python
from rondo.pipeline import load_pipeline, run_pipeline
run_pipeline(load_pipeline("pipe.yaml"), inputs={"source_text": "..."})
```

## The flagship

See `examples/pipelines/code-refine.yaml` for a 10-step assembly line:
analyze -> add comments -> add error trapping -> hostile review by a
DIFFERENT provider -> apply fixes -> write tests -> critique tests by a
THIRD provider -> strengthen tests -> final polish -> JSON summary.

The runner (`examples/api/code_refine_pipeline.py`) EXECUTES the generated
tests against the generated code. The pipeline proves its own output.

## Scope guard — one or two things per step

rondo's core discipline is small asks: a step that bundles ten tasks has ten
places to fudge; a step that asks for one has none. The scope guard
(REQ-116) scores each step's prompt and:

* **warns by default** — a fat step logs a `-WARNING-` and carries
  `scope_warning` in the envelope (visible, never blocking);
* **blocks in strict mode** — `strict_scope: true` makes a fat step a
  load-time error, naming the step and its signals;
* **exempts the genuine wide step** — `allow_broad: true` opts a step out
  (a review pass over many files is legitimately broad).

`--plan` shows each step's `scope_score` so you see fat steps before any
spend. It is a heuristic (surface signals, not meaning) — hence warn-default
and the override.

## Honest limits

* **v1 is sequential:** No DAGs or loops yet.
* **Shallow validation:** `expect` checks key presence, not deep types — but
  `verify:` (REQ-115) goes further: rondo ITSELF checks declared files exist
  and runs a declared command, so a step's success claim cannot override
  rondo's own observation. A verify block also checks CONTENT, not just
existence — `contains: [...]` (substrings that must be present) and
`min_bytes` (catches empty/stub files), so "I wrote the function" fails when
the file is empty or wrong. For inline plans the same loop closes via
  `rondo_verify(dispatch_id)` (MCP tool + API): rondo re-checks the declared
  postconditions and records verified/failed_verification in the audit
  trail. Free-text answers remain advisory (honest limit).
* **Estimates vs actuals:** `--plan` estimates are heuristics; the hard
  ceiling is enforced on actuals. (See `specs/Rondo-REQ-114-prompt-pipelines.md`.)
