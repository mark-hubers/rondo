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
            return json.dumps({
                "status": "partial",
                "tasks": [{
                    "task_name": "test",
                    "status": "error",
                    "error_code": "ERR_PROVIDER_DOWN",
                    "error_message": "Gemini HTTP 503: Service Unavailable",
                    "raw_output": "",
                    "duration_sec": 4.5,
                    "cost_usd": 0.0,
                }],
                "total_cost_usd": 0.0,
            })

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(
                rondo_multi_review(
                    prompt="review", providers='["gemini:gemini-2.5-pro"]', dry_run=False
                )
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
                return json.dumps({
                    "status": "partial",
                    "tasks": [{
                        "task_name": "t",
                        "status": "error",
                        "error_code": "ERR_PROVIDER_DOWN",
                        "error_message": "Gemini HTTP 503",
                        "raw_output": "",
                        "duration_sec": 4.0,
                        "cost_usd": 0.0,
                    }],
                    "total_cost_usd": 0.0,
                })
            # -- Second call (serial retry): succeeds
            return json.dumps({
                "status": "done",
                "tasks": [{
                    "task_name": "t",
                    "status": "done",
                    "raw_output": "Real review content here.",
                    "duration_sec": 8.0,
                    "cost_usd": 0.001,
                    "error_code": None,
                    "error_message": None,
                }],
                "total_cost_usd": 0.001,
            })

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            result = json.loads(
                rondo_multi_review(
                    prompt="review", providers='["gemini:gemini-2.5-pro"]', dry_run=False
                )
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
            return json.dumps({
                "status": "partial",
                "tasks": [{
                    "task_name": "t",
                    "status": "error",
                    "error_code": "ERR_AUTH",
                    "error_message": "Invalid API key",
                    "raw_output": "",
                    "duration_sec": 0.5,
                    "cost_usd": 0.0,
                }],
                "total_cost_usd": 0.0,
            })

        with patch("rondo.mcp_dispatch.rondo_run_file", side_effect=mock_run_file):
            rondo_multi_review(
                prompt="review", providers='["openai:gpt-4.1"]', dry_run=False
            )

        # -- Only ONE call (no retry for auth errors)
        assert call_count[0] == 1, (
            f"#248: ERR_AUTH should NOT trigger retry, got {call_count[0]} calls"
        )


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


class TestCloudDispatch:
    """REQ-109 reqs 046-063: cloud dispatch with profiles, tiers, cost caps."""

    def test_dry_run_returns_cloud_metadata(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Review this", dry_run=True))
        assert result["status"] == "done"
        assert "cloud" in result
        assert result["cloud"]["tier"] == "default"
        assert result["cloud"]["count_requested"] == 2

    def test_profile_review(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Review this", profile="review", dry_run=True))
        assert result["status"] == "done"
        assert result["cloud"]["profile"] == "review"

    def test_profile_coding(self) -> None:
        from rondo.mcp_tools import rondo_cloud

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


# -- sig: mgh-82a9.1b.f6df1b.bd01.69b6d9
