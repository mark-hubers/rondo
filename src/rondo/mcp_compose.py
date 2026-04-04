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
        # -- REQ-109 req 052/088: concurrent dispatch via ThreadPoolExecutor
        # -- Each thread gets its own adapter + HTTP connection (no shared mutable state)
        from concurrent.futures import ThreadPoolExecutor, as_completed  # pylint: disable=import-outside-toplevel

        def _dispatch_one(provider_model: str) -> dict:
            """Dispatch to one provider — runs in its own thread."""
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
            output = task.get("raw_output", "")
            return {
                "provider": provider_model,
                "status": r.get("status", "error"),
                "output": output,
                "cost_usd": r.get("total_cost_usd", 0),
                "duration_sec": task.get("duration_sec", 0),
            }

        with ThreadPoolExecutor(max_workers=len(provider_list)) as pool:
            futures = {pool.submit(_dispatch_one, p): p for p in provider_list}
            # -- Collect results in original provider order
            results_map: dict[str, dict] = {}
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    results_map[provider] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results_map[provider] = {
                        "provider": provider,
                        "status": "error",
                        "output": "",
                        "cost_usd": 0,
                        "duration_sec": 0,
                        "error": str(exc),
                    }

        # -- Preserve original provider order in output
        for provider in provider_list:
            result = results_map.get(provider, {"provider": provider, "status": "error"})
            per_provider.append(result)
            output = result.get("output", "")
            if output:
                all_findings.append(f"[{provider}]: {output}")

    total_cost = sum(p.get("cost_usd", 0) for p in per_provider)

    return json.dumps(
        {
            "status": "done",
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


# -- sig: mgh-6201.cd.bd955f.7648.c0f05e
