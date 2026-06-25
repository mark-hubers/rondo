# Contributing to Rondo

> **Status & posture.** Rondo is a *signed showcase*: source-available to
> read, install, fork, and learn from. It is **maintainer-mediated** — Mark
> Hubers authors and signs every commit (each `.py` carries an `orbit-sign`
> watermark proving authorship), so it does not take outside pull requests.
> Found a bug or have an idea? Open an issue. The rules below govern every
> commit in this tree, including the owner's.

## The non-negotiables (enforced by machinery, not goodwill)

1. **Tests first.** Every change starts with a failing test. The suite is
   ~2,800 tests and the build gate runs ALL of them — a gate that skips
   tests was found once and made structurally impossible (zero-collected
   is a hard failure).
2. **Conventions are locked by tests** (`tests/conventions/`):
   - every CLI flag must be exercised by a test (a flag nobody tests is a
     flag nobody can trust — the dead-flag lock)
   - cyclomatic complexity ≤ 15 (extract, don't exempt)
   - import layering enforced; no `shell=True`; SPDX headers; signatures
3. **Examples ARE the documentation.** 100+ runnable files under `examples/`,
   smoke-checked and drift-scanned (`rondo models --docs-drift`). A feature
   without a real working example isn't done.
4. **Honesty engineering.** Errors carry the envelope contract
   (`status`/`error_code`/`error_message`/`error_help`) — never silent,
   never a raw traceback at the user. Empty data says so; nothing fakes 100%.
5. **Mocked seams get contract tests.** At least one UNMOCKED test pins the
   real downstream shape per seam — mocks encode your guess, not the contract
   (two real bugs hid behind green mocks once; never again).

## Local loop

```bash
pip install -e .          # or: uv tool install --from . rondo
pytest tests/ -q          # the whole suite
pytest tests/conventions/ # the locks (run these before every commit)
rondo doctor              # is your dev install healthy
```

## Failure corpus rule

Real production failures become permanent fixtures (`tests/fixtures/corpus/`)
— sanitized, behavior-verified, leak-scanned. If you hit a parser or auth
bug live, preserve the artifact; it's worth more than the fix.
