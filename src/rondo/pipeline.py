# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Prompt pipelines — Rondo-REQ-114: prompt programs with plan/apply discipline.

THE thesis feature ("Terraform for prompts"): a pipeline is a declared
sequence of prompt steps with explicit data wiring ({{inputs.X}} and
{{steps.NAME.output}} placeholders — never blind output-appending), per-step
models and output contracts, ONE hard budget ceiling, a dispatch-nothing plan
mode, and full per-step results preserved in the envelope.

Reliability rules built in (the rondo_chain diseases this engine kills):
- a FAILED step's output never flows silently into a later prompt (req 021)
- the budget is a hard ceiling with partials preserved (req 010)
- plan mode is pure — zero dispatches, zero side effects (reqs 011-012)
- production dispatch rides the guarded rondo_run_file path, so every step
  gets audit, sanitize, envelopes, and quarantine for free (req 020); tests
  inject a dispatch callable (req 025, the matrix pattern)

Import direction: leaf-ish — yaml + stdlib + lazy guarded-dispatch import.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from rondo.verify import VerifyBlockError, extract_json_object, run_verification, validate_verify_block

logger = logging.getLogger(__name__)

_TOP_FIELDS = {"name", "budget_usd", "steps"}
_STEP_FIELDS = {
    "name",
    "prompt",
    "model",
    "expect",
    "on_fail",
    "retries",
    "tools",
    "max_turns",
    "add_dir",
    "timeout",
    "verify",
}
_ON_FAIL = {"stop", "continue"}
_MAX_RETRIES = 2
_PLACEHOLDER = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
_EST_OUTPUT_TOKENS = 2048  # -- matrix precedent: conservative per-step output budget
_MIN_STEP_EST_USD = 0.001  # -- unknown models never estimate $0 (matrix precedent)

DispatchFn = Callable[[str, str], dict[str, Any]]


class PipelineError(Exception):
    """Pipeline definition or wiring error — REQ-114 reqs 001-004."""


@dataclass
class PipelineStep:
    """One declared step of a prompt program."""

    name: str
    prompt: str
    model: str = ""
    expect: dict[str, Any] | None = None
    on_fail: str = "stop"
    retries: int = 0
    # -- RONDO-407 (v1.1, the Claude-driver flagship): tool grants for steps
    # -- that EDIT FILES via the claude subprocess engine. Empty = none.
    tools: str = ""
    max_turns: int = 0
    add_dir: str = ""
    timeout: int = 0  # -- per-step dispatch timeout seconds; 0 = dispatch default
    # -- RONDO-409 (REQ-115): rondo-checked postconditions — the anti-lying layer
    verify: dict[str, Any] | None = None


@dataclass
class PipelineSpec:
    """A validated pipeline definition — REQ-114 req 001."""

    name: str
    budget_usd: float
    steps: list[PipelineStep] = field(default_factory=list)


def _placeholders(prompt: str) -> list[tuple[str, str]]:
    """Parse placeholders into (domain, key): inputs.X / steps.NAME.output."""
    refs: list[tuple[str, str]] = []
    for token in _PLACEHOLDER.findall(prompt):
        parts = token.split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            refs.append(("inputs", parts[1]))
        elif parts[0] == "steps" and len(parts) == 3 and parts[2] == "output":
            refs.append(("steps", parts[1]))
        else:
            raise PipelineError(
                f"unknown placeholder '{{{{{token}}}}}' — use {{{{inputs.X}}}} or {{{{steps.NAME.output}}}}"
            )
    return refs


