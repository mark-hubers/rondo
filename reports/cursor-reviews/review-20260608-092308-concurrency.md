# Cursor deep review — rondo — 20260608-092308

**Model:** claude-opus-4-8-thinking-high | **Lens:** concurrency | **Mode:** plan (read-only)

---

I've completed a deep concurrency pass across `retry.py`, `dispatch.py`, `mcp_dispatch.py`, `parallel.py`, `runner.py`, `idempotency.py`, `audit.py`, the adapters, and `structured_log.py`, cross-checked against `specs/Rondo-STD-110`, `STD-107`, `STD-101`, and `IFS-101`. I deliberately skipped the already-known findings (unlocked `_cc_version_cache`/`_states` writes, `fcntl` Unix-only, the cursor `_save_state` field-read race, the idempotency PIPE_BUF corruption) and surfaced what is LEFT.

# Hostile concurrency review — rondo (what prior reviews missed)

Lens: data races, lost updates, budget overrun under parallel workers, TOCTOU. Assumes the real ThreadPool (`parallel.py`, `run_round` routes `workers>1` → `run_parallel`).

## 1. CRITICAL — Budget cap is completely unenforced in the parallel path
The ThreadPool path has **no budget check of any kind**. `run_round` sends `workers>1` to `run_parallel` (`runner.py:78-81`), and `_execute_parallel` (`parallel.py:149-173`) submits every task with zero running-cost tracking. The predictive budget logic only exists in the **sequential** MCP provider loop `_run_provider_round` (`mcp_dispatch.py:414-462`) and as a per-task `--max-budget-usd` flag to the claude subprocess (`dispatch.py:925`). Cloud-adapter tasks (`chat_completions.py:124`) never receive any cap at all.

Under real parallelism, N workers each spend before any cumulative check fires → overrun up to N × max-task-cost.

- Violates `specs/Rondo-IFS-101-caliber-integration.md:132` req 028 (MUST): "Rondo checks budget **before dispatch**, returns status='skipped' if over budget."
- Violates `specs/Rondo-STD-107-security.md:94` req 018 (MUST): "If cumulative... cost exceeds the... budget, pause dispatching and alert."
- Violates `specs/Rondo-STD-101-observability.md:435` req 212 (MUST): `budget_check` decision trace.

NEW vs prior: prior review #3 pointed at `mcp_dispatch.py:470` ("dispatch outside the lock") — but that loop is sequential; the real, larger gap is that the *parallel* path enforces nothing.

