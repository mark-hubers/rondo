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
| 14 | `essay_fact_check_pipeline.py` | api | subprocess | anthropic | essay | Multi-step essay claim extraction and fact-check loop |
| 15 | `field_named_return.py` | api | subprocess | anthropic | basic | Named JSON field contract for script-friendly outputs |
| 16 | `find_and_fix_pipeline.py` | api | subprocess | anthropic | pipeline | Find -> fix -> verify chain with real dispatches |
| 17 | `idempotency_cache_demo.py` | api | subprocess | anthropic | observability | Duplicate-request cache behavior and timing comparison |
| 18 | `incident_triage_playbook.py` | api | subprocess | anthropic | triage | Generate incident severity, owner, and first-response actions. |
| 19 | `lint_fix_verify_loop.py` | api | subprocess | anthropic | pipeline | Iterative lint/fix/verify automation pattern |
| 20 | `model_comparison.py` | api | http | anthropic,gemini,grok | review | Compare model outputs side-by-side for one review prompt. |
| 21 | `multi_ai_tiebreaker.py` | api | subprocess,http | anthropic | review | Multi-model disagreement handling and tie-break voting |
| 22 | `multi_platform_publish.py` | api | subprocess | anthropic | publish | One prompt pipeline that adapts copy for multiple platforms |
| 23 | `multi_provider_dispatch.py` | api | http | gemini,grok,ollama | review | Fan-out to multiple providers with one prompt |
| 24 | `normalize_responses.py` | api | subprocess | anthropic | config | Normalizing varied model payloads into one stable shape |
| 25 | `pr_review_workflow.py` | api | subprocess | anthropic | review | Run a PR-style review prompt and extract actionable findings. |
| 26 | `provider_scoring.py` | api | subprocess | anthropic | observability | Provider scoring and comparison from run outputs |
| 27 | `replay_demo.py` | api | subprocess | anthropic | observability | Replay baseline-vs-current outputs and summarize drift. |
| 28 | `research_freshness_scanner.py` | api | subprocess | anthropic | research | Research freshness scoring and stale-source detection |
| 29 | `retry_on_failure.py` | api | subprocess | anthropic | observability | Retry strategy and recovery handling for failed runs |
| 30 | `spec_code_drift_scanner.py` | api | subprocess | anthropic | drift | Spec-vs-code drift checks with PASS/FAIL verdicts |
| 31 | `yaml_round_loader.py` | api | subprocess | anthropic | config | Loading and dispatching YAML round definitions via API |
| 32 | `01-simple-review.yaml` | rounds | subprocess | anthropic | review | Simplest single-task YAML round review |
| 33 | `02-multi-provider.yaml` | rounds | http | gemini,grok,ollama | review | Same task across three providers for comparison |
| 34 | `03-budget-capped.yaml` | rounds | http | gemini | observability | Multi-task batch constrained by max budget |
| 35 | `04-with-hooks.py` | rounds | subprocess | anthropic | pipeline | Python round hooks (pre/post dispatch transformations) |
| 36 | `05-overnight-batch.yaml` | rounds | http | gemini,grok | observability | Overnight batch pattern with mixed provider tasks |
| 37 | `demo_pipeline.py` | rounds | subprocess | anthropic | pipeline | Four-stage scan/review/fix/verify round workflow |
| 38 | `phases_overnight.py` | rounds | subprocess | anthropic | pipeline | Multi-phase overnight plan with model-tier escalation |
| 39 | `review_demo.py` | rounds | subprocess | anthropic | review | Forward/reverse/sideways review strategy on a demo file |
| 40 | `round_caliber_fix.py` | rounds | subprocess | anthropic | pipeline | Caliber findings to automated fix workflow |
| 41 | `round_code_review.py` | rounds | subprocess | anthropic | review | Git-diff-aware review round with staged-change gate |
| 42 | `round_doc_sweep.py` | rounds | subprocess | anthropic | publish | Parallel docs cleanup tasks across repository files |
| 43 | `round_file_check.py` | rounds | subprocess | anthropic | basic | File existence gate + auto task + AI summary task |
| 44 | `round_hello.py` | rounds | subprocess | anthropic | basic | Absolute minimal one-task Python round |
| 45 | `round_multi_task.py` | rounds | subprocess | anthropic | pipeline | Multi-task round mixing auto and AI tasks |
| 46 | `round_refactor_audit.py` | rounds | subprocess | anthropic | review | Refactor audit with blocking/non-blocking gates |
| 47 | `round_security_audit.py` | rounds | subprocess | anthropic | review | Security audit pattern with clean-tree pre-gate |
| 48 | `round_test_generator.py` | rounds | subprocess | anthropic | pipeline | Auto-discover untested modules and generate test stubs |
| 49 | `01-execution-modes.sh` | cli | subprocess,http | anthropic,gemini | basic | CLI subprocess route vs provider HTTP route |
| 50 | `02-background-polling.sh` | cli | subprocess | anthropic | observability | Background polling command recipe for MCP-style flows |
| 51 | `03-consensus-review.sh` | cli | subprocess | gemini,grok | review | Two-provider file review consensus pattern |
| 52 | `04-model-comparison.sh` | cli | subprocess,http | anthropic,gemini,grok | review | Compare one prompt across three models from CLI. |
| 53 | `04-showcase-runner.sh` | cli | subprocess | — | observability | One-command showcase run plus API example validation |
| 54 | `05-batch-retry.sh` | cli | http | gemini,grok | pipeline | Run batch providers then retry failed dispatch ids via MCP tools. |
| 55 | `real-world-scripting.sh` | cli | subprocess,http | gemini,grok,mistral,ollama | pipeline | Shell scripting playbook for practical AI workflows |
| 56 | `scripted-prompting.sh` | cli | subprocess,http | anthropic,gemini,grok,mistral,ollama | pipeline | jq-driven branching, retries, and prompting scripts |
| 57 | `01-inline-host-plan.md` | mcp | inline | anthropic | basic | MCP default inline plan and host-executed behavior |
| 58 | `02-agent-host-plan.md` | mcp | agent | anthropic | basic | Explicit agent plan mode for host-side execution |
| 59 | `03-subprocess-fresh-session.md` | mcp | subprocess | anthropic | basic | Force fresh subprocess execution from MCP tool call |
| 60 | `04-provider-http-bypass.md` | mcp | http | anthropic,gemini,grok,mistral,openai,ollama | config | Provider-prefixed model behavior that bypasses execution routing |
| 61 | `05-background-polling.md` | mcp | subprocess | anthropic | observability | Background run lifecycle and polling tiers from MCP |
| 62 | `06-multi-provider-review.md` | mcp | http | anthropic,gemini,grok,mistral,openai | review | Multi-provider review workflow through MCP tools |
| 63 | `07-review-file.md` | mcp | subprocess | anthropic | review | File-scoped review workflow for real source files |
| 64 | `08-cloud-profile-tier.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai,ollama | config | Cloud profile/tier routing examples for model selection |
| 65 | `09-chain-pipeline.md` | mcp | subprocess | anthropic | pipeline | Chaining tool calls where each step feeds the next |
| 66 | `10-benchmark-model-selection.md` | mcp | subprocess,http | anthropic,gemini,grok,mistral,openai | observability | Benchmarking model options before choosing defaults |
| 67 | `11-retry-failed-dispatch.md` | mcp | subprocess | anthropic | observability | Recovery of failed dispatches using retry tools |
| 68 | `12-diff-two-runs.md` | mcp | subprocess | anthropic | drift | Compare run outputs to detect behavioral drift |
| 69 | `13-observability-suite.md` | mcp | subprocess | anthropic | observability | End-to-end health/metrics/history/audit monitoring flow |
| 70 | `README.md` | mcp | inline,subprocess,agent,http | anthropic,gemini,grok,mistral,openai,ollama | config | MCP playbook overview with copy/paste entry points |
