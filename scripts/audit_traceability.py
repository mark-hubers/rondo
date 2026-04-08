#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# ruff: noqa: I001
"""Audit finding traceability: Finding -> Commit -> Test -> Still Passing.

For each finding in audit_findings, verify the full traceability chain:
    1. A commit exists that references the finding (#NNN in message).
    2. The commit modified test files (new or updated tests).
    3. Those tests still pass (optional — pass --run-tests).

Also detects PHANTOM finding references: commits that claim "#NNN" but
no such finding exists in the DB (or existed when the commit was written).

Usage:
    python3 rondo/scripts/audit_traceability.py                    # default run on 200-260
    python3 rondo/scripts/audit_traceability.py --range 200 260    # explicit range
    python3 rondo/scripts/audit_traceability.py --sprint RONDO-209 # one sprint
    python3 rondo/scripts/audit_traceability.py --run-tests        # actually run pytest
    python3 rondo/scripts/audit_traceability.py --json             # JSON output

Output: rondo/reports/finding-traceability-YYYY-MM-DD.md

Security note: subprocess is required for git + pytest integration.
Partial exec path ("git", "python") is intentional — relies on venv $PATH.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404 — required for git/pytest integration
import sys
from datetime import UTC, datetime
from pathlib import Path

## Add repo scripts/ to path so we can import ob_queries + status_output
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ob_queries import findings, get_connection  # noqa: E402
from status_output import error_msg, pass_msg, warn_msg  # noqa: E402


## Status constants for per-finding verdicts
STATUS_PASS = "PASS"  # nosec B105 — enum value, not a secret
STATUS_WARN_NO_TESTS = "WARN_NO_TESTS"
STATUS_WARN_TEST_FAIL = "WARN_TEST_FAIL"
STATUS_WARN_TEST_MOVED = "WARN_TEST_MOVED"
STATUS_FAIL_NO_COMMIT = "FAIL_NO_COMMIT"
STATUS_FAIL_COLLISION = "FAIL_COLLISION"
STATUS_SKIP_LEGACY = "SKIP_LEGACY"
STATUS_SKIP_OPEN = "SKIP_OPEN"


def _out(msg: str = "") -> None:
    """Write a line to stdout (explicit stream — avoids bare print)."""
    sys.stdout.write(msg + "\n")


def run_git(*args: str, cwd: Path) -> str:
    """Run a git command and return stdout stripped. Raises on non-zero exit."""
    result = subprocess.run(  # nosec B603 B607 — intentional git invocation
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def find_closing_commits(finding_id: int, repo: Path) -> list[dict]:
    r"""Find commits that reference #<finding_id> in their message.

    Uses POSIX ERE with explicit non-digit boundaries (git's default regex
    flavor does NOT support \b). This prevents #254 from matching #2541
    while remaining portable across BSD/GNU git builds.

    Returns list of dicts with sha, subject, body.
    """
    ## (^|[^0-9])#NNN([^0-9]|$) — non-digit boundary for portable ERE
    pattern = rf"(^|[^0-9])#{finding_id}([^0-9]|$)"
    try:
        raw = run_git(
            "log",
            "--all",
            "--extended-regexp",
            f"--grep={pattern}",
            "--pretty=format:%H%x1f%s%x1f%b%x1e",
            cwd=repo,
        )
    except subprocess.CalledProcessError:
        return []

    if not raw:
        return []

    commits: list[dict] = []
    for entry in raw.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x1f")
        if len(parts) < 2:
            continue
        sha = parts[0]
        subject = parts[1]
        body = parts[2] if len(parts) > 2 else ""
        commits.append({"sha": sha, "subject": subject, "body": body})
    return commits


def get_modified_files(commit_sha: str, repo: Path) -> list[str]:
    """Return list of files modified in a commit."""
    try:
        raw = run_git("show", "--name-only", "--pretty=format:", commit_sha, cwd=repo)
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def filter_test_files(files: list[str]) -> list[str]:
    """Keep only test_*.py files under rondo/tests/ (any layer)."""
    return [f for f in files if f.startswith("rondo/tests/") and Path(f).name.startswith("test_") and f.endswith(".py")]


def resolve_test_path(historical_path: str, repo: Path) -> tuple[str, str]:
    """Resolve a possibly-stale historical test path to its current location.

    Returns (resolved_path, resolution_kind) where resolution_kind is one of:
        'exists'   — historical path exists as-is
        'moved'    — found a unique basename match at a new location
        'ambiguous'— multiple basename matches, cannot pick
        'missing'  — no basename match found anywhere
    """
    abs_historical = repo / historical_path
    if abs_historical.exists():
        return historical_path, "exists"

    basename = Path(historical_path).name
    tests_dir = repo / "rondo" / "tests"
    if not tests_dir.is_dir():
        return historical_path, "missing"

    matches = sorted(tests_dir.rglob(basename))
    if not matches:
        return historical_path, "missing"
    if len(matches) > 1:
        return historical_path, "ambiguous"

    resolved = matches[0].relative_to(repo).as_posix()
    return resolved, "moved"


def run_pytest_file(test_file: str, repo: Path, timeout_sec: int = 60) -> tuple[bool, str]:
    """Run a single test file with pytest. Returns (passed, summary_line)."""
    venv_python = str(repo / ".venv/bin/python")
    try:
        result = subprocess.run(  # nosec B603 — venv python, controlled args
            [venv_python, "-m", "pytest", test_file, "--tb=line", "-q"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout_sec}s"
    except (FileNotFoundError, OSError) as exc:
        return False, f"ERROR: {exc}"

    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    summary = lines[-1] if lines else "(no output)"
    return result.returncode == 0, summary


def find_phantom_commits(
    id_range: tuple[int, int],
    known_ids: set[int],
    repo: Path,
    since_days: int = 14,
) -> list[dict]:
    """Scan recent commits for #NNN references and flag any outside known_ids.

    Catches the RONDO-209 #254 pattern where a commit referenced a finding ID
    that did not exist in the DB at the time of commit.
    """
    try:
        raw = run_git(
            "log",
            "--all",
            f"--since={since_days} days ago",
            "--pretty=format:%H%x1f%s%x1e",
            cwd=repo,
        )
    except subprocess.CalledProcessError:
        return []

    ref_pattern = re.compile(r"#(\d{3,4})\b")
    phantoms: list[dict] = []
    for entry in raw.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x1f")
        if len(parts) < 2:
            continue
        sha, subject = parts[0], parts[1]
        for match in ref_pattern.finditer(subject):
            fid = int(match.group(1))
            if id_range[0] <= fid <= id_range[1] and fid not in known_ids:
                phantoms.append({"sha": sha[:8], "finding_id": fid, "subject": subject})
    return phantoms


def audit_finding(finding: dict, repo: Path, run_tests: bool) -> dict:
    """Audit a single finding. Returns dict with full verdict."""
    result: dict = {
        "id": finding["id"],
        "severity": finding["severity"],
        "status": finding["status"],
        "fix_sprint": finding["fix_sprint"],
        "description": finding["description"][:100],
        "verdict": STATUS_FAIL_NO_COMMIT,
        "commits": [],
        "test_files": [],
        "test_results": [],
        "notes": [],
    }

    if finding["status"] == "open":
        result["verdict"] = STATUS_SKIP_OPEN
        result["notes"].append("Finding still open — nothing to verify")
        return result

    if finding["fix_sprint"] == "RONDO-prior":
        result["verdict"] = STATUS_SKIP_LEGACY
        result["notes"].append("fix_sprint='RONDO-prior' — predates per-sprint tracking")
        return result

    commits = find_closing_commits(finding["id"], repo)
    result["commits"] = [{"sha": c["sha"][:8], "subject": c["subject"]} for c in commits]

    if not commits:
        result["verdict"] = STATUS_FAIL_NO_COMMIT
        result["notes"].append(f"No commit references #{finding['id']} in any branch history")
        return result

    all_test_files: set[str] = set()
    for commit in commits:
        files = get_modified_files(commit["sha"], repo)
        tests = filter_test_files(files)
        all_test_files.update(tests)

    result["test_files"] = sorted(all_test_files)

    if not all_test_files:
        result["verdict"] = STATUS_WARN_NO_TESTS
        result["notes"].append("Commit(s) found but no test_*.py files in rondo/tests/ were modified")
        return result

    if run_tests:
        any_real_failure = False
        any_moved = False
        any_missing = False
        for test_file in sorted(all_test_files):
            ## Resolve possibly-stale path to its current location
            resolved, kind = resolve_test_path(test_file, repo)
            if kind in ("missing", "ambiguous"):
                result["test_results"].append(
                    {
                        "file": test_file,
                        "passed": False,
                        "summary": f"SKIP ({kind}): file no longer at this path and basename lookup {kind}",
                    }
                )
                if kind == "missing":
                    any_missing = True
                else:
                    any_moved = True
                continue

            passed, summary = run_pytest_file(resolved, repo)
            display_path = resolved if kind == "exists" else f"{test_file} -> {resolved}"
            result["test_results"].append({"file": display_path, "passed": passed, "summary": summary})
            if kind == "moved":
                any_moved = True
            if not passed:
                any_real_failure = True

        if any_real_failure:
            result["verdict"] = STATUS_WARN_TEST_FAIL
            result["notes"].append("One or more referenced test files actually failed")
        elif any_missing:
            result["verdict"] = STATUS_WARN_TEST_MOVED
            result["notes"].append(
                "Test file(s) missing — moved or deleted since commit; tests that could run all passed"
            )
        elif any_moved:
            result["verdict"] = STATUS_PASS
            result["notes"].append(
                f"All {len(all_test_files)} test file(s) passing (some resolved via basename after path moved)"
            )
        else:
            result["verdict"] = STATUS_PASS
            result["notes"].append(f"All {len(all_test_files)} test file(s) still passing")
    else:
        result["verdict"] = STATUS_PASS
        result["notes"].append(
            f"{len(all_test_files)} test file(s) modified (re-run with --run-tests to verify passing)"
        )
    return result


def collect_findings(id_range: tuple[int, int], sprint: str | None) -> list[dict]:
    """Query findings in range, optionally filtered to one sprint."""
    with get_connection() as conn:
        rows = findings.list_by_status(conn, ["fixed", "open", "wont_fix"])
    result: list[dict] = []
    for row in rows:
        fid = row["id"]
        if not (id_range[0] <= fid <= id_range[1]):
            continue
        if sprint and row["fix_sprint"] != sprint:
            continue
        result.append(dict(row))
    return sorted(result, key=lambda r: r["id"])


def format_markdown_report(
    results: list[dict],
    phantoms: list[dict],
    id_range: tuple[int, int],
    sprint: str | None,
    run_tests: bool,
) -> str:
    """Build markdown report text."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    lines = [
        "# Rondo Finding Traceability Audit",
        "",
        f"**Generated:** {now}",
        f"**Range:** #{id_range[0]}..#{id_range[1]}" + (f" (sprint={sprint})" if sprint else ""),
        f"**Run tests:** {'yes' if run_tests else 'no (use --run-tests to execute)'}",
        f"**Findings audited:** {len(results)}",
        "",
        "## Summary",
        "",
        "| Verdict | Count |",
        "|---|---|",
    ]
    for verdict in [
        STATUS_PASS,
        STATUS_WARN_NO_TESTS,
        STATUS_WARN_TEST_FAIL,
        STATUS_FAIL_NO_COMMIT,
        STATUS_FAIL_COLLISION,
        STATUS_SKIP_LEGACY,
        STATUS_SKIP_OPEN,
    ]:
        if counts.get(verdict, 0):
            lines.append(f"| {verdict} | {counts[verdict]} |")
    lines.append("")

    if phantoms:
        lines.extend(
            [
                "## PHANTOM COMMIT REFERENCES",
                "",
                "Commits referencing a finding ID with no matching DB row (within last 14 days):",
                "",
                "| Commit | Finding ID | Subject |",
                "|---|---|---|",
            ]
        )
        for p in phantoms:
            lines.append(f"| `{p['sha']}` | #{p['finding_id']} | {p['subject']} |")
        lines.append("")

    lines.extend(["## Per-Finding Results", ""])
    for r in results:
        lines.append(f"### #{r['id']} — {r['verdict']} — {r['severity']}")
        lines.append("")
        lines.append(f"**Sprint:** {r['fix_sprint'] or '—'}")
        lines.append("")
        lines.append(f"**Description:** {r['description']}")
        lines.append("")
        if r["commits"]:
            lines.append("**Commits:**")
            for c in r["commits"]:
                lines.append(f"- `{c['sha']}` — {c['subject']}")
            lines.append("")
        if r["test_files"]:
            lines.append("**Test files modified:**")
            for t in r["test_files"]:
                lines.append(f"- `{t}`")
            lines.append("")
        if r["test_results"]:
            lines.append("**Test run results:**")
            for tr in r["test_results"]:
                marker = "PASS" if tr["passed"] else "FAIL"
                lines.append(f"- [{marker}] `{tr['file']}` — {tr['summary']}")
            lines.append("")
        if r["notes"]:
            lines.append("**Notes:**")
            for n in r["notes"]:
                lines.append(f"- {n}")
            lines.append("")
    return "\n".join(lines) + "\n"


