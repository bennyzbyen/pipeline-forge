#!/usr/bin/env python3
"""Regression-test explicit ClickHouse deployment profiles without a database."""

from __future__ import annotations

import json

import generate_ddl


def expect_value_error(code: str, callback) -> None:
    try:
        callback()
    except ValueError:
        return
    raise AssertionError(f"expected ValueError: {code}")


def schema() -> dict:
    return {
        "database": "fixture_db",
        "table_name": "fixture_table",
        "columns": [
            {"name": "period", "type": "String", "nullable": True},
            {"name": "code", "type": "String", "nullable": False},
            {"name": "updated_at", "type": "DateTime", "nullable": True},
        ],
        "primary_key": [],
        "indexes": [],
        "partition_by": [],
        "order_by": [],
        "engine": "",
        "settings": {},
    }


def main() -> int:
    expect_value_error(
        "missing_order_by",
        lambda: generate_ddl.build_create_table(schema(), "clickhouse", clickhouse_engine="MergeTree"),
    )
    expect_value_error(
        "missing_engine",
        lambda: generate_ddl.build_create_table(schema(), "clickhouse", order_by=["code"]),
    )
    expect_value_error(
        "nullable_key",
        lambda: generate_ddl.build_create_table(
            schema(), "clickhouse", order_by=["period", "code"], clickhouse_engine="MergeTree"
        ),
    )

    qa_sql, qa_notes = generate_ddl.build_create_table(
        schema(),
        "clickhouse",
        order_by=["period", "code"],
        clickhouse_engine="ReplacingMergeTree",
        allow_key_nullability_coercion=True,
    )
    assert "ENGINE = ReplacingMergeTree()" in qa_sql, qa_sql
    assert "ON CLUSTER" not in qa_sql, qa_sql
    assert "updated_at)" not in qa_sql.split("ENGINE = ", 1)[1].splitlines()[0], qa_sql
    assert any("not a uniqueness constraint" in item for item in qa_notes["risks"]), qa_notes

    prod_sql, _ = generate_ddl.build_create_table(
        schema(),
        "clickhouse",
        order_by=["period", "code"],
        clickhouse_engine="ReplicatedReplacingMergeTree",
        clickhouse_cluster="fixture_cluster",
        clickhouse_replication_path="/clickhouse/fixture/{shard}/fixture_table",
        clickhouse_version_column="updated_at",
        allow_key_nullability_coercion=True,
    )
    assert "ON CLUSTER fixture_cluster" in prod_sql, prod_sql
    assert "ReplicatedReplacingMergeTree('/clickhouse/fixture/{shard}/fixture_table', '{replica}', updated_at)" in prod_sql, prod_sql
    assert "cl_1shards_2replicas" not in prod_sql, prod_sql

    print(json.dumps({"status": "passed", "case_count": 5}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
