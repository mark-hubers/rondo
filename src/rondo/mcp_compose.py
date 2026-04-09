# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo composition tools — multi-review, chain, benchmark, explain, summarize.

Rondo-IFS-104, Rondo-REQ-109.
These are AI composition patterns that combine multiple dispatch calls.
Split from mcp_dispatch.py for module size.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# -- Constants (same as mcp_dispatch — avoid circular import)
_MAX_PROMPT_BYTES = 500_000  # -- H-07: max prompt bytes
_MAX_CHAIN_STEPS = 20  # -- H-08: max chain pipeline steps
_MAX_BENCHMARK_MODELS = 10  # -- H-09: max benchmark models


# -- ──────────────────────────────────────────────────────────────
# --  Composition tools — multi-model AI patterns
# -- ──────────────────────────────────────────────────────────────


def rondo_explain(
    output: str, question: str = "Is this correct?", model: str = "qwen2.5:32b", dry_run: bool = False
) -> str:
    """Second opinion: local model reviews another model's output at zero cost.

    Pass the output from a Claude/other dispatch + a review question.
    Default model is qwen2.5:32b (best local quality).
    """
    prompt = f"""Review this AI-generated output and answer the question.

## Output to review:
{output[:5000]}

## Question:
{question}

Be specific. If you find errors, list them. If correct, say why."""

    from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

    return rondo_run_file(
        prompt=prompt, model=model, dry_run=dry_run, done_when="Review complete with specific assessment."
    )


