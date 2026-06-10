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

## Spec scope honesty — STD-115 (result quarantine): what is REAL vs DESIGNED

STD-115 (`specs/Rondo-STD-115-result-quarantine.md`) describes a full result-
lifecycle quarantine (PENDING→VERIFIED→TRUSTED/REJECTED). Honesty requires
saying which parts exist in code TODAY (RONDO-391/394, 2026-06-10) and which
are design-only. No silent spec-vs-code gaps.

**BUILT and tested:**

| Capability | Where | Proven by |
|------------|-------|-----------|
| Quarantine STORE: failed-scrub results land in `~/.rondo/quarantine/` (files born 0o600), withheld from audit/spool/result/history, stub + flag + reference returned | `dispatch.py _quarantine_scrub_failure` | `tests/unit/test_sanitize_quarantine_cursor.py` |
| Results that cannot be verified safe never reach normal stores (the r006 inversion is closed) | same | same |
| Advisory results carry explicit scope (`guarantees_scope="advisory"` + `not_covered`) so consumers can't mistake them for guarded executions | `dispatch_routing.py` builders | `tests/unit/test_advisory_path_machinery_cursor.py` |

**DESIGNED, NOT BUILT** (the STD-115 state machine itself):

- reqs 001-006: PENDING/VERIFIED/TRUSTED/REJECTED lifecycle — no state field,
  no transitions exist in code.
- reqs 007-011: per-type verification criteria (Caliber gates, structure
  checks) — not implemented.
- reqs 012-015: approval/auto-approval bootstrap — not implemented.
- reqs 016-018: overnight PENDING + morning-report integration — not
  implemented.
- reqs 019-021: rejection-feeds-learning — not implemented.

The quarantine store above is the first real brick (a place unverifiable
results go that is NOT the trusted path); the lifecycle remains roadmap.
Consumers MUST NOT assume STD-115 lifecycle guarantees from this codebase
until this section says otherwise.

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
