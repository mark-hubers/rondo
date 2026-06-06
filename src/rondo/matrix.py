# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Experiment matrix engine — REQ-113 (RONDO-308).

model × effort × context × replicates as ONE budgeted, resumable, audited,
blind-scorable run. Driver: the USH essay-split protocol done by hand
(PROTOCOL.md 2026-06-03) and its wish-list (replicates, blind, variants).

Design:
    - dispatch is INJECTED (tests are hermetic; production uses _live_dispatch)
    - budget is a HARD ceiling: estimate-abort before, running-stop during
    - manifest.json per run = resume state + report source
    - blind mode: group codes sealed with SHA-256, revealed on command
    - self-ratings reported but labeled UNCALIBRATED, never ranked on

Import direction:
    matrix.py → adapters.factory (live dispatch only), chat_completions
    (cost table), yaml. No engine/dispatch imports — cells go through
    adapters directly in v1 (provider:model API path).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ALLOWED_FIELDS = {
    "name",
    "prompt",
    "prompt_file",
    "models",
    "efforts",
    "contexts",
    "replicates",
    "blind",
    "baseline",
    "budget_usd",
    "judge",
    "judge_rubric",  # -- req 051: rubric prompt, required with judge
    "inputs",  # -- req 005: {{name}} placeholder files
}
REQUIRED_FIELDS = {"name", "models", "budget_usd"}
EST_OUTPUT_TOKENS = 2048  # -- conservative per-cell output budget for estimates
MIN_CELL_EST_USD = 0.001  # -- floor so unknown models never estimate $0
NOISY_STDEV_RATIO = 0.25  # -- req 032: stdev > 25% of mean = noisy cell


class MatrixError(Exception):
    """Matrix definition or budget error — REQ-113 reqs 003, 010."""


@dataclass
class MatrixSpec:
    """A validated experiment matrix definition — REQ-113 req 001."""

    name: str
    prompt: str
    models: list[str]
    budget_usd: float
    efforts: list[str] = field(default_factory=list)
    contexts: dict[str, str] = field(default_factory=lambda: {"default": "none"})
    replicates: int = 1
    blind: bool = False
    baseline: str = ""
    judge: str = ""
    judge_rubric: str = ""  # -- req 051: caller-supplied rubric, required with judge


