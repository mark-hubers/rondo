Review complete. I read the full diffs for all 7 scoped files (including the quarantine commit `957bd9f` itself, which is the exclusive lower bound), traced `sanitize_task_result`'s actual scrub set, `TaskResult`'s fields, the finalize persistence flow, the per-class gate, the bounded lock + sweep, and the advisory choke point.

# MID-POINT HOSTILE DEEP REVIEW — findings

## HIGH

**1. Quarantine leaves `prompt_sent` raw → secret-bearing field leaks to spool/result/envelope on scrub failure.**
`sanitize_task_result` scrubs four fields — `prompt_sent`, `raw_output`, `stderr`, `parsed_result` (`sanitize.py:482-501`). The quarantine redactor stubs only three:

```836:841:src/rondo/dispatch.py
    result.raw_output = _QUARANTINE_STUB
    result.parsed_result = None
    result.stderr = ""
    result.metrics["sanitize_failed"] = True
    result.context_data["sanitize_error"] = error_detail
```

`prompt_sent` is never redacted. On any scrub failure the original `result` is unchanged (the deepcopy in sanitize is discarded on exception), so `result.prompt_sent` holds the **raw prompt** — the exact field RONDO-352/STD-104 r023 added scrubbing for "a secret in the prompt (e.g. an env var) must never reach those artifacts." After `_quarantine_scrub_failure` returns, finalize runs `spool_result(asdict(result))` (`dispatch.py:892`, includes `prompt_sent`), `_log_to_history`, and the returned envelope carries it. This reintroduces the morning review's headline finding #1 on the fail path — the milestone's whole claim ("audit/spool/result/history only ever see a stub") is false for `prompt_sent`.
*Fix:* add `result.prompt_sent = _QUARANTINE_STUB` (and stub `error_message`/`command_sent` if you consider them in-scope) in the redaction block; pin with a judge test asserting `prompt_sent` is stubbed after a forced scrub failure.

## MED

**2. Quarantine write's `except` misses `RecursionError` — the exact case the widened except was built for defeats redaction.**

```829:835:src/rondo/dispatch.py
    except (OSError, TypeError, ValueError) as write_exc:
        logger.error("-ERROR- quarantine write FAILED ...")
        qpath = ""
```