def _validate_step_identity(raw_step: dict, index: int, prior_names: set[str]) -> tuple[str, str]:
    """Name + prompt checks (reqs 001-002 identity half) — extracted for the complexity lock."""
    unknown = set(raw_step) - _STEP_FIELDS
    if unknown:
        raise PipelineError(f"step {index}: unknown field(s): {sorted(unknown)}")
    name = str(raw_step.get("name", "")).strip()
    if not name or not re.fullmatch(r"[A-Za-z_][\w-]*", name):
        raise PipelineError(f"step {index}: name missing or not identifier-safe: {name!r}")
    if name in prior_names:
        raise PipelineError(f"step {index}: duplicate step name '{name}'")
    prompt = str(raw_step.get("prompt", ""))
    if not prompt.strip():
        raise PipelineError(f"step '{name}': prompt is required")
    return name, prompt


def _validate_step_options(raw_step: dict, name: str) -> tuple[str, int, int, int, dict[str, Any] | None]:
    """on_fail/retries/max_turns/timeout/expect checks (req 002) — extracted for the complexity lock."""
    on_fail = str(raw_step.get("on_fail", "stop"))
    if on_fail not in _ON_FAIL:
        raise PipelineError(f"step '{name}': on_fail must be stop|continue, got '{on_fail}'")
    retries = raw_step.get("retries", 0)
    if not isinstance(retries, int) or not 0 <= retries <= _MAX_RETRIES:
        raise PipelineError(f"step '{name}': retries must be an int 0..{_MAX_RETRIES}, got {retries!r}")
    max_turns = raw_step.get("max_turns", 0)
    if not isinstance(max_turns, int) or max_turns < 0:
        raise PipelineError(f"step '{name}': max_turns must be a non-negative int, got {max_turns!r}")
    timeout = raw_step.get("timeout", 0)
    if not isinstance(timeout, int) or timeout < 0:
        raise PipelineError(f"step '{name}': timeout must be a non-negative int, got {timeout!r}")
    expect = raw_step.get("expect")
    if expect is not None:
        if not isinstance(expect, dict) or set(expect) != {"required"} or not isinstance(expect["required"], list):
            raise PipelineError(f"step '{name}': expect must be {{required: [keys]}}")
    return on_fail, retries, max_turns, timeout, expect


def _validate_verify(verify, name):  # noqa: ANN001, ANN201
    """Thin wrapper: shared validation lives in rondo.verify (RONDO-410 DRY)."""
    try:
        return validate_verify_block(verify, f"step '{name}'")
    except VerifyBlockError as exc:
        raise PipelineError(str(exc)) from exc


def _validate_step(raw_step: Any, index: int, prior_names: set[str]) -> PipelineStep:
    """Validate one step mapping — reqs 002-004."""
    if not isinstance(raw_step, dict):
        raise PipelineError(f"step {index}: must be a mapping")
    name, prompt = _validate_step_identity(raw_step, index, prior_names)
    on_fail, retries, max_turns, timeout, expect = _validate_step_options(raw_step, name)
    # -- req 004: a step may only reference steps declared BEFORE it
    for domain, key in _placeholders(prompt):
        if domain == "steps" and key not in prior_names:
            raise PipelineError(f"step '{name}': references step '{key}' which is not declared before it")
    return PipelineStep(
        name=name,
        prompt=prompt,
        model=str(raw_step.get("model", "") or ""),
        expect=expect,
        on_fail=on_fail,
        retries=retries,
        tools=str(raw_step.get("tools", "") or ""),
        max_turns=max_turns,
        add_dir=str(raw_step.get("add_dir", "") or ""),
        timeout=timeout,
        verify=_validate_verify(raw_step.get("verify"), name),
    )


