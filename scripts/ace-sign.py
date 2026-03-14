#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""ACE code signing — two-part cryptographic watermark on every source file.

Signature format: # -- sig: MgH-{public}.{private}

    Part 1 (public):  SHA-256 of file content, first 6 hex chars.
                      Anyone can verify this — hash the file, compare.
                      Proves the file is unmodified.

    Part 2 (private): HMAC-SHA256 with secret key, first 6 hex chars.
                      Only the key holder can generate or verify this.
                      Proves the file came from Mark's build pipeline.

Usage:
    python scripts/ace-sign.py sign               # -- sign all source + test files
    python scripts/ace-sign.py verify              # -- verify all signatures
    python scripts/ace-sign.py sign path/to/file.py  # -- sign one file
    python scripts/ace-sign.py verify path/to/file.py  # -- verify one file

The secret key lives at ~/.ace/signing-key (never committed, 600 perms).
Without the key, Part 2 cannot be generated or verified.
Part 1 can always be verified by anyone — it's a plain SHA-256.

Author: Mark Hubers
Built with: Claude Code + ACE Orbit
"""

from __future__ import annotations

import hashlib
import hmac
import re
import sys
from pathlib import Path

# -- Signature format: # -- sig: MgH-{6 hex}.{6 hex}
SIG_PATTERN = re.compile(r"^# -- sig: MgH-[0-9a-f]{6}\.[0-9a-f]{6}$")
SIG_PREFIX = "# -- sig: MgH-"
KEY_PATH = Path.home() / ".ace" / "signing-key"

# -- Default paths (relative to rondo/)
RONDO_ROOT = Path(__file__).parent.parent
SRC_DIR = RONDO_ROOT / "src" / "rondo"
TEST_DIR = RONDO_ROOT / "tests"


def load_key() -> bytes:
    """Load the signing key from ~/.ace/signing-key."""
    if not KEY_PATH.exists():
        print(f"-ERROR- Signing key not found: {KEY_PATH}", file=sys.stderr)
        print(
            '        Generate: python -c "import secrets; print(secrets.token_hex(32))" > ~/.ace/signing-key',
            file=sys.stderr,
        )
        sys.exit(1)
    return KEY_PATH.read_text(encoding="utf-8").strip().encode()


def compute_public(content: str) -> str:
    """Part 1 — SHA-256 of content, first 6 hex chars. Anyone can verify."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:6]


def compute_private(content: str, key: bytes) -> str:
    """Part 2 — HMAC-SHA256 with secret key, first 6 hex chars. Key required."""
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).hexdigest()[:6]


def strip_sig_line(content: str) -> str:
    """Remove existing signature line from content."""
    lines = content.splitlines()
    # -- Remove trailing sig line(s) and blank lines before them
    while lines and (SIG_PATTERN.match(lines[-1]) or lines[-1].strip() == ""):
        lines.pop()
    # -- Also strip old-format ace- signatures
    old_pattern = re.compile(r"^# -- sig: ace-[0-9a-f]{8}$")
    while lines and (old_pattern.match(lines[-1]) or lines[-1].strip() == ""):
        lines.pop()
    return "\n".join(lines) + "\n"


def sign_file(filepath: Path, key: bytes) -> tuple[str, str]:
    """Sign a file — add or update the two-part signature. Returns (public, private)."""
    content = filepath.read_text(encoding="utf-8")
    clean = strip_sig_line(content)
    pub = compute_public(clean)
    priv = compute_private(clean, key)
    signed = clean + f"\n{SIG_PREFIX}{pub}.{priv}\n"
    filepath.write_text(signed, encoding="utf-8")
    return pub, priv


def verify_file(filepath: Path, key: bytes) -> tuple[bool, str]:
    """Verify both parts of a file's signature. Returns (passed, detail)."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.rstrip().splitlines()

    # -- Find sig line
    if not lines or not SIG_PATTERN.match(lines[-1]):
        return False, "no signature found"

    # -- Parse existing sig
    sig_text = lines[-1].replace(SIG_PREFIX, "")
    parts = sig_text.split(".")
    if len(parts) != 2:
        return False, f"malformed signature: {sig_text}"

    existing_pub, existing_priv = parts
    clean = strip_sig_line(content)

    # -- Verify Part 1 (public — SHA-256)
    expected_pub = compute_public(clean)
    if existing_pub != expected_pub:
        return False, f"Part 1 MISMATCH — content modified (expected {expected_pub}, found {existing_pub})"

    # -- Verify Part 2 (private — HMAC)
    expected_priv = compute_private(clean, key)
    if existing_priv != expected_priv:
        return False, f"Part 2 MISMATCH — wrong key or tampered (expected {expected_priv}, found {existing_priv})"

    return True, f"MgH-{existing_pub}.{existing_priv}"


def get_all_files() -> list[Path]:
    """Get all Python files to sign/verify."""
    src_files = sorted(SRC_DIR.glob("*.py"))
    test_files = sorted(TEST_DIR.glob("test_*.py"))
    return src_files + test_files


def cmd_sign(targets: list[Path], key: bytes) -> int:
    """Sign files. Returns exit code."""
    signed = 0
    for filepath in targets:
        pub, priv = sign_file(filepath, key)
        print(f"   -PASS- {filepath.name:30s} MgH-{pub}.{priv}")
        signed += 1
    print(f"\n   {signed} files signed")
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
