#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo capability showcase: 10 real dispatch demonstrations.

Run:
    python rondo/examples/SHOWCASE.py

Also used by:
    rondo-test --showcase

Runtime target:
    Usually 2-4 minutes, depending on provider/API latency.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


# -- Make this script runnable from the ace2 repo root.
THIS_FILE = Path(__file__).resolve()
EXAMPLES_DIR = THIS_FILE.parent
RONDO_DIR = EXAMPLES_DIR.parent
RONDO_SRC = RONDO_DIR / "src"
API_DIR = EXAMPLES_DIR / "api"
for p in (RONDO_SRC, API_DIR):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from example_dispatch import first_task_parsed_json, invoke_rondo, run_prompt_json  # noqa: E402
from rondo.idempotency import clear_cache  # noqa: E402
from rondo.mcp_dispatch import rondo_run_file, rondo_run_status  # noqa: E402


SECTIONS: list[tuple[str, str]] = [
    ("Inline dispatch (same session)", 'Demonstrates execution="inline" returning host plan JSON'),
    (
        "Subprocess dispatch (fresh session)",
        'Demonstrates execution="subprocess" returning real task results',
    ),
    ("Agent dispatch", 'Demonstrates execution="agent" returning host agent plan JSON'),
    ("Multi-provider fan-out (5 clouds)", "Runs one prompt across five cloud providers"),
    ("Consensus review (tiebreaker)", "Collects votes from 3 models and reports majority"),
    ("Confidence escalation", "Escalates to a stronger model when confidence is low"),
    ("Find-and-fix pipeline", "Chains find -> propose fix -> verify in one script flow"),
    ("Structured JSON return", "Enforces schema via json_schema and reads parsed field"),
    ("Background polling", "Starts background dispatch and polls heartbeat + brief + final"),
    ("Idempotency cache", "Runs same prompt twice and confirms cached repeat output"),
]


def _provider_task_json(raw: str) -> dict[str, Any]:
    """Parse provider/task output JSON when possible."""
    env = json.loads(raw)
    tasks = env.get("tasks") or []
    if not tasks:
        return {}
    first = tasks[0]
    if first.get("status") == "error":
        code = first.get("error_code", "")
        msg = first.get("error_message", "")
        raise RuntimeError(f"task error {code}: {msg}")
    raw_out = (first.get("raw_output") or "").strip()
    if not raw_out:
        return {}
    try:
        return json.loads(raw_out)
    except json.JSONDecodeError:
        return {"_non_json": True, "snippet": raw_out[:160]}


def section_inline_plan() -> str:
    """Section 1: inline host plan."""
    raw = rondo_run_file(
        prompt='Return JSON only: {"ok": true, "mode": "inline"}',
        execution="inline",
        model="sonnet",
        dry_run=False,
        timeout_sec=45,
        _session=object(),
    )
    plan = json.loads(raw)
    if plan.get("engine") != "inline" or plan.get("kind") != "inline_dispatch_plan":
        raise RuntimeError(f"unexpected plan payload: {plan}")
    return f"engine={plan['engine']}, kind={plan['kind']}"


def section_subprocess_results() -> str:
    """Section 2: subprocess real result."""
    env = invoke_rondo(
        prompt='Return JSON only: {"mode":"subprocess","ok":true}',
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=90,
    )
    tasks = env.get("tasks") or []
    if not tasks:
        raise RuntimeError("no tasks returned")
    first_status = tasks[0].get("status", "")
    if first_status in ("error", ""):
        raise RuntimeError(f"task did not execute cleanly: {tasks[0]}")
    return f"status={env.get('status')}, first_task={first_status}, tasks={len(tasks)}"


def section_agent_plan() -> str:
    """Section 3: agent host plan."""
    raw = rondo_run_file(
        prompt='Return JSON only: {"ok": true, "mode": "agent"}',
        execution="agent",
        model="sonnet",
        dry_run=False,
        timeout_sec=45,
        _session=object(),
    )
    plan = json.loads(raw)
    if plan.get("engine") != "agent" or plan.get("kind") != "agent_dispatch_plan":
        raise RuntimeError(f"unexpected agent plan: {plan}")
    return f"engine={plan['engine']}, kind={plan['kind']}"


