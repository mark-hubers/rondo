# Reliability Triage — the 85% Alert — 2026-06-06

**Trigger:** First sweep of the newly ARMED watchdog
(`com.rondo.nightly-watchdog`) alerted: 7-day success rate 85% vs 95%
target (62 dispatches).
**Verdict: NO live bug.** Dominant cause was already fixed before the
alert fired; the meter's 7-day lookback is still digesting it.

---

## TL;DR

| Question | Answer |
|----------|--------|
| Are 404s still happening? | **NO** — live repro of the exact failing command passes (exit 0) |
| Was the meter wrong? | No — 52 done + 1 partial of 62 ≈ 85%. Honest meter, old corpses |
| Anything actually broken now? | Only a transient ERR_AUTH class (3 of 10 failures) — sprint candidate |
| When does the number recover? | By 2026-06-13 the morning failures roll out of the window |

---

## The 10 failures in the window, classified

| Count | Signature | Models | Verdict |
|-------|-----------|--------|---------|
| 5 | Gemini HTTP 404 — provider prefix not stripped from model in URL (`models/gemini:gemini-flash-latest`) | gemini:gemini-flash-latest | FIXED before alert (see timeline) |
| 3 | ERR_AUTH — "session auth lost: detected 'Invalid API key' in subprocess output" | sonnet ×2 (probe, 06-05), haiku ×1 (06-06 04:11) | Residual transient class — recommendation 2 |
| 1 | ERR_MALFORMED_JSON | haiku (summarize-readme) | Envelope caught it honestly — working as designed |
| 1 | ERR_PROVIDER, empty message | claude-opus-4-8 (06-03) | One-off, no pattern |

## Timeline that explains the 404s (all times CDT, 2026-06-06)

| Time | Event |
|------|-------|
| 08:20–08:41 | 5 golden-five commands (`rondo "Reply with exactly: OK" --model gemini:gemini-flash-latest` et al.) run against the INSTALLED uv tool → 404 |
| (prior state) | Installed build predated RONDO-328 — the campaign sprint that found this exact 404 live and fixed it (`_provider_task_result` strips prefix via `parse_model` before adapter dispatch, src/rondo/cli.py) |
| 16:00 | Installed tool refreshed from fixed source (file mtime ~/.local/share/uv/tools/rondo/.../cli.py; RONDO-328 strip code verified present in site-packages) |
| 18:02 | Live repro: same command verbatim → `"result": "OK"`, exit 0 |
| 18:0x | Audit trail confirms zero 404s after 08:41 |

## Why the dossier matters: the audit trail did its job

Every failure carried dispatch_id, model, error_code, prompt file, and
timestamps in `~/.rondo/audit/rondo_audit.jsonl` — the entire diagnosis
was archaeology, zero guesswork. The INTENT rows (62 in window) are
write-ahead records, not failures; reliability math uses completed
dispatches only.

## Recommendations (Mark decides)

1. **404s: no action.** Re-check `rondo nightly` after 2026-06-13;
   expected recovery to ≥95% as the window rolls.
2. **Sprint candidate:** auto-retry ×1 (or guided failure) for the
   ERR_AUTH session-loss class — sibling of RONDO-334's
   ERR_STREAM_DISCONNECT retry. 3 of 10 window failures.
3. **Cosmetic:** installed tool reports `0.7.0+20260421.1` — build
   stamp is April despite June code (`rondo version --bump` is not part
   of the install flow). Honesty nit, not a bug.