def load_pipeline(path: str | Path) -> PipelineSpec:
    """Load + validate a pipeline YAML — reqs 001-004. safe_load only."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PipelineError("pipeline YAML must be a mapping")
    unknown = set(raw) - _TOP_FIELDS
    if unknown:
        raise PipelineError(f"unknown pipeline field(s): {sorted(unknown)} — allowed: {sorted(_TOP_FIELDS)}")
    missing = {"name", "budget_usd", "steps"} - set(raw)
    if missing:
        raise PipelineError(f"missing required field(s): {sorted(missing)}")
    if not isinstance(raw["steps"], list):
        raise PipelineError("steps must be a list")
    steps: list[PipelineStep] = []
    seen: set[str] = set()
    for i, raw_step in enumerate(raw["steps"]):
        step = _validate_step(raw_step, i, seen)
        seen.add(step.name)
        steps.append(step)
    return PipelineSpec(name=str(raw["name"]), budget_usd=float(raw["budget_usd"]), steps=steps)


def _check_inputs_resolvable(spec: PipelineSpec, inputs: dict[str, str]) -> None:
    """Req 003: every {{inputs.X}} must be supplied BEFORE any dispatch."""
    for step in spec.steps:
        for domain, key in _placeholders(step.prompt):
            if domain == "inputs" and key not in inputs:
                raise PipelineError(f"step '{step.name}': unresolved placeholder {{{{inputs.{key}}}}} — not supplied")


def _resolve_prompt(step: PipelineStep, inputs: dict[str, str], outputs: dict[str, tuple[str, bool]]) -> str:
    """Substitute placeholders explicitly — req 024. Failed-step refs abort (req 021)."""
    resolved = step.prompt
    for domain, key in _placeholders(step.prompt):
        if domain == "inputs":
            resolved = resolved.replace("{{inputs." + key + "}}", inputs[key])
        else:
            output, ok = outputs[key]
            if not ok:
                raise PipelineError(
                    f"step '{step.name}' references step '{key}' which FAILED — refusing to substitute its output"
                )
            resolved = resolved.replace("{{steps." + key + ".output}}", output)
    return resolved


def _contract_error(step: PipelineStep, raw_output: str) -> tuple[dict[str, Any] | None, str]:
    """Check expect.required — returns (effective_parsed, error_text). Empty error == pass.

    Two-layer check (found LIVE, provider-divergent behavior): the required
    keys may land at the TOP LEVEL of the parsed output (gemini merges the
    step's requested keys into the smart-return wrapper) OR inside the
    wrapper's "result" when it is an object (gpt's habit). The contract
    passes if EITHER layer carries every required key; the layer that
    satisfied it becomes the step's parsed payload.
    """
    if not step.expect:
        return None, ""
    required = step.expect["required"]
    parsed = extract_json_object(raw_output)
    if parsed is None:
        return (
            None,
            f"ERR_CONTRACT: step '{step.name}' output is not parseable JSON (required: {required})",
        )
    if all(k in parsed for k in required):
        return parsed, ""
    inner = parsed.get("result")
    if isinstance(inner, dict) and all(k in inner for k in required):
        return inner, ""
    missing = [k for k in required if k not in parsed]
    return parsed, f"ERR_CONTRACT: step '{step.name}' output missing required key(s): {missing}"


def _estimate_step_cost(step: PipelineStep) -> float:
    """Plan-mode estimate (req 011) — heuristic admission number, never a quote."""
    from rondo.providers import compute_cost_usd  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    bare = (step.model or "").split(":", 1)[-1]
    in_tokens = max(1, len(step.prompt) // 4)
    return max(compute_cost_usd(bare, in_tokens, _EST_OUTPUT_TOKENS), _MIN_STEP_EST_USD)


def _build_plan(spec: PipelineSpec, inputs: dict[str, str]) -> dict[str, Any]:
    """Req 011/012: the dispatch-nothing, side-effect-free plan."""
    plan_steps = []
    total = 0.0
    for step in spec.steps:
        preview = step.prompt
        for domain, key in _placeholders(step.prompt):
            if domain == "inputs":
                preview = preview.replace("{{inputs." + key + "}}", inputs[key])
        est = _estimate_step_cost(step)
        total += est
        plan_steps.append(
            {
                "name": step.name,
                "model": step.model or "(config default)",
                "prompt_preview": preview[:300],
                "estimated_cost_usd": round(est, 6),
            }
        )
    return {
        "status": "plan",
        "name": spec.name,
        "steps": plan_steps,
        "total_estimated_cost_usd": round(total, 6),
        "budget_usd": spec.budget_usd,
        "within_budget_estimate": total <= spec.budget_usd,
    }


def unwrap_smart_return(raw_output: str) -> str:
    """Public helper: the smart-return wrapper's "result" payload, or raw as-is.

    For CONSUMERS that want clean content (the flagship runner extracts
    generated code this way). The engine itself pipes raw output verbatim —
    found LIVE: providers differ in where the real content lands (gemini
    merges requested keys into the wrapper top level; gpt fills "result"),
    so the engine never guesses; contracts check BOTH (see _contract_error).
    """
    parsed = extract_json_object(raw_output)
    if isinstance(parsed, dict) and "result" in parsed and ("passed" in parsed or "confidence" in parsed):
        inner = parsed["result"]
        return inner if isinstance(inner, str) else json.dumps(inner)
    return raw_output


def _default_dispatch(prompt: str, model: str, opts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Production dispatch — the guarded path (req 020): audit/sanitize/envelopes apply.

    RONDO-407: opts carries the step's tool grants so Claude-driver steps can
    EDIT FILES (allowed_tools/max_turns/add_dir flow to the claude subprocess).
    """
    from rondo.mcp_dispatch import rondo_run_file  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    opts = opts or {}
    envelope = json.loads(
        rondo_run_file(
            prompt=prompt,
            model=model,
            dry_run=False,
            allowed_tools=str(opts.get("tools", "") or ""),
            max_turns=int(opts.get("max_turns", 0) or 0),
            add_dir=str(opts.get("add_dir", "") or ""),
            timeout_sec=int(opts.get("timeout", 0) or 300),
        )
    )
    tasks = envelope.get("tasks") or []
    task = tasks[0] if tasks else {}
    return {
        "status": "done" if task.get("status") == "done" else "error",
        "raw_output": task.get("raw_output", ""),
        "cost_usd": float(task.get("cost_usd") or 0.0),
        "error": task.get("error_message", "") or envelope.get("error_message", ""),
    }


