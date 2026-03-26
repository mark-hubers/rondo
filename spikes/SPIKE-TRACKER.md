# Rondo Spike Tracker

**Purpose:** What each spike proved, where it diverged from specs, and what the builder should know.

**Rule:** Spikes are prototypes. Production code in `rondo/src/` is built fresh from specs, not copied from spikes. (Session 75 decision)

---

## Spike Inventory

| File | Lines | Created | Spec Coverage |
|------|-------|---------|--------------|
| `engine.py` | 505 | Session 74-75 | REQ-001 reqs 1-11 (Engine) |
| `dispatch.py` | 344 | Session 75 | REQ-001 reqs 12-28 (Dispatch) + ACE-IFS-001 partial |
| `runner.py` | ~300 | Session 75 | REQ-001 Runner layer |
| `parallel.py` | ~250 | Session 75 | REQ-002 reqs 1-9 (Parallel) |
| `overnight.py` | ~200 | Session 75 | REQ-002 reqs 10-18 (Overnight) |
| `report.py` | ~170 | Session 75 | REQ-002 reqs 29-36 (Morning Report) |
| `rounds/` (8 files) | ~44k | Session 75 | Consumer round definitions (OB-specific, not Rondo core) |

---

## What Each Spike Proved

### engine.py — REQ-001 Engine

**Proved:**
- Round/Task/Gate data model works (reqs 1-5)
- Pre-gate blocking halts round (req 6)
- Post-gates after all tasks (req 7)
- Task state machine transitions (req 8)
- Serialization to JSON + resume from JSON (reqs 10-11)
- Three-field contract (Do/Read/Done) works as task API (req 3)
- Auto tasks with Python callables work (req 4)

**Diverged from specs:**
- Uses `PASSED/FAILED/SKIPPED` status — spec now says `done/blocked/partial/error/skipped`
- Imports `ob_queries`, writes to `planning_rounds` — spec says Rondo has NO database
- `Gate` has `description` and `passed` state fields — spec's `Gate` is simpler, `GateResult` is separate
- `Task.model` defaults to `"sonnet"` — spec says `None` (let COALESCE handle it)

### dispatch.py — REQ-001 Dispatch + ACE-IFS-001

**Proved:**
- `claude -p` subprocess invocation works (req 12)
- CLAUDECODE + ANTHROPIC_API_KEY env stripping works (reqs 13, 17-18)
- Auth switching (max vs api) works (req 19)
- Model routing via `--model` flag works (reqs 20-23)
- JSON parsing from Claude output works (reqs 25-26)
- Exit code error handling works (req 27)
- Dry-run mode works (req 16)
- Temp file delivery for long prompts works
- Result saved to JSON file (req 15)

**Diverged from specs:**
- Returns plain dict, not `TaskResult` dataclass (STD-001)
- Uses `text` output format, not `stream-json` (ACE-IFS-001)
- No `files_modified` extraction (STD-001/STD-003)
- No cost/token/rate_limit capture (ACE-IFS-001 reqs 2-9)
- Uses `subprocess.run(timeout=300)` — spec says use `Popen` with SIGTERM-first (STD-001)
- Hardcodes `timeout=300`, not configurable (STD-002)

### runner.py — REQ-001 Runner

**Proved:**
- Sequential task dispatch works end-to-end
- Result collection and summary generation works
- Spec discovery (finding all OB specs) works

**Diverged from specs:**
- No `RoundResult` return object (REQ-001)
- No `DispatchUsage` metadata (REQ-001)
- Tightly coupled to OB spec file paths

### parallel.py — REQ-002 Parallel

**Proved:**
- `ThreadPoolExecutor` with configurable workers works (reqs 1-2)
- Throttle between launches works (req 3)
- `as_completed` result collection works (req 4)
- Basic conflict detection works (reqs 5-6)
- Single failure doesn't crash others (req 8)
- Speedup ratio calculation works (req 7)

**Diverged from specs:**
- No `files_modified` field — conflict detection is basic string matching
- No `DispatchUsage` per task
- No worktree isolation (reqs 37-41)

### overnight.py — REQ-002 Overnight

**Proved:**
- Phase-based sequential execution works (reqs 10-11)
- Phase failure doesn't block next (req 12)
- Rolling event log works (req 18)
- No interactive input needed (req 16)
- Event logging with timestamps works (req 17)

**Diverged from specs:**
- Hardcodes OB round names — spec says configurable modes (reqs 13-15)
- No watchdog (reqs 19-23)
- No usage threshold gating (reqs 24-28)
- No rate limit backoff (req 22)

### report.py — REQ-002 Morning Report

**Proved:**
- Result file aggregation works (req 29)
- Grouping by round type works (req 30)
- Dated filename generation works (req 34)

**Diverged from specs:**
- No health indicators (req 32)
- No action items from failures (req 33)
- No usage summary (req 36)
- No totals or timestamp (req 35)

---

## Spike-Only Features (NOT in specs — may inform future work)

| Feature | File | Notes |
|---------|------|-------|
| Temp file delivery for long prompts | `dispatch.py` | Good idea — consider for REQ-001 |
| OB spec discovery (`_find_ob_specs`) | `runner.py` | Consumer-specific, not Rondo core |
| 8 round definitions | `rounds/` | OB consumer code, not Rondo |
| DB recording to `planning_rounds` | `engine.py` | Consumer responsibility, not Rondo |

---

## Builder Notes

1. **Start from specs, not spikes.** The specs are authoritative. Spikes proved concepts.
2. **Status vocabulary changed.** Every `PASSED` → `done`, every `FAILED` → check which of `blocked/partial/error` fits.
3. **Stream-json is mandatory.** Spikes used text mode. Production uses `--output-format stream-json` for metadata.
4. **No DB in Rondo.** Engine spike writes to `planning_rounds` — that's consumer code. Rondo returns `RoundResult`.
5. **Kill sequence changed.** `subprocess.run(timeout=)` sends SIGKILL. Production uses `Popen` + SIGTERM → 5s → SIGKILL.
6. **`rounds/` are OB consumer code.** They stay as reference but don't go in `rondo/src/`.

---

## Change History

| Date | What |
|------|------|
| 2026-03-14 | Created — spike-to-spec gap analysis from deep review (Session 76) |
