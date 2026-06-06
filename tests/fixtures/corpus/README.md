# Corpus Fixtures — sanitized production regression records

**Why this exists (RONDO-313):** the parser/auth-loss regression corpora lived
only in `~/.rondo/audit` on the original dev machine — the corpus gates skipped
everywhere else ("local-only gates", Cursor review 2026-06-05, finding #301).
These fixtures make the gates run on EVERY machine, including CI.

## Contents

| Dir | Records | Source | Gate |
|-----|---------|--------|------|
| `parser/` | 12 | Sanitized from the 80 misfiled production outputs (REQ-100 req 126) | every record must `parse_task_json()` |
| `auth/` | 5 | 1 sanitized production auth-loss + 4 synthetic (one per `AUTH_LOSS_PATTERNS` signal, IFS-100 req 011) | every record must trip `detect_auth_loss()` |

## Rules

- Built ONLY by `scripts/build_corpus_fixtures.py` — never hand-edit.
  The builder redacts (paths, names, emails, key patterns), verifies the
  redaction kept each record's regression behavior, and aborts on any
  forbidden-token leak. Selection is structure-diverse and size-capped.
- The full local corpus (when present) still runs via the `historic` tests —
  fixtures are the floor, not the ceiling.
- Synthetic records are labeled `"sanitized_from": "synthetic — ..."` —
  never pass synthetic data off as production data.
