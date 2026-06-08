# Cursor deep review — rondo — 20260608-180758

**Model:** claude-opus-4-8-thinking-high | **Lens:** concurrency | **Mode:** plan (read-only)

---

Research complete. I read every file in the audit set, cross-checked `specs/Rondo-STD-110` (reqs 016-020) and the two prior reviews, and confirmed the runtime wiring (`AuditTrail` is built **per task** via `dispatch.py:112` → reconcile-on-init fires on every worker; one shared `_BudgetGate` per round). Here is the hostile review. I deliberately skip the already-known findings from the two prior reports (parallel budget *absence*, `_cc_version_cache`, PIPE_BUF, the original `_save_state` field-read race, fcntl-Unix-only as a generic note, advisory inline dispatch, prompt_sent leak).

# Hostile concurrency review — rondo (this session's fixes + what's LEFT)

Verdict up front: the three fixes are **directionally right but two of them are not actually correct**. RONDO-361 reintroduces a cross-process lost-update (fail-open), and RONDO-359 trades a data race for a Windows/NFS spec violation and still leaves the duplicate-OUTCOME window open. RONDO-360 is correct but only in-process. Separately, the *prior* parallel-budget fix (RONDO-354) has a live TOCTOU.

---

## 1. CRITICAL — RONDO-361 erases a peer's persisted OPEN breaker (cross-process lost update → fail-OPEN)

`_apply_memory_states` is supposed to merge in-memory state *on top of* peer state read from disk, "fail-closed." The `elif` branch does the opposite:

```353:367:src/rondo/retry.py
        with self._global_lock:
            states_items = list(self._states.items())
        for provider, state in states_items:
            with state.lock:
                s_open_until = state.open_until
                s_failure = state.failure_count
            if s_open_until > now:
                prev = payload.get(provider, {})
                payload[provider] = {
                    "open_until": max(s_open_until, float(prev.get("open_until", 0.0))),
                    "failure_count": float(max(s_failure, int(prev.get("failure_count", 0)))),
                }
            elif provider in payload:
                # -- Our state says CLOSED (success/recovery) — remove from payload
                del payload[provider]
```

Scenario (MCP server = P1, overnight CLI = P2, both dispatch):
1. P1 once used `gemini` successfully → `record_success` leaves `gemini` in `P1._states` with `open_until=0` (CLOSED, **stale**).
2. P2 trips `gemini` OPEN and persists it to disk (`open_until=future`).
3. P1 trips an **unrelated** provider (`grok`) → `record_failure` → `_save_state`.
4. `_read_existing_payload` correctly keeps P2's gemini (`retry.py:330-340`). Then `_apply_memory_states` hits `gemini` (P1 memory = CLOSED) → `del payload["gemini"]` → `os.replace` writes a file **without gemini**. P2's trip is gone.

P1's *stale* local CLOSED clobbers P2's *fresh* OPEN — the exact cross-process lost update the `#246` flock+merge was built to prevent, now reintroduced by the RONDO-361 merge. The reload that would have fixed P1's memory (`_maybe_reload`) only runs in `is_open` (`retry.py:439`), **not** in the write path, and `record_failure` never calls it — so `_save_state` routinely writes from a memory snapshot that is behind disk. This also directly contradicts the method's own docstring ("fail-closed … keep theirs … never shorten", `retry.py:342-352`). Net effect: a down provider's breaker silently clears for every other process → they resume hammering it. **Fix:** never `del`; let `_read_existing_payload`'s `open_until > now` filter age peer entries out, and only drop a provider you can prove you own.

## 2. HIGH — RONDO-354 `_BudgetGate` is a check-then-act TOCTOU → up to W× budget overrun (spec MUST)

This is the *remaining* hole after the parallel-budget fix prior review #1 demanded. The gate checks and records under the lock, but in **two separate** critical sections with the expensive dispatch in between and **no reservation**:

```240:252:src/rondo/parallel.py
    def over_budget(self) -> bool:
        if self.cap is None:
            return False
        with self._lock:
            return (self._running + self._estimate) >= self.cap

    def record(self, cost: float) -> None:
        with self._lock:
            self._running += cost
```

```283:288:src/rondo/parallel.py
    if gate is not None and gate.cap is not None and gate.over_budget():
        return _budget_blocked_result(task, config, gate.cap)
    tr, usage = dispatch_task_routed(task, config)
    if gate is not None:
        gate.record(tr.cost_usd or 0.0)
```

With `workers=W`, when `_running` sits just under `cap`, all W in-flight workers call `over_budget()` (each sees `running + estimate < cap` because nobody has reserved), all pass, all dispatch, all `record()` afterward. Overrun ≈ `(W-1) × actual_cost`. The lock makes the counter race-free but does nothing for admission. Violates the same three MUSTs the gate cites — `IFS-101:132` req 028, `STD-107:94` req 018, `STD-101:435` req 212 — "check budget **before dispatch**, skip if over." **Fix:** reserve `_estimate` against `_running` inside `over_budget` (single locked reserve/commit/refund), not a separate read then write.

