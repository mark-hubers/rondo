# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Structured logging, idempotency, context limits, token estimates, routing edges.

Split from TestAlwaysOnPipeline in RONDO-207. The original class had
67 tests in 1479 lines — above best-practice file size. This file is
a focused slice by theme: observability.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import logging
import sys

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.mcp_dispatch import resolve_dispatch_engine


class TestPipelineObservability:
    """RONDO-139 + RONDO-204 + RONDO-205: Structured logging, idempotency, context limits, token estimates, routing edges."""

    def test_all_plans_have_schema_version(self) -> None:
        """RONDO-146 (Finding #207): All plan responses include schema_version."""
        from rondo.mcp_dispatch import PLAN_SCHEMA_VERSION

        cases = [
            ("", False, "inline"),
            ("gemini:flash", False, "http"),
            ("local:qwen2.5:32b", False, "http"),
            ("llama3.1:8b", False, "http"),
            ("sonnet:new", False, "subprocess"),
            ("", True, "subprocess"),
            ("unknown-model", False, "error"),
        ]
        for model, bg, expected_engine in cases:
            r = resolve_dispatch_engine(model=model, background=bg, prompt="x")
            assert r["engine"] == expected_engine
            assert "schema_version" in r, f"Missing schema_version: {model!r}/{bg}"
            assert r["schema_version"] == PLAN_SCHEMA_VERSION

    def test_agent_plan_has_schema_version(self, monkeypatch) -> None:
        """RONDO-146: Agent plans (in-session Claude) include schema_version."""
        from rondo.mcp_dispatch import PLAN_SCHEMA_VERSION

        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        assert r["engine"] == "agent"
        assert r["schema_version"] == PLAN_SCHEMA_VERSION

    def test_routing_new_suffix_with_provider_prefix(self) -> None:
        """RONDO-146 (Finding #220): :new suffix on provider-prefixed model.

        Currently :new check happens after provider-prefix routing, so
        gemini:flash:new should route to HTTP (not subprocess).
        """
        # -- gemini:flash:new — provider prefix wins (HTTP), :new is part of model name
        r = resolve_dispatch_engine(model="gemini:flash:new", prompt="x")
        # -- This is HTTP because gemini: prefix wins
        assert r["engine"] == "http"
        assert r["provider"] == "gemini"

    def test_routing_background_with_unknown_model(self) -> None:
        """RONDO-146 (Finding #220): background=True + unknown model → still subprocess."""
        r = resolve_dispatch_engine(model="totally-unknown-xyz", background=True, prompt="x")
        # -- background forces subprocess regardless of model validity
        assert r["engine"] == "subprocess"

    def test_routing_whitespace_in_model_is_stripped(self, monkeypatch) -> None:
        """RONDO-206 Finding #220 FIX: whitespace in model name IS auto-stripped.

        Prior behavior (RONDO-146): whitespace was preserved — ' sonnet ' was
        treated as unknown model. This was documented-but-user-hostile.
        RONDO-206 actually fixes it: leading/trailing whitespace is stripped
        at the router entry so ' sonnet ' routes as 'sonnet'.

        Case sensitivity is still preserved (see test_routing_case_sensitive_for_claude_models)
        because opus[1m] has case-sensitive bracket syntax.
        """
        monkeypatch.delenv("CLAUDECODE", raising=False)
        r = resolve_dispatch_engine(model=" sonnet ", prompt="x")
        # -- Whitespace is now stripped → valid Claude model → subprocess (outside CC)
        assert r["engine"] == "subprocess", (
            "#220 fix: ' sonnet ' must normalize to 'sonnet' and route correctly"
        )
        assert r["model"] == "sonnet"

    def test_routing_case_sensitive_for_claude_models(self) -> None:
        """RONDO-146 (Finding #220): Claude model match is case-sensitive."""
        # -- 'SONNET' (uppercase) is not a known Claude model
        r = resolve_dispatch_engine(model="SONNET", prompt="x")
        assert r["engine"] == "error", "Uppercase SONNET should not match (case-sensitive)"

    def test_routing_inline_preserves_project_in_all_engines(self, monkeypatch) -> None:
        """RONDO-146 (Finding #220): project field preserved in inline + agent plans."""
        # -- Inline plan
        r = resolve_dispatch_engine(model="", prompt="x", project="/tmp/proj1")
        assert r["project"] == "/tmp/proj1"

        # -- Agent plan
        monkeypatch.setenv("CLAUDECODE", "1")
        r = resolve_dispatch_engine(model="haiku", prompt="x", project="/tmp/proj2")
        assert r["project"] == "/tmp/proj2"

    def test_idempotency_key_stable(self) -> None:
        """RONDO-147 (Finding #214): Same prompt+model produces same key."""
        from rondo.idempotency import compute_idempotency_key

        k1 = compute_idempotency_key("hello world", "gemini-2.5-flash")
        k2 = compute_idempotency_key("hello world", "gemini-2.5-flash")
        assert k1 == k2

        # -- Different prompt → different key
        k3 = compute_idempotency_key("hello WORLD", "gemini-2.5-flash")
        assert k1 != k3

        # -- Different model → different key
        k4 = compute_idempotency_key("hello world", "grok-3")
        assert k1 != k4

    def test_idempotency_cache_returns_cached(self) -> None:
        """RONDO-147: cached result returned within TTL."""
        from rondo.idempotency import cache_result, clear_cache, compute_idempotency_key, get_cached_result

        clear_cache()
        key = compute_idempotency_key("test prompt", "test-model")

        # -- Initially empty
        assert get_cached_result(key) is None

        # -- Cache something
        fake_result = {"status": "done", "raw_output": "cached"}
        cache_result(key, fake_result)

        # -- Retrieved within TTL
        retrieved = get_cached_result(key)
        assert retrieved == fake_result
        clear_cache()

    def test_idempotency_cache_expires(self) -> None:
        """RONDO-147: cached result evicted after TTL."""
        from rondo.idempotency import cache_result, clear_cache, compute_idempotency_key, get_cached_result

        clear_cache()
        key = compute_idempotency_key("expiring", "test")
        cache_result(key, {"x": 1})

        # -- TTL=0 → immediate expiry
        retrieved = get_cached_result(key, ttl_sec=0)
        assert retrieved is None
        clear_cache()

    def test_idempotency_cache_thread_safe(self) -> None:
        """RONDO-147: concurrent cache writes don't corrupt state."""
        import threading

        from rondo.idempotency import cache_result, cache_size, clear_cache, compute_idempotency_key

        clear_cache()
        errors: list[Exception] = []

        def writer(i: int) -> None:
            try:
                key = compute_idempotency_key(f"prompt {i}", "model")
                cache_result(key, {"i": i})
            except (RuntimeError, OSError) as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cache_size() == 50
        clear_cache()

    def test_idempotency_cache_persists_across_memory_wipe(self, tmp_path, monkeypatch) -> None:
        """RONDO-205 Finding #241: cache survives in-memory cache being wiped.

        Simulates a process restart: cache in Process A, wipe in-memory
        cache (as if Process B started fresh), then read — should find
        the value via the SQLite backing store.
        """
        import rondo.idempotency as idem

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem.clear_cache()

        key = idem.compute_idempotency_key("cross-process prompt", "gemini:flash")
        payload = {"status": "done", "raw_output": "shared result", "cost_usd": 0.001}
        idem.cache_result(key, payload)

        # -- Simulate "restart": wipe in-memory only (not the DB)
        with idem._cache_lock:
            idem._cache.clear()
        assert idem.cache_size() == 0, "precondition: in-memory wiped"

        # -- Fetch should succeed via SQLite fallback
        result = idem.get_cached_result(key)
        assert result is not None, (
            "#241: cache miss after in-memory wipe — SQLite fallback broken"
        )
        assert result["status"] == "done"
        assert result["raw_output"] == "shared result"
        assert result["cost_usd"] == 0.001

        # -- Promotion: after reading via SQLite, in-memory should be populated
        assert idem.cache_size() == 1, "#241: SQLite hit should promote to memory"

        idem.clear_cache()

    def test_idempotency_cache_crosses_process_boundary(self, tmp_path, monkeypatch) -> None:
        """RONDO-205 Finding #241: two separate process-like instances share cache.

        Uses RONDO_TEST_DIR to isolate the SQLite file. Process A caches,
        then we clear ALL in-memory state (including any OS-level caches
        the module may have built up) to simulate Process B starting fresh.
        """
        import importlib

        import rondo.idempotency as idem1

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem1.clear_cache()

        # -- "Process A" writes
        key = idem1.compute_idempotency_key("P1 prompt xyz", "openai:gpt-4.1")
        idem1.cache_result(key, {"result": "from-process-a"})

        # -- "Process B" — reload module to simulate fresh Python process
        importlib.reload(idem1)
        # -- After reload, in-memory cache is empty but SQLite file persists
        assert idem1.cache_size() == 0, "reloaded module has empty in-memory cache"

        found = idem1.get_cached_result(key)
        assert found is not None, (
            "#241: fresh-process read failed — SQLite backing store not shared"
        )
        assert found["result"] == "from-process-a"

        idem1.clear_cache()

    def test_idempotency_ttl_honored_in_file_layer(self, tmp_path, monkeypatch) -> None:
        """RONDO-209 #246: expired JSONL entries are filtered at scan time.

        Write a stale entry DIRECTLY into the append-only JSONL file with
        a wall-clock timestamp 1000s in the past, then verify get_cached_result
        returns None because the TTL filter drops it. This test must use
        proper JSONL format (one JSON object per line) so it actually
        exercises the TTL filter, not a malformed-parse fallback.
        """
        import json as _json
        import time as _time

        import rondo.idempotency as idem

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem.clear_cache()

        # -- Write a stale entry in PROPER JSONL format (one line per entry)
        cache_path = idem._default_cache_file()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        stale_time = _time.time() - 1000.0  # -- 1000 seconds ago
        stale_entry = {
            "key": "stale-key",
            "data": {"x": 1},
            "cached_at_wall": stale_time,
        }
        cache_path.write_text(_json.dumps(stale_entry) + "\n", encoding="utf-8")

        # -- Positive assertion: fixture is valid JSONL and contains the entry
        assert cache_path.exists()
        raw = cache_path.read_text(encoding="utf-8")
        assert "stale-key" in raw
        assert raw.endswith("\n"), "valid JSONL must end with newline"

        # -- Primary assertion: TTL filter drops the stale entry
        result = idem.get_cached_result("stale-key", ttl_sec=300)
        assert result is None, "#246: stale entry leaked past TTL filter in JSONL scan"

        # -- Negative assertion: fresh entry with same key IS returned
        fresh_entry = {
            "key": "stale-key",
            "data": {"x": 2},
            "cached_at_wall": _time.time(),
        }
        cache_path.write_text(
            _json.dumps(stale_entry) + "\n" + _json.dumps(fresh_entry) + "\n",
            encoding="utf-8",
        )
        result2 = idem.get_cached_result("stale-key", ttl_sec=300)
        assert result2 == {"x": 2}, (
            f"#246: latest-wins should return fresh entry, got {result2!r}"
        )

        idem.clear_cache()

    def test_dispatch_task_emits_structured_logs_with_request_id(
        self, tmp_path, monkeypatch, caplog
    ) -> None:
        """RONDO-205 Finding #242: dispatch_task wires structured_log + binds request_id.

        Previously: structured_log module existed but nothing called log_event.
        Now: dispatch_task wraps the whole dispatch in bind_request_id() and
        emits log_event at start/complete. This test proves:
          1. A request_id gets bound during dispatch
          2. log_event calls produce records tagged with that request_id
          3. The START and COMPLETE events share the SAME request_id
        """
        import json as _json
        import logging as _logging

        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task
        from rondo.engine import Task

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        caplog.set_level(_logging.INFO, logger="rondo.structured_log")

        # -- Dry-run task so we don't actually call subprocess/adapter
        task = Task(name="fp242-task", instruction="noop", done_when="ok")
        config = RondoConfig(auth="max", dry_run=True)

        dispatch_task(task, config, cli_model="sonnet", round_name="test-round")

        # -- Collect structured log records (JSON-formatted)
        structured_records: list[dict] = []
        for rec in caplog.records:
            if rec.name != "rondo.structured_log":
                continue
            try:
                payload = _json.loads(rec.message)
            except (ValueError, TypeError):
                continue
            structured_records.append(payload)

        assert len(structured_records) >= 2, (
            f"#242: expected at least 2 structured records (start + complete), "
            f"got {len(structured_records)}"
        )

        # -- All records from this dispatch must share a request_id
        request_ids = {rec["request_id"] for rec in structured_records if rec.get("request_id")}
        assert len(request_ids) == 1, (
            f"#242: multiple request_ids across same dispatch: {request_ids}"
        )
        rid = request_ids.pop()
        assert len(rid) == 32, f"#242: request_id should be 32-char UUID hex, got: {rid!r}"

        # -- Start event has task name + component=dispatch
        start_events = [r for r in structured_records if "dispatch_task start" in r.get("msg", "")]
        assert len(start_events) == 1, "#242: exactly one start event"
        assert start_events[0]["task"] == "fp242-task"
        assert start_events[0]["component"] == "dispatch"

    def test_dispatch_task_respects_existing_request_id(
        self, tmp_path, monkeypatch, caplog
    ) -> None:
        """RONDO-205 Finding #242: don't rebind if caller already bound one.

        When mcp_dispatch.rondo_run_file binds a request_id and then calls
        dispatch_task, the existing id must propagate — not get overwritten.
        This is the correlation guarantee for the full call chain.
        """
        import json as _json
        import logging as _logging

        from rondo.config import RondoConfig
        from rondo.dispatch import dispatch_task
        from rondo.engine import Task
        from rondo.structured_log import bind_request_id

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        caplog.set_level(_logging.INFO, logger="rondo.structured_log")

        task = Task(name="fp242-nested", instruction="noop", done_when="ok")
        config = RondoConfig(auth="max", dry_run=True)

        with bind_request_id("caller-supplied-id-abcd1234abcd1234") as expected_rid:
            dispatch_task(task, config, cli_model="sonnet")

        # -- Records from dispatch_task must use the caller's rid, not a new one
        rids_seen: set[str] = set()
        for rec in caplog.records:
            if rec.name != "rondo.structured_log":
                continue
            try:
                payload = _json.loads(rec.message)
            except (ValueError, TypeError):
                continue
            if payload.get("task") == "fp242-nested":
                rids_seen.add(payload.get("request_id", ""))

        assert rids_seen == {expected_rid}, (
            f"#242: dispatch_task rebound request_id. "
            f"expected={expected_rid}, got={rids_seen}"
        )

    def test_request_id_generation(self) -> None:
        """RONDO-148 (Finding #215): new_request_id returns unique 32-char hex."""
        from rondo.structured_log import new_request_id

        r1 = new_request_id()
        r2 = new_request_id()
        assert r1 != r2
        assert len(r1) == 32
        assert all(c in "0123456789abcdef" for c in r1)

    def test_bind_request_id_propagates(self) -> None:
        """RONDO-148: bind_request_id sets thread-local for nested calls."""
        from rondo.structured_log import bind_request_id, get_request_id

        # -- Initially empty
        assert get_request_id() == ""

        with bind_request_id() as rid:
            assert get_request_id() == rid
            assert len(rid) == 32

        # -- Restored after context exit
        assert get_request_id() == ""

    def test_bind_request_id_explicit(self) -> None:
        """RONDO-148: bind_request_id accepts explicit ID."""
        from rondo.structured_log import bind_request_id, get_request_id

        with bind_request_id("custom-rid-123") as rid:
            assert rid == "custom-rid-123"
            assert get_request_id() == "custom-rid-123"

    def test_bind_request_id_nested(self) -> None:
        """RONDO-148: nested binds save/restore correctly."""
        from rondo.structured_log import bind_request_id, get_request_id

        with bind_request_id("outer"):
            assert get_request_id() == "outer"
            with bind_request_id("inner"):
                assert get_request_id() == "inner"
            assert get_request_id() == "outer"

    def test_structured_logger_emits_json(self, caplog) -> None:
        """RONDO-148: StructuredLogger emits JSON-formatted records."""
        from rondo.structured_log import StructuredLogger, bind_request_id

        slog = StructuredLogger("test-component")
        with caplog.at_level(logging.INFO, logger="rondo.structured_log"):
            with bind_request_id("test-rid"):
                slog.info("test event", task_name="t1", model="sonnet")

        # -- Find our log record
        matching = [r for r in caplog.records if "test event" in r.message]
        assert len(matching) >= 1
        msg = matching[0].message
        # -- Should be valid JSON with request_id, component, task_name, model
        import json as _json

        parsed = _json.loads(msg)
        assert parsed["request_id"] == "test-rid"
        assert parsed["component"] == "test-component"
        assert parsed["task_name"] == "t1"
        assert parsed["model"] == "sonnet"
        assert parsed["msg"] == "test event"

    def test_structured_logger_thread_isolation(self) -> None:
        """RONDO-148: request_id is per-thread, not global."""
        import threading

        from rondo.structured_log import bind_request_id, get_request_id

        results: dict[str, str] = {}

        def worker(name: str, expected_rid: str) -> None:
            with bind_request_id(expected_rid):
                results[name] = get_request_id()

        t1 = threading.Thread(target=worker, args=("thread-1", "rid-aaa"))
        t2 = threading.Thread(target=worker, args=("thread-2", "rid-bbb"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["thread-1"] == "rid-aaa"
        assert results["thread-2"] == "rid-bbb"

    def test_context_limit_check_within_limit(self) -> None:
        """RONDO-200 (Finding #216): check_context_limit passes for short prompt."""
        from rondo.mcp_dispatch import check_context_limit

        fits, est, limit = check_context_limit("sonnet", "hello world")
        assert fits is True
        assert est < limit
        assert limit == 200_000

    def test_context_limit_check_over_limit(self) -> None:
        """RONDO-200: check_context_limit detects oversized prompt."""
        from rondo.mcp_dispatch import check_context_limit

        huge_prompt = "x" * 700_000
        fits, est, limit = check_context_limit("gpt-4.1", huge_prompt)
        assert fits is False
        assert est > limit

    def test_context_limit_1m_models(self) -> None:
        """RONDO-200: 1M context models accept large prompts."""
        from rondo.mcp_dispatch import check_context_limit

        big_prompt = "x" * 800_000
        fits, _est, _limit = check_context_limit("sonnet[1m]", big_prompt)
        assert fits is True
        fits, _est, _limit = check_context_limit("gemini-2.5-pro", big_prompt)
        assert fits is True

    def test_context_limit_unknown_model_uses_default(self) -> None:
        """RONDO-200: unknown model gets DEFAULT_CONTEXT_LIMIT."""
        from rondo.mcp_dispatch import DEFAULT_CONTEXT_LIMIT, check_context_limit

        _fits, _est, limit = check_context_limit("unknown-model-xyz", "small")
        assert limit == DEFAULT_CONTEXT_LIMIT

    def test_token_estimate_non_english_cjk(self) -> None:
        """RONDO-205 Finding #238: CJK text is counted with higher ratio.

        Old formula: len(text)//4 + 1 — massively undercounted CJK.
        Example: "你好世界" (len=4) → old=2, actual=6-8 tokens.

        New formula: ASCII at 4:1, non-ASCII at 2 tokens/char.
        This test proves CJK is no longer catastrophically undercounted.
        """
        from rondo.mcp_dispatch import estimate_token_count

        # -- 10 CJK chars ≈ 10-20 real tokens. New formula: 10*2+1 = 21.
        cjk_short = "你好世界再见中国日本" * 1  # 10 CJK chars
        cjk_tokens = estimate_token_count(cjk_short)
        assert cjk_tokens >= 20, (
            f"#238: CJK undercount still present. Got {cjk_tokens} for 10 CJK chars."
        )

        # -- Old broken formula would have given len(20 CJK)//4+1 = 6 tokens
        cjk_long = "你好世界再见中国日本" * 2  # 20 CJK chars
        cjk_long_tokens = estimate_token_count(cjk_long)
        assert cjk_long_tokens >= 40, (
            f"#238: 20 CJK chars should be ≥40 tokens. Got {cjk_long_tokens}."
        )

        # -- ASCII remains close to old (no regression for English)
        ascii_text = "hello world" * 10  # 110 ASCII chars
        ascii_tokens = estimate_token_count(ascii_text)
        assert 25 <= ascii_tokens <= 35, (
            f"#238: English token estimate should stay ~28. Got {ascii_tokens}."
        )

    def test_token_estimate_mixed_language(self) -> None:
        """RONDO-205 Finding #238: mixed ASCII + non-ASCII text is summed.

        A prompt like "Translate: 你好" (10 ASCII + 2 CJK) should be
        counted as ~3 ASCII tokens + 4 CJK tokens = 7+, not 3.
        """
        from rondo.mcp_dispatch import estimate_token_count

        mixed = "Translate: 你好"  # 11 ASCII + 2 CJK
        tokens = estimate_token_count(mixed)
        # -- 11 ASCII = ceil(11/4) = 3; 2 CJK = 4; + safety 1 = 8
        assert tokens >= 7, (
            f"#238: mixed text must sum both portions. Got {tokens}."
        )

    def test_token_estimate_empty_string(self) -> None:
        """RONDO-205 Finding #238: empty string returns 1, never 0.

        Edge case — zero-token prompt would break downstream math
        (division, ratios). Guarantee at least 1.
        """
        from rondo.mcp_dispatch import estimate_token_count

        assert estimate_token_count("") == 1

    def test_config_hot_reload(self, tmp_path) -> None:
        """RONDO-200 (Finding #218): reload_rondo_config picks up file changes."""
        from rondo.config import reload_rondo_config, reset_rondo_config

        config_file = tmp_path / "config.toml"
        config_file.write_text('[providers.gemini]\nenabled = true\nbest_model = "version-1"\n')

        reset_rondo_config()
        cfg = reload_rondo_config(config_path=str(config_file))
        assert cfg.get("providers", {}).get("gemini", {}).get("best_model") == "version-1"

        config_file.write_text('[providers.gemini]\nenabled = true\nbest_model = "version-2"\n')

        cfg2 = reload_rondo_config(config_path=str(config_file))
        assert cfg2.get("providers", {}).get("gemini", {}).get("best_model") == "version-2"
        reset_rondo_config()


# -- sig: mgh-783b.b1.bf3120.ae70.4a1225
