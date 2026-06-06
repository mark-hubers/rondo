# Stream-Ceiling Probe — Results (RONDO-329)

**Run:** 2026-06-06 09:01:11 → 09:07:59 | **Cost:** $0.1140 | **Outcome:** COMPLETED

## Setup

Identical workload to the 2026-06-05 incident: opus-4.8, effort **max**,
the 60KB essay-split prompt (`the-split-prompt-v2.md` + `draft-v7.md`),
1 cell, $2.00 hard cap. Spec: `ceiling-probe.yaml`.

## Result

| Metric | Value |
|--------|-------|
| Status | done (no disconnect) |
| Stream duration | 407.9s (~6.8 min) |
| Cost | $0.1140 |

## What this means for the ~30-min ceiling hypothesis

**One data point, not proof.** The incident stream died at ~1802s; this run
finished at 408s — in line with the wave-5 successful retries (445s, 462s).
Reading: the 1802s death was most plausibly **server-side variance on an
unusually long thinking trajectory**, not a hard wall every max-effort run
hits. Typical max-effort runs on this workload complete well under 10 min.

## Standing protections (regardless of ceiling reality)

- **RONDO-323:** a mid-stream disconnect now returns everything accumulated
  (`ERR_STREAM_DISCONNECT`, transient/retryable, partial in `raw_output`) —
  30 minutes of thinking can never evaporate again
- **Watchdog (req 214):** per-event silence detection distinguishes
  thinking-hard from hung at any duration

## Follow-up (only if it recurs)

If another dispatch dies near ~1800s, the audit forensics now capture
duration + partial — two such records would justify chunked/resumable
streaming work. Until then: handled, not chased.
