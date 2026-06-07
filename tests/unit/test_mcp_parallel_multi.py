# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Multi-review, parallel dispatch, disk-based retry, cloud dispatch features.

Split from test_mcp.py in RONDO-207 — original file was 1802 lines
(above best-practice range). This file focuses on: parallel + multi-review.

VER-001: Product acceptance / unit test coverage.
"""

import json

# -- ──────────────────────────────────────────────────────────────
# --  IFS-104 req 003 — Query tools
# -- ──────────────────────────────────────────────────────────────


class TestMultiReview:
    """REQ-109 req 033: multi-provider review tool."""

    def test_dry_run_returns_skipped(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["local:qwen2.5:32b", "gemini:gemini-2.5-flash"]',
                dry_run=True,
            )
        )
        assert result["status"] == "done"
        assert result["provider_count"] == 2
        assert all(p["status"] == "skipped" for p in result["per_provider"])
        assert result["total_cost_usd"] == 0

    def test_default_providers_on_empty(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="Review this", providers="[]", dry_run=True))
        assert result["provider_count"] == 3
        providers = [p["provider"] for p in result["per_provider"]]
        assert "local:qwen2.5:32b" in providers
        assert "gemini:gemini-2.5-flash" in providers
        assert "grok:grok-3" in providers

    def test_non_prefixed_provider_models_are_normalized(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["gemini-2.5-flash", "gpt-4o-mini", "grok-3"]',
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        assert "gemini:gemini-2.5-flash" in providers
        assert "openai:gpt-4o-mini" in providers
        assert "grok:grok-3" in providers

    def test_legacy_local_model_gets_local_prefix(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="Review this code", providers='["qwen2.5:32b"]', dry_run=True))
        providers = [p["provider"] for p in result["per_provider"]]
        assert providers == ["local:qwen2.5:32b"]

    def test_bare_provider_names_resolve_via_default_tier(self) -> None:
        """Bare provider names resolve via the default tier — RONDO-287 regression.

        Bare names like 'gemini' used to produce 'gemini:gemini' (HTTP 404).
        Must resolve via the tier parameter.
        """
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["gemini", "grok", "mistral"]',
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        ## tier defaults to "high" for multi_review (deep reviews need quality).
        assert "gemini:gemini-2.5-pro" in providers, f"got {providers}"
        assert "grok:grok-3" in providers, f"got {providers}"
        assert "mistral:mistral-large-latest" in providers, f"got {providers}"
        ## RONDO-287 guard: mangled forms MUST NOT appear.
        assert "gemini:gemini" not in providers
        assert "grok:grok" not in providers

    def test_bare_provider_names_with_tier_default(self) -> None:
        """Bare names + explicit tier='default' resolves to mid-tier models."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["gemini", "grok"]',
                tier="default",
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        assert "gemini:gemini-2.5-flash" in providers
        assert "grok:grok-3" in providers

    def test_bare_provider_names_with_tier_low(self) -> None:
        """Bare names + explicit tier='low' resolves to cheap models."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["openai"]',
                tier="low",
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        assert providers == ["openai:gpt-4o-mini"]

    def test_explicit_models_ignore_tier(self) -> None:
        """If user passes explicit provider:model, tier is ignored (no override)."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["gemini:gemini-2.5-flash", "grok:grok-3"]',
                tier="high",  ## Should NOT upgrade explicit gemini-2.5-flash to -pro
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        assert "gemini:gemini-2.5-flash" in providers
        assert "gemini:gemini-2.5-pro" not in providers

    def test_mixed_bare_and_explicit_both_normalize(self) -> None:
        """Bare and explicit names can be mixed in one call — both resolve correctly."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Review this code",
                providers='["gemini", "grok:grok-3"]',
                tier="high",
                dry_run=True,
            )
        )
        providers = [p["provider"] for p in result["per_provider"]]
        assert "gemini:gemini-2.5-pro" in providers  ## bare resolved via tier
        assert "grok:grok-3" in providers  ## explicit unchanged

    def test_invalid_json_returns_error(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="test", providers="not json"))
        assert result["status"] == "error"

    def test_too_many_providers_rejected(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        many = json.dumps([f"provider{i}" for i in range(15)])
        result = json.loads(rondo_multi_review(prompt="test", providers=many))
        assert result["status"] == "error"
        assert "ERR_INPUT_TOO_LARGE" in result.get("code", "")

    def test_prompt_truncated_in_response(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        long_prompt = "x" * 500
        result = json.loads(rondo_multi_review(prompt=long_prompt, providers="[]", dry_run=True))
        assert len(result["prompt"]) <= 200

    def test_empty_prompt_rejected(self) -> None:
        """REQ-109 req 080: empty prompt returns ERR_INVALID_INPUT."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="", providers="[]", dry_run=False))
        assert result["status"] == "error"
        assert result["code"] == "ERR_INVALID_INPUT"

    def test_whitespace_prompt_rejected(self) -> None:
        """REQ-109 req 080: whitespace-only prompt returns ERR_INVALID_INPUT."""
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(rondo_multi_review(prompt="   \n  ", providers="[]", dry_run=False))
        assert result["status"] == "error"
        assert result["code"] == "ERR_INVALID_INPUT"

    def test_provider_failure_surfaces_error_code_and_message(self) -> None:
        """RONDO-209 #248/#250: per-provider results include error_code + error_message.

        Before the fix, multi_review only returned status/output/cost/duration.
        Callers saw 'partial empty' with no idea WHY (HTTP 503? rate limit? auth?).
        Now the per-provider dict includes error_code + error_message.
        """
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        # -- Mock rondo_run_file to return a TaskResult-like error structure
        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            return json.dumps(
                {
                    "status": "partial",
                    "tasks": [
                        {
                            "task_name": "test",
                            "status": "error",
                            "error_code": "ERR_PROVIDER_DOWN",
                            "error_message": "Gemini HTTP 503: Service Unavailable",
                            "raw_output": "",
                            "duration_sec": 4.5,
                            "cost_usd": 0.0,
                        }
                    ],
                    "total_cost_usd": 0.0,
                }
            )

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(
                rondo_multi_review(prompt="review", providers='["gemini:gemini-2.5-pro"]', dry_run=False)
            )

        per_provider = result["per_provider"]
        assert len(per_provider) == 1
        provider_result = per_provider[0]

        # -- #248/#250: error_code and error_message must be present
        assert "error_code" in provider_result, "#248: error_code field missing"
        assert "error_message" in provider_result, "#248: error_message field missing"
        assert provider_result["error_code"] == "ERR_PROVIDER_DOWN"
        assert "503" in provider_result["error_message"], (
            f"#248: error_message must contain HTTP detail, got: {provider_result['error_message']!r}"
        )

    def test_provider_retry_on_transient_failure(self) -> None:
        """RONDO-209 #248/#250: retryable errors get one serial retry attempt.

        Pattern: parallel dispatch hits 503, serial retry afterward succeeds
        because the upstream throttle was triggered by concurrent siblings.
        """
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_count = [0]

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                # -- First call: simulate 503
                return json.dumps(
                    {
                        "status": "partial",
                        "tasks": [
                            {
                                "task_name": "t",
                                "status": "error",
                                "error_code": "ERR_PROVIDER_DOWN",
                                "error_message": "Gemini HTTP 503",
                                "raw_output": "",
                                "duration_sec": 4.0,
                                "cost_usd": 0.0,
                            }
                        ],
                        "total_cost_usd": 0.0,
                    }
                )
            # -- Second call (serial retry): succeeds
            return json.dumps(
                {
                    "status": "done",
                    "tasks": [
                        {
                            "task_name": "t",
                            "status": "done",
                            "raw_output": "Real review content here.",
                            "duration_sec": 8.0,
                            "cost_usd": 0.001,
                            "error_code": None,
                            "error_message": None,
                        }
                    ],
                    "total_cost_usd": 0.001,
                }
            )

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(
                rondo_multi_review(prompt="review", providers='["gemini:gemini-2.5-pro"]', dry_run=False)
            )

        # -- Both calls should have happened (parallel + serial retry)
        assert call_count[0] == 2, f"#248: expected 2 calls (initial + retry), got {call_count[0]}"

        per_provider = result["per_provider"]
        provider_result = per_provider[0]

        # -- Final state should be the SUCCESSFUL retry
        assert provider_result["status"] == "done", (
            f"#248: retry should have succeeded, got status={provider_result['status']}"
        )
        assert provider_result["output"] == "Real review content here."
        assert provider_result.get("attempt") == 2, (
            f"#248: attempt should be 2 after retry, got {provider_result.get('attempt')}"
        )

    def test_non_retryable_error_does_not_retry(self) -> None:
        """RONDO-209 #248: ERR_AUTH (400-class) should NOT retry.

        Only ERR_PROVIDER_DOWN and ERR_RATE_LIMIT (transient/throttle errors)
        warrant a retry. Auth failures, validation errors, etc. should fail
        immediately without burning more API quota.
        """
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_count = [0]

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            call_count[0] += 1
            return json.dumps(
                {
                    "status": "partial",
                    "tasks": [
                        {
                            "task_name": "t",
                            "status": "error",
                            "error_code": "ERR_AUTH",
                            "error_message": "Invalid API key",
                            "raw_output": "",
                            "duration_sec": 0.5,
                            "cost_usd": 0.0,
                        }
                    ],
                    "total_cost_usd": 0.0,
                }
            )

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            rondo_multi_review(prompt="review", providers='["openai:gpt-4.1"]', dry_run=False)

        # -- Only ONE call (no retry for auth errors)
        assert call_count[0] == 1, f"#248: ERR_AUTH should NOT trigger retry, got {call_count[0]} calls"


