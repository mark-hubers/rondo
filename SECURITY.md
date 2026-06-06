# Security

> **Status:** pre-release draft (RONDO-337). LICENSE and disclosure contact
> are the owner's call and intentionally not set here yet.

## Threat model — what Rondo defends against, by design

| Surface | Defense | Proven by |
|---------|---------|-----------|
| **API keys** | Loaded env-first (`OPENAI_API_KEY`, ...), then macOS Keychain, then 1Password. Never read from the config file. Shown last-4 only (doctor, logs) | `tests/unit/test_auth*` |
| **Secrets in artifacts** | Every prompt/result/error is scrubbed before any disk write (20+ provider key patterns). The guarantee is ARTIFACT-level: tests plant realistic keys at every ingress and sweep every file written — zero survivors or the suite fails | `tests/unit/test_redaction_guarantee.py` |
| **Downloaded round files** | `.py` rounds/phases EXECUTE on import, so they are refused by default. Explicit opt-in only: `--allow-python-rounds` or `[security] allow_python_rounds = true`. YAML/JSON rounds are the safe shareable format | `tests/unit/test_round_trust.py` |
| **Notifications** | Failure messages are scrubbed at the single send choke point — provider errors can carry key material and once reached the screen verbatim | `test_redaction_guarantee.py::TestNotifyGuarantee` |
| **Subprocess hygiene** | No `shell=True` anywhere (conventions-locked); child env constructed explicitly; `CLAUDECODE` always stripped | `tests/conventions/` |
| **Config file** | World-writable config is refused; TOML parsed with stdlib `tomllib` (no code execution) | `tests/unit/test_config.py` |

## Known assumptions (read before deploying anywhere shared)

- **MCP server has no authentication** — it assumes a LOCAL, single-user
  machine (stdio transport spawned by your own Claude Code). Do not expose it.
- Audit/spool files are tenant-scoped per OS user, not encrypted at rest.
- Public distributions exclude the Claude-subscription subprocess auth mode
  entirely (refused at validation and at dispatch).

## Reporting

Run `rondo doctor --bundle` — it writes a secrets-redacted diagnostic file
(keys appear last-4 only; the bundle is leak-scanned before writing and the
write ABORTS on any hit). Attach that file to your report.
