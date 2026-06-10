Read everything. Here's the review, ordered (1)–(8), grounded in the code and specs.

## (1) AUDIT shape — INTENT + immediate-OUTCOME is right, but two real gaps

**The shape is correct.** There is no "event kind" mechanism in the audit layer to reach for — `AuditRecord` is status-driven (`audit.py:204`, `status: str` is free-form, `record_outcome` does no enum validation at `audit.py:402`). STD-113's two-phase model (intent-before-action, outcome-after) is exactly the honest fit when the "action" is delegated to the host and never observed. Don't invent a new event kind; reuse INTENT→OUTCOME. `reconcile_stuck_intents` only looks for `status=="INTENT"` with no paired OUTCOME (`audit.py:690`), so writing the OUTCOME immediately means no stuck-intent fallout. Good.

**Gap A — don't reuse `status="plan"`.** The plan dict already uses `status: "plan"` for its *own* meaning (`dispatch_routing.py:106,125`). Reusing `"plan"` as the audit *OUTCOME* status conflates two namespaces. Use a distinct value — `status="advisory"` (or `"delegated"`). And note STD-113 §8 still claims only two states exist ("`INTENT` and `COMPLETE`", spec line 145) while the code already emits `done/error/blocked/skipped/stuck`. The status field is de-facto open vocabulary, but adding `"advisory"` should be documented in §8 for spec-honesty (ties to item 8.9).

**Gap B — there is no field to honestly record "engine kind".** You want to record `engine kind (inline/agent)`, but `AuditRecord` has no `engine` field (`audit.py:184-239`). Your options are: abuse `task_type` (semantically reserved for `(task_type, model)` affinity scoring, `audit.py:236-239` — polluting it corrupts scoring), or stuff it in `round_name`. Neither is honest. Recommend adding an append-only `engine: str = ""` field to `AuditRecord` + `to_dict` (`audit.py:241-270`) and to STD-113 req 003's field list. That's a real schema touch, not free — call it out.

**Watch-out C — forensics false-positive.** STD-113 req 021 says *non-`done`* OUTCOMEs MUST persist `error_message` (spec line 82). `"advisory"` is non-`done`. A naive convention/judge that asserts "non-done OUTCOME ⇒ non-empty error_message" will fail on advisory records. Pre-empt it: either scope that rule to failure statuses, or put a benign `blocked_reason`/note on the advisory OUTCOME explaining it's a delegated plan.

## (2) SANITIZE — agree, and it's already enforced inside the audit module

Agree with the principle, with a sharpening: **the caller should NOT pre-scrub at all.** `record_intent` already scrubs the persisted prompt file (`audit.py:383-385`) and `record_outcome` already scrubs `raw_output` before writing the result file (`audit.py:466-471`). So the correct wiring at the choke point is: pass the **raw** plan/prompt into `record_intent`/`record_outcome` and let the module scrub the persisted copy; return the **raw** plan dict to the host. Do *not* double-scrub. STD-114 r006 (spec line 67) governs writes to *audit/result/spool/reports*, not the in-flight MCP return to the authorized caller — your reading is right. One note: the returned plan carries `execution_token` and `_host_instruction` (`dispatch_routing.py:115-116`); dumping the whole plan as OUTCOME `raw_output` persists the token, which is *desirable* for correlation (see 6), not a secret.

## (3) SCOPE HONESTY — agree, but put it on EVERY builder, and the bump rule contradicts itself

Add `guarantees_scope` + `not_covered` — yes. Two corrections:

- **Put `guarantees_scope` on all three builders**, not just inline/agent. Add `guarantees_scope="guarded"` (or `"full"`) to `_build_subprocess_plan` (`dispatch_routing.py:136-145`) and the agent/inline builders get `"advisory"`. Otherwise absence is ambiguous: a consumer can't distinguish "old plan, field missing" from "advisory". Making it present-and-explicit everywhere is what actually makes misclassification impossible — which is the stated goal.
- **`not_covered`** for advisory should also include `"output_sanitization"` and `"idempotency"` (rondo never sees the host's output, and advisory plans aren't cached — see 7), not just the four you listed.

**On the version bump — the schema's own rule contradicts itself.** The comment says additive fields *don't* need a bump (`dispatch_routing.py:31-33`, "consumers on schema 1 ignore unknown fields"). But RONDO-294 *did* bump `1→2` for `_host_instruction`+`execution_token`, which are described in that very same comment as additive (`dispatch_routing.py:32-34,114`). So precedent contradicts the stated rule. Recommendation: **bump to `"3"`** for consumer discoverability (matching the RONDO-294 precedent) *and* fix the comment to say "bump on any field addition." A scope-honesty field is exactly the kind of change a consumer wants to detect by version.

## (4) NOT COVERED — agree on breaker; you ARE leaving a cheap real budget guarantee on the table

- **Circuit breaker:** genuinely N/A — no provider call, no failure to trip on. Declare not-covered. Correct.
- **Budget:** "not covered" is *over*-honest. You have the prompt and the model at the choke point, and you already have `estimate_token_count`/`check_context_limit` (`dispatch_routing.py:252-289`). A real, cheap pre-flight: **estimate the would-be cost and refuse to *issue* the plan if the estimate alone exceeds `max_budget`.** That's a genuine gate (doesn't track actuals, but refuses obviously-over-budget work). Reframe the envelope from `not_covered: ["budget"]` to `guarantees_scope` carrying `budget: "estimate-gated at issuance; actuals not tracked"`. That's strictly more honest *and* more useful.
- **Plan-issuance limiter:** also worth a cheap real counter — a plans-per-minute rate cap surfaced in audit catches a runaway caller issuing thousands of inline plans in a loop. Optional, but it's a real guarantee you can make where "execution budget" is impossible.