class TestParallelDispatch:
    """REQ-109 req 052: multi_review dispatches concurrently."""

    def test_parallel_preserves_provider_order(self) -> None:
        """Results come back in same order as input providers."""
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_order: list[str] = []

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            call_order.append(model)
            return json.dumps(
                {
                    "status": "done",
                    "tasks": [{"raw_output": f"Review from {model}", "duration_sec": 0.1}],
                    "total_cost_usd": 0,
                }
            )

        providers = '["provider_a:model_a", "provider_b:model_b", "provider_c:model_c"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(rondo_multi_review(prompt="test", providers=providers, dry_run=False))

        # -- Results must be in original order regardless of thread completion order
        result_providers = [r["provider"] for r in result["per_provider"]]
        assert result_providers == ["provider_a:model_a", "provider_b:model_b", "provider_c:model_c"]

    def test_parallel_one_failure_others_succeed(self) -> None:
        """REQ-109 req 088: one thread failure doesn't crash others."""
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        call_count = 0

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if "bad" in model:
                msg = "Simulated failure"
                raise ConnectionError(msg)
            return json.dumps(
                {"status": "done", "tasks": [{"raw_output": "OK", "duration_sec": 0.1}], "total_cost_usd": 0}
            )

        providers = '["good:model_a", "bad:model_b", "good:model_c"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(rondo_multi_review(prompt="test", providers=providers, dry_run=False))

        # -- All 3 dispatched
        assert call_count == 3
        # -- 2 succeeded, 1 failed
        statuses = [r["status"] for r in result["per_provider"]]
        assert statuses.count("done") == 2
        assert statuses.count("error") == 1

    def test_parallel_uses_threads(self) -> None:
        """Verify ThreadPoolExecutor is used (not sequential loop)."""
        import threading
        from unittest.mock import patch

        from rondo.mcp_server import rondo_multi_review

        threads_seen: set[int] = set()

        def mock_run_file(prompt: str = "", model: str = "", **kwargs: object) -> str:
            threads_seen.add(threading.current_thread().ident)
            import time

            time.sleep(0.05)  # force thread pool to use multiple workers
            return json.dumps(
                {"status": "done", "tasks": [{"raw_output": "OK", "duration_sec": 0.1}], "total_cost_usd": 0}
            )

        providers = '["a:m1", "b:m2", "c:m3"]'
        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            rondo_multi_review(prompt="test", providers=providers, dry_run=False)

        # -- With 3 providers, should use multiple threads (not all on main thread)
        assert len(threads_seen) >= 2, f"Expected multiple threads, got {len(threads_seen)}"


