-PASS- panel preserved (32595 chars)
12) Packaging + installation story (M)
- Publishable `pyproject.toml` metadata, console entrypoints, version source of truth
- `pipx`-first install docs + upgrade/uninstall instructions
- Decide dependency policy: “zero-dep core” vs optional extras (`rondo[openai]`, etc.) and document it

13) Secrets redaction + leakage prevention (M)
- Guarantee: no API keys in logs, audit JSONL, exceptions, debug dumps, example outputs
- Add automated redaction tests and a “print config (redacted)” command

14) Budget/cost guardrails are impossible to misunderstand (M)
- Preflight “plan” output (what will run, how many calls, worst-case cost)
- Hard caps + per-provider limits + matrix combinatorics preview
- Clear cancellation behavior + partial-results preservation

15) CLI UX contract for public users (M)
- Actionable errors instead of raw stack traces for user-caused failures
- Stable exit codes; strict stdout/stderr separation
- Optional machine-readable output mode (`--json`) that never mixes logs

16) Fix split-brain behavior (M)
- Document and/or reduce differences between subprocess Claude path vs HTTP adapters (effort, streaming, matrix support, auth)
- Mark clearly what’s API-only vs subprocess-only and why


P2 — ONBOARDING (first-run success, learnability)

1) `rondo init` first-run wizard (M)
- Create config skeleton (global and/or project)
- Prompt for providers (or instruct env vars), validate connectivity, run a cheap smoke dispatch
- Set safe defaults (budget caps on by default)

2) `rondo doctor` diagnostics (M)
- Validate config, paths/permissions, provider keys present (without printing them), network reachability, model availability, MCP status
- Emit a redacted “support bundle” users can paste into issues

3) Beginner docs rewrite around journeys (M)
- 10-minute Quickstart from a clean machine
- Glossary for Rondo-specific terms (round, dispatch, audit, matrix, drift, effort, etc.)
- Troubleshooting: auth, model not found, rate limits, JSON parse failures, Windows path/encoding issues

4) Security / privacy / cost pages (M)
- Threat model + safe/unsafe modes + executable rounds warning
- Exactly what is stored in audit logs and where; retention controls
- Cost model caveats by provider + how retries/matrices affect spend

5) Curated “Golden Path” examples (M)
- 5–10 examples that always run in CI (cheap, minimal, cross-platform)
- Everything else moved under “advanced” with explicit prerequisites

6) “Dry-run / plan mode” user experience (S)
- `--dry-run` that prints the plan, budget estimate, and file writes without executing providers

7) Provider/model capability reference (S)
- Provider setup pages + env var names
- Known quirks (streaming support, JSON mode differences, rate limits, timeouts)
- A command that lists known models/capabilities (and whether IDs are “live-verified”)

8) CI usage docs + templates (S)
- “Run Rondo in GitHub Actions” examples
- Guidance on secrets, audit retention, and non-interactive behavior


P3 — TRUST + SUPPORT (credibility, governance, operational maturity)

1) SemVer + deprecation policy + changelog discipline (S)
- `CHANGELOG.md` (Keep a Changelog style), clear breaking-change rules

2) Release engineering checklist + automation (M)
- Trusted publishing to PyPI (or documented manual process)
- Tagging, artifact verification guidance, rollback notes

3) Public repo hygiene (M)
- `LICENSE`, `NOTICE` if needed, dependency/license inventory
- `SECURITY.md` (vuln reporting), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
- Issue/PR templates that require `rondo doctor` output (redacted)

4) Audit trail trust controls (M)
- Stable audit schema versioning + migration
- Retention cleanup command + export/import utilities
- Make “audit reset” safe (confirmation, scoped reset, backups; never “one flag wipes everything” silently)

5) Stronger reliability tests (M)
- Adversarial concurrency tests (not “designed to pass”)
- Fuzz tests for config + JSON parsing + provider error normalization
- Windows path/encoding/permissions test coverage

6) Provider abstraction hardening (M)
- Normalized error taxonomy; consistent retry/backoff/timeouts
- Capability detection + graceful degradation when models/providers change
- Clear structured JSON contract + validation + retry-on-invalid policy

7) Telemetry policy (S/M depending on implementation)
- Prefer none by default; if added, strictly opt-in with transparent docs + easy disable
- Never collect prompts/responses; publish exactly what’s collected

8) Positioning + scope boundaries (S)
- “What Rondo is / is not” vs LangChain/LiteLLM/eval tools
- A support matrix page and “experimental features” policy


P4 — GROWTH (adoption, ecosystem, scale)

1) Expanded distribution options (M/L)
- Homebrew formula; optional standalone binaries (if desired) with reproducible build story

2) Plugin/provider extension system (L)
- Safe extension points + docs; explicit security boundary for plugins

3) Benchmarks + comparison tooling (M)
- `rondo benchmark` for repeatable local comparisons with budget caps
- Export formats (CSV/JSON) + sharable reports

4) Community and roadmap operations (S)
- Public roadmap, “good first issue” labeling, discussion channels, maintainer SLA expectations

5) Team/enterprise guidance (M)
- Multi-user/project config patterns, shared audit handling, CI best practices, compliance caveats

6) Growth docs/content (S)
- Tutorials, recipes, “cookbook” packs (signed/verified if you ever encourage sharing executable artifacts)