## 3. HIGH — RONDO-359 reconcile crashes on Windows instead of degrading (req 019 violation)

The flock sidecar added an **unguarded** `import fcntl` at the top of the reconcile body:

```659:674:src/rondo/audit.py
        import fcntl  # pylint: disable=import-outside-toplevel

        with _reconcile_lock:
            lock_path = self._jsonl_path.with_name(self._jsonl_path.name + ".reconcile.lock")
            try:
                lock_f = lock_path.open("w", encoding="utf-8")
            except OSError as exc:
                logger.warning("Reconcile lock open failed: %s", exc)
                return 0
            try:
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
```

On Windows `import fcntl` raises `ImportError`. `reconcile_stuck_intents` runs on every `AuditTrail.__init__` once a jsonl exists (`audit.py:289-291`), and `__init__` only catches `(OSError, TypeError, ValueError, AttributeError)` (`audit.py:292`) — **ImportError is not caught**, so it propagates and every dispatch after the first crashes at audit construction. `STD-110:439` req 019 (MUST) says where flock is unavailable (NFS/**Windows**) the code SHALL "fall back to single-writer mode and emit a WARNING — NEVER silently skip." The new code does neither; it aborts hard. (The old `_append_jsonl` path guards `except (ImportError, OSError)` at `audit.py:586` — reconcile must do the same and fall through to the in-process `_reconcile_lock`-only path.)

## 4. HIGH — RONDO-359 conflates "peer holds lock" with "flock unsupported" → silently skips the safety check on NFS (req 019)

```669:674:src/rondo/audit.py
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    logger.debug("Reconcile in progress on a peer process; skipping")
                    return 0
```

`LOCK_NB` raises `OSError(EWOULDBLOCK)` when a peer holds it (correct to skip) **and** `OSError(ENOLCK/EOPNOTSUPP)` when the filesystem doesn't support flock (NFS). Both are collapsed into "peer in progress; skipping" at **DEBUG** and `return 0`. On NFS reconcile therefore **never runs and never warns** — the precise "silently skip" req 019 forbids. It should distinguish errno: EWOULDBLOCK → skip (idempotent), anything else → WARN + run the in-process single-writer reconcile.

## 5. MED-HIGH — RONDO-359 lock doesn't cover the OUTCOME writers, so the duplicate-OUTCOME window it targets is still open (req 018)

The reconcile lock is on a **different** file (`.reconcile.lock`, `audit.py:662`) than the append path's flock (on the jsonl itself, `audit.py:578-585`). So `_reconcile_lock`/`.reconcile.lock` serialize *reconciler-vs-reconciler* but **not reconciler-vs-`record_outcome`**. A dispatch slower than `stuck_after_sec` (default 300s) ages its INTENT past threshold; reconcile's snapshot (`_scan_intents_and_outcomes`, `audit.py:611-629`, taken with no jsonl lock) sees no OUTCOME → writes a synthetic `stuck` (`audit.py:709-711`); the real dispatch then writes its genuine OUTCOME. Two OUTCOMEs for one `dispatch_id` — violating `STD-110:438` req 018 ("SHALL NOT create duplicate OUTCOME records"). RONDO-359 narrowed the reconciler/reconciler race but did not close the reconciler/writer race it claims to. The 25-worker stress test in the spec note (`STD-110:424-430`) used fast dispatches and would not exercise the >300s path.

## 6. MED — RONDO-359 reconcile scans the jsonl without the append flock → can manufacture a false-stuck

`_scan_intents_and_outcomes` does `read_text(...).splitlines()` (`audit.py:615`) while holding only `.reconcile.lock`, not the jsonl flock. A concurrent append (especially the Windows/NFS best-effort no-lock branch at `audit.py:591`) can leave the last line torn; `json.loads` skips it (`audit.py:620`). If the skipped line was the OUTCOME for an aged INTENT, reconcile thinks it's stuck and double-writes. The scan must take a `LOCK_SH`/`LOCK_EX` on the jsonl (the same lock the writers use), not a sidecar.

## 7. MED — RONDO-361 `_maybe_reload` mtime-equality gate can miss a peer's trip (the gap #5 claims to close)

```431:435:src/rondo/retry.py
        try:
            current = self._persist_path.stat().st_mtime
        except OSError:
            return
        if current != self._persist_mtime:
            self._load_state()
```

Two problems: (a) on filesystems with coarse `mtime` (1s, or NFS attribute-cache staleness), a peer write within the same tick as our own `_record_mtime()` (`retry.py:307`) leaves `current == self._persist_mtime` → no reload → the peer trip stays invisible to this live instance, defeating the headline #5 goal. (b) `_persist_mtime` is read here and written by both `_load_state` (`retry.py:413`) and `_save_state` (`retry.py:307`) with **no lock**; concurrent `is_open` callers can interleave so a stale writer resets `_persist_mtime` to an older value after a newer load — usually a harmless extra reload, but it can also mask a needed one. Compare a content hash or size+mtime, and guard `_persist_mtime`.

## 8. MED — RONDO-360 single-flight is in-process only; cross-process duplicates still both pay

`key_lock` is a per-key `threading.Lock` in one process (`idempotency.py:71-82`), and `_dispatch_and_cache` re-checks under it (`mcp_dispatch.py:925-931`) — correct for the in-process window prior review #3 raised. But the MCP server and a CLI run (or multi-process workers) share only the JSONL file, which is still check-then-act (`get_cached_result` at `idempotency.py:240` → dispatch → `cache_result` at `idempotency.py:272`, nothing held across). The module's stated guarantee — "duplicate LLM API calls = duplicate cost" (`idempotency.py:8`) — therefore holds only within a single process. The docstring at `idempotency.py:76-77` admits this; flag it so it isn't mistaken for a closed hole.

## 9. MED — RONDO-360 `_key_locks` grows without bound (memory leak in the long-lived MCP server)

```79:82:src/rondo/idempotency.py
    with _key_locks_guard:
        lk = _key_locks.setdefault(key, threading.Lock())
    with lk:
        yield
```

Every distinct idempotency key (SHA-256 of every unique prompt+model+execution) adds a `Lock` to `_key_locks` that is never evicted. The MCP server is a persistent process; over days of varied prompts this dict grows unboundedly. Needs an LRU/TTL eviction (and eviction must not free a lock another thread is blocked on — evict only when uncontended, e.g. tie lifetime to the idempotency TTL).

## 10. MED — RONDO-359 makes per-task reconcile a serialized full-file scan in the parallel path (scalability regression)

Each parallel worker builds its own `AuditTrail` (`dispatch.py:112` via `dispatch_task_routed`), so `reconcile_stuck_intents` runs **once per task** and now every run takes the blocking in-process `_reconcile_lock` (`audit.py:661`) around an O(N) `read_text` of the whole jsonl (`audit.py:615`). With T tasks and W workers you get T serialized full-file scans contending on one mutex at construction time — a hidden serialization point and O(T·N) I/O the pre-fix unlocked scan didn't impose. Reconcile-on-every-init is the deeper smell; gate it (once per process, or only when an INTENT older than threshold is actually present) rather than per task.

---

### Audit of the three fixes — bottom line
- **RONDO-359 (reconcile lock + flock):** the in-process `_reconcile_lock` is correct and deadlock-free (no path takes `_reconcile_lock` then `key_lock`/breaker locks, and `_append_jsonl`→`_maybe_rotate`→`rotate` is a consistent one-way lock order). But it is **incorrect/incomplete** on three counts: Windows hard-crash (#3), NFS silent-skip (#4), and the still-open reconciler-vs-writer duplicate (#5/#6).
- **RONDO-360 (key_lock + re-check):** **correct** in-process — the optimistic unlocked lookup (`mcp_dispatch.py:822`) followed by locked re-check (`mcp_dispatch.py:928`) is the right single-flight pattern, no reentrancy, no lock inversion. Caveats are scope (#8) and the unbounded map (#9), not correctness.
- **RONDO-361 (breaker):** the `state.lock`-scoped reads (#6 fix) and the snapshot-then-per-lock pattern are **deadlock-free and resolve the original field-read race** — `_global_lock` and `state.lock` are provably never held simultaneously, and `_save_state` is always called *after* releasing `state.lock`, so there's no flock↔state.lock inversion. **But** the merge logic is wrong (#1, the `del`) and the live-visibility mechanism is leaky (#7). The wall-clock `open_until` vs "monotonic" docstring contradiction is real but already noted by prior reviews.

### Corrections / what's genuinely solid (don't chase)
- The breaker's lock discipline is clean — there is **no** lock-ordering deadlock among `_global_lock`, `state.lock`, and the persist flock, contrary to what one might suspect from the nested calls.
- `key_lock` adds no deadlock risk with the audit/breaker locks (it's only acquired in `_dispatch_and_cache`, never reacquired downstream).
- `_BudgetGate`'s counter itself is race-free; the bug is purely the missing reservation (#2), not torn arithmetic.

The two I'd block on: **#1 (breaker fail-open clobber)** and **#2 (budget overrun TOCTOU)** — both defeat MUST-level guarantees under real parallelism.

Want me to (a) write this up into the scaffolded `reports/cursor-reviews/review-20260608-180758-concurrency.md`, and/or (b) turn #1, #2, #3/#4 into a TDD remediation plan (failing test first per the rondo rule)? I'll stay read-only until you say go.
