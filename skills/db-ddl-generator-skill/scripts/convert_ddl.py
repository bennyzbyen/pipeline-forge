#!/usr/bin/env python3
"""Convert CREATE TABLE DDL between supported database dialects."""

from __future__ import annotations

import argparse
from pathlib import Path

import generate_ddl
import parse_existing_ddl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--source", choices=["mysql", "mssql", "clickhouse", "postgres"], help="Source dialect override")
    parser.add_argument("--target", required=True, choices=["mysql", "mssql", "clickhouse", "postgres"])
    parser.add_argument("--env", choices=["qa", "prod"], default="qa")
    parser.add_argument("--database")
    parser.add_argument("--table")
    parser.add_argument("--partition-by")
    parser.add_argument("--order-by")
    parser.add_argument("--primary-key")
    parser.add_argument("--engine", choices=["MergeTree", "ReplacingMergeTree", "ReplicatedMergeTree", "ReplicatedReplacingMergeTree"])
    parser.add_argument("--cluster")
    parser.add_argument("--replication-path")
    parser.add_argument("--version-column")
    parser.add_argument("--allow-key-nullability-coercion", action="store_true")
    parser.add_argument("--sql-only", action="store_true")
    args = parser.parse_args()

    sql_text = parse_existing_ddl.read_sql(args.input)
    schema = parse_existing_ddl.parse_sql(sql_text, source=str(args.input))
    if args.source:
        schema["dialect"] = args.source
    sql, notes = generate_ddl.build_create_table(
        schema,
        target=args.target,
        env=args.env,
        database=args.database,
        table=args.table,
        partition_by=generate_ddl.split_csv(args.partition_by) or None,
        order_by=generate_ddl.split_csv(args.order_by) or None,
        primary_key=generate_ddl.split_csv(args.primary_key) or None,
        clickhouse_engine=args.engine,
        clickhouse_cluster=args.cluster,
        clickhouse_replication_path=args.replication_path,
        clickhouse_version_column=args.version_column,
        allow_key_nullability_coercion=args.allow_key_nullability_coercion,
    )
    if args.sql_only:
        print(sql)
        return

    differences = [
        f"source dialect: {schema.get('dialect', args.source or 'unknown')}",
        f"target dialect: {args.target}",
    ]
    if schema.get("indexes") and args.target == "clickhouse":
        differences.append("source secondary indexes were not converted to ClickHouse indexes; choose ORDER BY explicitly")
    if schema.get("engine") and args.target != "clickhouse":
        differences.append("source storage engine details were not converted to the target database")
    notes.setdefault("risks", []).extend(differences)
    print(generate_ddl.render_output(sql, notes, sql_only=False))


if __name__ == "__main__":
    main()
