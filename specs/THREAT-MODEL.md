# Rondo Threat Model

**Created:** 2026-03-31 | **Status:** ACTIVE
**Spec:** STD-107 addendum H-17 to H-19

---

## Supported Environment

Rondo is designed for **macOS/*nix, single-user dev machines, Claude Code MCP stdio sessions.**

Rondo is per-user infrastructure. Each developer runs their own Rondo instance on their own machine, spawned by Claude Code via MCP stdio or localhost services, with their own `~/.rondo` state (audit, history, spool, retry, config) and their own API keys. There is no shared or multi-tenant deployment mode for Rondo; running it as a long-lived daemon or shared network service is explicitly unsupported and out of scope.

## What Rondo Can Do

- Execute `claude -p` as subprocess (local only)
- Execute Ollama API calls (localhost only)
- Read/write files in `~/.rondo/` and project directories
- Create launchd plists for scheduling
- Send macOS notifications via osascript

## What Rondo Does NOT Expose

- No arbitrary shell execution (subprocess uses list args, never shell=True)
- No arbitrary network access (Ollama locked to OLLAMA_HOST, Claude via local binary)
- No database access (stateless — JSONL files only)
- No remote API calls without explicit provider adapter

## Not In Scope

- Multi-tenant server deployment
- Untrusted network clients connecting to MCP
- Windows platform support (watchdog uses select() on pipes)
- Arbitrary code execution from MCP tool parameters (round files loaded by user, not MCP)

## Security Controls

| Control | Implementation |
|---------|---------------|
| Credential stripping | dispatch.prepare_env() strips CLAUDECODE + API keys |
| Output sanitization | sanitize.py scrubs secrets before storage |
| Path validation | engine.validate_task() rejects traversal + symlinks |
| AppleScript injection | notify._escape_applescript() escapes quotes |
| Input size limits | MCP tools cap prompt (500KB), chain (20), benchmark (10) |
| File permissions | Spool dir 700, spool files 600 |
| Audit trail | Append-only JSONL with file lock (fcntl) |
| Subprocess safety | List args, SIGTERM-first kill, stdin piping |

## Stricter Configuration

For restricted environments:
- Set `RONDO_ALLOW_MUTATIONS=false` to disable real dispatch via MCP
- Set `RONDO_TEST_DIR` to sandbox all file writes
- Use `--dry-run` for preview-only mode
