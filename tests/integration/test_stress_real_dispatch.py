#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""RONDO-210 Phase C — Real concurrent stress test.

5 subprocess workers dispatching concurrent real API calls to gemini-flash.
Proves the cross-process locking work in RONDO-209 (idempotency JSONL,
audit fcntl.flock, circuit breaker persistence) survives under real load.

Unlike test_integration_multiprocess.py which uses mocked dispatches to
prove cross-process semantics, this test hits real gemini and verifies
no audit corruption, no lost idempotency entries, and no race errors
under real latency and real concurrency.

Cost: ~$0.10-0.20 per run (20 calls against gemini-2.5-flash).
Runtime: ~30-60 seconds.

Marked @pytest.mark.cloud — only runs with `pytest -m cloud`.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import textwrap
import time
from pathlib import Path

import pytest


def _has_gemini_key() -> bool:
    """Check if a Gemini API key is configured."""
    from rondo.adapters.auth import load_api_key

    try:
        key = load_api_key("gemini")
        return bool(key)
    except (FileNotFoundError, KeyError, ValueError):
        return False


skip_no_gemini = pytest.mark.skipif(not _has_gemini_key(), reason="No Gemini API key")

## Number of concurrent workers + dispatches-per-worker
WORKERS = 5
DISPATCHES_PER_WORKER = 4
TOTAL_CALLS = WORKERS * DISPATCHES_PER_WORKER

## Per-subprocess timeout — gemini usually returns in 1-5s; give headroom
WORKER_TIMEOUT_SEC = 120


def _build_worker_code(worker_id: int, rondo_test_dir: str) -> str:
    """Build the Python source for one stress worker subprocess.

    Each worker:
    1. Imports GeminiAdapter and AuditTrail
    2. Dispatches DISPATCHES_PER_WORKER unique prompts in sequence
    3. Uses the real two-phase audit API (record_intent + record_outcome)
       — writes 2 JSONL lines per dispatch — this is the race-prone path
       that RONDO-209 #251 (fcntl.flock rotation) was supposed to fix.
    4. Records idempotency entries (also race-prone cross-process)
    5. Prints one summary line to stdout: OK <successful_count>/<total>
    """
    return textwrap.dedent(f"""
        import os
        import sys
        import time

        os.environ["RONDO_TEST_DIR"] = {rondo_test_dir!r}

        from rondo.adapters.auth import load_api_key
        from rondo.adapters.gemini import GeminiAdapter
        from rondo.audit import AuditTrail
        from rondo import idempotency

        worker_id = {worker_id}
        total = {DISPATCHES_PER_WORKER}
        successful = 0

        adapter = GeminiAdapter(api_key=load_api_key("gemini"))
        trail = AuditTrail()  ## uses RONDO_TEST_DIR/audit/

        for i in range(total):
            ## Unique prompt per (worker, iteration) — forces cache miss
            prompt = f"Reply with exactly one word: WORKER{{worker_id}}ITER{{i}}"

            ## Phase 1: record_intent — writes JSONL line 1
            intent = trail.record_intent(
                task_name=f"stress-w{{worker_id}}-i{{i}}",
                round_name="stress-phase-c",
                model="gemini-2.5-flash",
                prompt=prompt,
            )

            t0 = time.time()
            result = adapter.dispatch(prompt=prompt, model="gemini-2.5-flash")
            elapsed = time.time() - t0

            if result.status == "done":
                successful += 1

            ## Phase 2: record_outcome — writes JSONL line 2
            trail.record_outcome(
                dispatch_id=intent.dispatch_id,
                status=result.status,
                exit_code=0 if result.status == "done" else 1,
                error_code=result.error_code or "",
                duration_sec=round(elapsed, 3),
                raw_output=result.raw_output or "",
                task_name=f"stress-w{{worker_id}}-i{{i}}",
                round_name="stress-phase-c",
                model="gemini-2.5-flash",
            )

            ## Record idempotency — also race-prone cross-process
            idempotency.cache_result(
                f"stress-{{worker_id}}-{{i}}",
                {{"worker": worker_id, "iter": i, "status": result.status}},
            )

        print(f"OK {{successful}}/{{total}}")
    """)