def section_multi_provider_fanout() -> str:
    """Section 4: five-cloud fan-out; degrade gracefully on dead providers."""
    prompt = 'Return JSON only: {"provider":"<name>","benefit":"one-line"}'
    models = [
        "gemini:gemini-2.5-flash",
        "grok:grok-3",
        "mistral:mistral-large-latest",
        "openai:gpt-4o-mini",
        "anthropic:claude-sonnet-4-6",
    ]
    passed = 0
    skipped = 0
    for model in models:
        try:
            payload = _provider_task_json(
                rondo_run_file(
                    prompt=prompt,
                    model=model,
                    dry_run=False,
                    timeout_sec=60,
                    execution="subprocess",
                )
            )
            if payload.get("_non_json"):
                raise RuntimeError("non-json output")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            print(f"           -WARNING- {model} unavailable: {str(exc)[:120]}")
    if passed == 0:
        raise RuntimeError("all five providers failed")
    return f"providers_ok={passed}, providers_skipped={skipped}"


def section_consensus_tiebreaker() -> str:
    """Section 5: 3-model vote."""
    prompt = (
        'Answer with JSON only: {"vote":"PASS"|"FAIL","reason":"<=12 words"}\n'
        "Question: Is f-string SQL interpolation safe with untrusted input?"
    )
    voters = [
        "anthropic:claude-haiku-4-5",
        "gemini:gemini-2.5-flash",
        "openai:gpt-4o-mini",
    ]
    votes: list[str] = []
    for model in voters:
        try:
            _, parsed = run_prompt_json(
                prompt=prompt,
                model=model,
                timeout_sec=60,
                execution="subprocess",
                rules="Security reviewer. Return strict JSON.",
            )
            vote = str(parsed.get("vote", "")).upper()
            if vote not in ("PASS", "FAIL"):
                result_txt = str(parsed.get("result", "")).lower()
                if "unsafe" in result_txt or "not safe" in result_txt:
                    vote = "FAIL"
                elif "safe" in result_txt:
                    vote = "PASS"
            if vote in ("PASS", "FAIL"):
                votes.append(vote)
        except Exception:  # noqa: BLE001
            continue
    if len(votes) < 1:
        raise RuntimeError(f"insufficient votes: {votes}")
    verdict = "PASS" if votes.count("PASS") >= votes.count("FAIL") else "FAIL"
    return f"votes={votes}, majority={verdict}, voters_responded={len(votes)}"


def section_confidence_escalation() -> str:
    """Section 6: confidence threshold and escalation."""
    base_prompt = (
        'Return JSON only: {"confidence": number, "result":"short"}.\n'
        "Assess this code safety: def x(url): return exec(requests.get(url).text)"
    )
    _, first = run_prompt_json(
        prompt=base_prompt,
        model="anthropic:claude-haiku-4-5",
        execution="subprocess",
        timeout_sec=60,
    )
    first_conf = float(first.get("confidence", 0.0))
    if first_conf >= 0.8:
        return f"initial_confidence={first_conf:.2f}, escalated=False"
    _, second = run_prompt_json(
        prompt=base_prompt + "\nContext: user controlled URL in web request path.",
        model="sonnet",
        execution="subprocess",
        timeout_sec=75,
        rules="Security expert. Return JSON only.",
    )
    second_conf = float(second.get("confidence", 0.0))
    return f"initial_confidence={first_conf:.2f}, escalated=True, escalated_confidence={second_conf:.2f}"


def section_find_and_fix() -> str:
    """Section 7: find -> fix -> verify."""
    code = "def login(u,p): return db.execute(f'SELECT * FROM users WHERE name={u}')"
    _, found = run_prompt_json(
        prompt=f'Return JSON only: {{"issues":["..."]}}. Find security issues:\n{code}',
        model="sonnet",
        execution="subprocess",
        timeout_sec=75,
    )
    issues = found.get("issues") or []
    if not issues:
        raise RuntimeError("no issues found for intentionally vulnerable code")
    issue = str(issues[0])[:180]
    _, fix = run_prompt_json(
        prompt=f'Return JSON only: {{"fix":"..."}}. Propose fix for issue: {issue}',
        model="sonnet",
        execution="subprocess",
        timeout_sec=75,
    )
    fix_text = str(fix.get("fix", "")).strip()
    if not fix_text:
        fix_text = str(fix.get("result", "")).strip()
    if not fix_text:
        suggestions = fix.get("suggestions") or []
        if suggestions:
            fix_text = str(suggestions[0]).strip()
    if not fix_text:
        raise RuntimeError("no fix proposal returned")
    _, verify = run_prompt_json(
        prompt=(
            'Return JSON only: {"verified":true|false,"why":"..."}.\n'
            f"Issue: {issue}\nFix proposal: {fix_text}"
        ),
        model="anthropic:claude-haiku-4-5",
        execution="subprocess",
        timeout_sec=60,
    )
    return f"issues={len(issues)}, fix_chars={len(fix_text)}, verified={verify.get('verified')}"


