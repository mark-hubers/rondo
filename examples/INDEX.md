# Rondo Example Index

Auto-generated from per-file `rondo-meta` headers.

| # | Example | Dir | Dispatch mode(s) | Providers | Task category | What it demonstrates |
|---|---|---|---|---|---|---|
| 1 | `01_simple_dispatch.py` | api | subprocess | anthropic | basic | Minimum Python API call returning live task results |
| 2 | `02_smart_return.py` | api | subprocess | anthropic | basic | Smart-return JSON structure and parsing flow |
| 3 | `03_execution_mode_triptych.py` | api | inline,subprocess,agent | anthropic | basic | Side-by-side behavior of all three execution modes |
| 4 | `adversarial_redteam.py` | api | subprocess | anthropic | flagship | Adversarial red-team: tell a real AI to actively fool rondo, measure the trap catch-rate against ground truth |
| 5 | `background_polling_workflow.py` | api | subprocess | anthropic | observability | Background run + heartbeat/brief/final polling loop |
| 6 | `batch_retry_runner.py` | api | http | gemini,grok | pipeline | Run batch review, detect failed providers, and retry just failures. |
| 7 | `benchmark_harness.py` | api | http | gemini,grok,openai | observability | Benchmark multiple provider models and rank by speed/cost. |
| 8 | `budget_aware_routing.py` | api | subprocess | anthropic | config | Cost-aware dispatch selection from script logic |
| 9 | `budget_guarded_parallel.py` | api | subprocess | anthropic | budget | Parallel round under a hard budget cap — spend can never exceed it |
| 10 | `build_failure_triage.py` | api | subprocess | anthropic | triage | Build-failure diagnosis with structured triage output |
| 11 | `claude_step_driver.py` | api | subprocess | anthropic | flagship | rondo drives Claude Code one verified step at a time — the prompt-coding thesis |
| 12 | `code_refine_pipeline.py` | api | pipeline | multi | flagship | 10-step code-refinement prompt program that proves its own output |
| 13 | `code_review_to_findings.py` | api | subprocess | anthropic | review | Real code review prompt converted into findings JSON |
| 14 | `community_reply_variant_lookup.py` | api | subprocess | anthropic | publish | Generate multiple response variants for community replies |
| 15 | `conductor_if_else.py` | api | subprocess | anthropic | flagship | if/else prompt coding: Python branching drives Claude Code with 100% control |
| 16 | `confidence_escalation.py` | api | subprocess | anthropic | pipeline | Confidence threshold flow that escalates to stronger model |
| 17 | `config_template_override.py` | api | subprocess | anthropic | config | Per-call override behavior for config-backed dispatch options |
| 18 | `controlled_review_loop.py` | api | mixed | anthropic,gemini,grok | flagship | Live controlled loop: rondo drives Claude step-by-step (verifying itself) then convenes OTHER AI bodies as a review gate before accepting |
| 19 | `cross_ai_verify.py` | api | mixed | anthropic,gemini | flagship | P2P cross-AI verify: one vendor does the work, a DIFFERENT vendor checks the claim — anti-lying by second opinion |
| 20 | `dispatch_with_hooks.py` | api | subprocess | anthropic | pipeline | Prompt/result hook lifecycle from Python API |
| 21 | `envelope_validation.py` | api | subprocess | anthropic | observability | Validate canonical envelope keys and error contract from live MCP/API dispatches |
| 22 | `error_recovery_patterns.py` | api | subprocess | anthropic | pipeline | Force an error, then recover with a real dispatch and actionable envelope checks |
| 23 | `essay_fact_check_pipeline.py` | api | subprocess | anthropic | essay | Multi-step essay claim extraction and fact-check loop |
| 24 | `field_named_return.py` | api | subprocess | anthropic | basic | Named JSON field contract for script-friendly outputs |
| 25 | `find_and_fix_pipeline.py` | api | subprocess | anthropic | pipeline | Find -> fix -> verify chain with real dispatches |
| 26 | `idempotency_cache_demo.py` | api | subprocess | anthropic | observability | Duplicate-request cache behavior and timing comparison |
| 27 | `incident_triage_playbook.py` | api | subprocess | anthropic | triage | Generate incident severity, owner, and first-response actions. |
| 28 | `lie_trap_loop.py` | api | subprocess | anthropic | flagship | Lie-trap loop: feed the engine the lies an AI returns, prove each trap fires and the if/else recovers |
| 29 | `lint_fix_verify_loop.py` | api | subprocess | anthropic | pipeline | Iterative lint/fix/verify automation pattern |
| 30 | `live_recovery_loop.py` | api | subprocess | anthropic | flagship | Live recovery loop: a real AI, a real failure, rondo catches it and the if/else recovers — end to end |
| 31 | `model_comparison.py` | api | http | anthropic,gemini,grok | review | Compare model outputs side-by-side for one review prompt. |
| 32 | `multi_ai_tiebreaker.py` | api | subprocess,http | anthropic | review | Multi-model disagreement handling and tie-break voting |
| 33 | `multi_platform_publish.py` | api | subprocess | anthropic | publish | One prompt pipeline that adapts copy for multiple platforms |
| 34 | `multi_provider_dispatch.py` | api | http | gemini,grok,ollama | review | Fan-out to multiple providers with one prompt |
| 35 | `normalize_responses.py` | api | subprocess | anthropic | config | Normalizing varied model payloads into one stable shape |
| 36 | `option_c_01_review_current_context.py` | api | inline | anthropic | option-c | Option C in-session file review using inline plan auto-execution contract |
| 37 | `option_c_02_ask_gemini.py` | api | http | gemini | option-c | Ask Gemini via MCP and return structured opinion |
| 38 | `option_c_03_provider_vote.py` | api | http | gemini,openai,grok | option-c | Three-provider vote on a design decision via MCP multi_review |
| 39 | `option_c_04_find_fix_verify_round.py` | api | subprocess | anthropic | option-c | Run declarative find-fix-verify round file through MCP |
| 40 | `option_c_05_replay_compare.py` | api | subprocess | anthropic | option-c | Replay previous dispatch and compare output via CLI |
| 41 | `option_c_06_fresh_session_subprocess.py` | api | subprocess | anthropic | option-c | Escape hatch: force fresh Sonnet subprocess session |
| 42 | `partial_status_handling.py` | api | subprocess | anthropic | observability | Show how to handle partial/non-JSON output while preserving raw_output |
| 43 | `pr_review_workflow.py` | api | subprocess | anthropic | review | Run a PR-style review prompt and extract actionable findings. |
| 44 | `provider_fallback_chain.py` | api | http,subprocess | grok,anthropic | pipeline | Primary provider failure path with automatic fallback dispatch |
| 45 | `provider_scoring.py` | api | subprocess | anthropic | observability | Provider scoring and comparison from run outputs |
| 46 | `replay_demo.py` | api | subprocess | anthropic | observability | Replay baseline-vs-current outputs and summarize drift. |
| 47 | `research_freshness_scanner.py` | api | subprocess | anthropic | research | Research freshness scoring and stale-source detection |
| 48 | `resilience_tour.py` | api | local | none | reliability | Breaker trip/recovery + Retry-After + idempotency dedup in one deterministic story |
| 49 | `retry_on_failure.py` | api | subprocess | anthropic | observability | Retry strategy and recovery handling for failed runs |
| 50 | `spec_code_drift_scanner.py` | api | subprocess | anthropic | drift | Spec-vs-code drift checks with PASS/FAIL verdicts |
| 51 | `timeout_and_backoff.py` | api | subprocess | anthropic | pipeline | Timeout-oriented retry loop with exponential backoff and live success path |
| 52 | `verified_step.py` | api | subprocess | anthropic | flagship | REQ-115 verified execution — rondo checks the work itself, the anti-lying layer |
| 53 | `yaml_round_loader.py` | api | subprocess | anthropic | config | Loading and dispatching YAML round definitions via API |
| 54 | `01-simple-review.yaml` | rounds | subprocess | anthropic | review | Simplest single-task YAML round review |
| 55 | `02-multi-provider.yaml` | rounds | http | gemini,grok,ollama | review | Same task across three providers for comparison |
| 56 | `03-budget-capped.yaml` | rounds | http | gemini | observability | Multi-task batch constrained by max budget |
| 57 | `04-with-hooks.py` | rounds | subprocess | anthropic | pipeline | Python round hooks (pre/post dispatch transformations) |
| 58 | `05-overnight-batch.yaml` | rounds | http | gemini,grok | observability | Overnight batch pattern with mixed provider tasks |
| 59 | `06-experiment-matrix.yaml` | rounds | matrix | anthropic,openai | experiment | Complete experiment-matrix definition: model x effort x replicates, blind, budgeted (REQ-113). |
| 60 | `06-find-fix-verify.yaml` | rounds | subprocess | anthropic | pipeline | Declarative find-fix-verify YAML workflow for Terraform-for-prompts style automation |
| 61 | `07-task-affinity.yaml` | rounds | cli | all | routing | Tag tasks with task_type so Rondo learns WHICH model is best at WHICH job — not one blended score. |
| 62 | `08-matrix-with-judge.yaml` | rounds | cli | multi | experiment | Experiment matrix WITH a judge: an external model scores every cell against your rubric — fair cross-model comparison, costed into the same budget. |
| 63 | `demo_pipeline.py` | rounds | subprocess | anthropic | pipeline | Four-stage scan/review/fix/verify round workflow |
| 64 | `phases_overnight.py` | rounds | subprocess | anthropic | pipeline | Multi-phase overnight plan with model-tier escalation |
| 65 | `review_demo.py` | rounds | subprocess | anthropic | review | Forward/reverse/sideways review strategy on a demo file |
| 66 | `round_caliber_fix.py` | rounds | subprocess | anthropic | pipeline | Caliber findings to automated fix workflow |
| 67 | `round_code_review.py` | rounds | subprocess | anthropic | review | Git-diff-aware review round with staged-change gate |
| 68 | `round_doc_sweep.py` | rounds | subprocess | anthropic | publish | Parallel docs cleanup tasks across repository files |
| 69 | `round_file_check.py` | rounds | subprocess | anthropic | basic | File existence gate + auto task + AI summary task |
| 70 | `round_hello.py` | rounds | subprocess | anthropic | basic | Absolute minimal one-task Python round |
| 71 | `round_multi_task.py` | rounds | subprocess | anthropic | pipeline | Multi-task round mixing auto and AI tasks |
| 72 | `round_refactor_audit.py` | rounds | subprocess | anthropic | review | Refactor audit with blocking/non-blocking gates |
| 73 | `round_security_audit.py` | rounds | subprocess | anthropic | review | Security audit pattern with clean-tree pre-gate |
| 74 | `round_test_generator.py` | rounds | subprocess | anthropic | pipeline | Auto-discover untested modules and generate test stubs |
| 75 | `01-execution-modes.sh` | cli | subprocess,http | anthropic,gemini | basic | CLI subprocess route vs provider HTTP route |
| 76 | `02-background-polling.sh` | cli | subprocess | anthropic | observability | Background polling command recipe for MCP-style flows |
| 77 | `03-consensus-review.sh` | cli | subprocess | gemini,grok | review | Two-provider file review consensus pattern |
| 78 | `04-model-comparison.sh` | cli | subprocess,http | anthropic,gemini,grok | review | Compare one prompt across three models from CLI. |
| 79 | `04-showcase-runner.sh` | cli | subprocess | — | observability | One-command showcase run plus API example validation |
| 80 | `05-batch-retry.sh` | cli | http | gemini,grok | pipeline | Run batch providers then retry failed dispatch ids via MCP tools. |
| 81 | `06-experiment-matrix.sh` | cli | matrix | anthropic,openai | experiment | Full experiment-matrix workflow: dry-run, execute, report, reveal (REQ-113). |
| 82 | `07-fleet-health.sh` | cli | cli | all | operations | The morning fleet check: model drift, learned scores, retry queue, reliability scoreboard. |
| 83 | `08-nightly-watchdog.sh` | cli | cli | all | operations | The night watchman: one schedulable command that sweeps drift + retryq + reliability and ALERTS instead of waiting to be asked. |
| 84 | `09-model-canary.sh` | cli | cli | all | operations | Auto-tiers + canary: derive low/mid/high from live catalogs (free) and PROVE every configured model still answers (~cents). |
| 85 | `10-doctor.sh` | cli | cli | all | operations | rondo doctor: the first command support asks anyone to run — install diagnosis with fix hints + a redacted support bundle. Zero dispatches, zero cost. |
| 86 | `real-world-scripting.sh` | cli | subprocess,http | gemini,grok,mistral,ollama | pipeline | Shell scripting playbook for practical AI workflows |
| 87 | `scripted-prompting.sh` | cli | subprocess,http | anthropic,gemini,grok,mistral,ollama | pipeline | jq-driven branching, retries, and prompting scripts |
| 88 | `01-inline-host-plan.md` | mcp | inline | anthropic | basic | MCP default inline plan and host-executed behavior |
| 89 | `02-agent-host-plan.md` | mcp | agent | anthropic | basic | Explicit agent plan mode for host-side execution |
| 90 | `03-subprocess-fresh-session.md` | mcp | subprocess | anthropic | basic | Force fresh subprocess execution from MCP tool call |
| 91 | `04-provider-http-bypass.md` | mcp | http | anthropic,gemini,grok,mistral,openai,ollama | config | Provider-prefixed model behavior that bypasses execution routing |
| 92 | `05-background-polling.md` | mcp | subprocess | anthropic | observability | Background run lifecycle and polling tiers from MCP |
| 93 | `06-multi-provider-review.md` | mcp | http | anthropic,gemini,grok,mistral,openai | review | Multi-provider review workflow through MCP tools |
| 94 | `07-review-file.md` | mcp | subprocess | anthropic | review | File-scoped review workflow for real source files |
| 95 | `08-cloud-profile-tier.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai,ollama | config | Cloud profile/tier routing examples for model selection |
| 96 | `09-chain-pipeline.md` | mcp | subprocess | anthropic | pipeline | Chaining tool calls where each step feeds the next |
| 97 | `10-benchmark-model-selection.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai | observability | Benchmarking model options before choosing defaults |
| 98 | `11-retry-failed-dispatch.md` | mcp | subprocess | anthropic | observability | Recovery of failed dispatches using retry tools |
| 99 | `12-diff-two-runs.md` | mcp | subprocess | anthropic | drift | Compare run outputs to detect behavioral drift |
| 100 | `13-observability-suite.md` | mcp | subprocess | anthropic | observability | End-to-end health/metrics/history/audit monitoring flow |
| 101 | `README.md` | mcp | inline,subprocess,agent,http | anthropic,gemini,grok,mistral,openai,ollama | config | MCP playbook overview with copy/paste entry points |
