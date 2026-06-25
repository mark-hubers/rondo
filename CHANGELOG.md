# Changelog

All notable changes to Rondo are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Rondo follows [Semantic Versioning](https://semver.org/) per `specs/Rondo-SOP-102-release.md`:

- **MAJOR** — breaking changes to the task API, config format, or CLI interface
- **MINOR** — new dispatch modes, report formats, or engine features (backward-compatible)
- **PATCH** — backward-compatible fixes

The installed version also carries build metadata (`MAJOR.MINOR.PATCH+YYYYMMDD.BUILD`,
e.g. `0.7.0+20260615.12`); the build segment is generated automatically and is not
part of the SemVer contract.

## [Unreleased] — preparing the first public release (target 0.7.0)

Rondo was developed privately; its full granular history (750+ commits) is
preserved in git. This section summarizes the capability surface at the first
public cut. It moves to a dated `[0.7.0]` section when the release is tagged.

### Added — core
- Multi-provider scripted AI dispatch (Claude, Gemini, Grok, Mistral, OpenAI,
  Anthropic API, Ollama) with health-based fallback and a uniform error envelope
- 25 CLI commands and 27 MCP tools (see `docs/API-STABILITY.md` for the stable surface)
- Budgeted dispatch with model-aware cost estimation and a hard per-run ceiling

### Added — the loop / control layer
- Pipeline engine for YAML "prompt programs" with plan/apply, budget, and contracts
- Verified execution — a step declares file/command postconditions that Rondo
  checks itself (sha256 + exit codes); `rondo_verify` and the `verify=` argument
- Scope guard to keep each step to a small, reviewable change

### Added — the cross-vendor jury (the thesis)
- `jury_review()` and the `rondo_jury` MCP tool: the model that writes the code
  does not certify it — a *different* vendor does (`docs/CROSS-VENDOR-JURY.md`)

### Added — trust & operations
- Crash-safe audit trail (intent + outcome records), secret sanitization at every
  storage boundary, and result quarantine on scrub failure
- Nightly watchdog, model canary, docs-drift scanner, and an honest reliability
  scoreboard (core vs end-to-end split — see `docs/SCORING.md`)

### Notes
- Quality is machinery-enforced: a 6-gate build (`bin/build`), ~2,800 tests, and
  AST-based convention locks (`tests/conventions/`). See `CONTRIBUTING.md`.
- Live/paid dispatch tests are opt-in (`pytest -m cloud` / `-m ollama`) and are
  not part of the default gate.