def print_console_summary(results: list[dict], phantoms: list[dict]) -> None:
    """Write compact console summary to stdout."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    _out()
    _out("=" * 70)
    _out("  RONDO FINDING TRACEABILITY AUDIT")
    _out("=" * 70)
    _out(f"  Total audited: {len(results)}")
    for verdict, count in counts.items():
        if verdict == STATUS_PASS:
            pass_msg(f"{verdict}: {count}")
        elif verdict.startswith("WARN"):
            warn_msg(f"{verdict}: {count}")
        elif verdict.startswith("FAIL"):
            error_msg(f"{verdict}: {count}")
        else:
            _out(f"  [SKIP] {verdict}: {count}")

    if phantoms:
        _out()
        warn_msg(f"PHANTOM COMMIT REFERENCES: {len(phantoms)}")
        for p in phantoms:
            _out(f"    {p['sha']} -> #{p['finding_id']}: {p['subject'][:80]}")

    _out()
    for r in results:
        if r["verdict"] in (STATUS_PASS, STATUS_SKIP_LEGACY, STATUS_SKIP_OPEN):
            continue
        if r["verdict"] == STATUS_PASS:
            marker = "-PASS-"
        elif r["verdict"].startswith("WARN"):
            marker = "-WARNING-"
        else:
            marker = "-ERROR-"
        _out(f"  {marker} #{r['id']} [{r['severity']}] {r['verdict']}: {r['description'][:60]}")
        for n in r["notes"][:2]:
            _out(f"           -> {n}")


def main() -> int:
    """Entry point for the traceability audit CLI."""
    parser = argparse.ArgumentParser(description="Audit finding traceability")
    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("LOW", "HIGH"),
        default=[200, 260],
        help="Finding ID range (default: 200 260)",
    )
    parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Filter to one sprint (e.g., RONDO-209)",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Actually run pytest on referenced test files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of writing a markdown report",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing the markdown report file",
    )
    args = parser.parse_args()

    id_range = (args.range[0], args.range[1])

    results_in = collect_findings(id_range, args.sprint)
    if not results_in:
        error_msg(f"No findings found in range #{id_range[0]}..#{id_range[1]}")
        return 1

    repo = REPO_ROOT
    audit_results = [audit_finding(f, repo, args.run_tests) for f in results_in]

    known_ids = {f["id"] for f in results_in}
    phantoms = find_phantom_commits(id_range, known_ids, repo)

    if args.json:
        _out(
            json.dumps(
                {
                    "range": list(id_range),
                    "sprint": args.sprint,
                    "run_tests": args.run_tests,
                    "findings": audit_results,
                    "phantoms": phantoms,
                },
                indent=2,
            )
        )
        return 0

    print_console_summary(audit_results, phantoms)

    if not args.no_report:
        report = format_markdown_report(audit_results, phantoms, id_range, args.sprint, args.run_tests)
        report_dir = repo / "rondo" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        report_path = report_dir / f"finding-traceability-{stamp}.md"
        report_path.write_text(report, encoding="utf-8")
        _out()
        pass_msg(f"Report written: {report_path.relative_to(repo)}")

    has_fail = any(r["verdict"].startswith("FAIL") for r in audit_results)
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6208.cd.bd955f.e4a1.audit_trace2