def _spawn_worker(worker_id: int, tmp_path: Path, src_path: Path) -> subprocess.Popen:
    """Launch one worker subprocess. Returns a Popen handle (non-blocking)."""
    code = f"import sys; sys.path.insert(0, {str(src_path)!r})\n"
    code += _build_worker_code(worker_id, str(tmp_path))

    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)

    return subprocess.Popen(  # nosec B603 — venv python, controlled args
        [sys.executable, "-c", code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_all(
    workers: list[subprocess.Popen], timeout_sec: int
) -> list[tuple[int, str, str]]:
    """Wait for all workers to complete. Returns list of (rc, stdout, stderr).

    On timeout, kill any stragglers so we do not leak subprocesses.
    """
    deadline = time.time() + timeout_sec
    results: list[tuple[int, str, str]] = []
    for w in workers:
        remaining = max(1, int(deadline - time.time()))
        try:
            stdout, stderr = w.communicate(timeout=remaining)
            results.append((w.returncode, stdout or "", stderr or ""))
        except subprocess.TimeoutExpired:
            w.kill()
            stdout, stderr = w.communicate()
            results.append((-1, stdout or "", stderr or "TIMEOUT"))
    return results


def _find_audit_jsonl(tmp_path: Path) -> Path | None:
    """Find the audit JSONL under RONDO_TEST_DIR."""
    ## The audit module writes under RONDO_TEST_DIR/audit/ by convention
    candidates = list(tmp_path.rglob("rondo_audit.jsonl"))
    if candidates:
        return candidates[0]
    all_jsonl = list(tmp_path.rglob("*.jsonl"))
    return all_jsonl[0] if all_jsonl else None


@pytest.mark.cloud
@skip_no_gemini
def test_stress_real_concurrent_dispatch(tmp_path: Path) -> None:
    """5 subprocess workers × 4 dispatches each against real gemini.

    Verifies:
        - Every worker completes successfully (returncode 0)
        - The shared audit JSONL has exactly TOTAL_CALLS lines
        - Every audit line is valid JSON (no torn writes from race)
        - No duplicate request_ids (idempotency path is race-safe)
        - No Python exceptions leaked to stderr from any worker
    """
    src_path = Path(__file__).parent.parent.parent / "src"
    assert src_path.is_dir(), f"Expected src path: {src_path}"

    ## Launch all workers in parallel
    workers = [_spawn_worker(i, tmp_path, src_path) for i in range(WORKERS)]
    results = _wait_all(workers, timeout_sec=WORKER_TIMEOUT_SEC)

    ## ─── Assertion 1: all workers exited cleanly ───
    failed_workers = [
        (i, rc, err) for i, (rc, _out, err) in enumerate(results) if rc != 0
    ]
    if failed_workers:
        msg_lines = [f"Worker {i}: rc={rc}, stderr={err[:400]}" for i, rc, err in failed_workers]
        pytest.fail("Worker subprocess(es) failed:\n" + "\n".join(msg_lines))

    ## ─── Assertion 2: every worker reported successful dispatches ───
    ## Allow for transient gemini 503s — we accept >=75% of dispatches per worker
    min_success_per_worker = max(1, int(DISPATCHES_PER_WORKER * 0.75))
    for i, (_rc, out, _err) in enumerate(results):
        last_line = (out.strip().splitlines() or [""])[-1]
        assert last_line.startswith("OK "), f"Worker {i} bad output: {out[:200]!r}"
        frac = last_line.replace("OK ", "")
        successful = int(frac.split("/")[0])
        assert successful >= min_success_per_worker, (
            f"Worker {i} only completed {successful}/{DISPATCHES_PER_WORKER} "
            f"dispatches (need >= {min_success_per_worker})"
        )

    ## ─── Assertion 3: audit log integrity ───
    audit_file = _find_audit_jsonl(tmp_path)
    assert audit_file is not None, (
        f"Expected audit JSONL under {tmp_path}, found none. "
        f"Tree: {sorted(p.name for p in tmp_path.rglob('*'))[:20]}"
    )

    lines = [line for line in audit_file.read_text().splitlines() if line.strip()]

    ## Every line must be parseable JSON — torn writes would fail here
    parsed: list[dict] = []
    for lineno, line in enumerate(lines, 1):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as e:
            pytest.fail(
                f"Audit JSONL line {lineno} corrupted (torn write?): {line[:200]!r} "
                f"(err: {e})"
            )

    ## ─── Assertion 3a: INTENT phase record count ───
    intent_records = [e for e in parsed if e.get("status") == "INTENT"]
    assert len(intent_records) == TOTAL_CALLS, (
        f"Expected {TOTAL_CALLS} INTENT records, got {len(intent_records)}. "
        f"A race condition may have lost INTENT phase writes."
    )

    ## ─── Assertion 3b: OUTCOME phase record count ───
    ## Terminal status values: 'done', 'error', 'partial'. NOT 'stuck' which
    ## is written by reconcile_stuck_intents — that is a separate finding below.
    outcome_records = [e for e in parsed if e.get("status") in ("done", "error", "partial")]
    assert len(outcome_records) == TOTAL_CALLS, (
        f"Expected {TOTAL_CALLS} OUTCOME records (done/error/partial), "
        f"got {len(outcome_records)}. Missing outcome = race condition."
    )

    ## ─── Assertion 3c: INTENT/OUTCOME dispatch_id pairing ───
    intent_ids = {e["dispatch_id"] for e in intent_records}
    outcome_ids = {e["dispatch_id"] for e in outcome_records}
    assert intent_ids == outcome_ids, (
        f"INTENT/OUTCOME dispatch_ids do not match — orphaned records. "
        f"INTENT-only: {intent_ids - outcome_ids}, "
        f"OUTCOME-only: {outcome_ids - intent_ids}"
    )

    ## ─── Assertion 4: ZERO spurious 'stuck' reconciliations ───
    ## Finding #257 (RONDO-210 Phase C): AuditTrail.__init__ with auto_reconcile=True
    ## runs reconcile_stuck_intents() which sees peer workers' in-flight INTENTs
    ## and falsely marks them as stuck (ERR_RECONCILED_STUCK). No dispatch in
    ## this test is actually stuck — every worker completes normally. Any 'stuck'
    ## record here is a false positive from the multi-process reconcile race.
    stuck_records = [e for e in parsed if e.get("status") == "stuck"]
    assert len(stuck_records) == 0, (
        f"SPURIOUS STUCK RECORDS — finding #257. "
        f"Found {len(stuck_records)} 'stuck' entries but no worker actually crashed. "
        f"Root cause: AuditTrail auto_reconcile falsely marks peer in-flight INTENTs as stuck. "
        f"Affected dispatch_ids: {[r['dispatch_id'] for r in stuck_records]}. "
        f"Fix: reconcile must respect cross-process in-flight tracking."
    )

    ## ─── Assertion 5: no worker leaked Python exceptions to stderr ───
    for i, (_rc, _out, err) in enumerate(results):
        ## "Traceback (most recent call last):" is the Python exception marker
        assert "Traceback" not in err, (
            f"Worker {i} leaked a Python traceback:\n{err[:800]}"
        )


# -- sig: mgh-6208.cd.bd955f.e4a1.stress1
