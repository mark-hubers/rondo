#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Generate and validate the Rondo examples index from per-file metadata headers.

Metadata header format (first meaningful comment line in each example file):
    # rondo-meta: mode=subprocess provider=anthropic category=basic value="One-line description"
"""

from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

META_RE = re.compile(r"^\s*#\s*rondo-meta:\s*(.+?)\s*$")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EXPECTED_EXAMPLE_COUNT = 88  # -- RONDO-316: +model-canary cli (87 was RONDO-315)


def _collect_example_files(examples_dir: Path) -> list[Path]:
    api_files = sorted(
        p for p in (examples_dir / "api").glob("*.py") if p.name != "example_dispatch.py"
    )
    round_files = sorted(
        [
            *list((examples_dir / "rounds").glob("*.py")),
            *list((examples_dir / "rounds").glob("*.yaml")),
            *list((examples_dir / "rounds").glob("*.yml")),
            *list((examples_dir / "rounds").glob("*.json")),
        ]
    )
    cli_files = sorted((examples_dir / "cli").glob("*.sh"))
    mcp_files = sorted((examples_dir / "mcp").glob("*.md"))
    return [*api_files, *round_files, *cli_files, *mcp_files]


def _parse_meta(file_path: Path) -> dict[str, str]:
    for line in file_path.read_text(encoding="utf-8").splitlines()[:15]:
        match = META_RE.match(line)
        if not match:
            continue
        tokens = shlex.split(match.group(1))
        out: dict[str, str] = {}
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            out[key.strip()] = value.strip()
        return out
    return {}


def _verify_docs(examples_dir: Path) -> list[str]:
    issues: list[str] = []
    for md_file in examples_dir.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        for link in MD_LINK_RE.findall(text):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = (md_file.parent / link).resolve()
            if not target.exists():
                issues.append(f"{md_file.relative_to(examples_dir.parent)} -> broken link: {link}")
    return issues


def generate_index(examples_dir: Path) -> tuple[str, list[str], list[str]]:
    files = _collect_example_files(examples_dir)
    missing_meta: list[str] = []
    bad_meta: list[str] = []
    rows: list[tuple[str, str, str, str, str, str]] = []

    for file_path in files:
        meta = _parse_meta(file_path)
        rel_dir = file_path.parent.name
        if not meta:
            missing_meta.append(str(file_path.relative_to(examples_dir.parent)))
            continue
        required = ("mode", "provider", "category")
        missing_keys = [key for key in required if not meta.get(key)]
        if missing_keys:
            bad_meta.append(f"{file_path.name}: missing {', '.join(missing_keys)}")
            continue
        value = meta.get("value", "Metadata-driven example reference")
        rows.append(
            (
                file_path.name,
                rel_dir,
                meta["mode"],
                meta["provider"],
                meta["category"],
                value,
            )
        )

    # -- Keep a stable ordering by directory bucket then filename.
    dir_order = {"api": 0, "rounds": 1, "cli": 2, "mcp": 3}
    rows.sort(key=lambda r: (dir_order.get(r[1], 99), r[0]))

    lines: list[str] = [
        "# Rondo Example Index",
        "",
        "Auto-generated from per-file `rondo-meta` headers.",
        "",
        "| # | Example | Dir | Dispatch mode(s) | Providers | Task category | What it demonstrates |",
        "|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(rows, start=1):
        example, directory, mode, provider, category, value = row
        lines.append(
            f"| {idx} | `{example}` | {directory} | {mode} | {provider} | {category} | {value} |"
        )
    lines.append("")
    return "\n".join(lines), missing_meta, bad_meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write rendered output to examples/INDEX.md")
    parser.add_argument("--check", action="store_true", help="Verify metadata and docs only (no write)")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    examples_dir = script_path.parent
    index_path = examples_dir / "INDEX.md"
    rendered, missing_meta, bad_meta = generate_index(examples_dir)
    link_issues = _verify_docs(examples_dir)
    discovered_count = len(_collect_example_files(examples_dir))

    if args.write:
        index_path.write_text(rendered, encoding="utf-8")
        print(f"-PASS- Wrote {index_path}")
    elif args.check:
        if not index_path.exists():
            print(f"-ERROR- Missing generated index file: {index_path}")
            return 1
        existing = index_path.read_text(encoding="utf-8")
        if existing != rendered:
            print("-ERROR- INDEX.md is out of sync with rondo-meta headers")
            print("  Hint: run '.venv/bin/python rondo/examples/generate_index.py --write'")
            return 1
    else:
        print(rendered)

    if missing_meta:
        print("-ERROR- Missing metadata headers:")
        for item in missing_meta:
            print(f"  - {item}")
    if bad_meta:
        print("-ERROR- Invalid metadata headers:")
        for item in bad_meta:
            print(f"  - {item}")
    if link_issues:
        print("-ERROR- Broken markdown links under examples/:")
        for issue in link_issues:
            print(f"  - {issue}")
    if discovered_count != EXPECTED_EXAMPLE_COUNT:
        print(
            f"-ERROR- Expected {EXPECTED_EXAMPLE_COUNT} examples, found {discovered_count}. "
            "Update EXPECTED_EXAMPLE_COUNT if this is intentional."
        )

    if missing_meta or bad_meta or link_issues or discovered_count != EXPECTED_EXAMPLE_COUNT:
        return 1

    print("-PASS- Example metadata + doc links look valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
