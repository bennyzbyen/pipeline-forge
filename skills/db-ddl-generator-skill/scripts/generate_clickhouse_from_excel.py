#!/usr/bin/env python3
"""Fast path: generate ClickHouse CREATE TABLE DDL directly from an Excel data dictionary."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

import generate_ddl
import parse_excel_schema


def infer_table_name(rows: List[List[Any]], sheet_name: str) -> str:
    # Common data-dictionary layout: row 2, col B stores the real table name.
    if len(rows) > 1 and len(rows[1]) > 1 and parse_excel_schema.cell_text(rows[1][1]):
        return parse_excel_schema.cell_text(rows[1][1])

    for row in rows[:5]:
        non_empty = [parse_excel_schema.cell_text(cell) for cell in row if parse_excel_schema.cell_text(cell)]
        if len(non_empty) == 1 and not parse_excel_schema.canonical_header(non_empty[0]):
            return non_empty[0]

    return sheet_name


def choose_order_by(schema: Dict[str, Any], explicit_order_by: Optional[List[str]] = None) -> List[str]:
    if explicit_order_by:
        return explicit_order_by

    names = [column["name"] for column in schema.get("columns", [])]
    lower_to_name = {name.lower(): name for name in names}
    for preferred in ("rowkey", "dateid", "id"):
        if preferred in lower_to_name:
            return [lower_to_name[preferred]]
    return names[:1]


def parse_excel(path: Path, sheet: Optional[str] = None) -> List[Dict[str, Any]]:
    schemas: List[Dict[str, Any]] = []
    for sheet_data in parse_excel_schema.read_xlsx_sheets(path, sheet=sheet):
        table_name = infer_table_name(sheet_data["rows"], sheet_data["sheet_name"])
        schema = parse_excel_schema.normalize_schema_from_rows(
            sheet_data["rows"],
            table_name=table_name,
            source=f"{path}#{sheet_data['sheet_name']}",
        )
        if schema.get("columns"):
            schemas.append(schema)
    return schemas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--database", required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--env", choices=["qa", "prod"], default="qa")
    parser.add_argument("--order-by", help="Comma-separated ORDER BY fields applied to every generated table")
    parser.add_argument("--partition-by", help="Comma-separated PARTITION BY fields applied to every generated table")
    parser.add_argument("--cot-period-code-rule", action="store_true", help="When both period and code exist, use PARTITION BY period and ORDER BY (period, code)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    schemas = parse_excel(args.input, sheet=args.sheet)
    if not schemas:
        raise SystemExit("no field-definition sheets were detected")

    explicit_order_by = generate_ddl.split_csv(args.order_by) or None
    partition_by = generate_ddl.split_csv(args.partition_by) or None
    sql_parts: List[str] = []

    for schema in schemas:
        order_by = choose_order_by(schema, explicit_order_by)
        effective_partition_by = partition_by
        if args.cot_period_code_rule and explicit_order_by is None and partition_by is None:
            effective_partition_by, order_by, _applied = generate_ddl.apply_cot_period_code_rule(schema, None, None)
        key_names = set(order_by or [])
        for column in schema.get("columns", []):
            if column["name"] in key_names:
                column["nullable"] = False
        sql, _notes = generate_ddl.build_create_table(
            schema,
            target="clickhouse",
            env=args.env,
            database=args.database,
            table=schema.get("table_name"),
            partition_by=effective_partition_by,
            order_by=order_by,
        )
        sql_parts.append(sql)

    result = "\n\n".join(sql_parts) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
