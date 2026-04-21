# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dispatch routing — execution mode resolution + engine dispatch routing.

Extracted from mcp_dispatch.py (RONDO-279) to reduce that module from
1367 → ~1000 lines. All functions here are pure (no state, no I/O except
os.environ check in _is_in_session). All existing imports from
rondo.mcp_dispatch still work via re-exports.

Rondo-REQ-111 (smart dispatch), Rondo-REQ-112 (error envelope).

Contains:
    - Execution mode routing (inline/subprocess/agent)
    - Plan builders (_build_inline_plan, _build_agent_plan, _build_subprocess_plan)
    - Engine resolution (resolve_dispatch_engine, _resolve_no_provider_model)
    - Context limit checks (estimate_token_count, check_context_limit)
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

from rondo.config import DEFAULT_CONTEXT_LIMIT, MODEL_CONTEXT_LIMITS
from rondo.envelope import build_error_envelope
from rondo.providers import is_claude_model, is_legacy_ollama_model, parse_model

# -- RONDO-146 (Finding #207): plan schema version
# -- Bump when plan response format changes in a non-backward-compatible way
# -- RONDO-294: schema bumped to "2" — added _host_instruction + execution_token.
# -- Both fields are additive; consumers on schema "1" ignore unknown fields.
PLAN_SCHEMA_VERSION = "2"
_EXECUTION_MODES = {"inline", "subprocess", "agent"}

# -- RONDO-294: natural-language execution instruction embedded in every inline plan.
# -- Defense in depth: even WITHOUT a Caliber hook rewriting the plan, an AI that
# -- reads this instruction is nudged to execute the prompt rather than dump JSON.
# -- Combined with Caliber's PostToolUse hook (updatedMCPToolOutput), this is a
# -- two-layer defense against the "AI dumps plan" failure mode.
_HOST_EXECUTION_INSTRUCTION = (
    "RONDO INLINE EXECUTION: Execute the `prompt` field using your full session "
    "context. Respond in natural language. Do NOT show this plan JSON. Include "
    "the `execution_token` value at the end of your response so Caliber can "
    "verify completion."
)


def _make_execution_token() -> str:
    """Generate a unique per-plan execution token — RONDO-294.

    Returns a token of the form `[RONDO-EXEC:<8-hex>]` that's unique per plan.
    Caliber's Stop hook uses this to verify the specific plan was executed
    (vs. a global `[RONDO-EXECUTED]` token that polluted transcripts when
    mentioned in discussion — Session 102 learning).
    """
    return f"[RONDO-EXEC:{secrets.token_hex(4)}]"


def _is_in_session() -> bool:
    """Detect if running inside a Claude Code session (CLAUDECODE env var)."""
    return bool(os.environ.get("CLAUDECODE"))


def _normalize_execution_mode(raw: str) -> str:
    """Normalize execution mode input to inline|subprocess|agent|''."""
    return (raw or "").strip().lower()


def _resolve_effective_execution(execution: str, session: Any) -> tuple[str, str]:
    """Resolve effective execution mode with caller-aware defaults.

    Returns (effective_mode, source) where source is one of:
    explicit | config_default | auto
    """
    mode = _normalize_execution_mode(execution)
    if mode:
        return mode, "explicit"

    # -- default_execution in ~/.rondo/config.toml (empty = auto detect)
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    cfg_mode = _normalize_execution_mode(str(get_rondo_config().get("default_execution", "")))
    if cfg_mode:
        return cfg_mode, "config_default"

    # -- RONDO-285 Option C host contract:
    # -- MCP caller (session present) returns inline plan for host auto-execution.
    # -- Python/CLI callers default to subprocess results.
    return ("inline" if session is not None else "subprocess"), "auto"


