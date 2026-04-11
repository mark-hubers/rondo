# Try Rondo — Zero to First Review in 10 Minutes

*You've never seen this project. Here's how to go from clone to successful AI dispatch.*

**Requirements:** Python 3.12+, Claude Code (Max plan OR API key)

---

## Step 1: Install (1 minute)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Rondo — one command, fully isolated, no venv dance
uv tool install rondo --from git+https://github.com/<owner>/ace2.git#subdirectory=rondo

# Verify
rondo --version
rondo preflight
```

That's it. `uv tool install` creates an isolated environment — no venv activation, no pip, no dependency conflicts. `rondo` is on your PATH.

**Alternative install methods** (if uv is blocked in your environment):
```bash
# pipx (similar isolation to uv)
pipx install rondo

# pip (global — last resort)
pip install --user rondo
```

**For developers** (editable install for contributing):
```bash
git clone <repo-url>
cd ace2/rondo
uv tool install --editable . --force
```

**Expected:** Version number + preflight shows GREEN or YELLOW (RED = fix first).

## Step 2: Run the Smoke Test (1 minute)

From the **rondo repo root** (or use absolute paths):

```bash
# Dry-run — no AI calls, no cost
rondo run examples/rounds/round_hello.py --dry-run

# Expected output:
# skipped: … (dry-run, no dispatch)
```

If this works, Rondo is installed correctly.

## Step 3: Real Dispatch (2 minutes)

```bash
# Uses your Claude Code session — $0 on Max plan
rondo run examples/rounds/round_hello.py

# Expected: "done: ..." with a response from Claude
```

**If it fails:**
| Error | Fix |
|-------|-----|
| ERR_NESTED_SESSION | You're inside Claude Code. Use MCP tools instead (Step 5) |
| ERR_AUTH | Set ANTHROPIC_API_KEY or ensure Max plan active |
| ERR_SUBPROCESS | Run `rondo preflight --json` for diagnostics |

## Step 4: Review a File with Cloud Providers (3 minutes)

```bash
# Configure at least one cloud provider
rondo init --config
# Edit ~/.rondo/config.toml — add your GEMINI_API_KEY

# Check it works
rondo providers

# Review a file
rondo review src/rondo/engine.py --dry-run   # preview
rondo review src/rondo/engine.py             # real dispatch to Gemini + Grok
```

**Expected:** Per-provider findings with [PASS/FAIL] status.

## Step 5: MCP Tools (If Using Claude Code) (2 minutes)

If Rondo is in your Claude Code MCP config, ask Claude:

> "Use rondo to check the health of my dispatch system"

Claude calls `rondo_health` automatically. Then:

> "Use rondo to review src/main.py with Gemini"

Claude calls `rondo_review_file` with the right parameters.

**22 MCP tools available** — see `rondo --ai-help` for the full list.

---

## What Just Happened

```
You wrote a Task        → Rondo dispatched it      → You got structured results
(instruction + done_when)  (to Claude/Gemini/Grok)    (status, cost, output, errors)
```

That's the entire model. Everything else (overnight batches, multi-provider review, threshold alerting, audit trails) builds on this.

---

## If Something Goes Wrong

```bash
rondo preflight              # environment check
rondo preflight --json       # machine-readable
rondo metrics                # dispatch health
rondo history                # recent dispatches
rondo audit --failed         # failed dispatches with details
```

Every error includes a recovery suggestion (ErrorPayload). The morning report (`reports/rondo-morning-*.md`) summarizes overnight runs.

---

## Next Steps

| Goal | Read |
|------|------|
| Understand the full system | `docs/RONDO-REFERENCE.md` |
| Common patterns and recipes | `docs/COOKBOOK.md` |
| Quick setup guide | `docs/GOLDEN-PATH.md` |
| Security model | `specs/THREAT-MODEL.md` |
| How the code is structured | 42 files, 4 layers: engine → dispatch → runner → overnight |

---

## Failure Recipes

**"Rondo says RED but my providers are UP"**
→ See Cookbook Recipe 2. Health measures YOUR dispatch quality, not provider availability.

**"I get ERR_NESTED_SESSION every time"**
→ You're running `rondo run` from inside Claude Code. Use MCP tools instead (`rondo_run`).

**"Config changes don't take effect"**
→ Config is loaded once at startup. Restart Claude Code to pick up TOML changes.

**"Overnight report says 0 errors but nothing ran"**
→ Tasks were "skipped" (dry-run or gate block). Check the Skipped count in the report.

---

*This file is for strangers. If you're Mark, use `docs/GOLDEN-PATH.md` instead.*