## (5) Failure semantics — agree, it's already the house pattern

Agree: return the plan even if the audit write fails. This is exactly what the existing OUTCOME path does — `_write_audit_outcome` is best-effort try/except, "an audit write failure never breaks the dispatch result" (`dispatch.py:765`), and STD-113 §20 mandates "Audit write fails → Dispatch proceeds … log WARNING, do not block." Use `log_event("ERROR"/"WARNING", …, component="mcp_dispatch")` to be loud. **One refinement:** if INTENT succeeds but OUTCOME fails, you've created an orphan INTENT that `reconcile_stuck_intents` will later mark `status="stuck"` (`audit.py:690`, STD-113 req 017) — misleading, since the host *did* get the plan. Mitigate by wrapping both writes so a mid-failure is logged as advisory-specific, or accept the rare "stuck" mislabel and document it.

## (6) dispatch_id in the returned plan — strong yes

Add `dispatch_id` to the returned plan. The plan already carries `execution_token` precisely so Caliber's Stop-hook can verify *this* plan ran (`dispatch_routing.py:50-58,116`). Today the token and the audit record live in **separate namespaces** — nothing links "host executed token X" to "audit record dsp_…". Injecting the INTENT's `dispatch_id` (`audit.py:352`) into the plan closes the loop: Stop-hook reads the token from the transcript → maps token→dispatch_id → can later attach a host-side completion event to the right record. **Ordering constraint this forces:** record INTENT *first*, take `record.dispatch_id` back, inject it into the plan dict, *then* `json.dumps` + return, and record OUTCOME with that same id. So the choke point at `mcp_dispatch.py:872-873` becomes intent→mutate-plan→outcome→return, not a bare `json.dumps(engine)`.

## (7) Idempotency — bypass STORE is correct, but the existing LOOKUP has a cross-mode hole

**Do NOT cache advisory plans.** Caching is actively harmful here: every inline plan mints a *fresh* `execution_token` (`dispatch_routing.py:116`, `_make_execution_token`), and you're now adding a fresh `dispatch_id`. A cache hit would hand two different host executions the *same* token+id → Caliber's Stop-hook can't distinguish them, and your audit correlation collapses. Plans are free to regenerate; freshness is the point. Bypass-store is correct.

**But flag a pre-existing collision the lookup creates** (`mcp_dispatch.py:824`, `_idempotency_lookup` → `compute_idempotency_key(prompt, model, execution)` at `:706`): the key uses the **raw** `execution` arg, computed *before* `_resolve_effective_execution` runs (`dispatch_routing.py:204`). Two callers with `execution=""` — one in-session (→inline), one not (→subprocess) — share a key. A cached *subprocess* result could be returned to an inline caller. 8.2 touches exactly this path, so fix it here: resolve the engine first; if advisory, **skip both lookup and store** (move the advisory detection ahead of the line-824 lookup, or key on the *resolved* mode). Bypass is correct *and* the advisory caller must never receive a stale guarded result.

## (8) Judge tests I'd pin (7)

1. **Audit completeness:** one inline and one agent dispatch each write exactly one INTENT + one paired OUTCOME to the JSONL; OUTCOME `status=="advisory"`, `exit_code==0`, `error_code is None`.
2. **Sanitize boundary (both directions):** inject a fake secret into the prompt → assert it is **redacted** in the persisted audit prompt file / result `raw_output`, **and verbatim** in the **returned** plan's `prompt` field. Pins (2).
3. **Scope non-ambiguity:** returned inline/agent plan has `guarantees_scope=="advisory"` and `not_covered ⊇ {budget, circuit_breaker, cost_tracking, result_audit}`; a subprocess plan has `guarantees_scope != "advisory"`. Pins (3).
4. **Correlation:** the returned plan's `dispatch_id` equals the audit INTENT/OUTCOME `dispatch_id`. Pins (6).
5. **Fail-open + loud:** monkeypatch `record_intent`/`record_outcome` to raise → the plan is still returned intact AND a WARNING/ERROR is logged. Pins (5).
6. **No caching of advisory:** two identical inline dispatches yield **different** `execution_token` and `dispatch_id`, and `get_cached_result(key) is None` afterward. Pins (7).
7. **No reconcile false-positive:** after an advisory dispatch, `reconcile_stuck_intents()` reconciles **0** records (INTENT has its OUTCOME). Pins the two-phase completeness.

(If you bump `PLAN_SCHEMA_VERSION` to `"3"`, add an 8th asserting the version on advisory plans.)

---

**Bottom line:** the design is fundamentally sound — choke-point INTENT+immediate-OUTCOME with `status="advisory"`, scrub-on-persist-only, scope-honest envelope, fail-open. The holes worth fixing before code: (1B) no `engine` field exists — add one; (3) `guarantees_scope` must be on *all* builders and the bump rule contradicts itself; (4) you're leaving a real estimate-based budget gate unclaimed; (6) the dispatch_id injection forces an intent→mutate→outcome ordering at the choke point; (7) there's a pre-existing cross-mode cache-collision in the line-824 lookup to close while you're here.