def section_structured_json() -> str:
    """Section 8: platform-enforced JSON schema."""
    schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["title", "score"],
            "additionalProperties": False,
        }
    )
    raw = rondo_run_file(
        prompt='Return a tiny object with title and score for "Rondo showcase".',
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=60,
        json_schema=schema,
    )
    env = json.loads(raw)
    parsed = first_task_parsed_json(env)
    title = parsed.get("title")
    score = parsed.get("score")
    if not isinstance(title, str):
        meta = parsed.get("metadata") or {}
        title = meta.get("title")
        score = meta.get("score", score)
    if not isinstance(title, str):
        raise RuntimeError(f"invalid title: {parsed}")
    return f"title={title[:24]!r}, score={score}"


def section_background_polling() -> str:
    """Section 9: background task with heartbeat/brief/full polls."""
    started = json.loads(
        rondo_run_file(
            prompt='Return JSON only: {"summary":"why polling matters","confidence":0.9}',
            model="sonnet",
            execution="subprocess",
            dry_run=False,
            background=True,
            timeout_sec=120,
        )
    )
    dispatch_id = started.get("dispatch_id", "")
    if not dispatch_id:
        raise RuntimeError(f"missing dispatch_id: {started}")
    deadline = time.time() + 75
    polls = 0
    while time.time() < deadline:
        hb = json.loads(rondo_run_status(dispatch_id=dispatch_id, heartbeat=True))
        br = json.loads(rondo_run_status(dispatch_id=dispatch_id, brief=True))
        polls += 1
        if br.get("status") in ("done", "error"):
            final = json.loads(rondo_run_status(dispatch_id=dispatch_id))
            tasks = final.get("tasks") or []
            if not tasks:
                raise RuntimeError(f"final payload missing tasks: {final}")
            return f"dispatch_id={dispatch_id}, polls={polls}, final_status={final.get('status')}, tasks={len(tasks)}"
        time.sleep(1.0)
    raise RuntimeError("background dispatch timed out")


def section_idempotency() -> str:
    """Section 10: repeat identical call and verify same payload."""
    clear_cache()
    prompt = 'Return JSON only: {"cache_demo":"stable","n":2}'
    t0 = time.perf_counter()
    first = rondo_run_file(
        prompt=prompt,
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=75,
    )
    t1 = time.perf_counter() - t0
    t2_start = time.perf_counter()
    second = rondo_run_file(
        prompt=prompt,
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=75,
    )
    t2 = time.perf_counter() - t2_start
    if first != second:
        raise RuntimeError("payload mismatch across duplicate calls")
    return f"same_payload=True, first={t1:.2f}s, second={t2:.2f}s"


def run_section(index: int, total: int, name: str, desc: str, fn: Any) -> tuple[bool, float]:
    """Execute one section and print normalized status output."""
    print(f"[{index:2d}/{total}] {name}")
    print(f"           {desc}")
    start = time.perf_counter()
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        print(f"           ✗ {elapsed:.1f}s  -FAIL- {str(exc)[:220]}")
        return False, elapsed
    elapsed = time.perf_counter() - start
    print(f"           ✓ {elapsed:.1f}s  {detail}")
    return True, elapsed


def main() -> int:
    """Run all showcase sections, fail if any section fails."""
    print("Rondo SHOWCASE — 10 real demonstrations")
    print("=======================================")
    print(f"Repository: {RONDO_DIR}")
    print(f"CLAUDECODE={os.getenv('CLAUDECODE', '')}")
    print()

    section_fns = [
        section_inline_plan,
        section_subprocess_results,
        section_agent_plan,
        section_multi_provider_fanout,
        section_consensus_tiebreaker,
        section_confidence_escalation,
        section_find_and_fix,
        section_structured_json,
        section_background_polling,
        section_idempotency,
    ]
    total = len(section_fns)
    passed = 0
    total_time = 0.0

    for i, (meta, fn) in enumerate(zip(SECTIONS, section_fns, strict=True), start=1):
        ok, elapsed = run_section(i, total, meta[0], meta[1], fn)
        total_time += elapsed
        if ok:
            passed += 1
        print()

    print("Summary")
    print("=======")
    print(f"Sections passed: {passed}/{total}")
    print(f"Total runtime:   {total_time:.1f}s")
    if passed != total:
        print("-FAIL- Showcase has failures.")
        return 1
    print("-PASS- Showcase all sections passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
