# Rondo Test Inventory

**Total tests:** 1618  
**Total files:** 44  
**Generated:** 2026-04-07 (RONDO-208)

## Summary by Layer

| Layer | Files | Tests | Purpose |
|-------|-------|-------|---------|
| **unit/** | 26 | 1145 | Unit Tests — Pure logic, no I/O |
| **integration/** | 8 | 180 | Integration Tests — Multiple components together |
| **e2e/** | 1 | 114 | End-to-End Tests — Full pipeline lifecycles |
| **pat/** | 6 | 133 | Product Acceptance Tests — Real behavior, zero mocking |
| **chaos/** | 2 | 15 | Chaos Tests — Failure injection |
| **conventions/** | 1 | 31 | Convention Tests — Style/layering/security rules |

---

## unit/ — Unit Tests — Pure logic, no I/O (1145 tests)

### `test_ai_help.py` (50)

**TestAiHelp** (6)
- `test_ai_help_commands_have_description`
- `test_ai_help_has_commands`
- `test_ai_help_has_config_options`
- `test_ai_help_has_task_schema`
- `test_ai_help_has_version`
- `test_ai_help_is_valid_json`

**TestAiHelpCLI** (1)
- `test_ai_help_flag`

**TestAiHelpCloudCapabilities** (7)
- `test_cloud_dispatch_capability_present`
- `test_cloud_dispatch_lists_providers`
- `test_important_section_has_cloud_info`
- `test_provider_health_capability_present`
- `test_provider_health_has_cache_ttl`
- `test_quick_examples_include_gemini`
- `test_quick_examples_include_multi_review`

**TestAiHelpCloudProviders** (8)
- `test_anthropic_provider_present`
- `test_description_mentions_cloud_providers`
- `test_each_cloud_provider_has_tiers`
- `test_each_provider_has_examples`
- `test_gemini_provider_present`
- `test_grok_provider_present`
- `test_mistral_provider_present`
- `test_openai_provider_present`

**TestAiHelpExampleRoundFile** (4)
- `test_example_has_build_round`
- `test_example_has_imports`
- `test_example_is_valid_python`
- `test_example_round_file_present`

**TestAiHelpGateSchema** (2)
- `test_gate_schema_has_fields`
- `test_gate_schema_present`

**TestAiHelpMCPTools** (5)
- `test_cloud_tools_have_cloud_category`
- `test_mcp_tools_have_categories`
- `test_mcp_tools_present`
- `test_rondo_cloud_in_mcp_tools`
- `test_rondo_multi_review_in_mcp_tools`

**TestAiHelpProviders** (4)
- `test_each_provider_has_models`
- `test_providers_has_claude`
- `test_providers_has_ollama`
- `test_providers_section_exists`

**TestAiHelpRoundSchema** (2)
- `test_round_schema_has_fields`
- `test_round_schema_present`

**TestAiHelpTaskSchemaComplete** (3)
- `test_task_schema_has_auto_fn`
- `test_task_schema_has_description`
- `test_task_schema_has_mode`

**TestCapabilities** (3)
- `test_capabilities_list`
- `test_dispatch_capability_details`
- `test_preflight_capability_details`

**TestHowItWorks** (3)
- `test_each_step_has_example`
- `test_how_it_works_present`
- `test_three_steps`

**TestQuickExamples** (2)
- `test_each_has_task_and_run`
- `test_quick_examples_present`

### `test_audit.py` (34)

**TestAuditDir** (2)
- `test_audit_dir_created_if_missing`
- `test_custom_audit_dir`

**TestAuditDispatchedAt** (1)
- `test_outcome_has_dispatched_at`

**TestAuditEdgeCases** (5)
- `test_crash_leaves_intent`
- `test_empty_prompt`
- `test_large_output_stored`
- `test_outcome_for_unknown_id_still_writes`
- `test_unicode_in_prompt`

**TestAuditRecordSchema** (2)
- `test_record_has_all_required_fields`
- `test_record_serializes_to_dict`

**TestAuditReset** (3)
- `test_reset_clears_jsonl`
- `test_reset_clears_prompt_result_files`
- `test_reset_empty_is_zero`

**TestAuditRotate** (3)
- `test_rotate_empty_is_noop`
- `test_rotate_moves_to_archive`
- `test_rotate_preserves_data`

**TestAuditRoundName** (1)
- `test_outcome_has_round_name`

**TestCredentialScrubbing** (2)
- `test_prompt_file_scrubbed`
- `test_result_file_scrubbed`

**TestFilesModified** (1)
- `test_files_modified_in_outcome`

**TestImmutability** (1)
- `test_outcome_appends_not_modifies`

**TestJsonlStorage** (2)
- `test_each_line_is_valid_json`
- `test_multiple_records_appended`

**TestMorningReportIds** (1)
- `test_get_failed_dispatches`

**TestPhaseOneIntent** (5)
- `test_intent_has_dispatch_id`
- `test_intent_has_prompt_hash`
- `test_intent_has_timestamp`
- `test_intent_written_to_jsonl`
- `test_record_intent_creates_record`

**TestPhaseTwoComplete** (2)
- `test_outcome_has_completed_at`
- `test_record_outcome_updates_status`

**TestPromptStorage** (2)
- `test_prompt_file_created`
- `test_prompt_file_referenced_in_record`

**TestResultStorage** (1)
- `test_result_file_created_on_outcome`

### `test_auth.py` (24)

**TestAutoChain** (3)
- `test_env_wins_over_keychain`
- `test_keychain_used_when_no_env`
- `test_returns_empty_when_all_fail`

**TestCaching** (3)
- `test_invalidate_clears_cache`
- `test_invalidate_nonexistent_is_safe`
- `test_second_call_uses_cache`

**TestEnvBackend** (6)
- `test_anthropic_env_var`
- `test_gemini_env_var`
- `test_grok_env_var`
- `test_returns_empty_for_unknown_provider`
- `test_returns_empty_when_not_set`
- `test_returns_env_var_when_set`

**TestKeyBackendInterface** (4)
- `test_env_backend_is_keybackend`
- `test_keybackend_is_abstract`
- `test_keychain_backend_is_keybackend`
- `test_onepassword_backend_is_keybackend`

**TestKeychainBackend** (4)
- `test_returns_empty_on_failure`
- `test_returns_empty_on_timeout`
- `test_returns_empty_when_security_missing`
- `test_returns_key_on_success`

**TestOnePasswordBackend** (4)
- `test_custom_vault_name`
- `test_returns_empty_on_op_failure`
- `test_returns_empty_when_op_not_installed`
- `test_returns_key_on_success`

### `test_cli.py` (85)

**TestBuildConfig** (11)
- `test_build_config_all_overrides`
- `test_build_config_auth_override`
- `test_build_config_dry_run_flag`
- `test_build_config_effort_override`
- `test_build_config_model_override`
- `test_build_config_no_overrides`
- `test_build_config_on_overage_override`
- `test_build_config_permission_mode_override`
- `test_build_config_timeout_override`
- `test_build_config_verbose_flag`
- `test_build_config_workers_override`

**TestCliEntryPoint** (2)
- `test_help_flag`
- `test_parser_exists`

**TestCliFlags** (12)
- `test_auth_flag`
- `test_config_flag`
- `test_default_flags`
- `test_dry_run_flag`
- `test_effort_flag`
- `test_model_flag`
- `test_on_overage_flag`
- `test_permission_mode_flag`
- `test_permission_mode_overnight`
- `test_timeout_flag`
- `test_verbose_flag`
- `test_workers_flag`

**TestCostDisplay** (1)
- `test_verbose_shows_cost`

**TestDynamicImport** (4)
- `test_load_round_file`
- `test_load_round_file_no_build_round`
- `test_load_round_file_not_found`
- `test_load_round_file_returns_wrong_type`

**TestExitCodes** (8)
- `test_config_validation_error`
- `test_error_exit_code`
- `test_exit_constants_defined`
- `test_file_not_found_exit_code`
- `test_keyboard_interrupt_exit_code`
- `test_no_subcommand_exit_code`
- `test_success_exit_code`
- `test_unexpected_error_exit_code`

**TestExpensiveSort** (1)
- `test_expensive_flag_accepted`

**TestFailureNotification** (1)
- `test_failure_notify_called_on_error`

**TestHistorySubcommand** (2)
- `test_history_empty`
- `test_history_json_empty`

**TestHumanInputField** (2)
- `test_task_accepts_human_input`
- `test_task_has_human_input_default`

**TestLoadPhasesFile** (5)
- `test_load_phases_file_import_error`
- `test_load_phases_file_no_build_phases`
- `test_load_phases_file_not_found`
- `test_load_phases_file_success`
- `test_load_phases_file_wrong_return_type`

**TestMainIntegration** (5)
- `test_main_no_args`
- `test_main_run_calls_run_round`
- `test_main_run_error_exit_code`
- `test_main_run_partial_exit_code`
- `test_main_run_with_flags`

**TestMainModule** (1)
- `test_main_module_calls_main`

**TestNewCLIFlags** (4)
- `test_bare_flag_in_config`
- `test_json_schema_auto_in_config`
- `test_max_budget_in_config`
- `test_system_prompt_in_config`

**TestOvernightSubcommand** (7)
- `test_overnight_config_validation_error`
- `test_overnight_error_status`
- `test_overnight_file_not_found`
- `test_overnight_no_build_phases`
- `test_overnight_report_save_failure`
- `test_overnight_success`
- `test_overnight_with_mode_flag`

**TestPreflightSubcommand** (4)
- `test_preflight_json_output`
- `test_preflight_returns_failure_when_red`
- `test_preflight_returns_success_when_green`
- `test_preflight_shows_checks`

**TestProvidersSubcommand** (5)
- `test_json_empty_when_no_providers`
- `test_json_output`
- `test_no_providers_configured`
- `test_shows_healthy_provider`
- `test_shows_unhealthy_provider`

**TestReportSubcommand** (1)
- `test_report_not_yet_implemented`

**TestRunWithFile** (2)
- `test_run_accepts_file_path`
- `test_run_file_required`

**TestRunnerValidation** (1)
- `test_invalid_round_returns_error_result`

**TestSubcommands** (3)
- `test_overnight_subcommand`
- `test_report_subcommand`
- `test_run_subcommand`

**TestVerboseOutput** (2)
- `test_non_verbose_run_prints_summary_only`
- `test_verbose_run_prints_details`

**TestVersionFlag** (1)
- `test_version_output`

### `test_config.py` (85)

**TestAllConfigFields** (14)
- `test_all_valid_efforts`
- `test_all_valid_models`
- `test_all_valid_output_formats`
- `test_all_valid_overage_actions`
- `test_all_valid_permission_modes`
- `test_effort_default`
- `test_invalid_permission_mode`
- `test_on_overage_default`
- `test_output_format_default`
- `test_permission_mode_coalesce`
- `test_permission_mode_default`
- `test_rate_limit_backoff_default`
- `test_watchdog_default`
- `test_worktree_isolation_default`

**TestCliOverride** (2)
- `test_cli_overrides_config_file`
- `test_cli_overrides_multiple_fields`

**TestCoalesce** (5)
- `test_full_coalesce_chain`
- `test_resolve_cli_none_explicit`
- `test_resolve_cli_wins`
- `test_resolve_config_wins_no_cli`
- `test_resolve_default_wins_no_cli_no_config`

**TestConfigDefaults** (9)
- `test_default_audit_dir_always_on`
- `test_default_auth_is_max`
- `test_default_bare_is_true`
- `test_default_dry_run_is_false`
- `test_default_model_is_sonnet`
- `test_default_output_format_stream_json`
- `test_default_round_timeout`
- `test_default_task_timeout`
- `test_default_workers`

**TestConfigDiscovery** (3)
- `test_discover_in_search_dir`
- `test_explicit_config_path`
- `test_no_walk_up`

**TestConfigFromToml** (2)
- `test_toml_partial_new_fields`
- `test_toml_with_new_fields`

**TestConfigImmutable** (2)
- `test_frozen_cannot_delete_field`
- `test_frozen_cannot_set_field`

**TestConfigIsDataclass** (1)
- `test_is_dataclass`

**TestConfigOverride** (1)
- `test_config_file_overrides_defaults`

**TestConfigPermissionModes** (1)
- `test_all_permission_modes_valid`

**TestConfigValidation** (2)
- `test_invalid_auth_rejected`
- `test_invalid_model_rejected`

**TestModelResolution** (3)
- `test_cli_model_overrides_task`
- `test_config_default_used_last`
- `test_task_model_overrides_config`

**TestNewConfigFields** (6)
- `test_all_new_fields_set`
- `test_bare_default_true`
- `test_config_frozen_cannot_modify`
- `test_dispatch_system_prompt_default_empty`
- `test_json_schema_default_empty`
- `test_max_budget_default_none`

**TestRelationshipValidation** (4)
- `test_default_config_relationship_valid`
- `test_watchdog_equal_to_task_timeout_fails`
- `test_watchdog_less_than_task_timeout_passes`
- `test_watchdog_must_be_less_than_task_timeout`

**TestTimeoutConfig** (3)
- `test_timeout_configurable`
- `test_timeout_default_300`
- `test_timeout_from_toml`

**TestTomlLoading** (2)
- `test_load_from_toml_file`
- `test_partial_toml_fills_defaults`

**TestTomlTypeChecking** (2)
- `test_correct_type_no_warning`
- `test_wrong_type_warns`

**TestUnknownKeys** (2)
- `test_unknown_keys_produce_warning`
- `test_unknown_toml_keys_ignored`

**TestValidationErrors** (18)
- `test_empty_claude_binary`
- `test_empty_report_dir`
- `test_empty_results_dir`
- `test_invalid_auth`
- `test_invalid_backoff_low`
- `test_invalid_effort`
- `test_invalid_model`
- `test_invalid_on_overage`
- `test_invalid_output_format`
- `test_invalid_throttle_negative`
- `test_invalid_throttle_too_high`
- `test_invalid_timeout_high`
- `test_invalid_timeout_low`
- `test_invalid_watchdog_high`
- `test_invalid_watchdog_low`
- `test_invalid_workers_high`
- `test_invalid_workers_low`
- `test_multiple_errors_returned`

**TestZeroConfig** (3)
- `test_default_config_all_fields_populated`
- `test_default_config_validates`
- `test_load_config_no_file`

### `test_dispatch.py` (203)

**TestAuditWiring** (1)
- `test_interactive_dispatch_records_audit`

**TestAutoTask** (3)
- `test_auto_task_exception`
- `test_auto_task_failure`
- `test_auto_task_success`

**TestAutoTaskDispatch** (4)
- `test_auto_task_calls_fn`
- `test_auto_task_exception`
- `test_auto_task_failure`
- `test_auto_task_no_subprocess`

**TestBudgetExceeded** (2)
- `test_budget_exceeded_in_result_events`
- `test_success_result_not_budget_exceeded`

**TestBuildSubprocessCmd** (7)
- `test_bare_flag_added_when_enabled`
- `test_bare_flag_present_by_default`
- `test_default_cmd_has_base_flags`
- `test_permission_mode_in_cmd`
- `test_tool_mode_default_no_extra_flags`
- `test_tool_mode_none_adds_tools_empty`
- `test_tool_mode_sandbox_adds_dangerously_skip`

**TestCCVersionDetection** (4)
- `test_bare_added_when_version_sufficient`
- `test_bare_skipped_when_version_too_old`
- `test_detect_cc_version`
- `test_detect_cc_version_missing`

**TestConfigCoalesce** (3)
- `test_cli_overrides_toml`
- `test_default_when_no_toml`
- `test_toml_overrides_default`

**TestConfigValidationDeep** (3)
- `test_negative_timeout_rejected`
- `test_valid_config_no_errors`
- `test_zero_workers_rejected`

**TestContextDataInPrompt** (4)
- `test_context_data_appears_in_prompt`
- `test_context_data_json_formatted`
- `test_empty_context_data_not_in_prompt`
- `test_large_list_uses_jsonl`

**TestContextDataSizeCap** (3)
- `test_combined_files_and_data_cap`
- `test_large_context_data_rejected`
- `test_small_context_data_accepted`

**TestCostOutputControl** (6)
- `test_json_schema_absent_when_empty`
- `test_json_schema_in_cmd`
- `test_max_budget_absent_when_none`
- `test_max_budget_in_cmd`
- `test_system_prompt_absent_when_empty`
- `test_system_prompt_in_cmd`

**TestCredentialSanitization** (1)
- `test_api_key_not_in_saved_result`

**TestDispatchAlwaysOn** (4)
- `test_auto_task_has_duration`
- `test_dry_run_has_model`
- `test_dry_run_has_timestamp`
- `test_error_result_has_auth_mode`

**TestDispatchErrorPaths** (5)
- `test_auto_task_exception`
- `test_auto_task_failure`
- `test_auto_task_success`
- `test_dry_run_returns_skipped`
- `test_validation_error_returns_result`

**TestDispatchInputValidation** (2)
- `test_empty_instruction_rejected`
- `test_invalid_tool_mode_rejected`

**TestDispatchIntegration** (8)
- `test_empty_stdout_error`
- `test_error_exit_code`
- `test_malformed_json_partial`
- `test_model_flag_passed`
- `test_permission_mode_default_auto`
- `test_permission_mode_passed`
- `test_result_capture_fields`
- `test_subprocess_command_has_claude_p`

**TestDispatchValidation** (3)
- `test_invalid_task_no_subprocess`
- `test_invalid_task_returns_error_result`
- `test_valid_task_passes_validation`

**TestDryRun** (2)
- `test_dry_run_no_subprocess`
- `test_dry_run_returns_prompt`

**TestDryRunOutput** (2)
- `test_dry_run_no_subprocess`
- `test_dry_run_returns_prompt`

**TestEngineFields** (3)
- `test_dispatch_usage_budget_field`
- `test_dispatch_usage_defaults`
- `test_task_all_new_fields`

**TestEnvPrep** (4)
- `test_auth_api_keeps_api_key`
- `test_auth_max_strips_api_key`
- `test_claudecode_stripped`
- `test_env_is_copy_not_original`

**TestEnvPrepDeep** (3)
- `test_api_key_kept_for_api`
- `test_api_key_stripped_for_max`
- `test_claudecode_always_stripped`

**TestEnvironmentPrep** (2)
- `test_env_has_path`
- `test_env_strips_claudecode`

**TestErrorClassification** (7)
- `test_auth_error_credit`
- `test_auth_error_invalid_key`
- `test_empty_stderr`
- `test_generic_error`
- `test_nested_session_error`
- `test_rate_limit_error`
- `test_rate_limit_lowercase`

**TestExtractCodeBlocks** (5)
- `test_multiple_blocks`
- `test_never_raises`
- `test_no_blocks_returns_empty`
- `test_no_language`
- `test_single_block`

**TestExtractJson** (6)
- `test_does_not_modify_raw_output`
- `test_empty_output_returns_none`
- `test_invalid_json_returns_none`
- `test_json_embedded_in_text`
- `test_nested_json_extracted`
- `test_valid_json`

**TestExtractTable** (3)
- `test_never_raises`
- `test_no_table_returns_empty`
- `test_simple_table`

**TestFileExtraction** (4)
- `test_extract_deduplicates`
- `test_extract_multiple_extensions`
- `test_extract_no_files`
- `test_extract_python_files`

**TestFileExtractionSTD108** (2)
- `test_empty_output`
- `test_no_duplicates`

**TestGateExecution** (4)
- `test_blocking_gate_prevents_proceed`
- `test_failing_gate`
- `test_non_blocking_gate_allows_proceed`
- `test_passing_gate`

**TestHistoryIntegration** (1)
- `test_history_logged_after_interactive_dispatch`

**TestHistoryWithRealData** (2)
- `test_aggregate_includes_duration`
- `test_query_by_round_and_model`

**TestModelResolution** (6)
- `test_model_1m_variant`
- `test_model_cli_overrides_config`
- `test_model_cli_overrides_task`
- `test_model_config_overrides_default`
- `test_model_default_sonnet`
- `test_model_from_task_hint`

**TestModelResolutionDeep** (4)
- `test_cli_overrides_task`
- `test_config_default_used`
- `test_invalid_model_raises`
- `test_task_overrides_config`

**TestModelValidation** (5)
- `test_1m_variants_valid`
- `test_invalid_model_from_cli`
- `test_invalid_model_from_config`
- `test_invalid_model_raises`
- `test_valid_models_set_exists`

**TestNotifyAllChannels** (1)
- `test_all_channels_fire`

**TestPreflightSerialization** (1)
- `test_result_serializable`

**TestProjectFlag** (3)
- `test_config_has_project_field`
- `test_default_project_is_empty`
- `test_project_sets_subprocess_cwd`

**TestPromptBuilder** (7)
- `test_prompt_contains_context_files`
- `test_prompt_contains_description`
- `test_prompt_contains_done_when`
- `test_prompt_contains_instruction`
- `test_prompt_contains_task_name`
- `test_prompt_includes_status_field`
- `test_prompt_requests_json_output`

**TestPromptBuildingDeep** (3)
- `test_prompt_always_has_output_format`
- `test_prompt_with_context_data_and_files`
- `test_prompt_with_description`

**TestResultSaving** (7)
- `test_max_output_bytes_scales_with_model`
- `test_output_cap_scales_for_1m_context_models`
- `test_output_cap_truncates_beyond_model_limit`
- `test_output_truncation`
- `test_result_file_permissions`
- `test_result_includes_metadata`
- `test_result_saved_to_json`

**TestResultSavingDeep** (3)
- `test_save_contains_usage`
- `test_save_creates_file`
- `test_save_file_permissions`

**TestRondoConstants** (6)
- `test_config_uses_default_prompt_when_auto`
- `test_config_uses_schema_constant`
- `test_default_system_prompt_exists`
- `test_default_system_prompt_mentions_json`
- `test_result_schema_has_required_fields`
- `test_result_schema_is_valid_json`

**TestRoundResultCalculation** (4)
- `test_all_done_is_done`
- `test_all_error`
- `test_empty_is_skipped`
- `test_mix_is_partial`

**TestRoundValidation** (2)
- `test_duplicate_task_names_rejected`
- `test_valid_round_no_errors`

**TestSanitizeWiring** (2)
- `test_auto_task_output_sanitized`
- `test_dry_run_not_sanitized`

**TestSpoolGating** (4)
- `test_async_dispatch_writes_spool`
- `test_dry_run_skips_spool`
- `test_spool_enabled_false_by_default`
- `test_sync_dispatch_skips_spool`

**TestStreamJsonParsing** (11)
- `test_assistant_text_collected`
- `test_context_window_captured`
- `test_cost_capture`
- `test_duration_capture`
- `test_init_event_extraction`
- `test_missing_rate_limit`
- `test_num_turns_captured`
- `test_overage_flag`
- `test_parse_lines`
- `test_rate_limit_extraction`
- `test_result_metadata_extraction`

**TestStreamJsonParsingDeep** (4)
- `test_empty_lines_skipped`
- `test_invalid_json_skipped`
- `test_rate_limit_populates_usage`
- `test_result_populates_cost`

**TestStructuredOutputParsing** (4)
- `test_extract_structured_output_found`
- `test_extract_structured_output_multiple_events`
- `test_extract_structured_output_not_found`
- `test_structured_output_preferred_over_text_parsing`

**TestSubprocessCommand** (4)
- `test_basic_command_structure`
- `test_effort_flag_added`
- `test_max_budget_flag`
- `test_permission_mode_flag`

**TestTaskJsonParsing** (6)
- `test_blocked_status_parsed`
- `test_json_without_code_fence`
- `test_last_json_block_wins`
- `test_malformed_json_returns_none`
- `test_partial_json_returns_none`
- `test_valid_json_parsed`

**TestWatchdog** (3)
- `test_watchdog_allows_output_producing_process`
- `test_watchdog_config_exists`
- `test_watchdog_kills_silent_process`

### `test_engine.py` (126)

**TestAutoTaskRun** (3)
- `test_auto_fn_callable`
- `test_auto_fn_defaults_none`
- `test_is_auto_property`

**TestBlockingPregate** (4)
- `test_all_gates_pass_should_proceed`
- `test_blocking_gate_fails_should_not_proceed`
- `test_mixed_gates_blocking_fails`
- `test_non_blocking_gate_fails_should_still_proceed`

**TestContextData** (15)
- `test_context_data_with_nested_structures`
- `test_context_files_absolute_path_rejected`
- `test_context_files_path_traversal_rejected`
- `test_context_files_relative_path_ok`
- `test_context_files_symlink_inside_root_ok`
- `test_context_files_symlink_outside_root_rejected`
- `test_context_files_total_size_capped`
- `test_context_files_under_size_cap_ok`
- `test_task_context_data_accepts_dict`
- `test_task_has_context_data_default_empty`
- `test_task_result_context_data_default_empty`
- `test_task_result_has_context_data`
- `test_validate_accepts_serializable`
- `test_validate_empty_context_data_ok`
- `test_validate_rejects_non_serializable`

**TestGateCheck** (6)
- `test_gate_blocking_default_true`
- `test_gate_check_fn_returns_tuple`
- `test_gate_has_name`
- `test_gate_non_blocking`
- `test_run_gate_failing`
- `test_run_gate_passing`

**TestGateExecution** (5)
- `test_blocking_gate_stops_round`
- `test_failing_gate`
- `test_gate_exception_caught`
- `test_non_blocking_gate_continues`
- `test_passing_gate`

**TestIsTerminal** (3)
- `test_all_terminal_states`
- `test_invalid_state_not_terminal`
- `test_non_terminal_states`

**TestNewFieldsSerialization** (3)
- `test_dispatch_usage_budget_field_serializable`
- `test_task_result_with_command_sent`
- `test_task_with_all_new_fields_serializable`

**TestParallelConflictDetection** (3)
- `test_conflict_detected`
- `test_empty_files_no_conflicts`
- `test_no_conflicts`

**TestParameterizedRound** (1)
- `test_parameterized_round`

**TestPostgateTiming** (2)
- `test_multiple_post_gates`
- `test_run_gates_works_for_post_gates`

**TestResumeRound** (2)
- `test_resume_sets_task_statuses`
- `test_resume_skips_completed_tasks`

**TestRoundBuilder** (1)
- `test_function_returns_round`

**TestRoundCompletion** (5)
- `test_all_done_is_complete`
- `test_empty_tasks_is_complete`
- `test_in_progress_is_not_complete`
- `test_mixed_terminal_is_complete`
- `test_pending_is_not_complete`

**TestRoundResultStatusCalculation** (9)
- `test_all_blocked`
- `test_all_done`
- `test_all_error`
- `test_all_skipped`
- `test_empty_results_skipped`
- `test_mix_done_and_blocked`
- `test_mix_done_and_error`
- `test_mix_done_and_partial`
- `test_mix_error_and_blocked_no_done`

**TestRoundStateManagement** (3)
- `test_is_terminal`
- `test_state_roundtrip`
- `test_terminal_states_complete`

**TestRoundStateWithNewFields** (2)
- `test_resume_preserves_pending_tasks`
- `test_state_dict_includes_tool_mode`

**TestRoundStatusAllTypes** (4)
- `test_all_blocked_is_error`
- `test_done_plus_skipped_is_partial`
- `test_mixed_done_blocked_is_partial`
- `test_skipped_only_is_skipped`

**TestRoundStructure** (5)
- `test_round_defaults_empty`
- `test_round_has_name`
- `test_round_has_post_gates`
- `test_round_has_pre_gates`
- `test_round_has_tasks`

**TestRoundValidation** (3)
- `test_duplicate_task_names_invalid`
- `test_empty_name_invalid`
- `test_valid_round_no_errors`

**TestSerializeRound** (2)
- `test_serialize_round_state`
- `test_serialize_to_json_string`

**TestStateTransitions** (5)
- `test_is_terminal_false`
- `test_is_terminal_true`
- `test_task_starts_pending`
- `test_task_status_can_be_set`
- `test_terminal_states`

**TestTaskFields** (5)
- `test_task_description_defaults_empty`
- `test_task_has_description`
- `test_task_has_mode_default_interactive`
- `test_task_has_name`
- `test_task_has_status_default_pending`

**TestTaskModelHint** (3)
- `test_model_can_be_set`
- `test_model_default_none`
- `test_model_haiku`

**TestTaskResultFields** (7)
- `test_all_status_values_valid`
- `test_command_sent_field`
- `test_context_data_field`
- `test_cost_field`
- `test_dispatch_id_field`
- `test_files_modified_field`
- `test_json_serializable`

**TestTaskValidation** (3)
- `test_auto_fn_only_valid`
- `test_both_instruction_and_auto_fn`
- `test_no_instruction_and_no_auto_fn`

**TestTaskValidationEdgeCases** (4)
- `test_auto_task_with_no_fn_rejected`
- `test_both_auto_and_interactive_rejected`
- `test_context_data_non_serializable_rejected`
- `test_empty_name_rejected`

**TestThreeFieldContract** (4)
- `test_all_three_fields`
- `test_context_files_field`
- `test_done_when_field`
- `test_instruction_field`

**TestValidateRound** (5)
- `test_duplicate_task_names`
- `test_empty_round_name`
- `test_empty_tasks_valid`
- `test_invalid_task_in_round`
- `test_valid_round`

**TestValidateTask** (9)
- `test_both_auto_and_interactive`
- `test_empty_name`
- `test_missing_done_when`
- `test_missing_instruction`
- `test_multiple_errors_returned`
- `test_neither_auto_nor_interactive`
- `test_valid_auto_task`
- `test_valid_interactive_task`
- `test_whitespace_name`

### `test_flaky.py` (20)

**TestConfidenceVariance** (2)
- `test_high_variance_detected`
- `test_low_variance_stable`

**TestDispatchOutcome** (2)
- `test_outcome_has_confidence`
- `test_outcome_has_required_fields`

**TestFlakinessScore** (4)
- `test_all_same_status_zero_flakiness`
- `test_alternating_status_high_flakiness`
- `test_one_flip_among_many`
- `test_single_run_zero_flakiness`

**TestFlakinessThreshold** (2)
- `test_above_threshold_flagged`
- `test_below_threshold_not_flagged`

**TestFlakyEdgeCases** (3)
- `test_empty_engine`
- `test_outcomes_sorted_by_time`
- `test_to_json`

**TestFlipDetection** (3)
- `test_detect_flip`
- `test_no_flip_same_status`
- `test_partial_counts_as_flip`

**TestGrouping** (2)
- `test_different_prompts_separate_groups`
- `test_same_prompt_grouped`

**TestPerModelFlakiness** (1)
- `test_model_flakiness_stats`

**TestRootCause** (1)
- `test_root_cause_enum`

### `test_health.py` (24)

**TestCheckHealth** (7)
- `test_adapter_exception_returns_unhealthy`
- `test_checked_at_is_recent`
- `test_closed_circuit_breaker_does_http_health_call`
- `test_healthy_adapter_returns_healthy_status`
- `test_open_circuit_breaker_skips_http_health_call`
- `test_unhealthy_adapter_returns_unhealthy_status`
- `test_unknown_provider_returns_unhealthy`

**TestClearHealthCache** (2)
- `test_clear_idempotent_on_empty`
- `test_clear_removes_entries`

**TestGetAllProvidersHealth** (3)
- `test_empty_config_returns_empty_dict`
- `test_includes_all_configured_providers`
- `test_returns_dict`

**TestGetProviderHealth** (3)
- `test_cached_result_not_rechecked_within_ttl`
- `test_returns_health_status`
- `test_stale_cache_rechecks`

**TestHealthStatus** (3)
- `test_default_error_is_empty`
- `test_healthy_status`
- `test_unhealthy_status_has_error`

**TestIsProviderHealthy** (2)
- `test_returns_false_for_unhealthy`
- `test_returns_true_for_healthy`

**TestProviderFallback** (4)
- `test_never_falls_back_to_interactive_claude`
- `test_returns_none_when_all_providers_down`
- `test_uses_fallback_when_primary_down`
- `test_uses_primary_when_healthy`

### `test_history.py` (17)

**TestDispatchRecord** (2)
- `test_record_has_required_fields`
- `test_record_has_timestamp`

**TestHistoryRoundName** (2)
- `test_query_by_round_name`
- `test_record_with_round_name`

**TestLoadHistory** (2)
- `test_load_empty_dir`
- `test_load_returns_records`

**TestLogDispatch** (3)
- `test_log_appends_jsonl`
- `test_log_creates_file`
- `test_log_is_valid_json_per_line`

**TestModelAggregate** (3)
- `test_aggregate_by_model`
- `test_aggregate_empty`
- `test_aggregate_success_rate`

**TestQueryHistory** (3)
- `test_query_by_model`
- `test_query_by_status`
- `test_query_no_filter_returns_all`

**TestToolModeValidation** (2)
- `test_invalid_tool_mode`
- `test_valid_tool_modes`

### `test_mcp_cursor_reviews.py` (7)

**TestCursorP0ErrorCode** (1)
- `test_audit_outcome_has_error_code`

**TestCursorP1InlinePrePop** (1)
- `test_inline_background_has_task_name`

**TestCursorP1MCPPaths** (2)
- `test_health_uses_test_dir`
- `test_metrics_uses_test_dir`

**TestCursorP2CommandSSoT** (3)
- `test_command_list_has_init`
- `test_command_list_has_mcp`
- `test_command_list_matches_cli`

### `test_mcp_parallel_multi.py` (24)

**TestCloudDispatch** (9)
- `test_count_exceeds_max`
- `test_count_override`
- `test_dry_run_returns_cloud_metadata`
- `test_estimated_cost_in_metadata`
- `test_invalid_profile_returns_error`
- `test_profile_coding`
- `test_profile_review`
- `test_tier_high`
- `test_tier_low`

**TestDiskBasedRetry** (5)
- `test_load_from_disk`
- `test_load_missing_returns_none`
- `test_prune_old_retry_files`
- `test_retry_checks_disk`
- `test_save_only_on_failures`

**TestMultiReview** (7)
- `test_default_providers_on_empty`
- `test_dry_run_returns_skipped`
- `test_empty_prompt_rejected`
- `test_invalid_json_returns_error`
- `test_prompt_truncated_in_response`
- `test_too_many_providers_rejected`
- `test_whitespace_prompt_rejected`

**TestParallelDispatch** (3)
- `test_parallel_one_failure_others_succeed`
- `test_parallel_preserves_provider_order`
- `test_parallel_uses_threads`

### `test_mcp_router.py` (38)

**TestDispatchEngineIntegration** (5)
- `test_claude_model_in_session_returns_agent_plan`
- `test_empty_model_returns_inline_plan`
- `test_force_new_subprocess`
- `test_inline_plan_has_schema`
- `test_ollama_model_dispatches_via_http`

**TestDryRunPromptLength** (1)
- `test_inline_dry_run_has_prompt_length`

**TestInlineDispatch** (4)
- `test_inline_dry_run`
- `test_inline_no_prompt_no_file_errors`
- `test_inline_same_json_as_file`
- `test_inline_with_done_when`

**TestResolveDispatchEngine** (28)
- `test_1m_models_detected`
- `test_agent_plan_has_all_fields`
- `test_agent_plan_has_status`
- `test_all_plans_have_status_field`
- `test_anthropic_prefix_distinct_from_bare`
- `test_anthropic_prefix_routes_to_http`
- `test_background_forces_subprocess`
- `test_background_overrides_agent`
- `test_background_overrides_inline`
- `test_background_with_unknown_model_still_subprocess`
- `test_case_sensitive_for_bracket_models`
- `test_claude_model_in_session_returns_agent`
- `test_claude_model_outside_session_returns_subprocess`
- `test_empty_model_returns_inline`
- `test_error_has_status_error`
- `test_file_path_and_inline_prompt_use_same_router`
- `test_gemini_routes_to_http`
- `test_grok_routes_to_http`
- `test_inline_plan_has_all_fields`
- `test_legacy_ollama_routes_to_http`
- `test_local_routes_to_http`
- `test_mistral_routes_to_http`
- `test_new_suffix_forces_subprocess`
- `test_openai_routes_to_http`
- `test_provider_prefix_with_new_suffix_strips_new`
- `test_router_agrees_with_get_provider`
- `test_unknown_model_returns_error`
- `test_whitespace_in_model_is_stripped`

### `test_mcp_run_status.py` (31)

**TestBackgroundTTL** (2)
- `test_expired_returns_expired`
- `test_max_100_entries`

**TestMCPDispatchE2E** (8)
- `test_audit_records_after_dispatch`
- `test_background_dry_run_returns_immediately`
- `test_file_dry_run_e2e`
- `test_full_tool_inventory`
- `test_inline_dry_run_e2e`
- `test_invalid_project_returns_error`
- `test_metrics_after_dispatch`
- `test_project_flag_dry_run`

**TestMCPInputLimits** (3)
- `test_benchmark_too_many_models`
- `test_chain_too_many_steps`
- `test_prompt_too_large`

**TestRicherStatus** (4)
- `test_brief_status_minimal`
- `test_brief_status_no_tasks`
- `test_inline_has_counts`
- `test_status_has_counts`

**TestRondoRunFile** (6)
- `test_dry_run_returns_json`
- `test_invalid_file_returns_error`
- `test_max_budget_accepted`
- `test_project_validation`
- `test_returns_valid_json`
- `test_tilde_expansion`

**TestRondoRunStatus** (8)
- `test_background_status_has_task_progress`
- `test_brief_has_only_status_and_counts`
- `test_completed_has_per_task_status`
- `test_completed_has_task_output`
- `test_empty_returns_dispatches`
- `test_heartbeat_done_status`
- `test_heartbeat_ultra_compact`
- `test_unknown_id_returns_error`

### `test_mcp_tools.py` (42)

**TestAuditSummaryTool** (1)
- `test_returns_list`

**TestDispatchInfoTool** (3)
- `test_has_commands`
- `test_has_design_principles`
- `test_has_version`

**TestHealthTool** (4)
- `test_lightweight`
- `test_providers_up_field`
- `test_returns_api_status`
- `test_returns_dispatch_health`

**TestMcpResource** (3)
- `test_create_server_has_resource`
- `test_help_resource_has_example`
- `test_help_resource_returns_json`

**TestMetricsTool** (3)
- `test_has_cost_fields`
- `test_has_reliability_fields`
- `test_returns_json_string`

**TestRondoBenchmark** (2)
- `test_benchmark_ranks_by_speed`
- `test_benchmark_returns_json`

**TestRondoChain** (2)
- `test_chain_empty_steps`
- `test_chain_returns_json`

**TestRondoCost** (2)
- `test_cost_has_period`
- `test_cost_returns_json`

**TestRondoDiff** (3)
- `test_diff_empty_previous`
- `test_diff_returns_json`
- `test_diff_same_results`

**TestRondoExplain** (2)
- `test_explain_default_model_is_local`
- `test_explain_returns_json`

**TestRondoHistory** (3)
- `test_history_has_aggregate`
- `test_history_returns_json`
- `test_history_with_model_filter`

**TestRondoModels** (5)
- `test_cloud_providers_have_tiers`
- `test_models_has_recommendations`
- `test_models_lists_all_cloud_providers`
- `test_models_returns_json`
- `test_providers_have_routing`

**TestRondoRetry** (2)
- `test_retry_returns_json`
- `test_retry_unknown_dispatch_errors`

**TestRondoScheduleMCP** (2)
- `test_schedule_create_dry_run`
- `test_schedule_list`

**TestRondoSummarize** (2)
- `test_summarize_empty_tasks`
- `test_summarize_returns_json`

**TestRondoTemplates** (2)
- `test_template_has_fields`
- `test_templates_returns_list`

**TestSpoolConsumeMCP** (1)
- `test_empty_spool_returns_zero`

### `test_metrics.py` (18)

**TestCostMetrics** (3)
- `test_avg_cost`
- `test_cost_by_model`
- `test_total_cost`

**TestHealthStatus** (3)
- `test_green_when_healthy`
- `test_red_when_mostly_errors`
- `test_yellow_when_some_errors`

**TestLatencyMetrics** (2)
- `test_avg_duration`
- `test_max_duration`

**TestMetricsInTaskResult** (4)
- `test_dispatch_returns_metrics`
- `test_dry_run_includes_metrics`
- `test_error_dispatch_includes_metrics`
- `test_task_result_has_metrics_field`

**TestMetricsSerialization** (2)
- `test_empty_audit`
- `test_to_dict`

**TestModelComparison** (1)
- `test_dispatches_by_model`

**TestReliabilityMetrics** (2)
- `test_error_breakdown`
- `test_success_rate`

**TestTokenMetrics** (1)
- `test_total_tokens`

### `test_notify.py` (24)

**TestAppleScriptInjection** (2)
- `test_double_quote_escaped`
- `test_shell_command_not_executed`

**TestBudgetThreshold** (3)
- `test_budget_50_fires`
- `test_budget_75_fires`
- `test_budget_under_50_no_fire`

**TestCostSpike** (2)
- `test_fires_on_3x_cost`
- `test_silent_on_normal_cost`

**TestErrorRateThreshold** (2)
- `test_fires_when_above_50pct`
- `test_silent_when_below_threshold`

**TestLatencyThreshold** (3)
- `test_fires_when_above_threshold`
- `test_silent_when_below_threshold`
- `test_silent_when_insufficient_samples`

**TestNotifyConfig** (2)
- `test_custom_channels`
- `test_default_channels`

**TestNotifyDedup** (2)
- `test_dedup_blocks_repeat`
- `test_different_keys_both_fire`

**TestNotifyFailure** (1)
- `test_failure_notification`

**TestNotifyRoundComplete** (3)
- `test_file_notification`
- `test_macos_notification`
- `test_terminal_notification`

**TestQuietMode** (2)
- `test_quiet_keeps_file`
- `test_quiet_suppresses_terminal`

**TestRateLimitNotify** (2)
- `test_rate_limit_deduped`
- `test_rate_limit_fires`

### `test_parallel.py` (34)

**TestConflictDetection** (7)
- `test_conflicts_advisory_not_blocking`
- `test_conflicts_in_round_result`
- `test_detect_multiple_conflicts`
- `test_detect_single_conflict`
- `test_empty_files_modified`
- `test_no_conflicts_when_no_overlapping_files`
- `test_three_tasks_same_file`

**TestEmptyRound** (1)
- `test_empty_round_skipped`

**TestGatesInParallel** (2)
- `test_blocking_pregate_skips_tasks`
- `test_post_gates_run_after_parallel_tasks`

**TestParallelDeep** (6)
- `test_no_conflicts_clean`
- `test_req001_uses_thread_pool`
- `test_req004_results_collected_as_completed`
- `test_req005_conflict_detection`
- `test_req007_reports_speedup_ratio`
- `test_req008_single_failure_doesnt_crash_others`

**TestResultCollection** (2)
- `test_all_results_collected`
- `test_usage_collected_for_each_task`

**TestResultFormat** (4)
- `test_returns_round_result`
- `test_round_name_preserved`
- `test_task_results_are_task_result_type`
- `test_usage_are_dispatch_usage_type`

**TestSummaryStats** (4)
- `test_all_done_status`
- `test_all_error_status`
- `test_done_and_error_counts_in_summary`
- `test_timing_fields_populated`

**TestTaskIsolation** (3)
- `test_exception_in_dispatch_caught`
- `test_no_shared_state_mutation`
- `test_one_failure_doesnt_crash_others`

**TestThreadPoolUsage** (1)
- `test_uses_thread_pool_executor`

**TestThrottle** (2)
- `test_throttle_delay_between_submissions`
- `test_zero_throttle`

**TestWorkerConfig** (2)
- `test_workers_1_still_works`
- `test_workers_from_config`

### `test_preflight.py` (25)

**TestAuthCheck** (3)
- `test_api_auth_needs_key`
- `test_api_auth_with_key_passes`
- `test_max_auth_no_key_needed`

**TestCCVersionCheck** (3)
- `test_old_version_warns`
- `test_version_in_checks_when_available`
- `test_version_unavailable_warns`

**TestClaudeBinaryCheck** (2)
- `test_claude_found`
- `test_claude_missing`

**TestDiskSpaceCheck** (2)
- `test_enough_disk_space`
- `test_low_disk_space`

**TestGitCheck** (2)
- `test_git_available`
- `test_git_missing`

**TestNestedSessionCheck** (2)
- `test_claudecode_not_set`
- `test_claudecode_set`

**TestPreflightCache** (3)
- `test_cache_stores_version`
- `test_second_run_uses_cache`
- `test_version_change_invalidates`

**TestPreflightPerformance** (1)
- `test_completes_quickly`

**TestPreflightProviderHealth** (4)
- `test_exception_becomes_warning`
- `test_healthy_provider_in_checks`
- `test_no_providers_no_change`
- `test_unhealthy_provider_in_warnings`

**TestPreflightResult** (3)
- `test_green_status`
- `test_red_status`
- `test_yellow_status`

### `test_providers.py` (85)

**TestAdapterEmptyResponse** (3)
- `test_anthropic_empty_content`
- `test_chat_completions_empty_choices`
- `test_gemini_missing_candidates`

**TestAdapterErrorCodes** (6)
- `test_anthropic_429_returns_err_rate_limit`
- `test_anthropic_500_returns_err_provider_down`
- `test_chat_completions_401_returns_err_auth`
- `test_chat_completions_429_returns_err_rate_limit`
- `test_chat_completions_500_returns_err_provider_down`
- `test_gemini_401_returns_err_auth`

**TestAdapterHealthStrategy** (5)
- `test_anthropic_health_500_is_down`
- `test_anthropic_health_checks_reachability`
- `test_anthropic_health_network_error_is_down`
- `test_chat_completions_health_404_still_reachable`
- `test_chat_completions_health_500_is_down`

**TestAdapterKeyInvalidation** (4)
- `test_429_does_not_invalidate_key`
- `test_anthropic_401_invalidates_key`
- `test_chat_completions_401_invalidates_key`
- `test_gemini_403_invalidates_key`

**TestAnthropicAPIAdapter** (3)
- `test_adapter_exists`
- `test_dispatch_no_key_returns_error`
- `test_routing_anthropic_prefix`

**TestCLIProviderDispatch** (1)
- `test_cli_dispatch_ollama_dry_run`

**TestChatCompletionsAdapter** (5)
- `test_adapter_exists`
- `test_different_providers_same_adapter`
- `test_dispatch_no_key_returns_error`
- `test_health_no_key_returns_false`
- `test_returns_task_result`

**TestFinalizationGuard** (3)
- `test_cli_provider_path_uses_finalize`
- `test_mcp_provider_path_uses_finalize`
- `test_no_manual_audit_outcome_in_provider_paths`

**TestGeminiAdapter** (5)
- `test_adapter_exists`
- `test_dispatch_no_key_returns_error`
- `test_health_no_key_returns_false`
- `test_routing_gemini_prefix`
- `test_routing_gemini_pro`

**TestLoadProvidersConfig** (5)
- `test_load_empty_dict`
- `test_load_from_dict`
- `test_load_idempotent`
- `test_load_no_providers_key`
- `test_load_toml_data_always_merges`

**TestMCPProviderRouting** (2)
- `test_claude_model_uses_existing_path`
- `test_ollama_model_routes_to_adapter`

**TestOllamaAdapter** (3)
- `test_ollama_adapter_exists`
- `test_ollama_dispatch_returns_task_result`
- `test_ollama_models_returns_list`

**TestProviderAuditTrail** (1)
- `test_ollama_dispatch_creates_audit`

**TestProviderConfigWiring** (2)
- `test_cli_main_calls_load_providers`
- `test_mcp_server_calls_load_providers`

**TestProviderInterface** (3)
- `test_adapter_has_dispatch`
- `test_adapter_has_health`
- `test_adapter_has_models`

**TestProviderRouting** (10)
- `test_load_task_models_missing_file`
- `test_parse_model_empty`
- `test_parse_model_no_prefix`
- `test_recommend_model_config_override`
- `test_recommend_model_for_task`
- `test_route_claude_models`
- `test_route_local_prefix`
- `test_route_local_prefix_extracts_model`
- `test_route_ollama_models_legacy`
- `test_unknown_model_returns_none`

**TestRecommendReviewProviders** (6)
- `test_code_review_returns_two_providers`
- `test_config_override_wins`
- `test_count_limits_results`
- `test_default_two_minimum_for_review`
- `test_security_returns_three_providers`
- `test_unknown_task_falls_back_to_single`

**TestRondoSchedule** (2)
- `test_schedule_daily`
- `test_schedule_generates_plist`

**TestSafeParallel** (2)
- `test_safe_parallel_true`
- `test_task_has_safe_parallel`

**TestScheduleSafeguards** (1)
- `test_max_schedules_enforced`

**TestTierResolution** (13)
- `test_parse_model_exact_beats_tier`
- `test_parse_model_exact_model_unchanged`
- `test_parse_model_no_config_tier_passthrough`
- `test_parse_model_tier_default`
- `test_parse_model_tier_high`
- `test_parse_model_tier_low`
- `test_resolve_tier_default`
- `test_resolve_tier_high`
- `test_resolve_tier_low`
- `test_resolve_tier_openai`
- `test_resolve_tier_same_model`
- `test_resolve_tier_unknown_provider`
- `test_resolve_tier_unknown_tier`

### `test_report.py` (23)

**TestActionItems** (6)
- `test_all_skipped_shows_skipped_message`
- `test_blocked_tasks_listed`
- `test_failed_tasks_listed`
- `test_no_action_items_when_clean`
- `test_skipped_count_in_phase`
- `test_skipped_count_in_summary`

**TestAggregation** (2)
- `test_report_aggregates_all_phases`
- `test_report_returns_string`

**TestDatedFilename** (2)
- `test_file_contains_report`
- `test_save_to_dated_file`

**TestGrouping** (1)
- `test_each_phase_has_section`

**TestHealthIndicators** (3)
- `test_all_pass_health`
- `test_fail_health`
- `test_partial_health`

**TestReportTotals** (3)
- `test_total_duration`
- `test_total_errors`
- `test_total_tasks`

**TestRoundStats** (3)
- `test_duration_shown`
- `test_tasks_done_count`
- `test_tasks_failed_count`

**TestUsageSummary** (3)
- `test_total_cost_in_report`
- `test_total_tokens_in_report`
- `test_watchdog_count_in_report`

### `test_review_tiers.py` (4)

**(module-level)** (4)
- `test_merge_maps_anthropic_to_claude`
- `test_merge_no_config_returns_copy`
- `test_merge_overrides_from_toml`
- `test_merge_skips_disabled_provider`

### `test_runner.py` (41)

**TestAutoDetect** (2)
- `test_default_config_routes_to_parallel`
- `test_workers_1_uses_sequential`

**TestCircuitBreaker** (4)
- `test_different_errors_dont_trip_breaker`
- `test_skipped_tasks_have_circuit_breaker_reason`
- `test_success_resets_breaker`
- `test_three_consecutive_errors_trips_breaker`

**TestCircuitBreakerDeep** (2)
- `test_resets_on_success`
- `test_trips_after_3_consecutive_same_error`

**TestFileConflictDetection** (3)
- `test_detects_overlap`
- `test_no_conflict`
- `test_no_files_no_conflict`

**TestNotifyOnFailure** (1)
- `test_failure_triggers_notify`

**TestPostGates** (3)
- `test_post_gate_results_captured`
- `test_post_gates_run_after_tasks`
- `test_post_gates_skipped_when_pregate_blocks`

**TestPreGates** (4)
- `test_all_pregates_pass_tasks_run`
- `test_blocking_pregate_fails_skips_tasks`
- `test_non_blocking_pregate_fails_tasks_still_run`
- `test_pregate_results_in_round_result`

**TestResultSaving** (2)
- `test_results_saved_to_dir`
- `test_round_summary_saved`

**TestRoundTimeout** (2)
- `test_round_timeout_records_reason`
- `test_round_timeout_skips_remaining_tasks`

**TestRunRoundContract** (4)
- `test_default_config_when_none`
- `test_returns_round_result`
- `test_round_name_in_result`
- `test_timing_fields_populated`

**TestRunnerValidation** (4)
- `test_duplicate_tasks_returns_error`
- `test_invalid_round_returns_error`
- `test_invalid_task_returns_error`
- `test_valid_round_proceeds`

**TestSaveResultSafe** (1)
- `test_save_called_per_task`

**TestTaskOrchestration** (7)
- `test_all_error_status`
- `test_all_tasks_dispatched`
- `test_empty_round_skipped`
- `test_mixed_results_partial_status`
- `test_task_failure_doesnt_crash_others`
- `test_task_results_collected`
- `test_usage_collected`

**TestTaskStateUpdates** (2)
- `test_task_status_updated_after_dispatch`
- `test_task_status_updated_to_in_progress`

### `test_sanitize.py` (46)

**TestConfidenceScoring** (2)
- `test_exact_match_high_confidence`
- `test_heuristic_match_medium_confidence`

**TestCustomPatterns** (2)
- `test_custom_pattern_detected`
- `test_custom_pattern_plus_defaults`

**TestDefaultPatterns** (7)
- `test_aws_access_key`
- `test_default_patterns_list_exists`
- `test_high_entropy_base64`
- `test_password_assignment`
- `test_private_key_marker`
- `test_secret_key_env`
- `test_token_pattern`

**TestEdgeCases** (5)
- `test_empty_string`
- `test_multiline_private_key`
- `test_nested_dict_scrubbed`
- `test_none_parsed_result`
- `test_unicode_text`

**TestEnvVarStripping** (3)
- `test_dollar_home`
- `test_dollar_var_stripped`
- `test_home_tilde_stripped`

**TestFalsePositiveGuards** (7)
- `test_bearer_as_english_word_not_redacted`
- `test_bearer_with_real_long_token_still_redacted`
- `test_certificate_block_not_confused_with_private_key`
- `test_meta_references_not_redacted`
- `test_password_function_call_not_redacted`
- `test_password_quoted_literal_still_redacted`
- `test_short_prefixes_not_redacted`

**TestFilePathTruncation** (2)
- `test_basename_preserved`
- `test_home_dir_hidden`

**TestQuietMode** (2)
- `test_clean_text_empty_detections`
- `test_clean_text_sanitized_equals_original`

**TestRawPreservation** (1)
- `test_sanitize_text_returns_original`

**TestScanDetection** (4)
- `test_clean_text_returns_zero`
- `test_detects_api_key_assignment`
- `test_detects_bearer_token`
- `test_detects_multiple_secrets`

**TestScrubAudit** (3)
- `test_detection_has_line_number`
- `test_detection_has_pattern_name`
- `test_detection_never_contains_secret_value`

**TestScrubCount** (2)
- `test_secrets_found_count`
- `test_task_result_has_count`

**TestScrubOrder** (3)
- `test_original_not_mutated`
- `test_sanitize_task_result_scrubs_parsed_result`
- `test_sanitize_task_result_scrubs_raw_output`

**TestScrubbing** (3)
- `test_multiple_redactions`
- `test_private_key_redacted`
- `test_redaction_placeholder`

### `test_spikes.py` (8)

**TestCCFlagSpikes** (8)
- `test_cc_version_minimum`
- `test_permission_mode_has_dontask`
- `test_s1_bare_flag_exists`
- `test_s2_tools_flag_exists`
- `test_s6_max_budget_flag_exists`
- `test_s7_json_schema_flag_exists`
- `test_s8_system_prompt_flag_exists`
- `test_s9_rondo_can_load_round`

### `test_spool.py` (27)

**TestSpoolConsume** (7)
- `test_consume_deletes_files`
- `test_consume_empty_spool`
- `test_consume_file_rejects_path_traversal`
- `test_consume_one_by_filename`
- `test_consume_preserves_data`
- `test_consume_returns_results`
- `test_write_sanitizes_task_name`

**TestSpoolDirectory** (2)
- `test_req051_auto_create`
- `test_spool_dir_configurable`

**TestSpoolExport** (1)
- `test_export_returns_json_array`

**TestSpoolInputValidation** (2)
- `test_rejects_empty_task_name`
- `test_rejects_non_dict_result`

**TestSpoolList** (3)
- `test_list_empty_spool`
- `test_list_returns_entries`
- `test_list_sorted_newest_first`

**TestSpoolMorningReport** (2)
- `test_multiple_overnight_runs`
- `test_overnight_results_consumable`

**TestSpoolPermissions** (2)
- `test_spool_dir_created_700`
- `test_spool_files_600`

**TestSpoolResilience** (1)
- `test_write_to_readonly_dir_doesnt_crash`

**TestSpoolResultFunction** (1)
- `test_spool_result_writes`

**TestSpoolTTL** (3)
- `test_clean_all`
- `test_expired_files_cleaned`
- `test_fresh_files_kept`

**TestSpoolWrite** (3)
- `test_filename_format`
- `test_multiple_results`
- `test_write_creates_file`


## integration/ — Integration Tests — Multiple components together (180 tests)

### `test_examples.py` (61)

**TestExampleBuildRound** (18)
- `test_build_round_returns_round[round_caliber_fix.py]`
- `test_build_round_returns_round[round_code_review.py]`
- `test_build_round_returns_round[round_doc_sweep.py]`
- `test_build_round_returns_round[round_file_check.py]`
- `test_build_round_returns_round[round_hello.py]`
- `test_build_round_returns_round[round_multi_task.py]`
- `test_build_round_returns_round[round_refactor_audit.py]`
- `test_build_round_returns_round[round_security_audit.py]`
- `test_build_round_returns_round[round_test_generator.py]`
- `test_has_build_round[round_caliber_fix.py]`
- `test_has_build_round[round_code_review.py]`
- `test_has_build_round[round_doc_sweep.py]`
- `test_has_build_round[round_file_check.py]`
- `test_has_build_round[round_hello.py]`
- `test_has_build_round[round_multi_task.py]`
- `test_has_build_round[round_refactor_audit.py]`
- `test_has_build_round[round_security_audit.py]`
- `test_has_build_round[round_test_generator.py]`

**TestExampleCount** (4)
- `test_at_least_three_examples`
- `test_expected_spec_files_present`
- `test_overnight_example_present`
- `test_practical_examples_present`

**TestExampleImports** (10)
- `test_only_imports_engine[phases_overnight.py]`
- `test_only_imports_engine[round_caliber_fix.py]`
- `test_only_imports_engine[round_code_review.py]`
- `test_only_imports_engine[round_doc_sweep.py]`
- `test_only_imports_engine[round_file_check.py]`
- `test_only_imports_engine[round_hello.py]`
- `test_only_imports_engine[round_multi_task.py]`
- `test_only_imports_engine[round_refactor_audit.py]`
- `test_only_imports_engine[round_security_audit.py]`
- `test_only_imports_engine[round_test_generator.py]`

**TestExampleSize** (13)
- `test_all_examples_under_100_lines[phases_overnight.py]`
- `test_all_examples_under_100_lines[round_caliber_fix.py]`
- `test_all_examples_under_100_lines[round_code_review.py]`
- `test_all_examples_under_100_lines[round_doc_sweep.py]`
- `test_all_examples_under_100_lines[round_file_check.py]`
- `test_all_examples_under_100_lines[round_hello.py]`
- `test_all_examples_under_100_lines[round_multi_task.py]`
- `test_all_examples_under_100_lines[round_refactor_audit.py]`
- `test_all_examples_under_100_lines[round_security_audit.py]`
- `test_all_examples_under_100_lines[round_test_generator.py]`
- `test_spec_examples_under_50_lines[round_file_check.py]`
- `test_spec_examples_under_50_lines[round_hello.py]`
- `test_spec_examples_under_50_lines[round_multi_task.py]`

**TestOvernightExample** (5)
- `test_build_phases_returns_list_of_rounds`
- `test_has_build_phases`
- `test_phases_accept_parameter`
- `test_phases_are_ordered`
- `test_phases_escalate_models`

**TestPracticalExamples** (7)
- `test_code_review_structure`
- `test_doc_sweep_custom_files`
- `test_doc_sweep_structure`
- `test_refactor_audit_accepts_target`
- `test_refactor_audit_structure`
- `test_test_generator_accepts_parameters`
- `test_test_generator_structure`

**TestSpecExamplesAsFixtures** (4)
- `test_file_check_round_structure`
- `test_hello_round_structure`
- `test_multi_task_accepts_parameters`
- `test_multi_task_round_structure`

### `test_integration_dispatch_chain.py` (10)

**TestDispatchChainIntegration** (10)
- `test_budget_cap_fires_before_circuit_breaker_check`
- `test_config_hot_reload_is_thread_safe`
- `test_full_cost_accumulation_across_session`
- `test_full_mcp_chain_dry_run_happy_path`
- `test_full_mcp_chain_error_path_produces_valid_error_response`
- `test_multi_hop_fallback_first_hop_succeeds`
- `test_multi_hop_fallback_no_claude_fallback`
- `test_parallel_circuit_breaker_is_thread_safe`
- `test_parallel_dispatch_thread_safety_no_audit_corruption`
- `test_routing_is_deterministic_under_concurrent_calls`

### `test_integration_flow.py` (11)

**TestMasterDispatchFlow** (11)
- `test_atomic_write_survives_disk_error`
- `test_budget_cap_actually_fires_with_real_costs`
- `test_dead_code_wired_context_limit_enforced`
- `test_dead_code_wired_idempotency_returns_cache`
- `test_dead_code_wired_structured_log_emits_request_id`
- `test_intent_prompt_file_is_sanitized`
- `test_sanitize_before_audit_verified_with_both_paths`
- `test_sanitize_intent_and_outcome_both_covered`
- `test_schema_version_survives_full_flow`
- `test_successful_http_dispatch_full_pipeline`
- `test_tenant_isolation_across_audit_and_spool`

### `test_integration_observability.py` (10)

**TestObservabilityIntegration** (10)
- `test_audit_trail_distinct_dispatches_get_distinct_ids`
- `test_bind_request_id_nested_binds_preserve_outer`
- `test_get_request_id_returns_empty_outside_context`
- `test_outcome_sanitize_before_persistence`
- `test_reconcile_stuck_intents_closes_orphans`
- `test_request_id_generation_is_unique_per_call`
- `test_request_id_propagates_through_nested_log_events`
- `test_sanitize_idempotent_multiple_passes_safe`
- `test_sanitize_runs_before_audit_outcome_stores_scrubbed`
- `test_sanitize_text_handles_mixed_content_integration`

### `test_integration_reliability.py` (10)

**TestReliabilityIntegration** (10)
- `test_audit_trail_records_dispatches_while_breaker_is_open`
- `test_breaker_and_audit_together_maintain_tenant_isolation`
- `test_breaker_failure_resets_on_success`
- `test_breaker_isolates_providers`
- `test_breaker_opens_then_blocks_subsequent_dispatches`
- `test_breaker_persists_across_restart_via_isolated_file`
- `test_breaker_reopens_after_cooldown`
- `test_breaker_state_file_tolerates_corrupt_json`
- `test_empty_persist_file_is_handled`
- `test_flaky_provider_succeeds_within_threshold`

### `test_integration_rotation_costs.py` (5)

**TestRotationAndCosts** (5)
- `test_audit_rotation_during_active_dispatch_preserves_data`
- `test_cost_tracking_survives_atomic_write_round_trip`
- `test_http_adapter_chain_composition_via_retry_and_breaker`
- `test_partial_success_parallel_dispatch_records_all_outcomes`
- `test_timeout_error_record_flows_through_audit`

### `test_live.py` (23)

**TestAutoFnExecution** (3)
- `test_auto_fn_exception_caught`
- `test_auto_fn_failure_shown`
- `test_auto_fn_runs_and_shows_result`

**TestHumanInputInLive** (3)
- `test_context_data_in_live`
- `test_human_input_displayed`
- `test_no_human_input_no_display`

**TestLiveModeREQ100MustReqs** (5)
- `test_req061_live_in_current_session`
- `test_req062_one_task_at_a_time`
- `test_req065_same_round_definition`
- `test_req067_output_to_terminal`
- `test_req070_resume_from_last`

**TestPresentTask** (2)
- `test_presents_auto_task`
- `test_presents_interactive_task`

**TestRunLive** (6)
- `test_pre_gate_blocking`
- `test_progress_saved`
- `test_runs_all_tasks`
- `test_single_task`
- `test_single_task_out_of_range`
- `test_start_from_skips_earlier`

**TestTimeoutReqs** (3)
- `test_req074_task_timeout_default`
- `test_req075_round_timeout_default`
- `test_req077_timeout_produces_err_timeout`

**TestToolModeReqs** (1)
- `test_req083_tool_mode_none_ignores_allowed`

### `test_overnight.py` (50)

**TestEventLogDeep** (4)
- `test_corrupt_file_recovers`
- `test_max_entries_enforced`
- `test_no_path_no_save`
- `test_persist_and_reload`

**TestEventLogging** (5)
- `test_end_event_logged`
- `test_event_log_persistence`
- `test_phase_events_logged`
- `test_rolling_log_max_100`
- `test_start_event_logged`

**TestModeConfig** (4)
- `test_mode_selects_phases`
- `test_no_mode_runs_all_phases`
- `test_standard_mode`
- `test_unknown_mode_raises`

**TestOvernightEventLog** (2)
- `test_event_log_has_start_and_end`
- `test_event_log_has_timestamps`

**TestOvernightPhaseOrdering** (2)
- `test_phases_run_in_order`
- `test_req012_phase_failure_continues`

**TestOvernightResult** (6)
- `test_all_done_status`
- `test_all_skipped_status`
- `test_has_mode`
- `test_has_timing_fields`
- `test_has_total_cost`
- `test_mixed_done_skipped_is_partial`

**TestOvernightResults** (2)
- `test_result_has_cost`
- `test_result_has_timing`

**TestOvernightSpoolIntegration** (1)
- `test_overnight_writes_spool`

**TestPhaseIsolation** (4)
- `test_all_phases_fail_status_error`
- `test_mixed_phases_partial_status`
- `test_phase_exception_caught`
- `test_phase_failure_doesnt_block_next`

**TestPhaseList** (3)
- `test_accepts_phase_list`
- `test_empty_phases`
- `test_single_phase`

**TestPhaseSequencing** (1)
- `test_phases_execute_in_order`

**TestRateLimitBackoff** (1)
- `test_rate_limit_error_triggers_backoff`

**TestUsageGating** (7)
- `test_blocked_status_returns_blocked`
- `test_no_overage_continues`
- `test_overage_continue_action`
- `test_overage_pause_action`
- `test_overage_stop_action`
- `test_stop_action_ends_overnight`
- `test_usage_gate_logged`

**TestUsageGatingDeep** (6)
- `test_blocked_always_blocks`
- `test_no_overage_no_block_continues`
- `test_normal_status_continues`
- `test_overage_respects_config_continue`
- `test_overage_respects_config_pause`
- `test_overage_respects_config_stop`

**TestWatchdogResponse** (2)
- `test_watchdog_error_continues_to_next_phase`
- `test_watchdog_event_logged`


## e2e/ — End-to-End Tests — Full pipeline lifecycles (114 tests)

### `test_integration_e2e.py` (114)

**TestE2EAiHelp** (4)
- `test_ai_help_has_capabilities`
- `test_ai_help_has_commands`
- `test_ai_help_has_task_schema`
- `test_ai_help_valid_json`

**TestE2EAiHelpDeep** (5)
- `test_ai_help_config_has_all_options`
- `test_ai_help_dispatch_features`
- `test_ai_help_dispatch_models`
- `test_ai_help_examples`
- `test_ai_help_result_schema`

**TestE2EAllExampleRounds** (5)
- `test_round_caliber_fix_dry_run`
- `test_round_code_review_dry_run`
- `test_round_doc_sweep_dry_run`
- `test_round_refactor_audit_dry_run`
- `test_round_test_generator_dry_run`

**TestE2EAlwaysOnInfrastructure** (4)
- `test_audit_trail_exists_after_dispatch`
- `test_dispatch_id_always_available`
- `test_flaky_engine_always_works`
- `test_sanitize_always_runs`

**TestE2EAuditCLI** (6)
- `test_audit_cost`
- `test_audit_cost_json`
- `test_audit_failed`
- `test_audit_json`
- `test_audit_list`
- `test_audit_nonexistent_id`

**TestE2EAuditPipeline** (3)
- `test_audit_scrubs_secrets_in_prompt`
- `test_complete_audit_lifecycle`
- `test_crash_recovery`

**TestE2EAutoTask** (1)
- `test_auto_task_dry_run`

**TestE2EBadConfig** (4)
- `test_bad_toml_syntax`
- `test_empty_config_file`
- `test_invalid_enum_in_toml`
- `test_wrong_type_in_toml`

**TestE2ECLIFlags** (5)
- `test_run_with_all_flags`
- `test_run_with_bare_flag`
- `test_run_with_json_schema_auto`
- `test_run_with_max_budget`
- `test_run_with_model_flag`

**TestE2ECompleteWorkflow** (2)
- `test_workflow_history_json_to_analysis`
- `test_workflow_preflight_then_dry_run`

**TestE2EConfigOverrides** (2)
- `test_model_flag_overrides_default`
- `test_workers_flag`

**TestE2EDryRun** (3)
- `test_dry_run_no_subprocess_call`
- `test_dry_run_shows_skipped`
- `test_dry_run_works_inside_claude_code`

**TestE2EErrorHandling** (4)
- `test_invalid_python_file`
- `test_invalid_subcommand`
- `test_missing_build_round_function`
- `test_nonexistent_round_file`

**TestE2EExampleRounds** (3)
- `test_round_file_check_dry_run`
- `test_round_hello_dry_run`
- `test_round_multi_task_dry_run`

**TestE2EFlakyCLI** (4)
- `test_flaky_custom_threshold`
- `test_flaky_default`
- `test_flaky_json`
- `test_flaky_model_reliability`

**TestE2EFlakyPipeline** (4)
- `test_confidence_variance_unstable_prompt`
- `test_detect_flaky_task_from_history`
- `test_full_json_report`
- `test_model_comparison`

**TestE2EFullPipeline** (1)
- `test_pipeline_produces_all_artifacts`

**TestE2EGatedRound** (1)
- `test_gated_round_dry_run`

**TestE2EHelp** (1)
- `test_help_shows_commands`

**TestE2EHistory** (3)
- `test_history_expensive_sort`
- `test_history_json_valid`
- `test_history_shows_cost`

**TestE2EHistoryFilters** (3)
- `test_history_filter_model_nonexistent`
- `test_history_filter_model_sonnet`
- `test_history_json_has_records`

**TestE2EInit** (5)
- `test_init_creates_file`
- `test_init_file_is_valid_python`
- `test_init_file_runs_dry`
- `test_init_no_overwrite`
- `test_init_with_name`

**TestE2ELiveMode** (2)
- `test_live_shows_context_data`
- `test_live_shows_task`

**TestE2ELiveMultiTask** (2)
- `test_live_from_task_2`
- `test_live_single_task`

**TestE2EModelCostComparison** (1)
- `test_history_shows_model_breakdown`

**TestE2EMultiTaskRound** (1)
- `test_multi_task_dry_run_shows_all`

**TestE2EOvernightDryRun** (2)
- `test_overnight_dry_run`
- `test_overnight_generates_report`

**TestE2EPreflight** (3)
- `test_preflight_json_valid`
- `test_preflight_returns_green`
- `test_preflight_shows_cc_version`

**TestE2EPreflightDetails** (4)
- `test_preflight_json_has_all_fields`
- `test_preflight_shows_auth`
- `test_preflight_shows_disk_space`
- `test_preflight_shows_git`

**TestE2EProvidersCLI** (2)
- `test_providers_json_valid`
- `test_providers_returns_success`

**TestE2EReviewDryRun** (5)
- `test_review_dry_run_json`
- `test_review_dry_run_shows_file_info`
- `test_review_empty_file_fails`
- `test_review_missing_file_fails`
- `test_review_tier_flag`

**TestE2ERoundWithContextFiles** (1)
- `test_dry_run_with_context_files`

**TestE2ESanitizePipeline** (3)
- `test_clean_output_passes_through`
- `test_sanitize_realistic_ai_output`
- `test_sanitize_task_result_pipeline`

**TestE2ESpoolCLI** (4)
- `test_spool_clean_empty`
- `test_spool_consume_empty`
- `test_spool_list_empty`
- `test_spool_list_json`

**TestE2ESpoolCLIReq101** (5)
- `test_spool_clean`
- `test_spool_export`
- `test_spool_help`
- `test_spool_list`
- `test_spool_list_json`

**TestE2ETraceability** (2)
- `test_traceability_json`
- `test_traceability_runs`

**TestE2EVersion** (1)
- `test_version_output`

**TestE2EVersionConsistency** (1)
- `test_installed_matches_repo_version`

**TestRealDispatchSmoke** (2)
- `test_real_claude_dispatch`
- `test_real_ollama_dispatch`


## pat/ — Product Acceptance Tests — Real behavior, zero mocking (133 tests)

### `test_mcp_integration.py` (20)

**TestAuditPipeline** (1)
- `test_audit_file_is_valid_json`

**TestMCPIntegration** (4)
- `test_agent_via_mcp_in_session`
- `test_inline_returns_instantly`
- `test_inline_via_mcp`
- `test_no_prompt_no_file_is_error`

**TestMCPQueryTools** (12)
- `test_audit_summary_returns_json`
- `test_cost_returns_json`
- `test_diff_empty_returns_json`
- `test_dispatch_info_returns_version`
- `test_health_returns_status`
- `test_history_returns_json`
- `test_metrics_returns_json`
- `test_models_returns_list`
- `test_run_status_no_id_returns_json`
- `test_schedule_list_returns_json`
- `test_spool_consume_returns_json`
- `test_templates_returns_json`

**TestMCPToolResponseValidity** (1)
- `test_all_query_tools_return_valid_json`

**TestSanitizeIntegrity** (2)
- `test_normal_text_not_mangled`
- `test_real_api_key_pattern_redacted`

### `test_pipeline_observability.py` (30)

**TestPipelineObservability** (30)
- `test_agent_plan_has_schema_version`
- `test_all_plans_have_schema_version`
- `test_bind_request_id_explicit`
- `test_bind_request_id_nested`
- `test_bind_request_id_propagates`
- `test_config_hot_reload`
- `test_context_limit_1m_models`
- `test_context_limit_check_over_limit`
- `test_context_limit_check_within_limit`
- `test_context_limit_unknown_model_uses_default`
- `test_dispatch_task_emits_structured_logs_with_request_id`
- `test_dispatch_task_respects_existing_request_id`
- `test_idempotency_cache_crosses_process_boundary`
- `test_idempotency_cache_expires`
- `test_idempotency_cache_persists_across_memory_wipe`
- `test_idempotency_cache_returns_cached`
- `test_idempotency_cache_thread_safe`
- `test_idempotency_key_stable`
- `test_idempotency_ttl_honored_in_file_layer`
- `test_request_id_generation`
- `test_routing_background_with_unknown_model`
- `test_routing_case_sensitive_for_claude_models`
- `test_routing_inline_preserves_project_in_all_engines`
- `test_routing_new_suffix_with_provider_prefix`
- `test_routing_whitespace_in_model_is_stripped`
- `test_structured_logger_emits_json`
- `test_structured_logger_thread_isolation`
- `test_token_estimate_empty_string`
- `test_token_estimate_mixed_language`
- `test_token_estimate_non_english_cjk`

### `test_pipeline_reliability.py` (19)

**TestPipelineReliability** (19)
- `test_adapter_exception_path_calls_finalize`
- `test_atomic_write_helper_creates_file`
- `test_atomic_write_no_tmp_leftover`
- `test_audit_log_auto_rotates_at_size_limit`
- `test_audit_result_file_is_atomic`
- `test_circuit_breaker_expired_state_not_restored`
- `test_circuit_breaker_isolates_providers`
- `test_circuit_breaker_opens_after_threshold`
- `test_circuit_breaker_persists_across_restart`
- `test_circuit_breaker_recovers_on_success`
- `test_dry_run_provider_path_calls_finalize`
- `test_finalize_failure_does_not_lose_result`
- `test_multi_hop_fallback_cycle_detection`
- `test_multi_hop_fallback_walks_chain`
- `test_provider_down_path_calls_finalize`
- `test_reconcile_stuck_intents`
- `test_retry_http_exhausts_attempts`
- `test_retry_http_no_retry_on_401`
- `test_retry_http_retries_on_500`

### `test_pipeline_security.py` (18)

**TestPipelineSecurity** (18)
- `test_audit_dir_tenant_isolation`
- `test_budget_cap_blocks_http_dispatch`
- `test_invalidate_only_affects_current_tenant`
- `test_key_cache_tenant_isolation`
- `test_key_cache_thread_safe`
- `test_no_budget_cap_no_blocking`
- `test_sanitize_detects_anthropic_specific`
- `test_sanitize_detects_aws_temp_key`
- `test_sanitize_detects_github_pat`
- `test_sanitize_detects_gitlab_pat`
- `test_sanitize_detects_google_api_key`
- `test_sanitize_detects_jwt`
- `test_sanitize_detects_slack_tokens`
- `test_sanitize_runs_before_audit_outcome`
- `test_subprocess_footgun_guard_blocks_auth_api`
- `test_subprocess_footgun_guard_blocks_in_session`
- `test_subprocess_footgun_opt_in_bypass`
- `test_subprocess_footgun_override_emits_warning`

### `test_real_providers.py` (7)

**TestBackgroundDispatch** (3)
- `test_background_dry_run_returns_id`
- `test_run_status_brief`
- `test_run_status_heartbeat`

**TestInSessionBehavior** (4)
- `test_cloud_works_everywhere`
- `test_inline_works_everywhere`
- `test_session_detection_matches_environment`
- `test_sonnet_routing_matches_context`

### `test_routing.py` (39)

**TestPublicAccessors** (4)
- `test_claude_models`
- `test_legacy_ollama`
- `test_not_claude`
- `test_not_ollama`

**TestResponseShape** (6)
- `test_agent_has_kind`
- `test_agent_has_note`
- `test_all_plans_have_status`
- `test_every_response_has_engine`
- `test_http_has_provider`
- `test_inline_has_kind`

**TestRouterParity** (3)
- `test_claude_models_parity`
- `test_legacy_ollama_parity`
- `test_prefixed_providers_parity`

**TestRoutingBackground** (3)
- `test_background_empty_model`
- `test_background_gemini`
- `test_background_sonnet`

**TestRoutingClaude** (7)
- `test_haiku_in_session`
- `test_haiku_outside_session`
- `test_new_suffix_forces_subprocess`
- `test_opus_in_session`
- `test_sonnet_1m_in_session`
- `test_sonnet_in_session`
- `test_sonnet_outside_session`

**TestRoutingCloudProviders** (7)
- `test_anthropic_api`
- `test_gemini`
- `test_gemini_tier`
- `test_grok`
- `test_local_ollama`
- `test_mistral`
- `test_openai`

**TestRoutingError** (2)
- `test_error_has_reason`
- `test_unknown_model`

**TestRoutingInline** (3)
- `test_empty_model`
- `test_empty_model_preserves_project`
- `test_empty_model_preserves_prompt`

**TestRoutingLegacyOllama** (4)
- `test_deepseek`
- `test_llama`
- `test_phi`
- `test_qwen`


## chaos/ — Chaos Tests — Failure injection (15 tests)

### `test_chaos.py` (7)

**TestConfigDisappears** (1)
- `test_missing_config_uses_defaults`

**TestCorruptAudit** (1)
- `test_corrupt_jsonl_doesnt_crash_history`

**TestDiskFull** (1)
- `test_spool_write_failure_doesnt_crash_overnight`

**TestMalformedOutput** (1)
- `test_malformed_json_gracefully_handled`

**TestPartialProviderOutage** (1)
- `test_health_shows_partial_when_one_down`

**TestRateLimitStorm** (1)
- `test_circuit_breaker_trips_after_3_consecutive`

**TestSubprocessCrash** (1)
- `test_subprocess_oserror_becomes_error_result`

### `test_property.py` (8)

**TestConfigValidationProperty** (1)
- `test_validation_never_crashes`

**TestErrorClassificationProperty** (2)
- `test_always_returns_err_code`
- `test_recovery_exists_for_all_codes`

**TestErrorPayloadProperty** (1)
- `test_construction_never_crashes`

**TestJsonExtractionProperty** (3)
- `test_binary_garbage_never_crashes`
- `test_never_crashes_on_arbitrary_text`
- `test_valid_json_shapes_return_dict_or_none`

**TestParseModelProperty** (1)
- `test_never_crashes_on_arbitrary_model`


## conventions/ — Convention Tests — Style/layering/security rules (31 tests)

### `test_conventions.py` (31)

**TestAdapterContract** (2)
- `test_adapter_contract_methods`
- `test_all_adapters_inherit_from_base`

**TestCommentConvention** (1)
- `test_comment_convention_ratio`

**TestCyclomaticComplexity** (1)
- `test_function_complexity`

**TestDocSpecSync** (3)
- `test_ai_help_tool_count_matches`
- `test_cli_command_count_matches`
- `test_mcp_tool_count_matches`

**TestErrorHandlingInCli** (2)
- `test_cmd_overnight_has_error_handling`
- `test_cmd_run_has_error_handling`

**TestImportLayering** (1)
- `test_import_layers_enforced`

**TestMgHSignature** (1)
- `test_all_files_have_signature`

**TestModuleDocstrings** (1)
- `test_all_modules_have_docstrings`

**TestNoBarePrints** (1)
- `test_no_bare_print_in_library`

**TestNoCircularImports** (1)
- `test_all_modules_import_cleanly`

**TestNoHardcodedKeys** (1)
- `test_no_hardcoded_keys_in_source`

**TestNoHardcodedSecrets** (1)
- `test_no_api_keys_in_source`

**TestNoHttpUrls** (1)
- `test_no_plain_http_api_calls`

**TestNoMutableDefaultArgs** (1)
- `test_no_mutable_defaults`

**TestNoSQLite** (1)
- `test_no_sqlite3_in_source`

**TestNoShellTrue** (1)
- `test_no_shell_true_in_source`

**TestNoTodoFixmeHack** (1)
- `test_no_todo_markers`

**TestNoWildcardImports** (1)
- `test_no_wildcard_imports`

**TestPublicFunctionDocstrings** (1)
- `test_public_functions_have_docstrings`

**TestPublicFunctionTypeAnnotations** (1)
- `test_public_functions_have_return_type`

**TestSanitizeScrubsKeys** (2)
- `test_api_key_scrubbed`
- `test_bearer_token_scrubbed`

**TestSpdxHeaders** (2)
- `test_spdx_copyright`
- `test_spdx_license`

**TestSpecReferences** (1)
- `test_source_modules_reference_specs`

**TestTestSpecReferences** (1)
- `test_test_modules_reference_ver001`

**TestWriteTextEncoding** (1)
- `test_write_text_has_encoding`