class TestDiskBasedRetry:
    """RONDO-106: retry persists to disk and loads across sessions."""

    def test_save_only_on_failures(self, tmp_path, monkeypatch) -> None:
        """Only save retry file when there are failed tasks."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result

        # -- Success result: no retry file
        success = {"tasks": [{"name": "t1", "status": "done"}]}
        _save_background_result("disp-ok", success)
        retry_dir = tmp_path / "retry"
        assert not (retry_dir / "disp-ok.json").exists()

        # -- Failure result: retry file created
        failure = {"tasks": [{"name": "t1", "status": "error", "error_message": "timeout"}]}
        _save_background_result("disp-fail", failure)
        assert (retry_dir / "disp-fail.json").exists()

    def test_load_from_disk(self, tmp_path, monkeypatch) -> None:
        """Load a retry record from disk when not in memory."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _load_background_result, _save_background_result

        failure = {"tasks": [{"name": "t1", "status": "error"}], "dispatch_id": "disp-123"}
        _save_background_result("disp-123", failure)
        loaded = _load_background_result("disp-123")
        assert loaded is not None
        assert loaded["dispatch_id"] == "disp-123"

    def test_load_missing_returns_none(self, tmp_path, monkeypatch) -> None:
        """Missing dispatch_id returns None, not crash."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _load_background_result

        assert _load_background_result("nonexistent") is None

    def test_retry_checks_disk(self, tmp_path, monkeypatch) -> None:
        """rondo_retry falls back to disk when not in memory."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result, rondo_retry

        # -- Save a failure to disk
        failure = {
            "tasks": [
                {"name": "scan", "status": "error", "error_message": "timeout", "model": "sonnet"},
            ],
            "dispatch_id": "disk-retry-1",
        }
        _save_background_result("disk-retry-1", failure)

        # -- rondo_retry should find it on disk (not in _background_results)
        result = json.loads(rondo_retry("disk-retry-1", model="haiku"))
        ## -- It will try to dispatch (which may fail in test env) but
        ## -- the point is it FOUND the dispatch, not "Unknown dispatch_id"
        assert result.get("status") != "error" or "Unknown dispatch_id" not in result.get("error", "")

    def test_prune_old_retry_files(self, tmp_path, monkeypatch) -> None:
        """Max 50 retry files — oldest pruned."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.mcp_server import _save_background_result

        failure = {"tasks": [{"name": "t", "status": "error"}]}
        # -- Create 55 retry files
        for i in range(55):
            _save_background_result(f"disp-{i:03d}", failure)

        retry_dir = tmp_path / "retry"
        files = list(retry_dir.glob("*.json"))
        assert len(files) <= 50


def _write_cloud_config(tmp_path, monkeypatch) -> None:
    """RONDO-341: hermetic cloud config via $RONDO_CONFIG.

    The profile tests used to pass ONLY on machines where the developer's
    personal ~/.rondo/config.toml defined profiles (the RONDO-300 bug
    class) — a fresh Linux container exposed them.
    """
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[cloud.profiles.review]\n"
        'providers = ["gemini", "grok"]\n'
        "[cloud.profiles.coding]\n"
        'providers = ["gemini"]\n'
        "[cloud.profiles.rondo341_hermetic]\n"
        'providers = ["gemini"]\n'
        "[providers.gemini]\n"
        "enabled = true\n"
        'default_model = "gemini-2.5-flash"\n'
        "[providers.grok]\n"
        "enabled = true\n"
        'default_model = "grok-3"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("RONDO_CONFIG", str(cfg))


class TestCloudDispatch:
    """REQ-109 reqs 046-063: cloud dispatch with profiles, tiers, cost caps."""

    def test_dry_run_returns_cloud_metadata(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Review this", dry_run=True))
        assert result["status"] == "done"
        assert "cloud" in result
        assert result["cloud"]["tier"] == "default"
        assert result["cloud"]["count_requested"] == 2

    def test_cloud_honors_rondo_config_env(self, tmp_path, monkeypatch) -> None:
        """RONDO-341: rondo_cloud resolves config via discover_config_path().

        Chain is $RONDO_CONFIG → XDG → legacy, not a hardcoded ~/.rondo path.

        The profile name exists ONLY in the fixture config — if this test
        passes, rondo_cloud read $RONDO_CONFIG; a developer's live
        ~/.rondo/config.toml cannot fake the green.
        """
        from rondo.mcp_tools import rondo_cloud

        _write_cloud_config(tmp_path, monkeypatch)
        result = json.loads(rondo_cloud(prompt="x", profile="rondo341_hermetic", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "rondo341_hermetic"

    def test_profile_review(self, tmp_path, monkeypatch) -> None:
        from rondo.mcp_tools import rondo_cloud

        _write_cloud_config(tmp_path, monkeypatch)
        result = json.loads(rondo_cloud(prompt="Review this", profile="review", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "review"

    def test_profile_coding(self, tmp_path, monkeypatch) -> None:
        from rondo.mcp_tools import rondo_cloud

        _write_cloud_config(tmp_path, monkeypatch)
        result = json.loads(rondo_cloud(prompt="Fix this", profile="coding", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "coding"

    def test_invalid_profile_returns_error(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", profile="nonexistent", dry_run=True))
        assert result["status"] == "error"
        assert "ERR_INVALID_PROFILE" in result.get("code", "")

    def test_count_override(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", count=3, dry_run=True))
        assert result["cloud"]["count_requested"] == 3

    def test_count_exceeds_max(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", count=10, dry_run=True))
        assert result["status"] == "error"
        assert "ERR_INPUT_TOO_LARGE" in result.get("code", "")

    def test_tier_high(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", tier="high", dry_run=True))
        assert result["cloud"]["tier"] == "high"

    def test_tier_low(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", tier="low", dry_run=True))
        assert result["cloud"]["tier"] == "low"

    def test_estimated_cost_in_metadata(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="test", dry_run=True))
        assert "estimated_cost_usd" in result["cloud"]
        assert result["cloud"]["estimated_cost_usd"] >= 0


class TestCostEstimatorCalibration:
    """RONDO-295 / Finding #278: calibrated cost estimator using real pricing.

    The old estimator was a flat tier_cost_factor x provider count — off by
    ~9x on typical prompts (blocked legit work) and 10x under on huge Opus
    prompts (let catastrophic spend through). Now uses compute_cost_usd
    against the real per-model pricing table.
    """

    def test_small_prompt_cheap_four_providers(self) -> None:
        # -- 4K-char prompt x 4 default providers should be pennies, not $0.60
        from rondo.mcp_tools import _estimate_dispatch_cost

        provider_models = [
            "gemini:gemini-2.5-flash",
            "grok:grok-3-mini",
            "mistral:mistral-medium-latest",
            "openai:gpt-4.1-mini",
        ]
        prompt = "x" * 4000  # -- ~1000 input tokens
        cost = _estimate_dispatch_cost(provider_models, prompt, "default")
        assert cost < 0.15, f"4-provider default on 4K prompt should be <$0.15, got ${cost:.4f}"

    def test_opus_huge_prompt_expensive(self) -> None:
        # -- 100K-char Opus x 4 high should exceed $1 — catches the catastrophic case
        from rondo.mcp_tools import _estimate_dispatch_cost

        provider_models = [
            "anthropic:claude-opus-4-6",
            "anthropic:claude-opus-4-6",
            "anthropic:claude-opus-4-6",
            "anthropic:claude-opus-4-6",
        ]
        prompt = "x" * 100_000  # -- ~25K tokens
        cost = _estimate_dispatch_cost(provider_models, prompt, "high")
        assert cost > 1.50, f"4x Opus on 100K prompt should exceed $1.50, got ${cost:.4f}"

    def test_bare_provider_name_fallback(self) -> None:
        # -- Bare "openai" (no :model) uses _DEFAULT_COST, doesn't crash
        from rondo.mcp_tools import _estimate_dispatch_cost

        cost = _estimate_dispatch_cost(["openai"], "short", "default")
        assert cost > 0
        assert cost < 0.01

    def test_empty_prompt_no_crash(self) -> None:
        from rondo.mcp_tools import _estimate_dispatch_cost

        cost = _estimate_dispatch_cost(["gemini:gemini-2.5-flash"], "", "default")
        assert cost >= 0

    def test_safety_margin_is_applied(self) -> None:
        # -- Estimate should be 1.3x raw compute_cost_usd
        from rondo.adapters.chat_completions import compute_cost_usd
        from rondo.mcp_tools import _estimate_dispatch_cost

        prompt = "x" * 400  # -- 100 input tokens
        raw = compute_cost_usd("gemini-2.5-flash", 100, 1000)  # -- default tier = 1000 output
        est = _estimate_dispatch_cost(["gemini:gemini-2.5-flash"], prompt, "default")
        assert abs(est - raw * 1.3) < 1e-6, f"Expected {raw * 1.3}, got {est}"

    def test_tier_affects_output_budget(self) -> None:
        # -- high tier reserves more output budget, so estimate grows
        from rondo.mcp_tools import _estimate_dispatch_cost

        prompt = "x" * 1000
        low = _estimate_dispatch_cost(["gemini:gemini-2.5-flash"], prompt, "low")
        default = _estimate_dispatch_cost(["gemini:gemini-2.5-flash"], prompt, "default")
        high = _estimate_dispatch_cost(["gemini:gemini-2.5-flash"], prompt, "high")
        assert low < default < high

    def test_scales_with_prompt_length(self) -> None:
        # -- Same provider, 1000x longer prompt → bigger estimate. Old heuristic
        # -- was flat regardless of prompt length; this proves the new one scales.
        # -- Uses a big ratio because fixed output-budget cost dominates at small prompts.
        from rondo.mcp_tools import _estimate_dispatch_cost

        short = _estimate_dispatch_cost(["openai:gpt-4.1"], "x" * 100, "default")
        long = _estimate_dispatch_cost(["openai:gpt-4.1"], "x" * 100_000, "default")
        assert long > short * 2, f"1000x longer prompt should >2x cost, got short={short:.4f} long={long:.4f}"

    def test_unknown_model_uses_default_cost(self) -> None:
        # -- Model not in _COST_TABLE → _DEFAULT_COST ($1/$3 per 1M), not crash or zero
        from rondo.mcp_tools import _estimate_dispatch_cost

        cost = _estimate_dispatch_cost(["custom:brand-new-model-xyz"], "x" * 4000, "default")
        assert cost > 0


# -- sig: mgh-82a9.1b.f6df1b.bd01.69b6d9
