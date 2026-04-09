# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Sanitize detection patterns, footgun guards, budget caps, tenant isolation.

Split from TestAlwaysOnPipeline in RONDO-207. The original class had
67 tests in 1479 lines — above best-practice file size. This file is
a focused slice by theme: security.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import sys

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))



class TestPipelineSecurity:
    """RONDO-139 + RONDO-204 + RONDO-205: Sanitize detection patterns, footgun guards, budget caps, tenant isolation."""

    def test_sanitize_runs_before_audit_outcome(self, tmp_path) -> None:
        """RONDO-140 (Finding #204): SANITIZE BEFORE AUDIT.

        Secrets in raw_output must be scrubbed BEFORE audit_trail.record_outcome
        writes to JSONL/result.json. Otherwise plaintext secrets land in audit logs.
        """
        from rondo.audit import AuditConfig, AuditTrail
        from rondo.config import RondoConfig
        from rondo.dispatch import _finalize_dispatch
        from rondo.engine import DispatchUsage, TaskResult

        # -- Construct a fake sk- pattern at runtime so gitleaks doesn't flag the test source
        # -- Pattern matches sanitize.py sk_prefix_key regex: sk-[A-Za-z0-9]{20,}
        secret = "sk-" + ("FAKETESTKEY" * 3)  # nosec B105 -- test fixture, not a real secret
        tr = TaskResult(
            task_name="leak-test",
            status="done",
            raw_output=f"Use this key: {secret}",
            model="gemini-2.5-flash",
        )
        usage = DispatchUsage(task_name="leak-test", model="gemini-2.5-flash", cost_usd=0.0)
        audit_trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = audit_trail.record_intent(
            task_name="leak-test", round_name="test", model="gemini-2.5-flash", prompt="give me a key"
        )
        config = RondoConfig(audit_dir=str(tmp_path))

        finalized_tr, _u = _finalize_dispatch(tr, usage, config, audit_trail, record, round_name="test")

        # -- Returned result is sanitized
        assert secret not in finalized_tr.raw_output, "Returned TaskResult still contains secret"
        assert "REDACTED" in finalized_tr.raw_output, "Returned TaskResult missing redaction marker"

        # -- Result file (persisted to disk) is sanitized
        result_files = list(tmp_path.glob("*.result.json"))
        assert len(result_files) >= 1, "No result file written"
        for rf in result_files:
            content = rf.read_text()
            assert secret not in content, f"Secret leaked into {rf.name}"

        # -- Audit JSONL is sanitized (or doesn't store raw_output at all)
        jsonl_files = list(tmp_path.glob("*.jsonl"))
        for jf in jsonl_files:
            content = jf.read_text()
            assert secret not in content, f"Secret leaked into {jf.name}"

        # -- Prompt file (if it captures prompt) doesn't leak the secret either
        prompt_files = list(tmp_path.glob("*.prompt.txt"))
        for pf in prompt_files:
            content = pf.read_text()
            # -- Prompt didn't contain the secret, but verify defensively
            assert secret not in content, f"Secret leaked into {pf.name}"

    def test_sanitize_detects_github_pat(self) -> None:
        """RONDO-143 (Finding #208): GitHub personal access tokens scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        # -- Fake but pattern-matching GitHub PAT
        fake = "ghp_" + ("A" * 40)
        tr = TaskResult(task_name="t", status="done", raw_output=f"token is {fake}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake not in sanitized.raw_output, "GitHub PAT leaked"

    def test_sanitize_detects_slack_tokens(self) -> None:
        """RONDO-143: Slack bot/user/app tokens scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        for prefix in ("xoxb-", "xoxp-", "xapp-"):
            fake = prefix + ("X" * 30)
            tr = TaskResult(task_name="t", status="done", raw_output=f"token: {fake}")
            sanitized, _report = sanitize_task_result(tr)
            assert fake not in sanitized.raw_output, f"Slack {prefix} token leaked"

    def test_sanitize_detects_jwt(self) -> None:
        """RONDO-143: JWT bearer tokens (three-part eyJ...) scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        fake_jwt = "eyJ" + ("A" * 20) + ".eyJ" + ("B" * 20) + "." + ("C" * 30)
        tr = TaskResult(task_name="t", status="done", raw_output=f"bearer: {fake_jwt}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake_jwt not in sanitized.raw_output, "JWT leaked"

    def test_sanitize_detects_aws_temp_key(self) -> None:
        """RONDO-143: AWS temporary access keys (ASIA prefix) scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        fake = "ASIA" + "1" * 16
        tr = TaskResult(task_name="t", status="done", raw_output=f"key: {fake}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake not in sanitized.raw_output, "AWS temp key leaked"

    def test_sanitize_detects_anthropic_specific(self) -> None:
        """RONDO-143: sk-ant- prefix caught with higher confidence."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        fake = "sk-ant-" + ("X" * 30)
        tr = TaskResult(task_name="t", status="done", raw_output=f"claude key: {fake}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake not in sanitized.raw_output, "Anthropic key leaked"

    def test_sanitize_detects_gitlab_pat(self) -> None:
        """RONDO-143: GitLab personal access tokens scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        fake = "glpat-" + ("Y" * 25)
        tr = TaskResult(task_name="t", status="done", raw_output=f"gitlab: {fake}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake not in sanitized.raw_output, "GitLab PAT leaked"

    def test_sanitize_detects_google_api_key(self) -> None:
        """RONDO-143: Google API keys (AIza prefix) scrubbed."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        fake = "AIza" + ("Z" * 35)
        tr = TaskResult(task_name="t", status="done", raw_output=f"google: {fake}")
        sanitized, _report = sanitize_task_result(tr)
        assert fake not in sanitized.raw_output, "Google API key leaked"

    def test_subprocess_footgun_guard_blocks_in_session(self, monkeypatch) -> None:
        """RONDO-143 (Finding #206): In-session subprocess dispatch hard-stop.

        If router regresses and a Claude model reaches _dispatch_interactive
        while CLAUDECODE is set, the guard returns ERR_SUBPROCESS_FOOTGUN
        instead of silently failing with 'not logged in'.
        """
        from rondo.config import RondoConfig
        from rondo.dispatch import _dispatch_interactive
        from rondo.engine import Task

        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.delenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", raising=False)

        task = Task(name="foot", instruction="hi", done_when="done")
        config = RondoConfig(auth="max")

        result, _usage = _dispatch_interactive(task, config, "sonnet", "2026-04-07T00:00:00Z")
        assert result.status == "error"
        assert result.error_code == "ERR_SUBPROCESS_FOOTGUN"
        assert "footgun" in result.error_message.lower() or "blocked" in result.error_message.lower()

    def test_subprocess_footgun_opt_in_bypass(self, monkeypatch) -> None:
        """Footgun guard can be bypassed with RONDO_ALLOW_IN_SESSION_SUBPROCESS=1.

        Opt-in escape for explicit CLI/cron use cases. Still runs the real
        dispatch which will fail — but the footgun guard doesn't block it.
        """
        from unittest.mock import patch

        from rondo.config import RondoConfig
        from rondo.dispatch import _dispatch_interactive
        from rondo.engine import Task

        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", "1")

        task = Task(name="foot", instruction="hi", done_when="done")
        config = RondoConfig(auth="max")

        # -- Mock the subprocess runner so we don't actually fork
        with patch("rondo.dispatch._run_subprocess") as mock_run:
            mock_run.return_value = ("{}", "", 0, False)
            try:
                result, _usage = _dispatch_interactive(task, config, "sonnet", "2026-04-07T00:00:00Z")
                # -- Guard didn't fire, so we got past it (even if dispatch itself fails later)
                assert result.error_code != "ERR_SUBPROCESS_FOOTGUN", "Guard should be bypassed"
            except (OSError, RuntimeError):
                # -- OK: dispatch logic may fail downstream — we just care guard didn't fire
                pass

    def test_subprocess_footgun_guard_blocks_auth_api(self, monkeypatch) -> None:
        """RONDO-205 Finding #237: guard ALSO blocks auth=api in-session.

        Prior behavior only blocked auth=max. Gemini R3 flagged that
        auth=api + CLAUDECODE + Claude model is still a footgun (cost
        surprise, nested contexts, user confusion). Guard now fires for
        both auth modes — auth=api is verified here.
        """
        from rondo.config import RondoConfig
        from rondo.dispatch import _dispatch_interactive
        from rondo.engine import Task

        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.delenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", raising=False)

        task = Task(name="foot-api", instruction="hi", done_when="done")
        config = RondoConfig(auth="api")  # -- #237: previously NOT guarded

        result, _usage = _dispatch_interactive(task, config, "sonnet", "2026-04-07T00:00:00Z")
        assert result.status == "error"
        assert result.error_code == "ERR_SUBPROCESS_FOOTGUN", (
            "#237: guard must fire for auth=api too, not just auth=max"
        )
        assert "api" in result.error_message.lower(), (
            "Error message should mention auth mode for diagnostics"
        )

    def test_subprocess_footgun_override_emits_warning(self, monkeypatch, caplog) -> None:
        """RONDO-205 Finding #237: override bypass must leave an audit trail.

        Previously the override was silent — no log, no alert. Gemini R3
        said this is a security gap (easy to accidentally leave set).
        Guard now emits a WARNING-level log when override is active in
        a blocking scenario, so it shows up in ops dashboards.
        """
        import logging as _logging
        from unittest.mock import patch

        from rondo.config import RondoConfig
        from rondo.dispatch import _dispatch_interactive
        from rondo.engine import Task

        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", "1")

        task = Task(name="foot-override", instruction="hi", done_when="done")
        config = RondoConfig(auth="max")

        caplog.set_level(_logging.WARNING, logger="rondo.dispatch")
        with patch("rondo.dispatch._run_subprocess") as mock_run:
            mock_run.return_value = ("{}", "", 0, False)
            try:
                _dispatch_interactive(task, config, "sonnet", "2026-04-07T00:00:00Z")
            except (OSError, RuntimeError):
                pass

        # -- #237: audit trail proof — warning must be logged
        override_warnings = [
            rec for rec in caplog.records
            if "FOOTGUN OVERRIDE ACTIVE" in rec.message
        ]
        assert len(override_warnings) >= 1, (
            "#237: override bypass must emit WARNING log (audit trail)"
        )
        # -- Verify warning includes task name for operator diagnosis
        assert "foot-override" in override_warnings[0].message

    def test_budget_cap_blocks_http_dispatch(self) -> None:
        """RONDO-141/202 (Finding #205 + #226): Predictive budget cap on HTTP adapter path.

        RONDO-202: cap is now PREDICTIVE — running + estimate >= cap blocks
        the next dispatch (not just running >= cap). After task 1 at $0.05,
        the estimate becomes $0.05 → task 2 pre-check sees $0.10 ≥ $0.08 → BLOCKED.
        """
        from unittest.mock import MagicMock, patch

        from rondo.config import RondoConfig
        from rondo.engine import Round, RoundResult, Task, TaskResult
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="budget-test",
            tasks=[
                Task(name="t1", instruction="hi", done_when="done"),
                Task(name="t2", instruction="hi", done_when="done"),
                Task(name="t3", instruction="hi", done_when="done"),
            ],
        )

        provider = MagicMock()

        def fake_dispatch(prompt: str, model: str, task_name: str) -> TaskResult:
            return TaskResult(task_name=task_name, status="done", raw_output="ok", model=model, cost_usd=0.05)

        provider.dispatch.side_effect = fake_dispatch
        config = RondoConfig(max_budget_usd=0.08, audit_dir="")

        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=config,
                model="gemini:gemini-2.5-flash",
                prompt="hi",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )

        assert isinstance(result, RoundResult)
        assert len(result.task_results) == 3

        # -- RONDO-202 predictive behavior:
        # -- t1: initial estimate $0.01 + running $0 = $0.01 < $0.08 → dispatches
        # --     after: running=$0.05, estimate updated to actual $0.05
        # -- t2: running $0.05 + estimate $0.05 = $0.10 ≥ $0.08 → BLOCKED
        # -- t3: same as t2 → BLOCKED
        assert result.task_results[0].status == "done"
        assert result.task_results[1].error_code == "ERR_BUDGET_EXCEEDED"
        assert result.task_results[2].error_code == "ERR_BUDGET_EXCEEDED"

        # -- Only t1 actually dispatched
        assert provider.dispatch.call_count == 1, (
            f"Predictive cap should block after t1 (running+estimate >= cap). "
            f"Got {provider.dispatch.call_count} dispatches."
        )

    def test_no_budget_cap_no_blocking(self) -> None:
        """If max_budget_usd is None, all dispatches proceed regardless of cost."""
        from unittest.mock import MagicMock, patch

        from rondo.config import RondoConfig
        from rondo.engine import Round, Task, TaskResult
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="no-cap-test",
            tasks=[Task(name=f"t{i}", instruction="hi", done_when="done") for i in range(5)],
        )
        provider = MagicMock()
        provider.dispatch.side_effect = lambda prompt, model, task_name: TaskResult(
            task_name=task_name, status="done", model=model, cost_usd=10.0
        )
        config = RondoConfig(audit_dir="")  # -- no max_budget_usd

        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=config,
                model="gemini:gemini-2.5-flash",
                prompt="hi",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )
        assert all(t.status == "done" for t in result.task_results)
        assert provider.dispatch.call_count == 5

    def test_key_cache_tenant_isolation(self, monkeypatch) -> None:
        """RONDO-142 (Finding #209): _KEY_CACHE is tenant-scoped.

        Was: cache keyed only by provider. User A's key reused for User B's
        request for 5 minutes (cross-tenant credential bleed).

        Now: cache keyed by (provider, tenant). User B gets their own key,
        not a leftover from User A.
        """
        from rondo.adapters import auth

        auth.invalidate_all_keys()

        # -- Tenant A logs in with their key
        monkeypatch.setenv("RONDO_TENANT", "alice")
        monkeypatch.setenv("XAI_API_KEY", "alice-secret-key")
        key_alice = auth.load_api_key("grok")
        assert key_alice == "alice-secret-key"

        # -- Switch to Tenant B with their own key
        monkeypatch.setenv("RONDO_TENANT", "bob")
        monkeypatch.setenv("XAI_API_KEY", "bob-secret-key")
        key_bob = auth.load_api_key("grok")
        # -- Bob must get HIS key, not Alice's cached one
        assert key_bob == "bob-secret-key", (
            f"Cross-tenant key leak: Bob got {key_bob!r} instead of bob-secret-key"
        )

        # -- Switch back to Alice — she should get her key from cache
        monkeypatch.setenv("RONDO_TENANT", "alice")
        monkeypatch.setenv("XAI_API_KEY", "different-key-now")
        key_alice2 = auth.load_api_key("grok")
        # -- Alice gets her CACHED value, not the new env (unless TTL expired)
        assert key_alice2 == "alice-secret-key", "Alice's cache lost — should still hit"

        auth.invalidate_all_keys()

    def test_key_cache_thread_safe(self, monkeypatch) -> None:
        """RONDO-142: concurrent loads don't corrupt cache or duplicate work."""
        import threading

        from rondo.adapters import auth

        auth.invalidate_all_keys()
        monkeypatch.setenv("RONDO_TENANT", "concurrent-test")
        monkeypatch.setenv("GEMINI_API_KEY", "concurrent-key-value")

        results: list[str] = []
        errors: list[Exception] = []

        def load_in_thread() -> None:
            try:
                results.append(auth.load_api_key("gemini"))
            except (RuntimeError, OSError) as exc:
                errors.append(exc)

        # -- 20 concurrent threads loading the same key
        threads = [threading.Thread(target=load_in_thread) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # -- All threads got the same key, no errors
        assert len(errors) == 0, f"Errors during concurrent load: {errors}"
        assert len(results) == 20
        assert all(r == "concurrent-key-value" for r in results), f"Inconsistent keys: {set(results)}"

        auth.invalidate_all_keys()

    def test_invalidate_only_affects_current_tenant(self, monkeypatch) -> None:
        """RONDO-142: invalidate_key only clears the calling tenant's cache."""
        from rondo.adapters import auth

        auth.invalidate_all_keys()

        # -- Cache for tenant A
        monkeypatch.setenv("RONDO_TENANT", "alice")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "alice-anthropic")
        auth.load_api_key("anthropic")

        # -- Cache for tenant B
        monkeypatch.setenv("RONDO_TENANT", "bob")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "bob-anthropic")
        auth.load_api_key("anthropic")

        # -- Bob invalidates HIS key
        auth.invalidate_key("anthropic")

        # -- Switch to Alice — her cache should still have her key
        monkeypatch.setenv("RONDO_TENANT", "alice")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # -- Alice's cache should still have her value (Bob's invalidate didn't touch it)
        key_alice = auth.load_api_key("anthropic")
        assert key_alice == "alice-anthropic", (
            f"Alice's cache wrongly invalidated by Bob's invalidate. Got: {key_alice!r}"
        )

        auth.invalidate_all_keys()

    def test_audit_dir_tenant_isolation(self, monkeypatch) -> None:
        """RONDO-200 (Finding #217): audit dir is tenant-scoped by default."""
        monkeypatch.delenv("RONDO_TEST_DIR", raising=False)
        monkeypatch.setenv("RONDO_TENANT", "alice")

        from rondo.audit import _default_audit_dir

        path_alice = _default_audit_dir()
        assert "alice" in path_alice, f"Audit dir should contain tenant: {path_alice}"

        monkeypatch.setenv("RONDO_TENANT", "bob")
        path_bob = _default_audit_dir()
        assert "bob" in path_bob
        assert path_alice != path_bob


# -- sig: mgh-7d5d.3d.f500d6.5568.dc996d
