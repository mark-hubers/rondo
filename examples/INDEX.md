# Rondo Example Index

Auto-generated from per-file `rondo-meta` headers.

| # | Example | Dir | Dispatch mode(s) | Providers | Task category | What it demonstrates |
|---|---|---|---|---|---|---|
| 1 | `01_simple_dispatch.py` | api | subprocess | anthropic | basic | Minimum Python API call returning live task results |
| 2 | `02_smart_return.py` | api | subprocess | anthropic | basic | Smart-return JSON structure and parsing flow |
| 3 | `03_execution_mode_triptych.py` | api | inline,subprocess,agent | anthropic | basic | Side-by-side behavior of all three execution modes |
| 4 | `background_polling_workflow.py` | api | subprocess | anthropic | observability | Background run + heartbeat/brief/final polling loop |
| 5 | `batch_retry_runner.py` | api | http | gemini,grok | pipeline | Run batch review, detect failed providers, and retry just failures. |
| 6 | `benchmark_harness.py` | api | http | gemini,grok,openai | observability | Benchmark multiple provider models and rank by speed/cost. |
| 7 | `budget_aware_routing.py` | api | subprocess | anthropic | config | Cost-aware dispatch selection from script logic |
| 8 | `build_failure_triage.py` | api | subprocess | anthropic | triage | Build-failure diagnosis with structured triage output |
| 9 | `code_review_to_findings.py` | api | subprocess | anthropic | review | Real code review prompt converted into findings JSON |
| 10 | `community_reply_variant_lookup.py` | api | subprocess | anthropic | publish | Generate multiple response variants for community replies |
| 11 | `confidence_escalation.py` | api | subprocess | anthropic | pipeline | Confidence threshold flow that escalates to stronger model |
| 12 | `config_template_override.py` | api | subprocess | anthropic | config | Per-call override behavior for config-backed dispatch options |
| 13 | `dispatch_with_hooks.py` | api | subprocess | anthropic | pipeline | Prompt/result hook lifecycle from Python API |
| 14 | `envelope_validation.py` | api | subprocess | anthropic | observability | Validate canonical envelope keys and error contract from live MCP/API dispatches |
| 15 | `error_recovery_patterns.py` | api | subprocess | anthropic | pipeline | Force an error, then recover with a real dispatch and actionable envelope checks |
| 16 | `essay_fact_check_pipeline.py` | api | subprocess | anthropic | essay | Multi-step essay claim extraction and fact-check loop |
| 17 | `field_named_return.py` | api | subprocess | anthropic | basic | Named JSON field contract for script-friendly outputs |
| 18 | `find_and_fix_pipeline.py` | api | subprocess | anthropic | pipeline | Find -> fix -> verify chain with real dispatches |
| 19 | `idempotency_cache_demo.py` | api | subprocess | anthropic | observability | Duplicate-request cache behavior and timing comparison |
| 20 | `incident_triage_playbook.py` | api | subprocess | anthropic | triage | Generate incident severity, owner, and first-response actions. |
| 21 | `lint_fix_verify_loop.py` | api | subprocess | anthropic | pipeline | Iterative lint/fix/verify automation pattern |
| 22 | `model_comparison.py` | api | http | anthropic,gemini,grok | review | Compare model outputs side-by-side for one review prompt. |
| 23 | `multi_ai_tiebreaker.py` | api | subprocess,http | anthropic | review | Multi-model disagreement handling and tie-break voting |
| 24 | `multi_platform_publish.py` | api | subprocess | anthropic | publish | One prompt pipeline that adapts copy for multiple platforms |
| 25 | `multi_provider_dispatch.py` | api | http | gemini,grok,ollama | review | Fan-out to multiple providers with one prompt |
| 26 | `normalize_responses.py` | api | subprocess | anthropic | config | Normalizing varied model payloads into one stable shape |
| 27 | `option_c_01_review_current_context.py` | api | inline | anthropic | option-c | Option C in-session file review using inline plan auto-execution contract |
| 28 | `option_c_02_ask_gemini.py` | api | http | gemini | option-c | Ask Gemini via MCP and return structured opinion |
| 29 | `option_c_03_provider_vote.py` | api | http | gemini,openai,grok | option-c | Three-provider vote on a design decision via MCP multi_review |
| 30 | `option_c_04_find_fix_verify_round.py` | api | subprocess | anthropic | option-c | Run declarative find-fix-verify round file through MCP |
| 31 | `option_c_05_replay_compare.py` | api | subprocess | anthropic | option-c | Replay previous dispatch and compare output via CLI |
| 32 | `option_c_06_fresh_session_subprocess.py` | api | subprocess | anthropic | option-c | Escape hatch: force fresh Sonnet subprocess session |
| 33 | `partial_status_handling.py` | api | subprocess | anthropic | observability | Show how to handle partial/non-JSON output while preserving raw_output |
| 34 | `pr_review_workflow.py` | api | subprocess | anthropic | review | Run a PR-style review prompt and extract actionable findings. |
| 35 | `provider_fallback_chain.py` | api | http,subprocess | grok,anthropic | pipeline | Primary provider failure path with automatic fallback dispatch |
| 36 | `provider_scoring.py` | api | subprocess | anthropic | observability | Provider scoring and comparison from run outputs |
| 37 | `replay_demo.py` | api | subprocess | anthropic | observability | Replay baseline-vs-current outputs and summarize drift. |
| 38 | `research_freshness_scanner.py` | api | subprocess | anthropic | research | Research freshness scoring and stale-source detection |
| 39 | `retry_on_failure.py` | api | subprocess | anthropic | observability | Retry strategy and recovery handling for failed runs |
| 40 | `spec_code_drift_scanner.py` | api | subprocess | anthropic | drift | Spec-vs-code drift checks with PASS/FAIL verdicts |
| 41 | `timeout_and_backoff.py` | api | subprocess | anthropic | pipeline | Timeout-oriented retry loop with exponential backoff and live success path |
| 42 | `yaml_round_loader.py` | api | subprocess | anthropic | config | Loading and dispatching YAML round definitions via API |
| 43 | `01-simple-review.yaml` | rounds | subprocess | anthropic | review | Simplest single-task YAML round review |
| 44 | `02-multi-provider.yaml` | rounds | http | gemini,grok,ollama | review | Same task across three providers for comparison |
| 45 | `03-budget-capped.yaml` | rounds | http | gemini | observability | Multi-task batch constrained by max budget |
| 46 | `04-with-hooks.py` | rounds | subprocess | anthropic | pipeline | Python round hooks (pre/post dispatch transformations) |
| 47 | `05-overnight-batch.yaml` | rounds | http | gemini,grok | observability | Overnight batch pattern with mixed provider tasks |
| 48 | `06-experiment-matrix.yaml` | rounds | matrix | anthropic,openai | experiment | Complete experiment-matrix definition: model x effort x replicates, blind, budgeted (REQ-113). |
| 49 | `06-find-fix-verify.yaml` | rounds | subprocess | anthropic | pipeline | Declarative find-fix-verify YAML workflow for Terraform-for-prompts style automation |
| 50 | `07-task-affinity.yaml` | rounds | cli | all | routing | Tag tasks with task_type so Rondo learns WHICH model is best at WHICH job — not one blended score. |
| 51 | `demo_pipeline.py` | rounds | subprocess | anthropic | pipeline | Four-stage scan/review/fix/verify round workflow |
| 52 | `phases_overnight.py` | rounds | subprocess | anthropic | pipeline | Multi-phase overnight plan with model-tier escalation |
| 53 | `review_demo.py` | rounds | subprocess | anthropic | review | Forward/reverse/sideways review strategy on a demo file |
| 54 | `round_caliber_fix.py` | rounds | subprocess | anthropic | pipeline | Caliber findings to automated fix workflow |
| 55 | `round_code_review.py` | rounds | subprocess | anthropic | review | Git-diff-aware review round with staged-change gate |
| 56 | `round_doc_sweep.py` | rounds | subprocess | anthropic | publish | Parallel docs cleanup tasks across repository files |
| 57 | `round_file_check.py` | rounds | subprocess | anthropic | basic | File existence gate + auto task + AI summary task |
| 58 | `round_hello.py` | rounds | subprocess | anthropic | basic | Absolute minimal one-task Python round |
| 59 | `round_multi_task.py` | rounds | subprocess | anthropic | pipeline | Multi-task round mixing auto and AI tasks |
| 60 | `round_refactor_audit.py` | rounds | subprocess | anthropic | review | Refactor audit with blocking/non-blocking gates |
| 61 | `round_security_audit.py` | rounds | subprocess | anthropic | review | Security audit pattern with clean-tree pre-gate |
| 62 | `round_test_generator.py` | rounds | subprocess | anthropic | pipeline | Auto-discover untested modules and generate test stubs |
| 63 | `01-execution-modes.sh` | cli | subprocess,http | anthropic,gemini | basic | CLI subprocess route vs provider HTTP route |
| 64 | `02-background-polling.sh` | cli | subprocess | anthropic | observability | Background polling command recipe for MCP-style flows |
| 65 | `03-consensus-review.sh` | cli | subprocess | gemini,grok | review | Two-provider file review consensus pattern |
| 66 | `04-model-comparison.sh` | cli | subprocess,http | anthropic,gemini,grok | review | Compare one prompt across three models from CLI. |
| 67 | `04-showcase-runner.sh` | cli | subprocess | — | observability | One-command showcase run plus API example validation |
| 68 | `05-batch-retry.sh` | cli | http | gemini,grok | pipeline | Run batch providers then retry failed dispatch ids via MCP tools. |
| 69 | `06-experiment-matrix.sh` | cli | matrix | anthropic,openai | experiment | Full experiment-matrix workflow: dry-run, execute, report, reveal (REQ-113). |
| 70 | `07-fleet-health.sh` | cli | cli | all | operations | The morning fleet check: model drift, learned scores, retry queue, reliability scoreboard. |
| 71 | `08-nightly-watchdog.sh` | cli | cli | all | operations | The night watchman: one schedulable command that sweeps drift + retryq + reliability and ALERTS instead of waiting to be asked. |
| 72 | `real-world-scripting.sh` | cli | subprocess,http | gemini,grok,mistral,ollama | pipeline | Shell scripting playbook for practical AI workflows |
| 73 | `scripted-prompting.sh` | cli | subprocess,http | anthropic,gemini,grok,mistral,ollama | pipeline | jq-driven branching, retries, and prompting scripts |
| 74 | `01-inline-host-plan.md` | mcp | inline | anthropic | basic | MCP default inline plan and host-executed behavior |
| 75 | `02-agent-host-plan.md` | mcp | agent | anthropic | basic | Explicit agent plan mode for host-side execution |
| 76 | `03-subprocess-fresh-session.md` | mcp | subprocess | anthropic | basic | Force fresh subprocess execution from MCP tool call |
| 77 | `04-provider-http-bypass.md` | mcp | http | anthropic,gemini,grok,mistral,openai,ollama | config | Provider-prefixed model behavior that bypasses execution routing |
| 78 | `05-background-polling.md` | mcp | subprocess | anthropic | observability | Background run lifecycle and polling tiers from MCP |
| 79 | `06-multi-provider-review.md` | mcp | http | anthropic,gemini,grok,mistral,openai | review | Multi-provider review workflow through MCP tools |
| 80 | `07-review-file.md` | mcp | subprocess | anthropic | review | File-scoped review workflow for real source files |
| 81 | `08-cloud-profile-tier.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai,ollama | config | Cloud profile/tier routing examples for model selection |
| 82 | `09-chain-pipeline.md` | mcp | subprocess | anthropic | pipeline | Chaining tool calls where each step feeds the next |
| 83 | `10-benchmark-model-selection.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai | observability | Benchmarking model options before choosing defaults |
| 84 | `11-retry-failed-dispatch.md` | mcp | subprocess | anthropic | observability | Recovery of failed dispatches using retry tools |
| 85 | `12-diff-two-runs.md` | mcp | subprocess | anthropic | drift | Compare run outputs to detect behavioral drift |
| 86 | `13-observability-suite.md` | mcp | subprocess | anthropic | observability | End-to-end health/metrics/history/audit monitoring flow |
| 87 | `README.md` | mcp | inline,subprocess,agent,http | anthropic,gemini,grok,mistral,openai,ollama | config | MCP playbook overview with copy/paste entry points |
