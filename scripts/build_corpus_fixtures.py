#!/usr/bin/env python3
"""Build sanitized corpus fixtures from the local production audit trail.

RONDO-313: the parser/auth-loss regression corpora lived only in
~/.rondo/audit — gates skipped on every other machine (Cursor finding #301,
"local-only gates"). This tool samples a small, diverse subset of those
production records, scrubs anything identifying, VERIFIES the scrub kept
the behavior that makes each record a regression test, and writes repo
fixtures under tests/fixtures/corpus/.

Selection rules:
   - parser records: bucket by structural feature (fenced JSON, multi-block,
     prose-wrapped, escaped strings), smallest record per bucket first,
     cap PARSER_TARGET records and MAX_RECORD_BYTES each.
   - auth records: deduplicate by normalized text, smallest first,
     cap AUTH_TARGET records.

Safety rules (hard failures, no partial writes):
   - every fixture is re-checked post-redaction: parser fixtures must still
     parse via parse_task_json; auth fixtures must still trip detect_auth_loss.
   - a forbidden-token scan runs over the final bytes; any hit aborts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

## -- make the rondo package importable when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rondo.dispatch_parse import detect_auth_loss, parse_task_json  # noqa: E402

AUDIT_DIR = Path.home() / ".rondo" / "audit"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "corpus"

PARSER_TARGET = 12
AUTH_TARGET = 6
MAX_RECORD_BYTES = 8_192

## -- redaction map: applied in order, longest/most-specific first
REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/Users/[A-Za-z0-9_.-]+"), "/Users/user"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "/home/user"),
    (re.compile(r"\bmarkhubers\b", re.IGNORECASE), "user"),
    (re.compile(r"\bmhubers\b", re.IGNORECASE), "user"),
    (re.compile(r"\bMark Hubers\b", re.IGNORECASE), "A. User"),
    (re.compile(r"\bHubers\b", re.IGNORECASE), "User"),
    (re.compile(r"\bMark\b"), "User"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "user@example.com"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{8,}"), "sk-REDACTED"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "ghp_REDACTED"),
    (re.compile(r"\bAKIA[A-Z0-9]{12,}"), "AKIA_REDACTED"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "xoxb-REDACTED"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"), "AIza_REDACTED"),
]

## -- if ANY of these survive redaction the build aborts — belt and braces
FORBIDDEN = ("markhubers", "mhubers", "hubers", "sk-ant-", "ghp_1", "AKIA0", "AKIA1")


def redact(text: str) -> str:
    """Apply every redaction pattern to text and return the scrubbed copy."""
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def scan_forbidden(text: str) -> list[str]:
    """Return forbidden tokens still present after redaction (empty = clean)."""
    lowered = text.lower()
    return [tok for tok in FORBIDDEN if tok.lower() in lowered]


def parser_feature(raw: str) -> str:
    """Classify a raw_output by the parser path it exercises (for diversity)."""
    if "```json" in raw or "```\n{" in raw:
        return "fenced"
    if raw.count('"result"') > 1 or raw.count('"status"') > 1:
        return "multiblock"
    if '\\"' in raw:
        return "escaped"
    if not raw.lstrip().startswith("{"):
        return "prose_wrapped"
    return "plain"


def collect_partials() -> tuple[list[str], list[str]]:
    """Read the local audit log; return (parser_raws, auth_raws) for partial records."""
    log = AUDIT_DIR / "rondo_audit.jsonl"
    if not log.exists():
        print("-ERROR- no local audit corpus at ~/.rondo/audit — nothing to build from")
        sys.exit(1)
    parser_raws: list[str] = []
    auth_raws: list[str] = []
    for line in log.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") != "partial":
            continue
        result_path = AUDIT_DIR / (rec.get("result_file") or "_none_")
        if not result_path.exists():
            continue
        try:
            raw = json.loads(result_path.read_text()).get("raw_output") or ""
        except (json.JSONDecodeError, OSError):
            continue
        if not raw:
            continue
        if "Not logged in" in raw or "Please run /login" in raw:
            auth_raws.append(raw)
        else:
            parser_raws.append(raw)
    return parser_raws, auth_raws


def select_parser_sample(raws: list[str]) -> list[str]:
    """Pick a small, structurally diverse, size-capped parser sample."""
    buckets: dict[str, list[str]] = {}
    for raw in raws:
        if len(raw.encode()) > MAX_RECORD_BYTES:
            continue
        if parse_task_json(raw) is None:
            continue  # -- corpus invariant: every kept record parses today
        buckets.setdefault(parser_feature(raw), []).append(raw)
    for bucket in buckets.values():
        bucket.sort(key=len)
    ## -- round-robin across buckets so every parser path is represented
    sample: list[str] = []
    seen: set[str] = set()
    idx = 0
    while len(sample) < PARSER_TARGET and any(idx < len(b) for b in buckets.values()):
        for feature in sorted(buckets):
            bucket = buckets[feature]
            if idx < len(bucket) and bucket[idx] not in seen:
                sample.append(bucket[idx])
                seen.add(bucket[idx])
                if len(sample) >= PARSER_TARGET:
                    break
        idx += 1
    counts = {feature: len(bucket) for feature, bucket in buckets.items()}
    print(f"   parser buckets: {counts}")
    return sample


def select_auth_sample(raws: list[str]) -> list[str]:
    """Pick distinct auth-loss variants, smallest first."""
    distinct: dict[str, str] = {}
    for raw in raws:
        key = re.sub(r"\s+", " ", raw).strip().lower()[:200]
        if key not in distinct or len(raw) < len(distinct[key]):
            distinct[key] = raw
    return sorted(distinct.values(), key=len)[:AUTH_TARGET]


def synthetic_auth_fixtures() -> list[dict[str, str]]:
    """One labeled synthetic record per detector signal — full coverage.

    Production only ever produced ONE auth-loss variant ("Not logged in").
    The fixture gate must still guard EVERY signal in AUTH_LOSS_PATTERNS on
    every machine, each in isolation — synthetic records fill the gap,
    honestly labeled.
    """
    from rondo.dispatch_parse import AUTH_LOSS_PATTERNS

    fixtures: list[dict[str, str]] = []
    for signal in AUTH_LOSS_PATTERNS:
        fixtures.append(
            {
                "sanitized_from": "synthetic — IFS-100 AUTH_LOSS_PATTERNS coverage (RONDO-313)",
                "expect": "auth_loss",
                "raw_output": f"Error: {signal} · Please resolve and retry.",
            }
        )
    return fixtures


def build_fixture(raw: str, expect: str) -> dict[str, str] | None:
    """Redact one record and verify behavior survived; None = drop the record."""
    clean = redact(raw)
    if scan_forbidden(clean):
        return None
    if expect == "parse" and parse_task_json(clean) is None:
        return None  # -- redaction broke the JSON structure; drop, don't ship
    if expect == "auth_loss" and detect_auth_loss(clean) is None:
        return None
    return {
        "sanitized_from": "production audit corpus (2026-06, RONDO-313)",
        "expect": expect,
        "raw_output": clean,
    }


def write_fixtures(kind: str, fixtures: list[dict[str, str]]) -> None:
    """Write fixtures as NN.json under tests/fixtures/corpus/<kind>/."""
    folder = FIXTURE_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.json"):
        old.unlink()
    for i, fixture in enumerate(fixtures, 1):
        (folder / f"{i:02d}.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
    print(f"-PASS- wrote {len(fixtures)} {kind} fixtures → {folder}")


def main() -> int:
    """Build, verify, and write the sanitized corpus fixtures."""
    parser_raws, auth_raws = collect_partials()
    print(f"local corpus: {len(parser_raws)} parser / {len(auth_raws)} auth partial records")

    parser_fixtures = [f for raw in select_parser_sample(parser_raws) if (f := build_fixture(raw, "parse")) is not None]
    auth_fixtures = [f for raw in select_auth_sample(auth_raws) if (f := build_fixture(raw, "auth_loss")) is not None]
    ## -- production only has ONE auth variant; cover the remaining detector
    ## -- signals with honestly-labeled synthetic records (gate needs >=5)
    auth_fixtures += synthetic_auth_fixtures()

    if len(parser_fixtures) < 10 or len(auth_fixtures) < 5:
        print(
            f"-ERROR- too few survivors after sanitize+verify "
            f"(parser={len(parser_fixtures)}, auth={len(auth_fixtures)}) — NOT writing"
        )
        return 1

    ## -- final whole-set forbidden scan before anything touches disk
    blob = json.dumps(parser_fixtures + auth_fixtures)
    leaks = scan_forbidden(blob)
    if leaks:
        print(f"-ERROR- forbidden tokens survived redaction: {leaks} — NOT writing")
        return 1

    write_fixtures("parser", parser_fixtures)
    write_fixtures("auth", auth_fixtures)
    print("-PASS- corpus fixtures built; run the fixture gates to confirm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