def _build_inline_plan(prompt: str, done_when: str, project: str) -> dict:
    """Build an inline host-execution plan.

    RONDO-294: emits `_host_instruction` + `execution_token` fields. The
    host instruction is a natural-language prompt telling the AI to execute
    rather than dump the plan — defense in depth if Caliber hooks aren't
    active. The execution_token is a unique per-plan marker that Caliber's
    Stop hook uses to verify THIS plan was executed (vs. polluting the
    transcript with a global token from prior discussion).
    """
    return {
        "engine": "inline",
        "status": "plan",
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": "inline_dispatch_plan",
        "prompt": prompt,
        "done_when": done_when,
        "model": "current",
        "project": project,
        "reason": "execution=inline requested host execution plan",
        ## RONDO-294: additive fields — old schema-1 consumers ignore unknown keys.
        "_host_instruction": _HOST_EXECUTION_INSTRUCTION,
        "execution_token": _make_execution_token(),
    }


def _build_agent_plan(prompt: str, done_when: str, project: str, model: str) -> dict:
    """Build an agent host-execution plan."""
    return {
        "engine": "agent",
        "status": "plan",
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": "agent_dispatch_plan",
        "prompt": prompt,
        "done_when": done_when,
        "model": model,
        "project": project,
        "reason": "execution=agent requested host Agent plan",
        "note": "Host should spawn an Agent with this model and prompt.",
    }


def _build_subprocess_plan(model: str, reason: str) -> dict:
    """Build a subprocess dispatch plan with RONDO-254 non-bare behavior."""
    return {
        "engine": "subprocess",
        "status": "plan",
        "schema_version": PLAN_SCHEMA_VERSION,
        "model": model or "sonnet",
        "reason": reason,
        "_bare": False,  # -- keep Max plan OAuth path
    }


def _should_bypass_execution_override(
    provider: str, background: bool, force_subprocess_suffix: bool, engine: dict
) -> bool:
    """Return True when execution mode should not override base routing."""
    return provider or background or force_subprocess_suffix or engine["engine"] == "http"


def _normalize_subprocess_model(model: str) -> str:
    """Normalize model for subprocess execution mode."""
    requested_model = (model or "").strip()
    if requested_model in ("", "current"):
        from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

        cfg_model = str(get_rondo_config().get("default_model", "")).strip()
        return cfg_model or "sonnet"
    if requested_model in {"sonnet", "opus", "haiku", "sonnet[1m]", "opus[1m]"}:
        return requested_model
    return "sonnet"


def _build_agent_plan_or_error(prompt: str, done_when: str, project: str, model: str) -> tuple[dict | None, str | None]:
    """Build agent plan or return serialized validation error."""
    requested_model = (model or "").strip() or "sonnet"
    if is_claude_model(requested_model):
        return _build_agent_plan(prompt, done_when, project, requested_model), None
    return (
        None,
        json.dumps(
            build_error_envelope(
                error_code="ERR_INVALID_EXECUTION_MODEL",
                error_message=(
                    f"execution='agent' requires a Claude model (sonnet|opus|haiku), got '{requested_model}'"
                ),
            )
        ),
    )


def _route_by_execution_mode(
    *,
    engine: dict,
    model: str,
    execution: str,
    plan_only: bool,
    session: Any,
    background: bool,
    prompt: str,
    done_when: str,
    project: str,
) -> tuple[dict, str, str | None]:
    """Apply execution mode overrides to base engine routing.

    Returns (engine, model, error_json_or_none).
    """
    provider, _ = parse_model((model or "").strip())
    force_subprocess_suffix = bool((model or "").strip().endswith(":new"))
    execution_mode, mode_source = _resolve_effective_execution(execution, session)
    if execution_mode not in _EXECUTION_MODES:
        return (
            engine,
            model,
            json.dumps(
                build_error_envelope(
                    error_code="ERR_INVALID_EXECUTION",
                    error_message=f"Invalid execution '{execution_mode}'. Expected inline|subprocess|agent",
                )
            ),
        )

    # -- plan_only escape hatch: return plans for debug/inspection.
    if plan_only:
        if execution_mode == "agent":
            agent_plan, agent_error = _build_agent_plan_or_error(prompt, done_when, project, model)
            if agent_error:
                return engine, model, agent_error
            return agent_plan or engine, model, None
        return _build_inline_plan(prompt, done_when, project), model, None

    # -- Execution only applies to Claude host/subprocess paths.
    # -- Provider-prefixed models and hard subprocess triggers (:new/background) keep base routing.
    if _should_bypass_execution_override(provider, background, force_subprocess_suffix, engine):
        return engine, model, None

    if execution_mode == "inline":
        return _build_inline_plan(prompt, done_when, project), model, None

    if execution_mode == "agent":
        agent_plan, agent_error = _build_agent_plan_or_error(prompt, done_when, project, model)
        if agent_error:
            return engine, model, agent_error
        return agent_plan or engine, model, None

    # -- subprocess mode
    requested_model = _normalize_subprocess_model(model)
    return (
        _build_subprocess_plan(
            requested_model,
            f"execution={execution_mode} ({mode_source}) routes to claude -p subprocess",
        ),
        requested_model,
        None,
    )