# -- REQ-109 req 033: benchmark same prompt across models
def rondo_benchmark(prompt: str, models: str = "[]", dry_run: bool = False) -> str:
    """Benchmark: dispatch same prompt to multiple models, rank by speed/cost.

    Returns results sorted by duration (fastest first).
    """
    try:
        model_list = json.loads(models) if models else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid models JSON"})

    # -- H-09: benchmark model limit
    if len(model_list) > _MAX_BENCHMARK_MODELS:
        return json.dumps(
            {
                "status": "error",
                "error": f"Too many models ({len(model_list)} > {_MAX_BENCHMARK_MODELS})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    if not model_list:
        model_list = ["llama3.1:8b", "qwen2.5:32b", "sonnet"]

    results: list[dict] = []
    for model_name in model_list:
        if dry_run:
            results.append(
                {
                    "model": model_name,
                    "status": "skipped",
                    "duration_sec": 0,
                    "output_length": 0,
                    "cost_usd": 0,
                }
            )
        else:
            from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

            raw = rondo_run_file(prompt=prompt, model=model_name, dry_run=False)
            r = json.loads(raw)
            tasks = r.get("tasks", [])
            task = tasks[0] if tasks else {}
            results.append(
                {
                    "model": model_name,
                    "status": r.get("status", "error"),
                    "duration_sec": task.get("duration_sec", 0),
                    "output_length": len(task.get("raw_output", "")),
                    "cost_usd": r.get("total_cost_usd", 0),
                }
            )

    ranked = sorted(results, key=lambda x: x["duration_sec"])

    return json.dumps(
        {
            "status": "done",
            "prompt": prompt[:100],
            "results": results,
            "ranked": ranked,
            "fastest": ranked[0]["model"] if ranked else "",
        },
        indent=2,
    )


# -- REQ-109 req 087: file review for AI editors
def rondo_review_file(
    path: str,
    providers: str = "[]",
    tier: str = "default",
    dry_run: bool = False,
) -> str:
    """Review a file with multiple cloud providers — REQ-109 req 087.

    Reads file at path, builds review prompt, dispatches via rondo_multi_review.
    AI editors call this instead of manually reading + pasting file contents.

    Args:
        path: File path to review (expanded with ~ and resolved).
        providers: JSON array of provider:model strings. Default: review profile.
        tier: Model tier (high/default/low). Used when providers not specified.
        dry_run: Preview prompt without dispatching.
    """
    from pathlib import Path as _Path  # pylint: disable=import-outside-toplevel

    file_path = _Path(path).expanduser().resolve()
    if not file_path.is_file():
        return json.dumps({"status": "error", "error": f"File not found: {path}", "code": "ERR_INVALID_INPUT"})

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return json.dumps({"status": "error", "error": f"Cannot read file: {exc}", "code": "ERR_INVALID_INPUT"})

    if not content.strip():
        return json.dumps({"status": "error", "error": "File is empty", "code": "ERR_INVALID_INPUT"})

    if len(content) > _MAX_PROMPT_BYTES:
        return json.dumps(
            {
                "status": "error",
                "error": f"File too large ({len(content)} bytes, max {_MAX_PROMPT_BYTES})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    prompt = f"Review this file for bugs, security issues, and code quality.\n\nFile: {file_path.name}\n\n```\n{content}\n```"

    # -- Resolve providers from tier + config if not specified
    if not providers or providers == "[]":
        from rondo.providers import _providers_config, load_providers_config  # pylint: disable=import-outside-toplevel

        load_providers_config()
        tier_map = {"high": "best_model", "default": "default_model", "low": "cheap_model"}
        tier_key = tier_map.get(tier, "default_model")

        from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

        cfg = get_rondo_config()
        profile_providers = cfg.get("cloud", {}).get("profiles", {}).get("review", {}).get("providers", [])
        if not profile_providers:
            profile_providers = ["gemini", "grok"]

        resolved = []
        for name in profile_providers:
            model = _providers_config.get(name, {}).get(tier_key, "")
            resolved.append(f"{name}:{model}" if model else name)
        providers = json.dumps(resolved)

    result_json = rondo_multi_review(prompt=prompt, providers=providers, dry_run=dry_run)
    result = json.loads(result_json)
    result["file"] = str(file_path)
    result["file_size"] = len(content)
    result["tier"] = tier
    return json.dumps(result, indent=2)


# -- RONDO-209 #248/#250: which error codes warrant a one-time serial retry
# -- after the parallel batch finishes. The upstream API is likely throttling
# -- under concurrent load, so a retry without sibling concurrency often works.
_RETRYABLE_PROVIDER_ERRORS = frozenset({"ERR_PROVIDER_DOWN", "ERR_RATE_LIMIT"})


def _multi_review_dispatch_one(provider_model: str, prompt: str) -> dict:
    """RONDO-209 #248/#250: dispatch one provider, surface error_code+message.

    Extracted from rondo_multi_review for cyclomatic complexity. Returns a
    structured dict with status/output/cost/duration AND the underlying
    error_code + error_message so callers can diagnose failures (HTTP 503,
    rate limit, auth error) instead of just seeing 'partial empty'.
    """
    from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

    raw = rondo_run_file(
        prompt=prompt,
        model=provider_model,
        dry_run=False,
        done_when="Review complete. List specific findings as bullet points.",
    )
    r = json.loads(raw)
    tasks = r.get("tasks", [])
    task = tasks[0] if tasks else {}
    return {
        "provider": provider_model,
        "status": r.get("status", "error"),
        "output": task.get("raw_output", ""),
        "cost_usd": r.get("total_cost_usd", 0),
        "duration_sec": task.get("duration_sec", 0),
        "error_code": task.get("error_code") or "",
        "error_message": task.get("error_message") or "",
        "attempt": 1,
    }


def _multi_review_run_parallel(provider_list: list[str], prompt: str) -> dict[str, dict]:
    """RONDO-209: dispatch all providers in parallel + serial retry pass.

    Returns results_map: {provider: result_dict}. Handles ThreadPoolExecutor
    setup, concurrent collection, exception wrapping, and the post-batch
    serial retry for transient failures (#248/#250).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed  # pylint: disable=import-outside-toplevel

    results_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(provider_list)) as pool:
        futures = {pool.submit(_multi_review_dispatch_one, p, prompt): p for p in provider_list}
        for future in as_completed(futures):
            provider = futures[future]
            try:
                results_map[provider] = future.result()
            except Exception as exc:  # noqa: BLE001 — thread boundary
                # -- RONDO-209 #254: broad-except is INTENTIONAL at thread boundaries.
                # -- We collect results from N parallel providers; if one thread
                # -- crashes for ANY reason (HTTP error, programmer bug, OOM), we
                # -- want the OTHER N-1 providers to still report. Errors are
                # -- surfaced as ERR_INTERNAL with message — programmer errors
                # -- are visible, not silent.
                results_map[provider] = {
                    "provider": provider,
                    "status": "error",
                    "output": "",
                    "cost_usd": 0,
                    "duration_sec": 0,
                    "error_code": "ERR_INTERNAL",
                    "error_message": str(exc),
                    "attempt": 1,
                }

    # -- Serial retry pass for transient failures
    _multi_review_serial_retry(
        provider_list,
        results_map,
        set(_RETRYABLE_PROVIDER_ERRORS),
        lambda p: _multi_review_dispatch_one(p, prompt),
    )
    return results_map


def _multi_review_serial_retry(
    provider_list: list[str],
    results_map: dict[str, dict],
    retryable_errors: set[str],
    dispatch_fn: Callable[[str], dict],
) -> None:
    """RONDO-209 #248/#250: serial retry pass for transient provider failures.

    After the parallel batch finishes, walk results_map for any provider
    that returned a retryable error code (ERR_PROVIDER_DOWN, ERR_RATE_LIMIT)
    and run ONE more dispatch attempt sequentially. This typically succeeds
    because the upstream API throttle was triggered by the concurrent siblings,
    not by anything intrinsic to the request.

    Mutates results_map in place: replaces with retry result if retry
    succeeded, otherwise keeps the first attempt's error and adds
    retry_error_code/retry_error_message for diagnostics.
    """
    for provider in provider_list:
        result = results_map.get(provider, {})
        err_code = result.get("error_code", "")
        if err_code not in retryable_errors:
            continue
        logger.info(
            "Multi-review retry: %s previously failed with %s — retrying serially",
            provider,
            err_code,
        )
        retry_result = dispatch_fn(provider)
        retry_result["attempt"] = 2
        if retry_result.get("status") == "done":
            results_map[provider] = retry_result
        else:
            results_map[provider]["attempt"] = 2
            results_map[provider]["retry_error_code"] = retry_result.get("error_code", "")
            results_map[provider]["retry_error_message"] = retry_result.get("error_message", "")


# -- REQ-109 req 033: multi-provider parallel review
def rondo_multi_review(
    prompt: str,
    providers: str = "[]",
    dry_run: bool = False,
) -> str:
    """Multi-provider review: same prompt → N providers → per-provider + merged findings.

    REQ-109 req 033. Replaces ai-review --all-providers --compare.
    Pass providers as JSON array: ["local:qwen2.5:32b", "gemini:gemini-2.5-flash", "grok:grok-3"]
    Default: local + gemini + grok (if keys available).
    """
    try:
        provider_list = json.loads(providers) if providers else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid providers JSON"})

    if len(provider_list) > _MAX_BENCHMARK_MODELS:
        return json.dumps(
            {
                "status": "error",
                "error": f"Too many providers ({len(provider_list)} > {_MAX_BENCHMARK_MODELS})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    if not prompt or not prompt.strip():
        return json.dumps({"status": "error", "error": "Prompt is empty", "code": "ERR_INVALID_INPUT"})

    if not provider_list:
        provider_list = ["local:qwen2.5:32b", "gemini:gemini-2.5-flash", "grok:grok-3"]

    per_provider: list[dict] = []
    all_findings: list[str] = []

    if dry_run:
        for provider in provider_list:
            per_provider.append(
                {
                    "provider": provider,
                    "status": "skipped",
                    "findings": [],
                    "cost_usd": 0,
                    "duration_sec": 0,
                }
            )
    else:
        # -- RONDO-209 #248/#250: parallel dispatch + serial retry for transient failures
        results_map = _multi_review_run_parallel(provider_list, prompt)
        for provider in provider_list:
            result = results_map.get(provider, {"provider": provider, "status": "error"})
            per_provider.append(result)
            output = result.get("output", "")
            if output:
                all_findings.append(f"[{provider}]: {output}")

    total_cost = sum(p.get("cost_usd", 0) for p in per_provider)

    # -- RONDO-211 #256: top-level status reflects ACTUAL provider outcomes,
    # -- not a hardcoded "done". Otherwise a caller checking top-level status
    # -- would think the review succeeded when all providers actually failed
    # -- (observed in RONDO-210 Phase B when gemini hit 503).
    succeeded = sum(1 for p in per_provider if p.get("status") in ("done", "skipped"))
    total_providers = len(per_provider)
    if total_providers == 0:
        top_status = "error"
    elif succeeded == total_providers:
        top_status = "done"
    elif succeeded == 0:
        top_status = "error"
    else:
        top_status = "partial"

    return json.dumps(
        {
            "status": top_status,
            "prompt": prompt[:200],
            "provider_count": len(provider_list),
            "per_provider": per_provider,
            "merged_findings": "\n\n---\n\n".join(all_findings),
            "total_cost_usd": total_cost,
        },
        indent=2,
    )


# -- REQ-109: pipeline — output of step N feeds step N+1
def rondo_chain(steps_json: str, dry_run: bool = False) -> str:
    """Chain dispatch: output of step N feeds as context to step N+1.

    Each step is {prompt, model, done_when?}. Previous output appended to prompt.
    """
    try:
        steps = json.loads(steps_json) if steps_json else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid steps_json"})

    # -- H-08: chain step limit
    if len(steps) > _MAX_CHAIN_STEPS:
        return json.dumps(
            {
                "status": "error",
                "error": f"Too many steps ({len(steps)} > {_MAX_CHAIN_STEPS})",
                "code": "ERR_INPUT_TOO_LARGE",
            }
        )

    if not steps:
        return json.dumps({"status": "done", "steps": [], "total_cost_usd": 0})

    results: list[dict] = []
    previous_output = ""
    total_cost = 0.0

    for i, step in enumerate(steps):
        step_prompt = step.get("prompt", "")
        if previous_output:
            step_prompt = f"{step_prompt}\n\n## Previous step output:\n{previous_output}"

        step_model = step.get("model", "sonnet")
        step_done = step.get("done_when", "Task completed.")

        if dry_run:
            results.append(
                {
                    "step": i + 1,
                    "prompt_preview": step_prompt[:300],
                    "model": step_model,
                    "status": "skipped",
                }
            )
            previous_output = f"[dry-run step {i + 1} output]"
        else:
            from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

            raw = rondo_run_file(
                prompt=step_prompt,
                model=step_model,
                done_when=step_done,
                dry_run=False,
            )
            step_result = json.loads(raw)
            tasks = step_result.get("tasks", [])
            output = tasks[0].get("raw_output", "") if tasks else ""
            cost = step_result.get("total_cost_usd", 0)
            total_cost += cost
            previous_output = output
            results.append(
                {
                    "step": i + 1,
                    "model": step_model,
                    "status": step_result.get("status", "unknown"),
                    "output_length": len(output),
                    "cost_usd": cost,
                }
            )

    return json.dumps(
        {"status": "done", "steps": results, "total_cost_usd": total_cost},
        indent=2,
    )


def rondo_summarize(dispatch_json: str, dry_run: bool = False, model: str = "haiku") -> str:
    """Condense multiple task results into one summary — via AI dispatch.

    Takes a dispatch result JSON, builds a summarization prompt from all
    task outputs, dispatches to AI, returns the summary.
    """
    try:
        data = json.loads(dispatch_json) if dispatch_json else {}
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid dispatch_json"})

    tasks = data.get("tasks", [])
    if not tasks:
        return json.dumps({"status": "done", "summary": "No tasks to summarize"})

    # -- Build summarization prompt from all task outputs
    parts = ["Summarize these task results into a concise report:\n"]
    for task in tasks:
        name = task.get("name", "unknown")
        full_output = task.get("raw_output", "")
        output = full_output[:3000]
        if len(full_output) > 3000:
            output += f"\n[TRUNCATED: {len(full_output)} chars total, showing first 3000]"
        status = task.get("status", "unknown")
        parts.append(f"## Task: {name} ({status})\n{output}\n")

    prompt = "\n".join(parts)

    if dry_run:
        return json.dumps(
            {"status": "done", "summary_prompt": prompt[:500], "prompt_length": len(prompt), "task_count": len(tasks)}
        )

    # -- Dispatch summarization via rondo_run_file
    from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

    result = rondo_run_file(prompt=prompt, done_when="Summary report written.", dry_run=False, model=model)
    return result


# -- ──────────────────────────────────────────────────────────────
# --  Codebase review — RONDO-215 Option C
# -- ──────────────────────────────────────────────────────────────

# -- Per-provider preambles (calibrated from 4-model self-assessment 2026-04-09).
# -- All 4 providers agreed: markdown fenced blocks, batched calls, structured output.
# -- Differences are in FRAMING — what each provider focuses on.
_REVIEW_PREAMBLES: dict[str, str] = {
    "gemini": "You have deep context capacity. Focus on cross-module interactions, data flow across files, and architectural coherence.",
    "openai": "Focus on line-by-line bugs, edge cases, and error handling gaps. Be surgical — cite exact line numbers.",
    "grok": "Think adversarially. What assumptions are wrong? What breaks under stress or hostile input? Challenge the architecture.",
    "mistral": "Focus on security: input validation, path traversal, credential handling, data exposure, and compliance patterns.",
}

_MAX_BATCH_CHARS = 80_000  # -- stay within all providers' practical context
_DEFAULT_BATCH_SIZE = 4


def _extract_module_summary(filepath: str, content: str) -> str:
    """Extract module docstring + imports for architecture context."""
    lines = content.split("\n")
    summary_parts: list[str] = []

    # -- Extract module docstring (first triple-quoted block)
    in_docstring = False
    docstring_lines: list[str] = []
    for line in lines[:30]:  # -- only scan first 30 lines
        if '"""' in line and not in_docstring:
            in_docstring = True
            docstring_lines.append(line.split('"""', 1)[-1] if line.count('"""') == 1 else line.split('"""')[1])
            if line.count('"""') >= 2:
                break
            continue
        if in_docstring:
            if '"""' in line:
                docstring_lines.append(line.split('"""')[0])
                break
            docstring_lines.append(line)
    if docstring_lines:
        summary_parts.append(" ".join(dl.strip() for dl in docstring_lines if dl.strip())[:200])

    # -- Extract rondo imports (shows dependency graph)
    imports = [ln.strip() for ln in lines if ln.strip().startswith(("from rondo.", "import rondo."))]
    if imports:
        summary_parts.append(
            "imports: " + ", ".join(i.split("import")[0].strip().replace("from ", "") for i in imports[:5])
        )

    return f"- **{filepath}**: {' | '.join(summary_parts)}" if summary_parts else f"- **{filepath}**"


def _build_batch_prompt(
    batch_files: list[tuple[str, str]],
    all_summaries: list[str],
    focus: str,
    batch_num: int,
    total_batches: int,
) -> str:
    """Build a review prompt for one batch of files."""
    parts: list[str] = []

    parts.append(f"# Code Review — Batch {batch_num}/{total_batches}\n")

    # -- Architecture summary (all modules, not just this batch)
    parts.append("## Architecture Summary (all modules in this codebase)\n")
    parts.extend(all_summaries)
    parts.append("")

    # -- Focus area
    focus_text = focus or "reliability, error handling, DRY, security"
    parts.append(f"## Focus: {focus_text}\n")

    # -- Files in this batch
    parts.append("## Files to review\n")
    for filepath, content in batch_files:
        parts.append(f"### file: {filepath}")
        parts.append("```python")
        parts.append(content)
        parts.append("```\n")

    # -- Output format (all 4 providers said structured template is best)
    parts.append("## Output format")
    parts.append("Return findings as a table. One row per finding:")
    parts.append("| # | File | Line | Severity | Description | Recommendation |")
    parts.append("|---|------|------|----------|-------------|----------------|")
    parts.append("")
    parts.append("Rate severity: HIGH / MEDIUM / LOW.")
    parts.append("After the table, give a 2-sentence overall assessment of this batch.")

    return "\n".join(parts)


def _read_source_files(path_list: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Read source files from paths. Returns (files, errors)."""
    from pathlib import Path as _Path  # pylint: disable=import-outside-toplevel

    files: list[tuple[str, str]] = []
    errors: list[str] = []
    for p in path_list:
        fp = _Path(p).expanduser().resolve()
        if not fp.is_file():
            errors.append(f"Not found: {p}")
            continue
        try:
            content = fp.read_text(encoding="utf-8")
            files.append((str(fp.relative_to(fp.parent.parent.parent.parent)), content))
        except (OSError, UnicodeDecodeError, ValueError):
            files.append((str(fp.name), fp.read_text(encoding="utf-8", errors="replace")))
    return files, errors


def _batch_files(files: list[tuple[str, str]], batch_size: int, max_chars: int) -> list[list[tuple[str, str]]]:
    """Group files into batches respecting size + char limits."""
    batches: list[list[tuple[str, str]]] = []
    current_batch: list[tuple[str, str]] = []
    current_chars = 0
    for fp, content in files:
        if current_batch and (len(current_batch) >= batch_size or current_chars + len(content) > max_chars):
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append((fp, content))
        current_chars += len(content)
    if current_batch:
        batches.append(current_batch)
    return batches


def _resolve_review_providers(providers_json: str) -> str:
    """Resolve providers from config review_deep profile at high tier."""
    if providers_json and providers_json != "[]":
        return providers_json
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    cfg = get_rondo_config()
    profile = cfg.get("cloud", {}).get("profiles", {}).get("review_deep", {}).get("providers", [])
    if not profile:
        profile = ["gemini", "grok", "mistral", "openai"]
    from rondo.providers import _providers_config, load_providers_config  # pylint: disable=import-outside-toplevel

    load_providers_config()
    resolved = []
    for name in profile:
        model = _providers_config.get(name, {}).get("best_model", "")
        resolved.append(f"{name}:{model}" if model else name)
    return json.dumps(resolved)


def rondo_review_codebase(
    paths: str = "[]",
    focus: str = "",
    providers: str = "[]",
    batch_size: int = _DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> str:
    """Review multiple source files with AI providers — RONDO-215 Option C.

    Reads files, groups into batches, builds per-batch prompts with markdown
    fenced code blocks and architecture context, dispatches via rondo_multi_review.

    Calibrated from 4-model self-assessment (2026-04-09): all providers prefer
    batched calls over full dump, markdown fenced format, structured output.

    Args:
        paths: JSON array of file paths to review (relative or absolute).
        focus: Review focus — "reliability", "security", "dry", "architecture", or custom text.
        providers: JSON array of provider:model strings. Default: review_deep profile.
        batch_size: Files per batch (default 4, calibrated from provider self-assessment).
        dry_run: Preview prompts without dispatching.
    """
    try:
        path_list = json.loads(paths) if paths else []
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "error", "error": "Invalid paths JSON", "code": "ERR_INVALID_INPUT"})

    if not path_list:
        return json.dumps({"status": "error", "error": "No file paths provided", "code": "ERR_INVALID_INPUT"})

    files, errors = _read_source_files(path_list)
    if not files:
        return json.dumps({"status": "error", "error": f"No readable files: {errors}", "code": "ERR_INVALID_INPUT"})

    all_summaries = [_extract_module_summary(fp, content) for fp, content in files]
    batches = _batch_files(files, batch_size, _MAX_BATCH_CHARS)
    providers = _resolve_review_providers(providers)

    batch_results: list[dict] = []
    total_cost = 0.0
    for i, batch in enumerate(batches, 1):
        prompt = _build_batch_prompt(batch, all_summaries, focus, i, len(batches))

        if dry_run:
            batch_results.append(
                {"batch": i, "files": [fp for fp, _ in batch], "prompt_length": len(prompt), "status": "dry_run"}
            )
            continue

        result_json = rondo_multi_review(prompt=prompt, providers=providers, dry_run=False)
        result = json.loads(result_json)
        result["batch"] = i
        result["files"] = [fp for fp, _ in batch]
        batch_results.append(result)
        total_cost += result.get("total_cost_usd", 0)

    return json.dumps(
        {
            "status": "done" if not dry_run else "dry_run",
            "total_files": len(files),
            "total_batches": len(batches),
            "batch_size": batch_size,
            "focus": focus or "reliability, error handling, DRY, security",
            "providers": json.loads(providers),
            "total_cost_usd": total_cost,
            "file_errors": errors,
            "batches": batch_results,
        },
        indent=2,
    )


# -- sig: mgh-6201.cd.bd955f.7648.c0f05e