## 2. HIGH — `_run_provider_round` cost lock is concurrency theater
`mcp_dispatch.py:409-462` wraps `running_cost` in `cost_lock` and is documented "RONDO-202 thread-safe running cost," but the body is a plain sequential `for task in round_def.tasks` loop — no threads. The lock guards nothing and gives false confidence that budget is concurrency-safe (it isn't; see #1). The estimate also tracks only the **last** task's cost (`mcp_dispatch.py:462`), so a cheap-then-expensive ordering underestimates and lets an over-budget dispatch through even here.

## 3. HIGH — Idempotency is a check-then-act TOCTOU → duplicate billable dispatch
`_idempotency_lookup` (`mcp_dispatch.py:694-715`) → miss → dispatch → `_idempotency_store` (`mcp_dispatch.py:718-724`). The in-memory `_cache_lock` is released the instant the read returns (`idempotency.py:227-246`); nothing is held across lookup → dispatch → store. Two identical concurrent dispatches both miss and **both pay**.

This defeats the module's own stated guarantee (`idempotency.py:8` "duplicate LLM API calls = duplicate cost"). Distinct from prior cursor #6, which was about JSONL line corruption, not the duplicate-dispatch window.

## 4. HIGH — `reconcile_stuck_intents` does an unlocked read-modify-write → duplicate OUTCOMEs (spec MUST violation)
`audit.py:623-679` scans the whole JSONL via `_scan_intents_and_outcomes` (`audit.py:603-621`, no lock), decides which INTENTs are "stuck," then appends synthetic OUTCOMEs. The per-line `flock` in `_append_jsonl` (`audit.py:570-577`) does **not** cover the scan→decide→append sequence. Reconcile runs automatically on **every** `AuditTrail.__init__` (`audit.py:281-285`), and a fresh `AuditTrail` is built per dispatch (`mcp_dispatch.py:261`, `dispatch.py:576`). Concurrent workers each read the same stale snapshot and each append a stuck OUTCOME for the same `dispatch_id`.

- Violates `specs/Rondo-STD-110-concurrency-safety.md:436` req 016 (MUST): "hold an exclusive `fcntl.flock`... before any read-modify-write... Unlocked read-then-write of shared state is forbidden."
- Violates `STD-110:438` req 018 (MUST): reconcile idempotent, no duplicate OUTCOME.
- Violates `STD-110:439` req 019 (MUST): degrade with WARNING, never silently skip.

The spec's own v0.6 note tries to waive the flock layer via a 25-worker stress test, but the requirement table still says MUST, and the age threshold (req 017, the only one implemented) narrows the window — it doesn't close it (two fresh processes starting after a crash both reconcile the same genuinely-old INTENT).

## 5. MED-HIGH — Circuit breaker isn't shared across concurrently-running processes
Live processes consult only in-memory `_states`. The persisted file is read **once** in `_load_state()` at construction (`retry.py:252`, `341-370`) and written only on transition. So when worker/process A trips "gemini" (`retry.py:388-404`), an already-running peer B keeps hammering gemini — B never re-reads the file. The "global shared breaker" (`retry.py:428`) is shared across threads in one process, but across concurrent processes it's shared only at restart, not during their lifetime (MCP server + CLI overlap). Prior cursor #8 covered the field-read race, not this live-share gap.

## 6. MED-HIGH — Breaker persists outside the per-state lock → lost update on the state file
`is_open` / `record_failure` / `record_success` decide the transition under `state.lock`, then call `_save_state()` **after releasing it** (`retry.py:384-385`, `403-404`, `414-415`). `_save_state` itself only holds `_global_lock` while reading each `state.open_until`/`failure_count` (`retry.py:318-324`). Between the release and that read, another thread can mutate the same state, so the persisted snapshot can reflect a *different* logical state than the transition that triggered the save (a just-closed breaker written as OPEN, or a fresh OPEN dropped). Compounded by a docstring/code contradiction: `open_until` is documented "monotonic timestamp" (`retry.py:224`) but set and compared with wall-clock `time.time()` (`retry.py:379`, `395`) — an NTP step misfires every cooldown.

## 7. MED — `_cc_version_cache` negative-result thundering herd
`detect_cc_version` caches only on success; on failure `_cc_version_cache` stays `None` (`dispatch.py:124-142`), so every parallel worker re-spawns `claude --version` with a 5s timeout (`dispatch.py:128-133`) on every dispatch when claude is missing/slow → N concurrent 5s stalls and a subprocess storm. Plus the direct global read at `dispatch.py:877` (`cc_ver = _cc_version_cache or detect_cc_version(...)`) bypasses the function's own guard — the shared-mutable read `STD-110:69-86` C2 forbids. Prior #1 flagged only the "unlocked write"; the negative-cache herd and the raw read are what's left.

## 8. MED — No admission control under fan-out; failure threshold overshoots before OPEN
Each adapter checks `is_open` then dispatches (`chat_completions.py:146`, `gemini.py:76`, `anthropic_api.py:206`). The per-provider gate allows 4 in-flight (`retry.py:86`) and the breaker only opens after `failure_threshold` recorded failures, so against a down provider every in-flight request clears the `is_open` check, all fail, and the OPEN that results can't retroactively stop the concurrent burst already past the check — a classic TOCTOU between `is_open()` and the call.

## 9. MED — Rotate/append size-gate race + missing degradation alert for reconcile
`_maybe_rotate()` runs *before* the append flock is taken (`audit.py:567`), so a peer can rotate/unlink between the size check and the append (append mode recreates the file — benign for data, but the size-gate decision is racy). More importantly, the STD-110 req 019 "degrade with WARNING, never silently skip" alert exists only on the append path (`audit.py:578-583`); reconcile (#4) has neither lock nor warning.

## 10. LOW-MED — request_id correlation lost across ThreadPool workers
`bind_request_id` sets a `threading.local` on the **calling** thread (`structured_log.py:36`, `49-66`); `run_parallel` worker threads (`parallel.py:156`) never inherit it. So audit INTENT/OUTCOME and `log_event` records emitted from pool workers carry `request_id=""` — the cross-component trace `STD-101:423` req 200/212 depends on breaks precisely in the parallel path. The thread-local itself is correct; it's just never propagated into the pool.

---

### Two corrections to the prior reviews
- `_background_results` is **not** an unlocked race (contra `reports/codebase-review-2026-06-08.md:35`): every access holds `_background_lock` (`mcp_dispatch.py:78,84,148,1004,1022,1055,1061`). Don't chase it.
- Genuinely solid and worth keeping: the per-provider semaphore released across backoff (`retry.py:170-206`), the audit append flock + age-threshold reconcile design (`audit.py:557-601`), and the rotate cross-process flock (`audit.py:467-509`).

The headline is #1: **under the ThreadPool, the budget guarantee three specs call MUST simply does not run.** Everything else is a real but narrower race.

Want me to turn these into a TDD remediation plan (failing test first per the rondo rule), starting with the parallel-path budget gate and the idempotency atomic check?
