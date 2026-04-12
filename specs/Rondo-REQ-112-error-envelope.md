# Rondo-REQ-112: Error/Result Envelope Unification

**Created:** 2026-04-11  
**Status:** DRAFT  
**Classification:** open  
**Version:** 0.1  
**Owner:** Mark G. Hubers  
**Depends on:** REQ-100, REQ-111, STD-113

---

## 1. Purpose

Define one canonical dispatch envelope shape used by MCP, Python API, and CLI dispatch-facing paths.

This spec resolves inconsistent `partial` handling and requires stable `error_code` mapping for known failures.

---

## 2. Canonical Envelope

Required keys for dispatch result payloads:

- `schema_version` (string, current `"2"`)
- `status` (`done | partial | error | running | dispatched | plan`)
- `tasks` (array)
- `done_count` (int)
- `error_count` (int)
- `partial_count` (int)
- `pending_count` (int)
- `total_cost_usd` (number)
- `duration_sec` (number)
- `dry_run` (bool)

When `status="error"`, payload MUST include:

- `error_code` (string)
- `error_message` (string)

Backward-compat aliases MAY remain:

- `error` (alias of `error_message`)
- `code` (alias of `error_code`)

---

## 3. Task Status Semantics

Allowed task statuses:

- `done`
- `skipped`
- `partial`
- `error`
- `blocked`
- `pending`

`partial` means: dispatch executed and produced task output, but strict parsing/contract completion was incomplete.

---

## 4. Top-level Status Derivation

Top-level dispatch `status` MUST be derived deterministically from task statuses:

1. pending only -> `running`
2. done/skipped only -> `done`
3. any partial and no error/blocked -> `partial`
4. any mix containing partial or done with error/blocked -> `partial`
5. error/blocked only -> `error`

Implication: a response with a task `status="partial"` and non-empty output MUST NOT report top-level `status="error"` unless all tasks are hard failures.

---

## 5. Stable Error Code Taxonomy

Known envelope-building failures MUST map to stable codes:

- `ERR_INPUT_TOO_LARGE`
- `ERR_FILE_NOT_FOUND`
- `ERR_PROJECT_NOT_FOUND`
- `ERR_INVALID_INPUT`
- `ERR_INVALID_EXECUTION`
- `ERR_INVALID_EXECUTION_MODEL`
- `ERR_PROVIDER_DOWN`
- `ERR_PROVIDER`
- `ERR_BUDGET_EXCEEDED`
- `ERR_MALFORMED_JSON`
- `ERR_DISPATCH_EXCEPTION`
- `ERR_UNKNOWN_DISPATCH_ID`

Unknown exceptions SHOULD map to `ERR_DISPATCH_EXCEPTION`.

---

## 6. Requirements

| Req # | Requirement | Priority | Test |
|---|---|---|---|
| 500 | MCP `rondo_run_file` MUST return canonical envelope shape for dispatch results. | MUST | unit/integration |
| 501 | MCP `rondo_run_status` full payload MUST return canonical envelope shape. | MUST | unit |
| 502 | Python API helpers MUST normalize envelopes before example logic branches. | MUST | integration |
| 503 | Dispatch-facing CLI paths MUST emit stable `error_code` + `error_message` for known dispatch errors. | SHOULD | unit |
| 504 | Top-level status derivation MUST follow Section 4 exactly. | MUST | unit |
| 505 | `partial_count` MUST be present and accurate in canonical envelopes. | MUST | unit |
| 506 | Known failures listed in Section 5 MUST emit their stable `error_code`. | MUST | unit |

---

## 7. Version History

| Ver | Date | Changes |
|---|---|---|
| 0.1 | 2026-04-11 | Initial envelope unification spec. |
