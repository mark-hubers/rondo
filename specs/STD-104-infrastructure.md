# STD-104: Infrastructure

*How Rondo handles persistence, concurrency, subprocess isolation, and security. The operational foundation for a stateless dispatch framework.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-005, Caliber-STD-104

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
- Build gate configuration (STD-101: Observability)
- Consumer-side storage (OB decides what to persist)

---

## 3. Requirements

### Spool Directory (Rondo's Persistence)

1. Rondo writes results to a spool directory — this is its ONLY persistence mechanism. No database, no SQLite, no state file.
2. Spool directory default: `reports/rondo-results/` relative to project root. Configurable via `paths.results_dir` in `rondo.toml`.
3. Each round execution creates a timestamped subdirectory: `{round-name}_{ISO-timestamp}/`. This is the atomic unit of persistence.
4. Within the execution directory, each task result is a separate JSON file: `task-{NN}-{task-name}.json`. Round summary is `round-summary.json`.
5. Spool files follow the mailbox pattern: write once, read many, delete on TTL expiry. Rondo never modifies a written result file.
6. Default TTL: 30 days. Cleanup is the consumer's responsibility — Rondo provides a `rondo cleanup --older-than 30d` command but does not auto-delete.
7. Spool directory MUST survive Rondo crashes. A crash mid-round leaves completed task files intact — only the round summary will be missing.

### Atomic File Writes

8. All file writes use the atomic pattern: write to a temp file in the same directory, then `os.rename()` to the final path. Never leave a partial file on disk.
9. Temp files use the pattern `{final-name}.tmp.{pid}` to avoid collisions between parallel workers.
10. If the rename fails (permissions, disk full), log at ERROR with the temp file path so data can be recovered manually.
11. JSON files are written with `indent=2` for human readability. Compact JSON is not worth the debugging cost.

### Worktree Isolation (Parallel Execution)

12. Parallel tasks that modify files MUST run in separate git worktrees. One worktree per concurrent task that needs file access.
13. Worktree creation: `git worktree add {path} --detach`. Path is `{project-root}/.rondo-worktrees/task-{NN}-{name}`.
14. Worktree cleanup: after the task completes (success or failure), remove the worktree with `git worktree remove {path}`. On failure, log at WARNING and leave the worktree for manual cleanup.
15. Tasks that only read files (no `tool_mode: "sandbox"`) do NOT need worktrees — they share the main working directory.
16. Worktree count MUST NOT exceed `config.parallel.workers`. The runner enforces this limit before creating new worktrees.

### Subprocess Isolation

17. Every `claude -p` dispatch runs as a subprocess with a controlled environment. The runner constructs the environment explicitly — no inheriting the full parent environment blindly.
18. `CLAUDECODE` MUST be stripped from the child environment. This prevents the nested-session guard from blocking dispatch. Non-negotiable.
19. `ANTHROPIC_API_KEY` handling depends on auth mode: stripped for `max` (use subscription), preserved for `api` (pay-per-token). See STD-102 rules 22-23.
20. Each subprocess gets its own working directory: the project root for sequential tasks, the worktree path for parallel tasks.
21. Subprocess arguments MUST be constructed as a list, never a string. No `shell=True` anywhere in Rondo. This prevents shell injection and ensures consistent argument parsing.

### Security

22. No hardcoded secrets in source — API keys, tokens, and credentials via environment variables only. Enforced by convention test (STD-103 rule 20).
23. Result files MUST NOT contain API keys. Before writing a TaskResult to spool, strip any environment variables from the `prompt_sent` field that might contain secrets.
24. Spool directory permissions: owner-read-write only (mode 0700 on the directory, 0600 on files). Result files may contain proprietary prompts and AI output.
25. Pre-commit hook: gitleaks MUST run to prevent secrets from being committed to git.
26. No network calls from Rondo itself — all network access happens inside the `claude -p` subprocess. Rondo is a local orchestrator that delegates network to Claude.

---

## 10. Rules & Constraints

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
| WAL mode / connection pooling | None | No database connections |
| HMAC payload signing | None | Local dispatch only, no remote transport |
| `--reimport` from files | N/A | Files are the primary store, not a backup |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-005 topics (persistence, concurrency, security) adapted for Rondo's stateless context. 26 requirements. Spool mailbox pattern, atomic writes, worktree isolation, subprocess environment control. No DB sections (Rondo has no database). |
