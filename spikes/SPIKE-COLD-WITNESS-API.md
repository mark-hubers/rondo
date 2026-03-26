# Spike: Cold Witness API Integration

**Date:** 2026-03-24
**Product:** Rondo
**Status:** SPIKE (prototype ready, API key needed)

---

## What We're Proving

Can we automate the Gemini "Cold Witness" spec review that found 79 findings in Session 85, making it:
1. Scriptable (CLI call, not manual web chat)
2. Repeatable (same prompt = same reviewer persona every time)
3. Cheap ($0.005/spec with flash, ~$1.25 for all 250 specs)
4. Integrated into Rondo dispatch pipeline

## What Already Works

| Component | Status | Location |
|-----------|--------|----------|
| Gemini API call pattern | PROVEN (spike S45, S56) | `caliber/spikes/engine/witness-spike.py` |
| Cold Witness prompt | SAVED | `~/.claude/prompts/cold-witness.md` |
| Spec review script | BUILT | `scripts/gemini_spec_review.py` |
| 17-pattern convergence matrix | IN PROMPT | Covers all review patterns |

## Three Approaches

### Approach A: Standalone CLI (built, ready to test)
```bash
## Review one spec
gemini-spec-review orbital/specs/OB-REQ-105-finding-management.md

## Review all OB specs
gemini-spec-review orbital/specs/ --product OB --save

## Review everything (~$1.25)
gemini-spec-review --batch all --save
```
**Pro:** Simple, immediate, no infrastructure needed.
**Con:** Sequential (1 req/sec rate limit), no parallelism.

### Approach B: Rondo Batch Dispatch
```python
## rondo dispatches N specs to Gemini in parallel
rondo dispatch --task spec-review --provider gemini-2.5-flash \
    --input orbital/specs/ --max-concurrent 5
```
**Pro:** Parallel (5x faster), cost tracking, retry handling built into Rondo.
**Con:** Requires Rondo dispatch engine (not built yet — Step 4 in build order).

### Approach C: Overnight Batch via Claude Batch API + Gemini
```python
## Submit all 250 specs as a batch, collect results in morning
rondo overnight --task spec-review --provider gemini-2.5-flash
```
**Pro:** Fire and forget, results in morning report. Cheapest (batch pricing).
**Con:** Requires both Rondo overnight mode AND Gemini batch API (if available).

## Recommendation

**Start with Approach A** (already built). Test with 5 specs. Validate findings quality. Then:
- If findings are useful → use it as a regular review gate
- When Rondo dispatch is built (Step 4) → migrate to Approach B
- When overnight mode works → add as nightly job (Approach C)

## Setup Steps

1. Get Gemini API key (Google AI Studio: https://aistudio.google.com/apikey)
2. Save key:
   ```bash
   echo 'export GEMINI_API_KEY="your-key"' >> ~/.claude/.env-keys
   source ~/.claude/.env-keys
   ```
3. Test with one spec:
   ```bash
   gemini-spec-review orbital/specs/OB-REQ-100-orbital-database.md --verbose
   ```
4. Batch review:
   ```bash
   gemini-spec-review --batch all --save --model gemini-2.5-flash
   ```

## Cost Model

| Model | Per Spec | All 250 | Per Month (weekly) |
|-------|----------|---------|-------------------|
| gemini-2.5-flash | $0.005 | $1.25 | $5.00 |
| gemini-2.5-pro | $0.04 | $10.00 | $40.00 |
| gemini-2.5-flash-lite | $0.002 | $0.50 | $2.00 |

## Integration with Existing Review

The Cold Witness is ONE reviewer. The full review pipeline:
1. **Convergence Scanner** (local, free) — 17 pattern checks, 100% coverage
2. **Cold Witness** (Gemini API, ~$1.25) — adversarial structural review
3. **Claude Deep Review** (in-session) — content quality, cross-ref validation
4. **Human Review** (Mark) — final decisions on CRITICAL findings

Each catches different things. Different AI = different blind spots.

---

*"The cheapest token is the one you never send." — Gemini Cold Witness, Session 85*
