# Rondo-REQ-112: Error/Result Envelope Unification

**Created:** 2026-04-11  
**Status:** BUILT (verified 2026-06-14, RONDO-432)  
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
- `error_help` (string user-facing next action)

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
| 507 | Every emitted `error_code` MUST include a user-facing remediation message (`error_message`) and actionable guidance (`error_help`). | MUST | unit |
| 508 | Dispatch timeouts MUST emit `ERR_TIMEOUT`; timeout paths MUST NOT fail silently or hang without an error envelope. | MUST | integration |
| 509 | `partial` task outcomes SHOULD preserve `tasks[].raw_output` so callers can recover useful output even when strict parsing fails. | SHOULD | integration |

### Caller Acceptance Tables (RONDO-276 hardening)

#### MCP callers (`rondo_run`, `rondo_run_status`)

| Parameter | Allowed values | Default | MUST/SHOULD |
|---|---|---|---|
| `status` | `done`, `partial`, `error`, `running`, `dispatched`, `plan` | derived by envelope normalizer | MUST be normalized before returning full payloads. |
| `schema_version` | string (`"2"` current) | `"2"` | MUST be present on canonical dispatch payloads. |
| `error_code` / `error_message` | string fields when `status="error"` | empty unless error | MUST be present for known failures and unknown dispatch exceptions. |
| `error_help` | actionable string guidance | derived from `error_code` mapping | MUST be present on error envelopes for caller remediation UX. |
| `brief` / `heartbeat` (status polling) | `true`, `false` | `false` | SHOULD preserve canonical full payload shape prior to truncation for short views. |
| `dispatch_id` | non-empty string | n/a | MUST return `ERR_UNKNOWN_DISPATCH_ID` envelope when id is missing/unknown. |

#### Python API callers (`rondo_run_file` results consumed directly)

| Parameter | Allowed values | Default | MUST/SHOULD |
|---|---|---|---|
| `status` | same set as MCP table | derived by envelope normalizer | MUST follow deterministic top-level derivation rules from Section 4. |
| `tasks[].status` | `done`, `skipped`, `partial`, `error`, `blocked`, `pending` | provider/dispatch result dependent | MUST be the source of truth for top-level derivation. |
| `partial_count` | integer >= 0 | `0` | MUST be present and accurate on normalized envelopes. |
| `error_code` mapping | stable taxonomy in Section 5 | n/a | MUST emit listed stable codes for known failures. |
| `error_help` | actionable guidance text | derived from `error_code` mapping | SHOULD be surfaced by examples/automation logs when errors occur. |
| helper normalization behavior | normalized envelope dict | n/a | SHOULD normalize before user/example branching logic to avoid caller drift. |

#### CLI callers (dispatch-facing outputs)

| Parameter | Allowed values | Default | MUST/SHOULD |
|---|---|---|---|
| dispatch error fields | `error_code`, `error_message`, `error_help` | n/a | MUST expose stable dispatch error identifiers plus remediation guidance. |
| smart-return JSON fields | normalized JSON response object | provider raw parsed/normalized | SHOULD remain consistent and parseable, with `_json_valid` signal for callers. |
| `status` interpretation | CLI exit code mapping | done=0, non-done=1 | MUST treat hard-failure dispatch statuses as non-zero exit path. |
| `partial` behavior | success-with-caveat semantics | n/a | SHOULD document and surface `partial` distinctly from hard `error`. |

---

## 7. Version History

| Ver | Date | Changes |
|---|---|---|
| 0.1 | 2026-04-11 | Initial envelope unification spec. |
