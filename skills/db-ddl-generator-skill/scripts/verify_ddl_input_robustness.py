#!/usr/bin/env python3
"""Regression-test DDL CLI rejection of malformed or unconfirmed inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


GENERATOR = Path(__file__).resolve().parent / "generate_ddl.py"


def base_schema(columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "database": "fixture_db",
        "table_name": "fixture_table",
        "columns": columns,
        "primary_key": [],
        "indexes": [],
        "partition_by": [],
        "order_by": [],
        "engine": "",
        "settings": {},
    }


def write_schema(path: Path, schema: dict[str, Any]) -> None:
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *arguments],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def assert_rejected(completed: subprocess.CompletedProcess[str], expected: str, output: Path) -> None:
    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0, combined
    assert expected.lower() in combined.lower(), combined
    assert "Traceback (most recent call last)" not in combined, combined
    assert not output.exists(), f"rejected input left misleading SQL artifact: {output}"


def run_regression() -> dict[str, object]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ddl_input_robustness_") as temp_dir:
        root = Path(temp_dir)
        valid = root / "valid.json"
        write_schema(valid, base_schema([{"name": "id", "type": "bigint", "nullable": False}]))

        unsupported_output = root / "unsupported.sql"
        completed = run_cli([str(valid), "--target", "oracle", "--output", str(unsupported_output)])
        assert_rejected(completed, "invalid choice", unsupported_output)
        results.append({"case": "unsupported_dialect", "status": "passed", "exit_code": completed.returncode})

        empty = root / "empty.json"
        write_schema(empty, base_schema([]))
        empty_output = root / "empty.sql"
        completed = run_cli([str(empty), "--target", "mysql", "--output", str(empty_output)])
        assert_rejected(completed, "schema contains no columns", empty_output)
        results.append({"case": "empty_columns", "status": "passed", "exit_code": completed.returncode})

        empty_tables = root / "empty_tables.json"
        empty_tables.write_text('{"tables": []}\n', encoding="utf-8")
        empty_tables_output = root / "empty_tables.sql"
        completed = run_cli(
            [str(empty_tables), "--target", "mysql", "--all-tables", "--output", str(empty_tables_output)]
        )
        assert_rejected(completed, "schema contains no tables", empty_tables_output)
        results.append({"case": "empty_table_list", "status": "passed", "exit_code": completed.returncode})

        duplicate = root / "duplicate.json"
        write_schema(
            duplicate,
            base_schema(
                [
                    {"name": "record_id", "type": "bigint", "nullable": False},
                    {"name": "RECORD_ID", "type": "string", "nullable": True},
                ]
            ),
        )
        duplicate_output = root / "duplicate.sql"
        completed = run_cli([str(duplicate), "--target", "postgres", "--output", str(duplicate_output)])
        assert_rejected(completed, "duplicate column names", duplicate_output)
        results.append({"case": "duplicate_columns", "status": "passed", "exit_code": completed.returncode})

        nullable_key = root / "nullable_key.json"
        write_schema(nullable_key, base_schema([{"name": "record_id", "type": "String", "nullable": True}]))
        nullable_output = root / "nullable_key.sql"
        completed = run_cli(
            [
                str(nullable_key),
                "--target",
                "clickhouse",
                "--database",
                "fixture_db",
                "--engine",
                "MergeTree",
                "--order-by",
                "record_id",
                "--output",
                str(nullable_output),
            ]
        )
        assert_rejected(completed, "--allow-key-nullability-coercion", nullable_output)
        results.append(
            {"case": "unconfirmed_clickhouse_nullable_key", "status": "passed", "exit_code": completed.returncode}
        )

    return {
        "status": "passed",
        "case_count": len(results),
        "cases": results,
        "external_service_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
