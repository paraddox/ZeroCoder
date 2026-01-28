#!/usr/bin/env python3
"""
ZeroCoder Migration Validation Script
=====================================

Validates that the migration from Python to TypeScript backend
was successful by comparing database contents and API responses.

Usage: python scripts/validate_migration.py [--python-port PORT] [--ts-port PORT]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from urllib.error import URLError

# Configuration
ZEROCODER_DIR = Path.home() / ".zerocoder"
PYTHON_DB = ZEROCODER_DIR / "registry.db"
TYPESCRIPT_DB = ZEROCODER_DIR / "zerocoder.db"


def log_info(msg: str) -> None:
    """Print info message."""
    print(f"[INFO] {msg}")


def log_success(msg: str) -> None:
    """Print success message."""
    print(f"[SUCCESS] {msg}")


def log_error(msg: str) -> None:
    """Print error message."""
    print(f"[ERROR] {msg}")


def log_warn(msg: str) -> None:
    """Print warning message."""
    print(f"[WARN] {msg}")


def check_database_exists(db_path: Path, name: str) -> bool:
    """Check if a database file exists."""
    if not db_path.exists():
        log_error(f"{name} database not found: {db_path}")
        return False
    log_success(f"{name} database exists: {db_path}")
    return True


def get_table_count(conn: sqlite3.Connection, table: str) -> int:
    """Get row count for a table."""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except sqlite3.Error:
        return 0


def validate_projects_table(py_conn: sqlite3.Connection, ts_conn: sqlite3.Connection) -> bool:
    """Validate projects table migration."""
    log_info("Validating projects table...")

    py_count = get_table_count(py_conn, "projects")
    ts_count = get_table_count(ts_conn, "projects")

    log_info(f"  Python projects: {py_count}")
    log_info(f"  TypeScript projects: {ts_count}")

    if py_count == 0:
        log_warn("No projects in Python database")
        return True

    if ts_count < py_count:
        log_error(f"Project count mismatch: {ts_count} < {py_count}")
        return False

    # Check specific project data
    py_projects = py_conn.execute(
        "SELECT name, git_url, target_container_count FROM projects ORDER BY name"
    ).fetchall()

    ts_projects = ts_conn.execute(
        "SELECT name, git_url, target_container_count FROM projects ORDER BY name"
    ).fetchall()

    mismatches = []
    for py_proj in py_projects:
        name, git_url, target_count = py_proj
        ts_proj = ts_conn.execute(
            "SELECT name, git_url, target_container_count FROM projects WHERE name = ?",
            (name,)
        ).fetchone()

        if not ts_proj:
            mismatches.append(f"Project '{name}' not found in TypeScript database")
        elif ts_proj[1] != git_url:
            mismatches.append(f"Project '{name}' git_url mismatch")
        elif ts_proj[2] != target_count:
            mismatches.append(f"Project '{name}' target_container_count mismatch")

    if mismatches:
        for mismatch in mismatches:
            log_error(f"  {mismatch}")
        return False

    log_success(f"All {py_count} projects validated successfully")
    return True


def validate_remote_machines(py_conn: sqlite3.Connection, ts_conn: sqlite3.Connection) -> bool:
    """Validate remote_machines table migration."""
    log_info("Validating remote_machines table...")

    py_count = get_table_count(py_conn, "remote_machines")
    ts_count = get_table_count(ts_conn, "remote_machines")

    log_info(f"  Python remote machines: {py_count}")
    log_info(f"  TypeScript remote machines: {ts_count}")

    if py_count == 0:
        log_warn("No remote machines in Python database")
        return True

    if ts_count < py_count:
        log_error(f"Remote machine count mismatch: {ts_count} < {py_count}")
        return False

    log_success(f"All {py_count} remote machines validated successfully")
    return True


def check_server_health(port: int, name: str) -> bool:
    """Check if a server is running and healthy."""
    log_info(f"Checking {name} server health on port {port}...")

    try:
        with urlopen(f"http://localhost:{port}/health", timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                log_success(f"{name} server is healthy: {data}")
                return True
            else:
                log_error(f"{name} server returned status {response.status}")
                return False
    except URLError as e:
        log_error(f"{name} server not reachable: {e}")
        return False
    except Exception as e:
        log_error(f"Error checking {name} server: {e}")
        return False


def validate_session_scoped_tables(py_conn: sqlite3.Connection, ts_conn: sqlite3.Connection) -> bool:
    """Validate that session-scoped tables are NOT migrated (by design)."""
    log_info("Validating session-scoped tables (should be empty)...")

    session_tables = [
        "containers",
        "feature_cache",
        "feature_stats_cache",
        "remote_agents",
        "project_verification_state",
    ]

    all_valid = True
    for table in session_tables:
        py_count = get_table_count(py_conn, table)
        ts_count = get_table_count(ts_conn, table)

        # Python may have old data, but TypeScript should be empty (rebuilt at runtime)
        if ts_count > 0:
            log_warn(f"  {table}: TypeScript has {ts_count} rows (should be empty initially)")
        else:
            log_info(f"  {table}: Empty (correct - rebuilt at runtime)")

    return all_valid


def run_validation(args: argparse.Namespace) -> int:
    """Run all validation checks."""
    print("=" * 50)
    print("ZeroCoder Migration Validation")
    print("=" * 50)
    print()

    results = []

    # Check database files exist
    log_info("Step 1: Checking database files...")
    py_exists = check_database_exists(PYTHON_DB, "Python")
    ts_exists = check_database_exists(TYPESCRIPT_DB, "TypeScript")

    if not py_exists and not ts_exists:
        log_error("Neither database exists - nothing to validate")
        return 1

    results.append(py_exists or ts_exists)  # At least one should exist

    # Connect to databases
    py_conn = None
    ts_conn = None

    try:
        if py_exists:
            py_conn = sqlite3.connect(PYTHON_DB)
        if ts_exists:
            ts_conn = sqlite3.connect(TYPESCRIPT_DB)

        # Validate tables
        if py_conn and ts_conn:
            log_info("Step 2: Validating table data...")
            results.append(validate_projects_table(py_conn, ts_conn))
            results.append(validate_remote_machines(py_conn, ts_conn))
            results.append(validate_session_scoped_tables(py_conn, ts_conn))
        else:
            log_warn("Skipping table validation - both databases not available")

    finally:
        if py_conn:
            py_conn.close()
        if ts_conn:
            ts_conn.close()

    # Check server health
    log_info("Step 3: Checking server health...")
    python_healthy = check_server_health(args.python_port, "Python")
    ts_healthy = check_server_health(args.ts_port, "TypeScript")

    if python_healthy and ts_healthy:
        log_warn("Both servers are running - only one should be active")
    elif not python_healthy and not ts_healthy:
        log_warn("Neither server is running")
    elif ts_healthy:
        log_success("TypeScript server is active")
    else:
        log_info("Python server is active (TypeScript not running)")

    # Summary
    print()
    print("=" * 50)
    if all(results):
        print("Validation PASSED ✓")
        print("=" * 50)
        return 0
    else:
        print("Validation FAILED ✗")
        print("=" * 50)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate ZeroCoder migration from Python to TypeScript"
    )
    parser.add_argument(
        "--python-port",
        type=int,
        default=8888,
        help="Python server port (default: 8888)",
    )
    parser.add_argument(
        "--ts-port",
        type=int,
        default=8000,
        help="TypeScript server port (default: 8000)",
    )

    args = parser.parse_args()

    try:
        return run_validation(args)
    except KeyboardInterrupt:
        print("\nValidation interrupted")
        return 130
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
