#!/usr/bin/env python3
"""Exercise the four-dialect parse/normalize/convert matrix without a database."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import parse_existing_ddl


DIALECTS = ("mysql", "mssql", "clickhouse", "postgres")
FIXTURES = {
    "mysql": """CREATE TABLE `fixture_matrix` (
  `id` bigint NOT NULL COMMENT 'fixture id',
  `name` varchar(64) NULL,
  `amount` decimal(12,2) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
""",
    "mssql": """CREATE TABLE [dbo].[fixture_matrix] (
  [id] bigint NOT NULL,
  [name] nvarchar(64) NULL,
  [amount] decimal(12,2) NOT NULL,
  CONSTRAINT [PK_fixture_matrix] PRIMARY KEY ([id])
);
""",
    "clickhouse": """CREATE TABLE fixture.fixture_matrix (
  `id` Int64,
  `name` Nullable(String),
  `amount` Decimal(12,2)
) ENGINE = MergeTree
ORDER BY (id);
""",
    "postgres": """CREATE TABLE public.fixture_matrix (
  id bigint NOT NULL,
  name varchar(64) NULL,
  amount numeric(12,2) NOT NULL,
  PRIMARY KEY (id)
);
COMMENT ON COLUMN public.fixture_matrix.id IS 'fixture id';
""",
}


def assert_normalized(schema: dict[str, Any], dialect: str) -> None:
    assert schema["dialect"] == dialect, (dialect, schema["dialect"])
    assert schema["table_name"] == "fixture_matrix", schema
    assert [column["name"] for column in schema["columns"]] == ["id", "name", "amount"], schema
    if dialect == "clickhouse":
        assert schema["primary_key"] == [], schema
        assert schema["order_by"] == ["id"], schema
    else:
        assert schema["primary_key"] == ["id"], schema
    by_name = {column["name"]: column for column in schema["columns"]}
    assert by_name["id"]["nullable"] is False, schema
    assert by_name["amount"]["nullable"] is False, schema


def run_conversion(script: Path, input_path: Path, source: str, target: str) -> str:
    command = [
        sys.executable,
        str(script),
        str(input_path),
        "--source",
        source,
        "--target",
        target,
        "--table",
        "fixture_matrix",
        "--sql-only",
    ]
    if target == "clickhouse":
        command.extend(["--database", "fixture", "--engine", "MergeTree", "--order-by", "id"])
    completed = subprocess.run(command, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"{source}->{target} failed with {completed.returncode}:\n{completed.stdout}\n{completed.stderr}"
        )
    assert "CREATE TABLE" in completed.stdout.upper(), (source, target, completed.stdout)
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    script = Path(__file__).resolve().parent / "convert_ddl.py"
    results: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="pipelineforge_ddl_matrix_") as temp_dir:
        root = Path(temp_dir)
        for source, ddl in FIXTURES.items():
            source_schema = parse_existing_ddl.parse_sql(ddl, source=f"synthetic:{source}")
            assert_normalized(source_schema, source)
            input_path = root / f"{source}.sql"
            input_path.write_text(ddl, encoding="utf-8")
            for target in DIALECTS:
                rendered = run_conversion(script, input_path, source, target)
                round_trip = parse_existing_ddl.parse_sql(rendered, source=f"synthetic:{source}->{target}")
                assert round_trip["table_name"] == "fixture_matrix", (source, target, round_trip)
                assert [column["name"] for column in round_trip["columns"]] == ["id", "name", "amount"], (
                    source,
                    target,
                    round_trip,
                )
                assert round_trip["primary_key"] == source_schema["primary_key"] or target == "clickhouse", (
                    source,
                    target,
                    round_trip,
                )
                if target == "clickhouse":
                    assert round_trip["engine"].startswith("MergeTree"), round_trip
                    assert round_trip["order_by"] == ["id"], round_trip
                elif target == "postgres":
                    # Plain PostgreSQL CREATE TABLE can be intentionally ANSI-like;
                    # dialect detection only claims postgres when a postgres marker exists.
                    assert round_trip["dialect"] in {"postgres", "unknown"}, (
                        source,
                        target,
                        round_trip["dialect"],
                        rendered,
                    )
                    assert "numeric(12,2)" in rendered.lower(), rendered
                    assert "[" not in rendered and "`" not in rendered, rendered
                else:
                    assert round_trip["dialect"] == target, (source, target, round_trip["dialect"], rendered)
                results.append(
                    {
                        "case": f"{source}_to_{target}",
                        "source": source,
                        "target": target,
                        "status": "passed",
                    }
                )

    print(
        json.dumps(
            {
                "status": "passed",
                "source_dialect_count": len(DIALECTS),
                "target_dialect_count": len(DIALECTS),
                "case_count": len(results),
                "cases": results,
                "external_service_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