The headline reason the outer except was widened to `Exception` (`dispatch.py:874`) is a deeply-nested `parsed_result` raising `RecursionError` in `_scrub_dict`. But the quarantine write does `json.dump(asdict(result))` (`dispatch.py:828`) over that **same** nested structure — `asdict` + `json.dump` both recurse and re-raise `RecursionError`, which is **not** in `(OSError, TypeError, ValueError)` (it's a `RuntimeError`). It escapes `_quarantine_scrub_failure` *before* the redaction lines run → finalize crashes with `result` still raw, and the docstring's "Redaction wins even if the quarantine write fails" is false for precisely the targeted case.
*Fix:* widen the write `except` to `Exception` (BLE001-annotated) so redaction always runs; optionally cap serialization depth.

**3. Per-class cold-start probe re-opens a bounded blind-admit window (K concurrent probes).**

```285:293:src/rondo/parallel.py
            while class_key not in self._sampled and self._inflight.get(class_key, 0) > 0:
                self._cond.wait(timeout=_GATE_PROBE_WAIT_SEC)
            est = self._estimates.get(class_key, 0.0) if class_key in self._sampled else 0.0
            if self._spent + self._reserved + est > self.cap:
                return None
```

The probe-alone guard is now **per class**. With K distinct provider classes in a round, K unsampled probes run **concurrently**, each reserving `est=0.0` against the global cap (`0+0+0 > cap` is false) → up to K simultaneous blind dispatches before any sample lands. The old gate allowed exactly **one** blind probe round-wide. The morning's global-zeroing bug is genuinely fixed, but this side effect should be acknowledged: worst-case cold-start overrun is now `(K-1) × probe_cost`.
*Fix:* keep a single global "one unsampled probe at a time" gate, or reserve a conservative non-zero est for unsampled classes.

**4. Idempotency fast-path moved below routing — cache hits now preempted by route/context errors + added latency.**
The lookup (`mcp_dispatch.py:886`) now runs *after* `resolve_dispatch_engine`, the `engine=="error"` context check (`:842`), and `_route_by_execution_mode`/`route_error` (`:867`). A duplicate that previously short-circuited instantly now (a) pays full routing cost on every cache hit, and (b) if routing returns `error`/`route_error` (context-limit recompute, session/option-C state, registry change between calls), the error **preempts** the previously-servable cached result. For identical inputs routing is mostly deterministic so the semantic change is narrow, but it's a real weakening of the fast-path guarantee and a hot-path latency regression. The inline-cross-contamination fix itself is sound.
*Fix:* if no behavioral need, restore the guarded-path lookup before routing (keep only the inline/agent exclusion); else add a test pinning "cache hit survives a now-erroring route."

## LOW-MED

**5. `_save_background_result` still write_text-then-chmod — the chmod-window twin RONDO-393 missed.**

```114:115:src/rondo/mcp_dispatch.py
        retry_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        retry_path.chmod(0o600)  # -- STD-110 S5: restrictive permissions
```

This is the identical pattern RONDO-393 killed in `save_result` and the retry dead-letter, but the retry **enqueue** write was not converted. The full result dict (with `raw_output`) sits at umask (commonly `0o644`) between write and chmod. Dir is `0o700` (`:112`) so same-uid-only in practice — same mitigation argument the campaign used for the audit dir, but the MUST/window is unaddressed in a twin the campaign claimed to sweep.
*Fix:* mkstemp→fdopen(0o600)→os.replace, same as the others.

**6. http_skeleton `TypeError/ValueError` widening can attribute local/callback bugs to the provider and open its breaker.**

```223:228:src/rondo/adapters/http_skeleton.py
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        ...
        get_circuit_breaker().record_failure(plan.provider)
```

`TypeError`/`ValueError` from `_done_result`, token math, or a plan-supplied callback is now converted to `ERR_PROVIDER` **and** records a breaker failure — a local bug can trip/open the circuit for a healthy provider, masking a code fault as an outage. The "not bare Exception" reasoning is sound, but these two are broad enough to catch own-bugs that shouldn't count against the provider.
*Fix:* scope the `TypeError/ValueError` catch tightly around the parse/token block, not the whole try (which includes `_done_result` and callbacks); don't `record_failure` for non-network faults.

## LOW

**7. Advisory budget gate uses API pricing regardless of host auth → can refuse free work.** `_advisory_budget_refusal` estimates via `compute_cost_usd(plan_model, ...)` (`mcp_dispatch.py:933`), which is API pricing. For an inline/agent plan the **host** executes (often a Claude subscription = $0 to rondo), so a tiny `max_budget` can refuse a plan whose real cost is zero. The refusal message is honest ("actuals of host-executed work are not tracked") but it's a wrong-side refusal. *Fix:* document that the gate is intentionally conservative, or skip it for known-free auth classes.

**8. Budget-refused advisory plans are not audited.** `refusal` returns before `_audit_advisory_plan` (`mcp_dispatch.py:874-877`). A budget refusal is a real enforcement event with no audit/forensic trace. *Fix:* record an INTENT+OUTCOME (status `refused`) for the refused plan.

**9. matrix per-cell output born wide.** `(out_dir / f"{safe_stem}.txt").write_text(str(result.get("output","")))` (`matrix.py:286`) — raw model output written at umask, no chmod, no visible sanitize. You named "matrix" as a born-wide candidate; it is. *Fix:* mkstemp 0o600 + sanitize if outputs can carry secrets.

**10. `--timeout-per-mutant` counts ANY timeout as CAUGHT with no baseline check.** `except subprocess.TimeoutExpired: return True` (`mutate.py:208-214`). A legitimately slow suite (not the mutation) is scored "caught" → inflated/meaningless kill rate; conflates "code broke and hangs" with "tests are slow." Opt-in (default 0) so low. *Fix:* time the unmutated baseline first and require timeout > k×baseline, or report timeouts as a distinct outcome.

**11. (note) Advisory path adds ~4 file writes per plan on the PRIMARY interactive path.** `_audit_advisory_plan` does INTENT jsonl + prompt file + OUTCOME jsonl + result file, constructing a fresh `AuditTrail` per call (`mcp_dispatch.py:961-1001`). `auto_reconcile=False` correctly avoids the reconcile scan, but for Cursor's constant inline use this is real IO + audit-dir growth between rotations. Watch volume.

## Checked, clean (no finding)
- **EXDEV/`os.replace`**: every mkstemp uses `dir=` the target's own directory (`audit.py:142`, `dispatch.py:251`, `idempotency.py:319`, `retry_queue.py:153`) → same-filesystem, no cross-device replace. Quarantine never replaces (writes in-place).
- **Sweep vs compaction deadlock**: `sweep_stale_key_locks` probes key-lock files with `LOCK_EX|LOCK_NB` (non-blocking) while holding the `.compact.lock` — different files, non-blocking, and `cross_process_key_lock` never takes the compact lock → no lock-order inversion, no deadlock.
- **Sweep unlink-while-held**: documented degradation (open-but-not-yet-flocked peer lands on a dead inode) is genuinely double-pay only — cache writes are flock'd append-only with later-wins scan, so no corruption. Confirmed worst case.
- **Reconcile self-deadlock**: thread-local `_reconcile_jsonl_held` correctly lets the reconciling thread's synthetic appends skip re-flocking (`audit.py:657-665`) while other threads still lock; `_reconcile_with_jsonl_flock` now holds LOCK_EX on the audit file itself across scan+write.
- **MAX-KEEP vs `setdefault`**: `cost>0` does `max(cost,0.001,existing)`, `cost==0 & ok` does `setdefault(...,0.0)` — a free success never lowers a paid class's estimate; a paid sample upgrades a previously-free class. Correct. (`_inflight` keyed by provider prefix = bounded set, not an unbounded leak.)
- **Bounded lock budget=0**: deadline `=now` → first failed NB acquire returns False immediately (true "no wait"); garbage/negative env → 3s default. Correct.
- **Quarantine file completeness**: `asdict(result)` captures all fields including `prompt_sent` → never-lose-data store is complete (the leak in #1 is only that the *in-place* result keeps `prompt_sent` for the other stores).
- **Advisory sanitize-on-persist**: `record_intent` scrubs the prompt file (`audit.py:403`), `record_outcome` scrubs `raw_output` (the plan JSON incl. raw prompt) before the result file (`audit.py:488`); JSONL records store neither raw prompt nor raw_output. Correct.

---

**BLOCKERS: 1 — ready for re-score: no.**

Finding #1 (prompt_sent leak) re-opens the exact MUST-inversion this milestone was built to close, so a hostile re-score will land it as a HIGH again; fix it before 8.11. I'd also fix #2 before the re-score (it falsifies the stated "redaction wins" guarantee on the one case the widening targeted). Findings #3–#11 are legitimate but won't block a ≥7.5; #3 and #4 are the ones most likely to cost a fraction of a point if left unacknowledged.