def load_matrix(path: str) -> MatrixSpec:
    """Load + validate a matrix YAML — REQ-113 reqs 001, 003.

    safe_load only; unknown fields rejected; required fields enforced.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MatrixError("matrix YAML must be a mapping")
    unknown = set(raw) - ALLOWED_FIELDS
    if unknown:
        raise MatrixError(f"unknown matrix field(s): {sorted(unknown)} — allowed: {sorted(ALLOWED_FIELDS)}")
    missing = REQUIRED_FIELDS - set(raw)
    if missing:
        raise MatrixError(f"missing required field(s): {sorted(missing)}")
    prompt = raw.get("prompt", "")
    if not prompt and raw.get("prompt_file"):
        prompt = Path(raw["prompt_file"]).expanduser().read_text(encoding="utf-8")
    if not prompt:
        raise MatrixError("missing required field(s): prompt (or prompt_file)")
    # -- REQ-113 req 005 (first real-use lesson): file inputs substitute into
    # -- {{name}} placeholders; an unresolved placeholder ABORTS — a template
    # -- must never be dispatched as if it were content (the 4.6v4.8 run
    # -- dispatched a paste-here placeholder; all 6 cells correctly refused).
    for input_name, input_path in (raw.get("inputs") or {}).items():
        content = Path(str(input_path)).expanduser().read_text(encoding="utf-8")
        prompt = prompt.replace("{{" + str(input_name) + "}}", content)
    import re  # pylint: disable=import-outside-toplevel

    leftover = re.findall(r"\{\{\w+\}\}", prompt)
    if leftover:
        raise MatrixError(f"unresolved prompt placeholder(s): {sorted(set(leftover))} — add them under `inputs:`")
    # -- req 051 (RONDO-317): a judge without a rubric scores against
    # -- nothing — refuse at load, not at dispatch time
    if raw.get("judge") and not raw.get("judge_rubric"):
        raise MatrixError("judge set but judge_rubric missing — req 051 requires a caller-supplied rubric")
    contexts = raw.get("contexts") or {"default": "none"}
    return MatrixSpec(
        name=str(raw["name"]),
        prompt=prompt,
        models=list(raw["models"]),
        budget_usd=float(raw["budget_usd"]),
        efforts=list(raw.get("efforts") or []),
        contexts={str(k): str(v) for k, v in contexts.items()},
        replicates=int(raw.get("replicates", 1)),
        blind=bool(raw.get("blind", False)),
        baseline=str(raw.get("baseline", "")),
        judge=str(raw.get("judge", "")),
        judge_rubric=str(raw.get("judge_rubric", "")),
    )


def default_effort_capable(model: str) -> bool:
    """Effort applies to thinking-default Claude models — REQ-109 reqs 200/204."""
    from rondo.adapters.anthropic_api import DEFAULT_THINKING_MODEL_PATTERNS  # pylint: disable=import-outside-toplevel

    bare = model.split(":", 1)[-1]
    return any(fnmatch(bare, pat) for pat in DEFAULT_THINKING_MODEL_PATTERNS) or bare in ("high",)


def build_grid(spec: MatrixSpec, *, effort_capable: Callable[[str], bool]) -> list[dict[str, Any]]:
    """Expand the matrix into cells — REQ-113 reqs 002, 004.

    Effort axis collapses to a single 'n/a' for non-effort models: never an
    error, never duplicated spend.
    """
    efforts = spec.efforts or ["n/a"]
    cells: list[dict[str, Any]] = []
    for model in spec.models:
        model_efforts = efforts if effort_capable(model) else ["n/a"]
        for effort in model_efforts:
            for ctx_name in spec.contexts:
                for rep in range(1, spec.replicates + 1):
                    key = f"{model}|{effort}|{ctx_name}|r{rep}"
                    cells.append({"model": model, "effort": effort, "context": ctx_name, "replicate": rep, "key": key})
    return cells


def estimate_grid_cost(cells: list[dict[str, Any]], prompt: str) -> float:
    """Pre-dispatch full-grid estimate — REQ-113 req 010."""
    from rondo.adapters.chat_completions import compute_cost_usd  # pylint: disable=import-outside-toplevel

    in_tokens = max(1, len(prompt) // 4)
    total = 0.0
    for cell in cells:
        bare = cell["model"].split(":", 1)[-1]
        total += max(compute_cost_usd(bare, in_tokens, EST_OUTPUT_TOKENS), MIN_CELL_EST_USD)
    return total


def _matrix_base_dir(base_dir: str | None) -> Path:
    """Resolve the matrix storage root — honors RONDO_TEST_DIR (hermeticity, #292)."""
    if base_dir:
        return Path(base_dir).expanduser()
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return Path(test_dir) / "matrix"
    return Path("~/.rondo/matrix").expanduser()


def _group_key(cell: dict[str, Any]) -> str:
    """Replicates share a group: model|effort|context."""
    return f"{cell['model']}|{cell['effort']}|{cell['context']}"


def _save_manifest(out_dir: Path, manifest: dict[str, Any]) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def _resolve_context_text(spec: MatrixSpec, ctx_name: str) -> str:
    src = spec.contexts.get(ctx_name, "none")
    if src in ("none", ""):
        return ""
    return Path(src).expanduser().read_text(encoding="utf-8")


def _load_or_init_manifest(spec: MatrixSpec, out_dir: Path, cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume manifest if present, else create + blind-seal — reqs 022, 040-042.

    Extracted from run_matrix (RONDO-322 complexity lock).
    """
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest: dict[str, Any] = {
        "name": spec.name,
        "created_at": datetime.now(UTC).isoformat(),
        "blind": spec.blind,
        "baseline": spec.baseline,
        "spent_usd": 0.0,
        "cells": {},
        "revealed_at": "",
    }
    # -- blind seal (reqs 040, 042): group codes, mapping sealed + hashed
    if spec.blind:
        groups = sorted({_group_key(c) for c in cells})
        mapping = {f"cell-{chr(ord('A') + i)}": g for i, g in enumerate(groups)}
        sealed = json.dumps(mapping, sort_keys=True)
        (out_dir / "manifest.sealed.json").write_text(sealed, encoding="utf-8")
        (out_dir / "manifest.sealed.json").chmod(0o600)
        manifest["sealed_sha256"] = hashlib.sha256(sealed.encode("utf-8")).hexdigest()
    _save_manifest(out_dir, manifest)
    return manifest


def run_matrix(
    spec: MatrixSpec,
    *,
    dispatch: Callable[[dict[str, Any], str], dict[str, Any]],
    effort_capable: Callable[[str], bool] = default_effort_capable,
    base_dir: str | None = None,
    estimate_ok: bool = False,
) -> dict[str, Any]:
    """Run the grid — REQ-113 reqs 010-012, 020-023, 030, 040-042.

    `dispatch(cell, full_prompt)` returns {status, cost_usd, latency_sec,
    output, self_rating?}. Injected for tests; production = _live_dispatch.
    `estimate_ok=True` skips the pre-run estimate gate (the RUNNING budget
    stop always applies — the ceiling is never optional).
    """
    cells = build_grid(spec, effort_capable=effort_capable)
    if not estimate_ok:
        est = estimate_grid_cost(cells, spec.prompt)
        if est > spec.budget_usd:
            raise MatrixError(
                f"estimated grid cost ${est:.3f} exceeds budget ${spec.budget_usd:.3f} "
                f"({len(cells)} cells) — raise budget_usd or shrink the grid"
            )

    out_dir = _matrix_base_dir(base_dir) / spec.name
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = _load_or_init_manifest(spec, out_dir, cells)

    code_by_group: dict[str, str] = {}
    if spec.blind:
        sealed_path = out_dir / "manifest.sealed.json"
        mapping = json.loads(sealed_path.read_text(encoding="utf-8"))
        code_by_group = {group: code for code, group in mapping.items()}

    for cell in cells:
        if manifest["cells"].get(cell["key"], {}).get("status") == "done":
            continue  # -- req 022: idempotent resume
        if manifest["spent_usd"] >= spec.budget_usd:
            manifest["cells"][cell["key"]] = {"status": "budget_exhausted"}
            continue  # -- req 012: ceiling reached — record and move on

        ctx_text = _resolve_context_text(spec, cell["context"])
        full_prompt = spec.prompt + (f"\n\n## Context\n\n{ctx_text}" if ctx_text else "")
        record: dict[str, Any] = {"status": "error", "cost_usd": 0.0, "latency_sec": 0.0}
        try:
            result = dispatch(cell, full_prompt)
            record.update(
                {
                    "status": result.get("status", "error"),
                    "cost_usd": float(result.get("cost_usd", 0.0)),
                    "latency_sec": float(result.get("latency_sec", 0.0)),
                    "self_rating": result.get("self_rating"),
                    "error": result.get("error", ""),
                }
            )
            # -- per-cell result file (req 030); blind = coded filename (req 040)
            group = _group_key(cell)
            stem = f"{code_by_group[group]}-r{cell['replicate']}" if spec.blind else cell["key"].replace("|", "_")
            safe_stem = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in stem)
            (out_dir / f"{safe_stem}.txt").write_text(str(result.get("output", "")), encoding="utf-8")
            record["file"] = f"{safe_stem}.txt"
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            # -- req 023: one cell's failure never aborts the run
            record["error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("-WARNING- matrix cell %s failed: %s", cell["key"], exc)

        manifest["spent_usd"] = round(manifest["spent_usd"] + record["cost_usd"], 6)

        # -- req 051 (RONDO-317): judge each completed cell. The judge is an
        # -- ordinary dispatch through the SAME injected dispatcher (audited
        # -- in production), costed against the SAME budget, and its crash
        # -- never kills the cell it was scoring.
        if spec.judge and record.get("status") == "done":
            if manifest["spent_usd"] >= spec.budget_usd:
                record["judge"] = {"skipped": "budget_exhausted"}
            else:
                record["judge"] = _judge_cell(spec, record, out_dir, dispatch)
                manifest["spent_usd"] = round(manifest["spent_usd"] + record["judge"].get("cost_usd", 0.0), 6)

        manifest["cells"][cell["key"]] = record
        _save_manifest(out_dir, manifest)  # -- crash-safe resume after every cell

    return manifest


def _judge_cell(
    spec: MatrixSpec,
    record: dict[str, Any],
    out_dir: Path,
    dispatch: Callable[[dict[str, Any], str], dict[str, Any]],
) -> dict[str, Any]:
    """Score one completed cell with the judge model — req 051."""
    try:
        output_text = (out_dir / record["file"]).read_text(encoding="utf-8")
    except (OSError, KeyError) as exc:
        return {"score": None, "reason": "", "cost_usd": 0.0, "error": f"no cell output to judge: {exc}"}

    baseline_block = ""
    if spec.baseline:
        try:
            baseline_text = Path(spec.baseline).expanduser().read_text(encoding="utf-8")
            baseline_block = f"\n\n## Baseline (reference)\n\n{baseline_text}"
        except OSError:
            baseline_block = ""

    judge_prompt = (
        f"{spec.judge_rubric}{baseline_block}\n\n## Candidate output\n\n{output_text}\n\n"
        'Return ONLY JSON: {"score": <0-10 number>, "reason": "<one sentence>"}'
    )
    judge_cell = {"model": spec.judge, "effort": "n/a", "context": "judge", "replicate": 0, "is_judge": True}
    try:
        result = dispatch(judge_cell, judge_prompt)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return {"score": None, "reason": "", "cost_usd": 0.0, "error": f"{exc}"}

    score: float | None = None
    reason = ""
    raw = str(result.get("output", ""))
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start : end + 1]) if start >= 0 <= end else {}
        if isinstance(parsed.get("score"), (int, float)):
            score = float(parsed["score"])
        reason = str(parsed.get("reason", ""))[:200]
    except (json.JSONDecodeError, ValueError, TypeError):
        reason = "unparseable judge output"
    return {"score": score, "reason": reason, "cost_usd": float(result.get("cost_usd", 0.0)), "error": ""}


def _live_dispatch(cell: dict[str, Any], full_prompt: str) -> dict[str, Any]:
    """Production cell dispatch — provider:model via the adapter layer (v1).

    Audited like any dispatch (adapters flow through the shared pipeline).
    Subprocess (Max-plan claude) models: follow-up — REQ-113 v2.
    """
    from rondo.adapters.auth import load_api_key  # pylint: disable=import-outside-toplevel
    from rondo.adapters.factory import get_adapter  # pylint: disable=import-outside-toplevel
    from rondo.providers import parse_model  # pylint: disable=import-outside-toplevel

    provider, model = parse_model(cell["model"])
    if not provider or provider == "claude":
        raise ValueError(f"matrix v1 requires provider-prefixed models; got {cell['model']!r}")
    _ = load_api_key  # -- key handled inside factory; kept for explicitness
    adapter = get_adapter(provider, model)
    if adapter is None:
        raise ValueError(f"no adapter for provider {provider!r}")
    kwargs: dict[str, Any] = {}
    if cell["effort"] not in ("n/a", ""):
        kwargs["effort"] = cell["effort"]
    start = time.monotonic()
    tr = adapter.dispatch(prompt=full_prompt, model=model, **kwargs)
    rating = None
    try:
        parsed = json.loads(tr.raw_output) if tr.raw_output.strip().startswith("{") else None
        if isinstance(parsed, dict):
            meta = parsed.get("_meta") or {}
            rating = meta.get("quality") or parsed.get("confidence")
    except (json.JSONDecodeError, AttributeError):
        rating = None
    return {
        "status": tr.status,
        "cost_usd": tr.cost_usd or 0.0,
        "latency_sec": time.monotonic() - start,
        "output": tr.raw_output or "",
        "self_rating": rating,
        "error": tr.error_message or "",
    }


def run_matrix_live(spec: MatrixSpec, *, base_dir: str | None = None) -> dict[str, Any]:
    """Run a matrix with real provider dispatch (CLI entry)."""
    return run_matrix(spec, dispatch=_live_dispatch, base_dir=base_dir)


def reveal_matrix(name: str, *, base_dir: str | None = None) -> dict[str, str]:
    """Reveal the blind mapping — REQ-113 reqs 041-042 (seal verified)."""
    out_dir = _matrix_base_dir(base_dir) / name
    sealed_path = out_dir / "manifest.sealed.json"
    if not sealed_path.exists():
        raise MatrixError(f"matrix {name!r} has no sealed mapping (not a blind run?)")
    sealed = sealed_path.read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.get("sealed_sha256", "")
    actual = hashlib.sha256(sealed.encode("utf-8")).hexdigest()
    if expected and actual != expected:
        raise MatrixError("sealed mapping hash MISMATCH — mapping was modified after creation")
    manifest["revealed_at"] = datetime.now(UTC).isoformat()
    _save_manifest(out_dir, manifest)
    return json.loads(sealed)


def _report_group_row(
    label: str,
    members: list[tuple[str, dict[str, Any]]],
    out_dir: Path,
    baseline_text: str,
) -> str:
    """Render one report row: stats, self/judge columns, flags — reqs 031-033, 050-051.

    Extracted from matrix_report (RONDO-322 complexity lock).
    """
    done = [r for _, r in members if r.get("status") == "done"]
    cost = sum(r.get("cost_usd", 0.0) for _, r in members)
    lats = [r["latency_sec"] for r in done if r.get("latency_sec")]
    ratings = [r["self_rating"] for r in done if isinstance(r.get("self_rating"), (int, float))]
    lat = f"{statistics.mean(lats):.1f}" if lats else "-"
    flags = []
    if ratings:
        mean = statistics.mean(ratings)
        stdev = statistics.stdev(ratings) if len(ratings) > 1 else 0.0
        self_col = f"{mean:.1f} ± {stdev:.1f} (n={len(ratings)})"
        if mean and stdev > NOISY_STDEV_RATIO * mean:
            flags.append("noisy")
    else:
        self_col = "-"
    if baseline_text and done:
        try:
            out_text = (out_dir / done[0]["file"]).read_text(encoding="utf-8")
            flags.append(f"len×{len(out_text) / max(1, len(baseline_text)):.2f}")
        except (OSError, KeyError):
            pass
    statuses = {r.get("status") for _, r in members}
    if "budget_exhausted" in statuses:
        flags.append("budget_exhausted")
    if "error" in statuses:
        flags.append("errors")
    # -- req 051: external judge scores — unlike self-ratings these come
    # -- from one consistent scorer, so cross-group comparison is fair
    judge_scores = [
        r["judge"]["score"]
        for r in done
        if isinstance(r.get("judge"), dict) and isinstance(r["judge"].get("score"), (int, float))
    ]
    judge_col = f"{statistics.mean(judge_scores):.1f} (n={len(judge_scores)})" if judge_scores else "-"
    return f"  {label:<44} {len(done):>4} {cost:>8.4f} {lat:>7} {self_col:>22} {judge_col:>11} {','.join(flags)}"


def matrix_report(name: str, *, base_dir: str | None = None) -> str:
    """Per-group report: replicate stats, noise flags, baseline deltas — reqs 031-033, 050."""
    out_dir = _matrix_base_dir(base_dir) / name
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blind_hidden = manifest.get("blind") and not manifest.get("revealed_at")

    code_by_group: dict[str, str] = {}
    if manifest.get("blind"):
        try:
            mapping = json.loads((out_dir / "manifest.sealed.json").read_text(encoding="utf-8"))
            code_by_group = {group: code for code, group in mapping.items()}
        except (OSError, json.JSONDecodeError):
            pass

    baseline_text = ""
    if manifest.get("baseline"):
        try:
            baseline_text = Path(manifest["baseline"]).expanduser().read_text(encoding="utf-8")
        except OSError:
            baseline_text = ""

    # -- group cells (replicates together)
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, rec in manifest["cells"].items():
        model, effort, ctx, _rep = key.split("|")
        groups.setdefault(f"{model}|{effort}|{ctx}", []).append((key, rec))

    lines = [f"  Matrix: {name}   spent ${manifest['spent_usd']:.4f}   cells {len(manifest['cells'])}"]
    lines.append(
        f"  {'Group':<44} {'done':>4} {'cost$':>8} {'lat s':>7} {'self (uncalibrated)':>22} {'judge':>11} flags"
    )
    lines.append(f"  {'─' * 44} {'─' * 4} {'─' * 8} {'─' * 7} {'─' * 22} {'─' * 11} {'─' * 10}")
    for group, members in sorted(groups.items()):
        label = code_by_group.get(group, group) if blind_hidden else group
        lines.append(_report_group_row(label, members, out_dir, baseline_text))
    if blind_hidden:
        lines.append(f"  (blind run — groups coded; `rondo matrix reveal {name}` to de-anonymize)")
    return "\n".join(lines)


def matrix_status(name: str, *, base_dir: str | None = None) -> dict[str, Any]:
    """Counts by status for `rondo matrix status` — req 060."""
    out_dir = _matrix_base_dir(base_dir) / name
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for rec in manifest["cells"].values():
        counts[rec.get("status", "?")] = counts.get(rec.get("status", "?"), 0) + 1
    return {"name": name, "spent_usd": manifest["spent_usd"], "counts": counts}


# -- sig: mgh-6201.cd.bd955f.f1a9.mx308b


# -- sig: mgh-6201.cd.bd955f.499c.7fd53c
