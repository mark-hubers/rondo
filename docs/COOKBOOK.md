# Rondo Cookbook — Real-World Scenarios

*Practical patterns for common dispatch situations. Each recipe is copy-paste ready.*

**See also:** `docs/GOLDEN-PATH.md` (first-time setup), `docs/RONDO-REFERENCE.md` (full system guide), `docs/EXAMPLE-VERIFICATION.md` (how to verify examples and prompt Claude to test)

**Coverage:** These recipes plus `examples/cli/README.md`, `examples/mcp/README.md`, and `examples/cli/scripted-prompting.sh` are intended to span **most real usage**: multi-provider review, health/metrics debugging, overnight batches, local models, auth recovery, cost control, chains, and background polling.

---

## Recipe 1: Multi-Provider Code Review (Get Consensus)

**Situation:** You want 2+ AI providers to independently review the same code, then merge findings.

**CLI:**
```bash
rondo review src/main.py                          # default: Gemini + Grok
rondo review src/main.py --providers gemini,mistral --tier high  # custom
rondo review src/main.py --dry-run                # preview without dispatching
```

**MCP (Claude Code):**
```
rondo_multi_review(
    prompt="Review this file for bugs and security issues.\n\n```python\n<file content>\n```",
    providers='["gemini:gemini-2.5-flash", "grok:grok-3"]',
    dry_run=False
)
```

**What you get back:** Per-provider findings + merged list. Each provider catches different things — Gemini is strong on architecture, Grok on edge cases, Mistral on security.

**Cost:** ~$0.01-0.05 per provider per file (depends on file size and model tier).

---

## Recipe 2: "RED Health But Providers Are Green"

**Situation:** `rondo_health` returns RED, but `rondo providers` shows all providers UP.

**What it means:** Health RED can mean:
- Recent dispatches failed (success rate < 50%)
- Audit trail has errors
- Spool has stale undelivered results

It does NOT mean providers are down. Health measures *your recent dispatch quality*, not provider availability.

**Debug steps:**
```bash
rondo metrics                    # see success rate + error breakdown
rondo audit --failed             # show which dispatches failed and why
rondo history --expensive        # check if costs are abnormal
rondo spool list                 # check for stuck results
rondo preflight                  # full environment check
```

**Common fixes:**
| Error code | Meaning | Fix |
|-----------|---------|-----|
| ERR_SUBPROCESS | Claude binary failed to start | Check `claude --version`, restart Claude Code |
| ERR_NESTED_SESSION | Can't dispatch from inside Claude Code | Use MCP tools instead of CLI |
| ERR_AUTH | API key missing or invalid | Check `rondo providers`, verify env vars |
| ERR_TIMEOUT | Task exceeded timeout | Add `--timeout 120` or simplify the task |
| ERR_RATE_LIMIT | Provider rate limited you | Wait, or switch to a different provider |

---

## Recipe 3: Overnight Batch with Morning Report

**Situation:** Run all your review/scan tasks overnight, get a summary in the morning.

**Setup:**
```bash
# Create a phases file (see examples/rounds/phases_overnight.py)
rondo overnight examples/rounds/phases_overnight.py --dry-run   # preview
rondo overnight examples/rounds/phases_overnight.py             # real run
```

**Schedule it:**
```bash
rondo schedule examples/rounds/phases_overnight.py --interval weekly --install
```

**Morning check:**
```bash
rondo spool consume              # pick up overnight results
cat reports/rondo-morning-*.md   # read the report
rondo metrics                    # check overall health
```