def _dispatch_step(dispatch: DispatchFn, prompt: str, step: PipelineStep) -> dict[str, Any]:
    """Call the dispatch seam — 3-arg form (opts) with 2-arg fallback.

    RONDO-407: the production dispatch needs the step's tool grants
    (tools/max_turns/add_dir) for file-editing Claude steps; injected test
    dispatches keep the simple (prompt, model) signature (req 025).
    """
    opts = {"tools": step.tools, "max_turns": step.max_turns, "add_dir": step.add_dir, "timeout": step.timeout}
    try:
        return dispatch(prompt, step.model, opts)  # type: ignore[call-arg]
    except TypeError:
        return dispatch(prompt, step.model)


def _self_reported_failure(step: PipelineStep, raw_output: str) -> str:
    """RONDO-407: honor the model's OWN passed=false admission as step failure.

    The smart-return contract defines "passed" as the success bool. The
    Claude-driver flagship depends on this: each step VERIFIES its own work
    and reports honestly; the engine refuses to advance past a step that
    says it did not succeed. Empty string == no self-reported failure.
    """
    parsed = extract_json_object(raw_output)
    if isinstance(parsed, dict) and parsed.get("passed") is False:
        detail = parsed.get("issues") or parsed.get("result") or "no detail given"
        return f"ERR_STEP_REPORTED_FAILURE: step '{step.name}' reported passed=false: {str(detail)[:300]}"
    return ""


def _run_verification(step: PipelineStep) -> dict[str, Any]:
    """REQ-115 r020: rondo observes the world ITSELF (shared core in rondo.verify)."""
    return run_verification(step.verify or {}, cwd=step.add_dir)