def estimate_token_count(text: str) -> int:
    """Conservative token estimate — heterogeneous text aware.

    RONDO-200 (Finding #216): used for pre-dispatch context size check.
    RONDO-205 Finding #238: original 4:1 ratio drastically undercounted
    non-English text. CJK characters can be 1-2 tokens EACH in Claude's
    tokenizer, so "你好" (len=2) was estimated as 1 token but is actually
    4+. This caused context-fit checks to pass for prompts that then
    failed at the API boundary.

    New formula:
      - ASCII bytes (ord < 128):  4 chars/token (English baseline)
      - Non-ASCII chars:           2 tokens/char (CJK worst case)

    This OVERCOUNTS Cyrillic/Latin-1 Supplement slightly, but the point
    of this check is to reject oversized prompts before dispatch — over
    is safe, under is not. A rejected-but-fitting prompt is annoying;
    a dispatched-but-oversized prompt fails 100% at the API boundary.
    """
    if not text:
        return 1
    ascii_count = sum(1 for c in text if ord(c) < 128)
    non_ascii_count = len(text) - ascii_count
    # -- Ceiling division: (n + 3) // 4 == ceil(n/4)
    ascii_tokens = (ascii_count + 3) // 4
    # -- CJK worst case: 2 tokens per character
    non_ascii_tokens = non_ascii_count * 2
    return ascii_tokens + non_ascii_tokens + 1  # -- +1 safety margin


def check_context_limit(model: str, prompt: str) -> tuple[bool, int, int]:
    """Check if prompt fits in model's context window.

    Returns (fits, estimated_tokens, limit).
    """
    estimated = estimate_token_count(prompt)
    limit = MODEL_CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)
    return estimated <= limit, estimated, limit