**Report fields:** Done count, error count, skipped count (new — shows tasks that didn't dispatch), cost, duration, action items with recovery suggestions.

---

## Recipe 4: Use Local Models ($0 Cost)

**Situation:** You want fast, free AI feedback for simple tasks (classify, scan, lint review).

**Requirements:** Ollama running locally (`ollama serve`).

```bash
rondo run round.py --model llama3.1:8b          # fast, free
rondo run round.py --model qwen2.5:32b          # better quality, still free
rondo run round.py --model local:deepseek-r1    # reasoning model
```

**MCP:**
```
rondo_run(file_path="scan.py", model="llama3.1:8b", dry_run=False)
```

**When to use local vs cloud:**
| Task type | Recommended | Why |
|-----------|-------------|-----|
| Quick scan/classify | Local 8B | Fast, free, good enough |
| Code review | Cloud (Gemini/Grok) | Needs reasoning depth |
| Security audit | Cloud (Mistral) | Needs domain knowledge |
| Architecture review | Cloud (Gemini Pro) | Needs broad context |
| Test generation | Local 32B | Good enough, saves money |

---

## Recipe 5: Auth Failure Recovery

**Situation:** Dispatch fails with ERR_AUTH.

**Step 1 — Identify which provider:**
```bash
rondo providers --json    # shows health + which are DOWN
```

**Step 2 — Check keys:**
```bash
# Environment variables
echo $GEMINI_API_KEY | head -c 8     # should show first 8 chars
echo $XAI_API_KEY | head -c 8
echo $MISTRAL_API_KEY | head -c 8

# Or check config
cat ~/.rondo/config.toml | grep -A 2 "providers"
```

**Step 3 — Test the provider directly:**
```bash
rondo run examples/rounds/round_hello.py --model gemini:gemini-2.5-flash
```

**Common causes:**
- Key expired or revoked → regenerate at provider's console
- Key in env but not in TOML → Rondo checks both, but env takes priority
- Wrong key format → some providers need `Bearer` prefix, Rondo handles this automatically
- Rate limited → wait or use a different provider

---

## Recipe 6: Cost Optimization

**Situation:** You're spending too much on AI dispatches.

**Check current spend:**
```bash
rondo metrics                         # total cost, per-model breakdown
rondo audit --cost                    # total + average per dispatch
rondo history --expensive             # top 10 most expensive dispatches
```

**Cost reduction strategies:**

1. **Use local models for simple tasks** — $0 for Ollama
2. **Use `--model haiku`** for Claude tasks that don't need Sonnet
3. **Use tier `low`** — `rondo review file.py --tier low` picks cheap models per provider
4. **Set cost caps** — `--max-budget 0.50` (API key auth only, not Max plan)
5. **Use dry-run first** — `--dry-run` is always free

**Provider cost comparison (approximate):**
| Provider | Cheap model | Cost/1K tokens |
|----------|------------|---------------|
| Ollama | llama3.1:8b | $0.00 |
| Gemini | gemini-2.5-flash | ~$0.0001 |
| Mistral | mistral-small | ~$0.0002 |
| Grok | grok-3-mini | ~$0.0003 |
| Claude | haiku | ~$0.0003 |
| OpenAI | gpt-4o-mini | ~$0.0002 |

---

## Recipe 7: Chaining Dispatches (Pipeline)

**Situation:** Output from one AI task feeds into the next.

**MCP (recommended):**
```
rondo_chain(
    steps='[
        {"prompt": "Scan this codebase for security issues", "model": "gemini:gemini-2.5-flash"},
        {"prompt": "For each issue found, suggest a fix with code", "model": "sonnet"}
    ]',
    dry_run=False
)
```

**How it works:** Step 1 output becomes Step 2 input automatically. Each step can use a different model — cheap model for scanning, expensive model for fixing.

---

## Recipe 8: Background Dispatch with Polling

**Situation:** Long-running task — dispatch and check back later.

**MCP:**
```
# Start
result = rondo_run(file_path="big_scan.py", background=True, dry_run=False)
dispatch_id = result["dispatch_id"]

# Poll cheaply (~10 tokens)
rondo_run_status(dispatch_id=dispatch_id, heartbeat=True)
# → {"s":"w","d":0,"e":0,"p":3}  (w=working, 3 pending)

# When done, get full results
rondo_run_status(dispatch_id=dispatch_id)
# → Full JSON with all task results
```

**Three polling tiers:**
| Tier | Flag | Tokens | Use when |
|------|------|--------|----------|
| Heartbeat | `heartbeat=True` | ~10 | Tight polling loop |
| Brief | `brief=True` | ~40 | Normal status check |
| Full | (default) | ~300+ | Task is done, get results |

---

*For the complete system guide, see `docs/RONDO-REFERENCE.md`.*
*For first-time setup, see `docs/GOLDEN-PATH.md`.*
