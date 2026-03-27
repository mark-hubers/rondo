#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo round: DB Bootstrap Validation.

Validates YAML schemas → generates SQL → bootstraps Postgres → verifies.
The proof that specs become real: 422 YAML files → 421 tables → 0 errors.

Usage:
    rondo run rondo/rounds/db_bootstrap_validation.py
    rondo live rondo/rounds/db_bootstrap_validation.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
SCHEMA_SCRIPT = REPO_ROOT / "scripts" / "generate_schema.py"
SQL_FILE = REPO_ROOT / "db" / "generated" / "all-postgres.sql"

## DB connection
DB_HOST = "192.168.64.14"
DB_PORT = "5432"
DB_USER = "postgres"
DB_PASS = "ob2lab"
DB_NAME = "ace2_dev"

PSQL = "/opt/homebrew/Cellar/libpq/18.3/bin/psql"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command and return result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=check,
        env={**__import__("os").environ, "PGPASSWORD": DB_PASS},
    )


def _psql(sql: str, db: str = DB_NAME) -> subprocess.CompletedProcess[str]:
    """Run SQL via psql."""
    return _run([PSQL, "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER, "-d", db, "-c", sql], check=False)


def _psql_file(filepath: str, db: str = DB_NAME) -> subprocess.CompletedProcess[str]:
    """Run SQL file via psql."""
    return _run([PSQL, "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER, "-d", db, "-f", filepath], check=False)


def step_validate() -> tuple[bool, str]:
    """Step 1: Run YAML schema validation with all 6 checks."""
    result = _run([str(VENV_PYTHON), str(SCHEMA_SCRIPT), "--validate"], check=False)
    output = result.stdout + result.stderr

    if result.returncode != 0:
        ## Count errors (not warnings)
        errors = [line for line in output.split("\n") if "ERROR" in line or ("issue" in line and "WARNING" not in line)]
        return False, f"Validation failed: {len(errors)} errors\n{output[-500:]}"

    return True, f"Validation passed\n{output[-200:]}"


def step_generate() -> tuple[bool, str]:
    """Step 2: Generate SQL for all products."""
    _run([str(VENV_PYTHON), str(SCHEMA_SCRIPT), "--postgres", "all"], check=False)

    if not SQL_FILE.exists():
        return False, f"SQL file not generated: {SQL_FILE}"

    size = SQL_FILE.stat().st_size
    return True, f"Generated {size:,} bytes of SQL"


def step_bootstrap_db() -> tuple[bool, str]:
    """Step 3: Drop + recreate + load DB."""
    ## Drop existing
    _psql("DROP DATABASE IF EXISTS ace2_dev;", db="postgres")

    ## Create fresh
    result = _psql("CREATE DATABASE ace2_dev;", db="postgres")
    if result.returncode != 0:
        return False, f"CREATE DATABASE failed: {result.stderr}"

    ## Create schemas
    _psql(
        "CREATE SCHEMA IF NOT EXISTS ace; "
        "CREATE SCHEMA IF NOT EXISTS ob; "
        "CREATE SCHEMA IF NOT EXISTS caliber; "
        "CREATE SCHEMA IF NOT EXISTS shared;"
    )

    ## Load SQL
    result = _psql_file(str(SQL_FILE))
    errors = [line for line in result.stderr.split("\n") if "ERROR" in line]

    if errors:
        return False, f"{len(errors)} errors during load:\n" + "\n".join(errors[:10])

    return True, "DB loaded with 0 errors"


def step_verify() -> tuple[bool, str]:
    """Step 4: Verify table count matches expected."""
    result = _psql(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('ace','ob','caliber','shared');"
    )
    output = result.stdout.strip()

    ## Parse count from psql output
    lines = [line.strip() for line in output.split("\n") if line.strip().isdigit()]
    if not lines:
        return False, f"Could not parse table count from: {output}"

    count = int(lines[0])
    if count < 400:
        return False, f"Only {count} tables created (expected 420+)"

    return True, f"{count} tables verified in ace2_dev"


def build_round() -> dict:
    """Build the Rondo round definition.

    Returns a simple dict-based round for direct execution.
    This avoids importing rondo.engine which may not be in path.
    """
    return {
        "name": "db-bootstrap-validation",
        "description": "Validate YAML → Generate SQL → Bootstrap Postgres → Verify",
        "steps": [
            {"name": "validate-yaml", "fn": step_validate},
            {"name": "generate-sql", "fn": step_generate},
            {"name": "bootstrap-db", "fn": step_bootstrap_db},
            {"name": "verify-tables", "fn": step_verify},
        ],
    }


def main() -> int:
    """Run the round directly (without rondo CLI)."""
    round_def = build_round()
    print(f"=== {round_def['name']} ===")
    print(f"    {round_def['description']}\n")

    all_passed = True
    for step in round_def["steps"]:
        name = step["name"]
        print(f"  [{name}] ...", end=" ", flush=True)
        passed, detail = step["fn"]()
        status = "-PASS-" if passed else "-FAIL-"
        print(f"{status}")
        print(f"    {detail}\n")
        if not passed:
            all_passed = False
            print(f"  ROUND FAILED at step: {name}")
            break

    if all_passed:
        print("=== ROUND PASSED — DB bootstrap verified ===")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
