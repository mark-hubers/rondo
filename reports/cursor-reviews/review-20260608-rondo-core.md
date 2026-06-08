Deep review complete. I read the dispatch core, concurrency, secret-handling, auth, retry/breaker, audit, routing, and the MCP surface, and cross-checked against the repo's own specs. Findings ranked by severity, top 8.

## Hostile review — Rondo

### 1. `prompt_sent` is never scrubbed — secret leak to spool + result files (HIGH, security)
`sanitize_task_result` only scrubs `raw_output`, `stderr`, and `parsed_result` — it never touches `prompt_sent` (`src/rondo/sanitize.py:464-498`). But `save_result` writes the whole record via `data = asdict(result)` (`src/rondo/dispatch.py:244`), and `_finalize_dispatch` spools `asdict(result)` too (`src/rondo/dispatch.py:815`). So the full prompt lands unredacted in `results_dir/task-*.json` and the spool mailbox.

This is a direct violation of your own MUST-level spec: `specs/Rondo-STD-104-infrastructure.md:90` ("Before writing a TaskResult to spool, strip … the `prompt_sent` field") and `specs/Rondo-STD-100-data-standards.md:311`. The audit prompt-file path *does* sanitize (`audit.py:331`); the persisted `TaskResult` does not. Given the "artifact-level secrets guarantee" claim, this is the headline bug.

### 2. The sanitizer fails open (HIGH, security)
In `_finalize_dispatch` the scrub is wrapped so that any failure is swallowed and the pipeline keeps going:

```800:808:src/rondo/dispatch.py
    try:
        result, _sr = sanitize_task_result(result, config=None)
    except (TypeError, AttributeError) as exc:
        logger.debug("Sanitize failed (non-fatal): %s", exc)
```

After this, the code still spools, saves, and logs the result. A security control that, on its own malfunction, persists the *unsanitized* payload is fail-open. A scrub failure should fail the persistence, not the scrub.

### 3. Biggest architectural weakness: the default "dispatch" doesn't dispatch
For the in-session default (`execution=inline`, empty model), `rondo_run` doesn't execute anything — it returns a JSON *plan* containing a natural-language `_host_instruction` ("Execute the `prompt` field … Do NOT show this plan JSON") plus an `execution_token`, and relies on the calling LLM voluntarily obeying it, verified by an external Caliber hook (`src/rondo/dispatch_routing.py:42-47`, `94-117`, `386-405`).

So the core dispatch contract for the primary path is "ask the host model nicely and hope a hook checks the token." There's no execution guarantee and no in-process verification, yet audit/idempotency/metrics/reliability all assume a real execution happened. Every reliability number computed over inline dispatches is measuring something Rondo never controlled. This is the soft center the other 59 modules are built around.

### 4. Subprocess I/O can stall → false `ERR_TIMEOUT` (MED-HIGH, correctness/concurrency)
Two related issues in the subprocess runner:

- The full prompt (allowed up to `_MAX_PROMPT_BYTES = 500_000`, `mcp_dispatch.py:67`) is written to stdin and closed *before any read* (`src/rondo/dispatch.py:1004-1007`). Classic pipe-deadlock shape: if the child emits stdout before draining stdin and both OS buffers (~64KB) fill, the parent blocks on `stdin.write`.
- The watchdog loop only `select`s/reads **stdout**, and reads stderr just once at exit (`src/rondo/dispatch.py:966-969`). A child that fills its ~64KB stderr buffer blocks, stops emitting stdout, and the watchdog reads that as silence and kills it (`_kill("watchdog_silence")`).

In both cases legitimate work is killed and surfaced as a timeout. `claude -p`'s read-then-stream behavior masks it today, but the runner is general and the pattern is unsafe. Fix: a stdin-writer thread or `communicate(input=...)`, and drain stderr concurrently.

### 5. Health check reports dead credentials as healthy (MED-HIGH, honesty/error-handling)
`ChatCompletionsAdapter.health()` returns `True` for any non-5xx, explicitly including 401/403 (`src/rondo/chat_completions.py:298-302`): "401/403/404 from /models = API is reachable." So an expired/invalid key reports the provider as up; `rondo doctor`/`rondo_health` show GREEN, and the next real dispatch dies `ERR_AUTH`. For a project whose dim-10 bar is an "honest reliability scoreboard," a green health signal over broken auth is the wrong default.

### 6. Idempotency's "race-safe" claim is false for its own payloads (MED, concurrency)
`_append_cache_entry` justifies safety with POSIX PIPE_BUF atomicity — "JSON lines are typically <1KB … <PIPE_BUF (typically 4KB)" (`src/rondo/idempotency.py:80-103`). But `cache_result` stores the serialized result, and the cached `result_str` includes `raw_output` that can be hundreds of KB to multiple MB (truncation cap scales to 2–4MB, `dispatch.py:64-90`). Those lines are far larger than PIPE_BUF, and `O_APPEND` atomicity is not guaranteed for large writes or on NFS. Under real cross-process concurrency you get interleaved/corrupt JSONL — the exact failure the module claims to have eliminated. The audit JSONL relies on the same reasoning at `audit.py:578-583`.

### 7. Non-zero exit silently downgraded to success (MED, correctness)
When `returncode != 0`, if *any* assistant text was emitted the result is parsed normally and can be recorded `status="done"` (`src/rondo/dispatch.py:618-638`). A subprocess that crashed after partial output, or exited non-zero for a real reason, is recorded as a completed dispatch. This both hides failures and inflates the reliability rate the watchdog is supposed to police.

### 8. Process-global circuit breaker, shared and racy (MED, concurrency)
`_GLOBAL_BREAKER = CircuitBreaker()` (`src/rondo/retry.py:428`) is keyed only by provider name and shared across every provider plus `claude_cli`, persisted with wall-clock `open_until`. `_save_state` iterates `self._states` and reads each `state.open_until`/`failure_count` while holding only `_global_lock`, never the per-`state.lock` that `record_failure`/`is_open` mutate under (`retry.py:318-327` vs `388-415`) — a genuine data race on those fields. Also, a system clock/NTP adjustment mis-times every cooldown, and the breaker file is a shared single mutable cross-process file on the hot path.

---

### What's genuinely well-built
- **Two-phase append-only audit** (INTENT before launch, OUTCOME after) with `reconcile_stuck_intents` and an age threshold to avoid false-reconciling peer in-flight work (`src/rondo/audit.py:287-344`, `623-679`). This is real crash-forensics design, not theater.
- **The secret detector** is broad and thoughtful: NFKC + explicit Cyrillic/Greek homoglyph mapping before scanning (`sanitize.py:362-411`), wide provider-token coverage, entropy-aware base64. The *intent* (scrub before persist) is right — finding #1 is a coverage gap, not a design flaw.
- **Subprocess/env hygiene fundamentals**: never `shell=True`, command-as-list, prompt via stdin (ARG_MAX-safe), `prepare_env` strips `ANTHROPIC_API_KEY` under `auth=max` with a public-build hard refusal (`dispatch.py:150-174`), 0600/0700 perms, tenant-scoped dirs, and path-traversal guards in `spool._safe_task_slug` / `_validated_spool_path`.
- **`retry_http`**: deliberately narrowed exception types so a `NameError`/`TypeError` in `fn()` isn't silently retried, honors `Retry-After` (capped), per-provider semaphore (`retry.py:144-211`). Good restraint.

The top three (prompt_sent leak, fail-open sanitizer, advisory inline dispatch) are the ones I'd block a release on. Want me to turn these into a prioritized remediation plan with specific fixes?
