# Rondo-STD-104: Infrastructure

*How Rondo handles persistence, concurrency, subprocess isolation, and security. The operational foundation for a stateless dispatch framework.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-005, Rondo-STD-104 (Caliber)
**Depends on:** CORE-STD-005, CORE-STD-012, CORE-STD-021, Rondo-STD-100, CORE-STD-013

---

## 1. Purpose & Scope

Defines the infrastructure rules for Rondo: spool-based persistence (no database), subprocess isolation via worktrees, atomic file writes, and security requirements. Rondo is stateless — it has no database, no migrations, no abstraction layer. Its infrastructure is the filesystem and subprocess management.

**IN scope:**
- Spool directory persistence (mailbox pattern, TTL)
- Worktree creation and cleanup for parallel tasks
- Atomic file writes to spool
- Subprocess isolation (environment, working directory)
- Security (API keys, secrets, file permissions)

**OUT of scope:**
- Database abstraction (Rondo has no DB — CORE-STD-005 domain)
- Backup and migration (Rondo has no schema — CORE-STD-005 domain)
- Build gate configuration (Rondo-STD-101: Observability)
- Consumer-side storage (OB decides what to persist)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo orchestrates subprocesses that can modify files, consume API resources, and interact with the filesystem. Without infrastructure discipline — atomic writes, worktree isolation, file permission enforcement — a crash mid-dispatch can corrupt spool files, a parallel task can modify the main repo, and a misconfigured subprocess can leak secrets.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Spool Directory (Rondo's Persistence)
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL rondo writes results to a spool directory — this is its ONLY persistence mechanism. No database, no SQLite, no state file | MUST |
| 002 | System SHALL spool directory default: `reports/rondo-results/` relative to project root. Configurable via `paths.results_dir` in `rondo.toml` | MUST |
| 003 | System SHALL each round execution creates a timestamped subdirectory: `{round-name}_{ISO-timestamp}/`. This is the atomic unit of persistence | MUST |
| 004 | System SHALL within the execution directory, each task result is a separate JSON file: `task-{NN}-{task-name}.json`. Round summary is `round-summary.json` | MUST |
| 005 | System SHALL spool files follow the mailbox pattern: write once, read many, delete on TTL expiry. Rondo never modifies a written result file | MUST |
| 006 | System SHALL default TTL: 30 days. Cleanup is the consumer's responsibility — Rondo provides a `rondo cleanup --older-than 30d` command but does not auto-delete | MUST |
| 007 | Spool directory MUST survive Rondo crashes. A crash mid-round leaves completed task files intact — only the round summary will be missing | MUST |

### Atomic File Writes
| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | System SHALL all file writes use the atomic pattern: write to a temp file in the same directory, then `os.rename()` to the final path. Never leave a partial file on disk | MUST |
| 009 | System SHALL temp files use the pattern `{final-name}.tmp.{pid}` to avoid collisions between parallel workers | MUST |
| 010 | System SHALL if the rename fails (permissions, disk full), log at ERROR with the temp file path so data can be recovered manually | MUST |
| 011 | System SHALL jSON files are written with `indent=2` for human readability. Compact JSON is not worth the debugging cost | MUST |

### Worktree Isolation (Parallel Execution)
| ID | Requirement | Priority |
|----|-------------|----------|
| 012 | Parallel tasks that modify files MUST run in separate git worktrees. One worktree per concurrent task that needs file access | MUST |
| 013 | System SHALL worktree creation: `git worktree add {path} --detach`. Path is `{project-root}/.rondo-worktrees/task-{NN}-{name}` | MUST |
| 014 | System SHALL worktree cleanup: after the task completes (success or failure), remove the worktree with `git worktree remove {path}`. On failure, log at WARNING and leave the worktree for manual cleanup | MUST |
| 015 | System SHALL tasks that only read files (no `tool_mode: "sandbox"`) do NOT need worktrees — they share the main working directory | MUST |
| 016 | Worktree count MUST NOT exceed `config.parallel.workers`. The runner enforces this limit before creating new worktrees | MUST |

### Subprocess Isolation
| ID | Requirement | Priority |
|----|-------------|----------|
| 017 | System SHALL every `claude -p` dispatch runs as a subprocess with a controlled environment. The runner constructs the environment explicitly — no inheriting the full parent environment blindly | MUST |
| 018 | `CLAUDECODE` MUST be stripped from the child environment. This prevents the nested-session guard from blocking dispatch. Non-negotiable | MUST |
| 019 | System SHALL `ANTHROPIC_API_KEY` handling depends on auth mode: stripped for `max` (use subscription), preserved for `api` (pay-per-token). See Rondo-STD-109 (auth mode setting; was STD-102 rules 22-23 pre-merge) | MUST |
| 020 | System SHALL each subprocess gets its own working directory: the project root for sequential tasks, the worktree path for parallel tasks | MUST |
| 021 | Subprocess arguments MUST be constructed as a list, never a string. No `shell=True` anywhere in Rondo. This prevents shell injection and ensures consistent argument parsing | MUST |

### Security
| ID | Requirement | Priority |
|----|-------------|----------|
| 022 | System SHALL no hardcoded secrets in source — API keys, tokens, and credentials via environment variables only. Enforced by convention test (Rondo-STD-103 rule 20) | MUST |
| 023 | Result files MUST NOT contain API keys. Before writing a TaskResult to spool, strip any environment variables from the `prompt_sent` field that might contain secrets | MUST |
| 024 | System SHALL spool directory permissions: owner-read-write only (mode 0700 on the directory, 0600 on files). Result files may contain proprietary prompts and AI output | SHOULD |
| 025 | Pre-commit hook: gitleaks MUST run to prevent secrets from being committed to git | MUST |
| 026 | System SHALL no network calls from Rondo itself — all network access happens inside the `claude -p` subprocess. Rondo is a local orchestrator that delegates network to Claude | MUST |

---
## 4. Architecture / Design

Two infrastructure layers: (1) spool directory management (create, write atomically, enforce permissions, TTL cleanup), (2) worktree lifecycle (create per parallel task, set as subprocess cwd, cleanup on completion). Both layers are managed by the runner, not the dispatch module. Dispatch receives a working directory and writes to a spool path — it does not manage infrastructure directly.

---

## 5. Data Model

No dedicated data model. Infrastructure state is the filesystem: spool directories, worktree paths, temp files. The `.cleanup-marker` file in the spool root tracks last cleanup timestamp. Worktree state is managed by git (`.git/worktrees/`).

---

## 6. Data Boundary

Spool files are the data boundary between Rondo and consumers. Rondo writes to the spool directory; consumers read from it. Worktrees are internal to Rondo — consumers never interact with worktrees. The spool directory path is the only infrastructure detail exposed to consumers.

---

## 7. MCP / API Interface

No MCP interface for infrastructure. Spool directory is accessed via filesystem, not API. CORE-STD-021 MCP tools that query results read from consumer-side stores (OB database), not directly from Rondo's spool directory.

---

## 8. States & Modes

Worktrees have three states: creating, active (subprocess running), cleanup. Spool files have two states: writing (temp file) and complete (renamed to final path). Failed renames leave temp files for manual recovery. Startup scan removes orphaned worktrees from previous crashes.

---

## 9. Configuration

Infrastructure config in `rondo.toml`: `paths.results_dir` (spool root), `parallel.workers` (worktree limit). File permissions are fixed (0700 directory, 0600 files) and not configurable — security over convenience. Cleanup TTL is a CLI argument, not config.

---

## 10. Rules
**Stateless consistency (CRIT fix):** STD-104 req 001 says 'no database.' `break_glass_events` is a SHARED table (owned by CORE-STD-015, stored in Postgres), NOT a Rondo-local database. Rondo WRITES to it via the shared DB connection but does NOT own a local DB. Spool directory remains the ONLY Rondo-local persistence. The shared Postgres connection is infrastructure, not Rondo state. & Constraints

### Spool Directory Layout

```
reports/rondo-results/                     # spool root
├── health-check_2026-03-18T03-00-00Z/     # one dir per round execution
│   ├── round-summary.json                 # RoundResult as JSON
│   ├── task-01-spec-health.json           # TaskResult + DispatchUsage
│   ├── task-02-digest-refresh.json
│   └── task-03-convention-check.json
├── overnight-batch_2026-03-18T04-00-00Z/
│   ├── round-summary.json
│   ├── task-01-phase-1.json
│   └── task-02-phase-2.json
└── .cleanup-marker                        # tracks last cleanup run
```

### Atomic Write Sequence

```
1. Create temp file: task-01-spec-health.json.tmp.12345
2. Write full JSON content to temp file
3. Flush and fsync
4. os.rename(temp_path, final_path)           # atomic on same filesystem
5. If rename fails → log ERROR, preserve temp file
```

### Worktree Lifecycle

```
1. Runner decides task needs file access (tool_mode != "none")
2. Check worktree count < config.workers
3. git worktree add .rondo-worktrees/task-01-check --detach
4. Set subprocess cwd to worktree path
5. Dispatch task
6. Task completes (any status)
7. git worktree remove .rondo-worktrees/task-01-check
8. If remove fails → WARNING, leave for manual cleanup
```

### What Rondo Does NOT Have (vs CORE-STD-005)

| CORE-STD-005 Has | Rondo Equivalent | Why |
|----------------|-----------------|-----|
| Database abstraction (Postgres/SQLite) | None | Rondo is stateless — spool files only |
| Schema migrations | None | No schema to migrate |
| Backup strategy | Spool files ARE the backup | Consumer imports from spool |
| Database connections / pooling | None | No database — JSONL spool files only |
| HMAC payload signing | None | Local dispatch only, no remote transport |
| `--reimport` from files | Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. | Files are the primary store, not a backup |

---

## 11. Quality Attributes

- **Crash safety:** Atomic writes ensure no partial spool files. Completed task files survive mid-round crashes.
- **Isolation:** Parallel tasks cannot interfere — separate worktrees, separate environments.
- **Recoverability:** Temp files preserved on write failure. Orphaned worktrees cleaned on startup.

---

## 12. Shared Patterns

- **Atomic write:** write-to-temp + rename. Same pattern used in ACE knowledge engine and OB spool writes.
- **Mailbox pattern:** Write-once, read-many, delete-on-TTL. Standard message queue pattern adapted for filesystem.
- **Worktree isolation:** git worktrees for parallel subprocess safety. Shared with Caliber's parallel scan approach.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo spool → OB | Result JSON files | Rondo-STD-100 field naming, Rondo-STD-104 file permissions |
| Rondo worktrees → git | Worktree create/remove | git worktree CLI contract |
| Rondo spool → Caliber | Task result files for quality verification | Rondo-STD-100 schema |
| Rondo spool → CORE-STD-013 | Spool events as TrackerData | Append-only pattern |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-005 | Parent infrastructure standard — Rondo adapts persistence, concurrency, security for stateless context |
| CORE-STD-012 | Requirement readiness — infrastructure availability is a prerequisite |
| CORE-STD-013 | TrackerData — spool write events are trackable |
| CORE-STD-021 | MCP standard — spool data accessed via consumer MCP tools, not directly |

---

## 15. Self-Correction

Infrastructure does not self-correct. Spool writes are deterministic — same input, same output. Worktree management follows a fixed lifecycle. If infrastructure fails (disk full, permissions wrong), it reports the error and stops. Recovery is operator action, not automation.

---

## 16. Assumptions

1. Spool directory and final file are on the same filesystem (required for atomic `os.rename()`).
2. Git is available and the project is a git repository (required for worktrees).
3. Filesystem supports POSIX permissions (mode 0700, 0600).
4. Disk space is sufficient — Rondo does not check disk space before writes.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Mid-round crash → completed task files intact | Crash test (kill mid-run) |
| 2 | Parallel tasks → no file conflicts | Parallel execution test |
| 3 | Orphaned worktrees cleaned on startup | Startup scan test |
| 4 | Spool files have 0600 permissions | Permission test |

---

## 18. Build Notes / Estimate

Atomic writer: 2 hours (temp file, rename, error handling). Worktree manager: 3 hours (create, track, cleanup, orphan scan). Permission enforcement: 1 hour. Cleanup command: 1 hour. Total: ~7 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Atomic write tests | Temp file creation, rename, failure recovery |
| Worktree tests | Create, subprocess cwd, cleanup, orphan detection |
| Permission tests | Directory 0700, file 0600 enforcement |
| Cleanup tests | TTL expiry, marker file update |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Disk full during write | Temp file left, no final file | Error logged with temp path for manual recovery |
| Worktree remove fails | Orphaned worktree consumes space | Startup scan + WARNING log |
| Permission denied | Spool write fails | Error at startup if directory not writable |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Infrastructure guards (spool permissions, atomic write enforcement, worktree isolation) can be relaxed under DR mode with human approval for emergency spool recovery.

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-005 | Parent infrastructure standard |
| Depends on | CORE-STD-012 | Infrastructure readiness prerequisites |
| Used by | Rondo-STD-101 | Spool files store observability data |
| Used by | Rondo-STD-107 | Security rules for file permissions and subprocess isolation |
| Used by | Rondo-REQ-101 | Parallel execution uses worktrees |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Spool, not database | Rondo is stateless — filesystem persistence matches the design | 2026-03-18 |
| D2: Atomic writes via rename | Standard POSIX pattern — no partial files on crash | 2026-03-18 |
| D3: Worktrees, not containers | Lower overhead for local execution. Containers for future remote dispatch. | 2026-03-18 |

---

## 23. Open Questions

None currently. Spool pattern and worktree lifecycle are proven in production.

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Spool directory** | Filesystem directory where Rondo writes result files (mailbox pattern) |
| **Atomic write** | Write to temp file + rename — ensures no partial files |
| **Worktree** | git worktree providing isolated working directory for parallel tasks |

---

## 25. Risk / Criticality

**MEDIUM.** Infrastructure failures are visible (error logs, missing files) and recoverable (temp files, orphan cleanup). The main risk is silent permission misconfiguration that exposes spool files containing proprietary prompts.

---

## 26. External Scan

Atomic write via rename is a POSIX standard. Git worktrees are a built-in git feature. Mailbox pattern is decades old (Unix mail spool). No novel infrastructure approaches — proven patterns applied to dispatch context.

---

## 27. Security Considerations

Spool directory: 0700 (owner-only access). Spool files: 0600 (owner read/write). Worktrees inherit repo permissions. Subprocess environment is explicitly constructed — no blind inheritance. See Rondo-STD-107 rules 10, 14, 22-24 for full security requirements.

---

## 28. Performance / Resource

Worktree creation: ~100ms (git worktree add). Atomic write: ~5ms (write + fsync + rename). Spool directory scan for cleanup: ~10ms per 1000 files. Worktree disk cost: ~50MB per worktree (shallow copy). Maximum worktrees limited by `config.parallel.workers`.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) treats infrastructure availability as a gating condition — dispatch cannot proceed if the spool directory is not writable. CORE-STD-013 (TrackerData) can track spool write events for operational monitoring. CORE-STD-021 MCP tools read from consumer stores, not directly from Rondo spool.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Infrastructure standards | THEORY | Specced for deployment infrastructure | Phase 2 build |
| Container standards | THEORY | Specced for container conventions | Phase 2 build |
| Resource limits | THEORY | Specced for CPU/memory constraints | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-005 topics (persistence, concurrency, security) adapted for Rondo's stateless context. 26 requirements. Spool mailbox pattern, atomic writes, worktree isolation, subprocess environment control. No DB sections (Rondo has no database). |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
| 0.3 | 2026-03-31 | Session 93: ~/.rondo/ data directory layout. 6 new reqs (027-032). |

---

## ~/.rondo/ Data Directory Layout (Session 93)

All persistent Rondo runtime data lives in `~/.rondo/`. Separate from project-level results.

```
~/.rondo/
├── audit/                  # Dispatch audit trail (STD-113)
│   ├── rondo_audit.jsonl   # Append-only JSONL
│   ├── dsp_*.prompt.txt    # Saved prompts
│   ├── dsp_*.result.json   # Saved results
│   └── archive/            # Rotated monthly files
├── spool/                  # Overnight mailbox (REQ-101)
├── logs/                   # Scheduled run logs
└── build-counter.json      # CalVer build number
```

| # | Requirement | Priority |
|---|-------------|----------|
| 027 | All persistent Rondo runtime data MUST be in `~/.rondo/` | MUST |
| 028 | `~/.rondo/` auto-created on first write | MUST |
| 029 | Subdirectories auto-created on first write | MUST |
| 030 | Session-scoped temp data MAY use `/tmp/` | MAY |
| 031 | Scheduled run logs MUST go to `~/.rondo/logs/`, NOT `/tmp/` | MUST |
| 032 | `RONDO_TEST_DIR` redirects ALL `~/.rondo/` paths to test tmp | MUST |