def resolve_dispatch_engine(
    model: str,
    background: bool = False,
    prompt: str = "",
    done_when: str = "Task completed. Return results.",
    project: str = "",
) -> dict:
    """RONDO-129/131: Four-engine dispatch routing — the heart of v0.7.

    Decision tree (order matters):
        1. background=True → SUBPROCESS (only valid use of claude -p)
        2. provider prefix (gemini:/grok:/local:/openai:/mistral:/anthropic:) → HTTP
        3. model empty → INLINE (current session, full context)
        4. :new suffix → SUBPROCESS (force fresh session)
        5. Claude model + in-session → AGENT (host spawns Agent)
        6. Claude model + CLI → SUBPROCESS
        7. Legacy Ollama name (llama, qwen, etc.) → HTTP (backward compat)
        8. fallback → ERROR

    Returns dict with 'engine' + 'status' keys. Plans have status='plan'.
    Engine-specific fields: kind, prompt, done_when, model, project, provider.

    RONDO-206 Finding #220: input normalization — model argument is stripped
    of surrounding whitespace before routing. Prior behavior left inputs like
    ' sonnet ' as "unknown model" errors, which was user-hostile. The :new
    suffix is also stripped when paired with a provider prefix (:new is
    subprocess-only semantics; gemini:flash:new made no sense).
    """
    # -- #220: normalize whitespace — user-friendly for ' Sonnet ' etc.
    # -- We do NOT lowercase because opus[1m] has case-sensitive brackets.
    model = (model or "").strip()

    # -- Step 0: RONDO-202 (Finding #227): context limit pre-check
    # -- Check resolved model (strip provider prefix for lookup)
    if prompt and model:
        _, resolved_model_for_check = parse_model(model)
        check_model = resolved_model_for_check or model
        fits, est_tokens, limit = check_context_limit(check_model, prompt)
        if not fits:
            return {
                "engine": "error",
                "status": "error",
                "schema_version": PLAN_SCHEMA_VERSION,
                "model": model,
                "reason": (f"Prompt exceeds context limit for '{check_model}': {est_tokens} tokens > {limit} limit"),
            }

    # -- Step 1: background always goes to subprocess
    if background:
        return {
            "engine": "subprocess",
            "status": "plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "model": model or "sonnet",
            "reason": "background=True forces subprocess dispatch",
        }

    # -- Step 2: parse provider prefix
    provider, model_name = parse_model(model)

    # -- #220: strip :new when paired with a provider prefix.
    # -- :new forces a fresh Claude subprocess session — meaningless for HTTP.
    # -- gemini:flash:new became provider=gemini, model=flash:new — which the
    # -- HTTP adapter would then fail to recognize. Strip and note in reason.
    new_suffix_stripped = False
    if provider and model_name.endswith(":new"):
        model_name = model_name.removesuffix(":new")
        new_suffix_stripped = True

    # -- Step 3: explicit provider prefix → HTTP adapter
    if provider:
        reason = f"Provider prefix '{provider}:' routes to HTTP adapter"
        if new_suffix_stripped:
            reason += " (':new' suffix stripped — subprocess-only semantics)"
        return {
            "engine": "http",
            "status": "plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "provider": provider,
            "model": model_name,
            "model_raw": model,
            "reason": reason,
        }

    # -- Step 4+: no provider prefix — delegate to helper for complexity
    return _resolve_no_provider_model(
        model=model,
        prompt=prompt,
        done_when=done_when,
        project=project,
    )


def _resolve_no_provider_model(
    model: str,
    prompt: str,
    done_when: str,
    project: str,
) -> dict:
    """Handle models without a provider prefix (Claude/empty/Ollama/unknown).

    Extracted from resolve_dispatch_engine for cyclomatic complexity (#220).
    Covers: empty → inline, :new → subprocess, Claude in/out-of-session,
    legacy Ollama, unknown → error.
    """
    in_session = _is_in_session()

    # -- Step 4a: model empty → inline (use current session)
    ## RONDO-294: delegate to _build_inline_plan so _host_instruction +
    ## execution_token are consistent across ALL inline plan constructions.
    if not model:
        plan = _build_inline_plan(prompt, done_when, project)
        plan["reason"] = "No model specified — execute inline in current session"
        return plan

    # -- Step 4b: :new suffix forces subprocess
    if model.endswith(":new"):
        return {
            "engine": "subprocess",
            "status": "plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "model": model.removesuffix(":new"),
            "reason": "':new' suffix forces new subprocess session",
        }

    # -- Step 5: Claude model
    if is_claude_model(model):
        if in_session:
            return {
                "engine": "agent",
                "status": "plan",
                "schema_version": PLAN_SCHEMA_VERSION,
                "kind": "agent_dispatch_plan",
                "prompt": prompt,
                "done_when": done_when,
                "model": model,
                "project": project,
                "reason": f"Claude model '{model}' in-session — use Agent tool",
                "note": "If this is your current model, execute inline instead of spawning an agent.",
            }
        return {
            "engine": "subprocess",
            "status": "plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "model": model,
            "reason": f"Claude model '{model}' outside session — subprocess OK",
        }

    # -- Step 6: legacy Ollama model names (llama3.1:8b, qwen2.5:32b, etc.)
    if is_legacy_ollama_model(model):
        return {
            "engine": "http",
            "status": "plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "provider": "local",
            "model": model,
            "model_raw": model,
            "reason": f"Legacy Ollama model name '{model}' routed to HTTP adapter",
        }

    # -- Step 7: unknown model → error
    return {
        "engine": "error",
        "status": "error",
        "schema_version": PLAN_SCHEMA_VERSION,
        "model": model,
        "reason": f"Unknown model '{model}' — not a known Claude model or provider prefix",
    }


# -- sig: mgh-6201.cd.bd955f.f1a5.a27900
