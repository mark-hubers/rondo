#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""ACE code signing — burn a cryptographic watermark into every source file.

Generates an HMAC-SHA256 signature from file content + secret key.
The signature proves the file passed through Mark's build pipeline.

Usage:
    python scripts/ace-sign.py sign               # -- sign all source + test files
    python scripts/ace-sign.py verify              # -- verify all signatures
    python scripts/ace-sign.py sign path/to/file.py  # -- sign one file
    python scripts/ace-sign.py verify path/to/file.py  # -- verify one file

The secret key lives at ~/.ace/signing-key (never committed, 600 perms).
Without the key, signatures cannot be generated or verified.

Author: Mark Hubers
Built with: Claude Code + ACE Orbit
"""

from __future__ import annotations

import hashlib
import hmac
import re
import sys
from pathlib import Path

# -- Signature format: # -- sig: ace-{8 hex chars}
SIG_PATTERN = re.compile(r"^# -- sig: ace-[0-9a-f]{8}$")
SIG_PREFIX = "# -- sig: ace-"
KEY_PATH = Path.home() / ".ace" / "signing-key"

# -- Default paths (relative to rondo/)
RONDO_ROOT = Path(__file__).parent.parent
SRC_DIR = RONDO_ROOT / "src" / "rondo"
TEST_DIR = RONDO_ROOT / "tests"


def load_key() -> bytes:
    """Load the signing key from ~/.ace/signing-key."""
    if not KEY_PATH.exists():
        print(f"-ERROR- Signing key not found: {KEY_PATH}", file=sys.stderr)
        print("        Generate one: python -c \"import secrets; print(secrets.token_hex(32))\" > ~/.ace/signing-key",
              file=sys.stderr)
        sys.exit(1)
    return KEY_PATH.read_text(encoding="utf-8").strip().encode()


def compute_sig(content: str, key: bytes) -> str:
    """Compute HMAC-SHA256 signature of content, return 8-char hex prefix."""
    mac = hmac.new(key, content.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()[:8]


def strip_sig_line(content: str) -> str:
    """Remove existing signature line from content."""
    lines = content.splitlines()
    # -- Remove trailing sig line(s) and blank lines before them
    while lines and (SIG_PATTERN.match(lines[-1]) or lines[-1].strip() == ""):
        lines.pop()
    return "\n".join(lines) + "\n"


def sign_file(filepath: Path, key: bytes) -> str:
    """Sign a file — add or update the signature line. Returns the sig."""
    content = filepath.read_text(encoding="utf-8")
    clean = strip_sig_line(content)
    sig = compute_sig(clean, key)
    signed = clean + f"\n{SIG_PREFIX}{sig}\n"
    filepath.write_text(signed, encoding="utf-8")
    return sig


def verify_file(filepath: Path, key: bytes) -> tuple[bool, str]:
    """Verify a file's signature. Returns (passed, detail)."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.rstrip().splitlines()

    # -- Find sig line
    if not lines or not SIG_PATTERN.match(lines[-1]):
        return False, "no signature found"

    existing_sig = lines[-1].replace(SIG_PREFIX, "")
    clean = strip_sig_line(content)
    expected_sig = compute_sig(clean, key)

    if existing_sig == expected_sig:
        return True, f"ace-{existing_sig}"
    return False, f"MISMATCH — expected ace-{expected_sig}, found ace-{existing_sig}"


def get_all_files() -> list[Path]:
    """Get all Python files to sign/verify."""
    src_files = sorted(SRC_DIR.glob("*.py"))
    test_files = sorted(TEST_DIR.glob("test_*.py"))
    return src_files + test_files


def cmd_sign(targets: list[Path], key: bytes) -> int:
    """Sign files. Returns exit code."""
    passed = 0
    for filepath in targets:
        sig = sign_file(filepath, key)
        print(f"   -PASS- {filepath.name:30s} ace-{sig}")
        passed += 1
    print(f"\n   {passed} files signed")
    return 0


def cmd_verify(targets: list[Path], key: bytes) -> int:
    """Verify files. Returns exit code."""
    passed = 0
    failed = 0
    for filepath in targets:
        ok, detail = verify_file(filepath, key)
        if ok:
            print(f"   -PASS- {filepath.name:30s} {detail}")
            passed += 1
        else:
            print(f"   -FAIL- {filepath.name:30s} {detail}")
            failed += 1
    print(f"\n   {passed} passed, {failed} failed")
    return 1 if failed > 0 else 0


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) < 2 or sys.argv[1] not in ("sign", "verify"):
        print("Usage: ace-sign.py sign|verify [file.py ...]")
        return 2

    command = sys.argv[1]
    key = load_key()

    # -- Specific files or all
    if len(sys.argv) > 2:
        targets = [Path(p) for p in sys.argv[2:]]
    else:
        targets = get_all_files()

    if command == "sign":
        return cmd_sign(targets, key)
    return cmd_verify(targets, key)


if __name__ == "__main__":
    sys.exit(main())