def _run_step(step: PipelineStep, prompt: str, dispatch: DispatchFn) -> dict[str, Any]:
    """Dispatch one step with retries + contract + self-report gates — reqs 005/022."""
    record: dict[str, Any] = {"name": step.name, "status": "error", "raw_output": "", "cost_usd": 0.0, "error": ""}
    for attempt in range(step.retries + 1):
        result = _dispatch_step(dispatch, prompt, step)
        record["raw_output"] = str(result.get("raw_output", ""))
        record["cost_usd"] = record["cost_usd"] + float(result.get("cost_usd") or 0.0)
        if result.get("status") != "done":
            record["error"] = str(result.get("error", "") or f"step '{step.name}' dispatch failed")
            continue  # -- retry if attempts remain
        self_fail = _self_reported_failure(step, record["raw_output"])
        if self_fail:
            record["error"] = self_fail
            continue  # -- the model said it failed; retry IS the fix loop
        parsed, contract_err = _contract_error(step, record["raw_output"])
        if contract_err:
            record["error"] = contract_err
            continue  # -- a contract failure is retryable too (req 022)
        if step.verify is not None:
            # -- REQ-115 r020: rondo's OWN observation outranks every claim above
            verification = _run_verification(step)
            record["verification"] = verification
            if not verification["ok"]:
                record["error"] = verification["error"]
                continue  # -- verification failure is retryable like the rest
        record["status"] = "done"
        record["error"] = ""
        if parsed is not None:
            record["parsed"] = parsed
        break
    if record["status"] != "done":
        logger.warning(
            "-WARNING- pipeline step '%s' failed after %d attempt(s): %s", step.name, step.retries + 1, record["error"]
        )
    return record


def run_pipeline(
    spec: PipelineSpec,
    inputs: dict[str, str] | None = None,
    dispatch: DispatchFn | None = None,
    plan: bool = False,
) -> dict[str, Any]:
    """Execute (or plan) a pipeline — REQ-114 reqs 010-024.

    Returns the result envelope. Never raises for STEP failures (those are
    recorded honestly); raises PipelineError only for wiring violations
    (unresolved inputs before any dispatch; referencing a FAILED step is
    reported in the envelope as status "error").
    """
    inputs = dict(inputs or {})
    _check_inputs_resolvable(spec, inputs)  # -- req 003: before ANY dispatch
    if plan:
        return _build_plan(spec, inputs)

    dispatch = dispatch or _default_dispatch
    records: list[dict[str, Any]] = []
    outputs: dict[str, tuple[str, bool]] = {}
    spent = 0.0
    high_cost = 0.0  # -- MAX-KEEP admission estimate (budget-gate precedent)
    status = "done"
    pipeline_error = ""

    for step in spec.steps:
        est = high_cost if high_cost > 0 else _MIN_STEP_EST_USD
        if spent + est > spec.budget_usd:
            status = "partial"
            pipeline_error = (
                f"ERR_BUDGET_EXCEEDED: spent ${spent:.4f} + estimated ${est:.4f} for step "
                f"'{step.name}' exceeds budget ${spec.budget_usd:.4f} — remaining steps not dispatched"
            )
            break
        try:
            prompt = _resolve_prompt(step, inputs, outputs)
        except PipelineError as exc:
            status = "error"
            pipeline_error = str(exc)
            break
        record = _run_step(step, prompt, dispatch)
        records.append(record)
        spent += record["cost_usd"]
        high_cost = max(high_cost, record["cost_usd"])
        outputs[step.name] = (record["raw_output"], record["status"] == "done")
        if record["status"] != "done" and step.on_fail == "stop":
            status = "partial"
            break

    envelope: dict[str, Any] = {
        "status": status,
        "name": spec.name,
        "steps": records,
        "total_cost_usd": round(spent, 6),
    }
    if pipeline_error:
        envelope["error"] = pipeline_error
    return envelope


# -- sig: mgh-6201.cd.bd955f.6b92.64f794
