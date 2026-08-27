#!/usr/bin/env python3
"""Generate formatted CREATE TABLE DDL from the standard schema contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def configure_stdout_utf8() -> None:
    """Prefer UTF-8 stdout so Chinese comments survive when users do not pass --output."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def esc_comment(text: Any) -> str:
    return str(text or "").replace("'", "''")


def split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def apply_cot_period_code_rule(
    schema: Dict[str, Any],
    partition_by: Optional[List[str]],
    order_by: Optional[List[str]],
) -> Tuple[Optional[List[str]], Optional[List[str]], bool]:
    """Use COT convention when both period and code exist."""
    if partition_by is not None or order_by is not None:
        return partition_by, order_by, False

    lower_to_name = {column["name"].lower(): column["name"] for column in schema.get("columns", [])}
    if "period" not in lower_to_name or "code" not in lower_to_name:
        return partition_by, order_by, False

    period = lower_to_name["period"]
    code = lower_to_name["code"]
    key_names = {period, code}
    for column in schema.get("columns", []):
        if column["name"] in key_names:
            column["nullable"] = False
    return [period], [period, code], True


def base_type(type_text: str) -> str:
    text = (type_text or "string").strip()
    text = re.sub(r"\s+", " ", text)
    if text.lower().startswith("nullable(") and text.endswith(")"):
        text = text[9:-1]
    return re.sub(r"\s*\(.*\)", "", text).strip().lower()


def numeric_args(type_text: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(r"\((\d+)(?:\s*,\s*(\d+))?\)", type_text or "")
    if not match:
        return None, None
    first = int(match.group(1))
    second = int(match.group(2)) if match.group(2) else None
    return first, second


def quote_ident(name: str, target: str) -> str:
    if target == "mysql" or target == "clickhouse":
        return f"`{name}`"
    if target == "mssql":
        return f"[{name}]"
    if target == "postgres":
        if re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            return name
        return f'"{name}"'
    return name


def table_ref(schema: Dict[str, Any], target: str, database: Optional[str], table: Optional[str]) -> str:
    table_name = table or schema.get("table_name") or "target_table"
    if target == "clickhouse":
        db = database or schema.get("database") or "default"
        return f"{db}.{table_name}"
    if target == "mssql":
        owner = schema.get("schema") or "dbo"
        return f"[{owner}].[{table_name}]"
    if target == "postgres":
        owner = schema.get("schema") or "public"
        return f"{owner}.{quote_ident(table_name, target)}"
    return quote_ident(table_name, target)


def map_type(type_text: str, target: str, column: Dict[str, Any]) -> str:
    raw = type_text or column.get("type") or "string"
    btype = base_type(raw)
    length = column.get("length")
    precision = column.get("precision")
    scale = column.get("scale")
    parsed_first, parsed_second = numeric_args(raw)
    length = length or (parsed_first if parsed_second is None else None)
    precision = precision or (parsed_first if parsed_second is not None else None)
    scale = scale if scale is not None else parsed_second

    if target == "clickhouse":
        raw_inner = raw[9:-1] if raw.lower().startswith("nullable(") and raw.endswith(")") else raw
        if re.match(r"^(Date|DateTime|DateTime64|Decimal|LowCardinality)\b", raw_inner):
            return raw_inner
        clickhouse_exact = {
            "int8": "Int8",
            "int16": "Int16",
            "int32": "Int32",
            "int64": "Int64",
            "uint8": "UInt8",
            "uint16": "UInt16",
            "uint32": "UInt32",
            "uint64": "UInt64",
            "float32": "Float32",
            "float64": "Float64",
            "string": "String",
            "uuid": "UUID",
        }
        if btype in clickhouse_exact:
            return clickhouse_exact[btype]
        if btype in {"tinyint", "bit", "boolean", "bool"}:
            return "Int8"
        if btype in {"smallint", "int2"}:
            return "Int16"
        if btype in {"int", "integer", "int4"}:
            return "Int32"
        if btype in {"bigint", "int8"}:
            return "Int64"
        if btype in {"float", "real"}:
            return "Float32"
        if btype in {"double", "double precision"}:
            return "Float64"
        if btype in {"decimal", "numeric", "number"}:
            return f"Decimal({precision or 18}, {scale if scale is not None else 4})"
        if btype in {"date"}:
            return "Date"
        if btype in {"datetime", "datetime2", "timestamp", "timestamp without time zone", "timestamp with time zone", "smalldatetime"}:
            return "DateTime"
        if btype in {"uuid", "uniqueidentifier"}:
            return "UUID"
        return "String"

    if target == "mysql":
        if btype in {"int8", "tinyint", "bit", "bool", "boolean"}:
            return "tinyint(1)" if btype in {"bool", "boolean", "bit"} else "tinyint"
        if btype in {"int16", "smallint"}:
            return "smallint"
        if btype in {"int32", "int", "integer", "int4"}:
            return "int"
        if btype in {"int64", "bigint", "int8"}:
            return "bigint"
        if btype in {"uint8"}:
            return "tinyint unsigned"
        if btype in {"uint16"}:
            return "smallint unsigned"
        if btype in {"uint32"}:
            return "int unsigned"
        if btype in {"uint64"}:
            return "bigint unsigned"
        if btype in {"float32", "float", "real"}:
            return "float"
        if btype in {"float64", "double", "double precision"}:
            return "double"
        if btype in {"decimal", "numeric"}:
            return f"decimal({precision or 18},{scale if scale is not None else 4})"
        if btype in {"date"}:
            return "date"
        if btype in {"datetime", "datetime2", "datetime64", "timestamp"}:
            return "datetime"
        if btype in {"text", "json", "jsonb", "string"} and not length:
            return "text"
        return f"varchar({length or 255})"

    if target == "postgres":
        if btype in {"tinyint", "int8", "smallint", "int16", "bit", "bool", "boolean"}:
            return "boolean" if btype in {"bool", "boolean", "bit"} else "smallint"
        if btype in {"int", "integer", "int32", "int4"}:
            return "integer"
        if btype in {"bigint", "int64", "int8"}:
            return "bigint"
        if btype in {"uint64"}:
            return "numeric(20,0)"
        if btype in {"float32", "float", "real"}:
            return "real"
        if btype in {"float64", "double", "double precision"}:
            return "double precision"
        if btype in {"decimal", "numeric"}:
            return f"numeric({precision or 18},{scale if scale is not None else 4})"
        if btype in {"date"}:
            return "date"
        if btype in {"datetime", "datetime2", "datetime64", "timestamp"}:
            return "timestamp"
        if btype in {"json", "jsonb"}:
            return "jsonb"
        if btype in {"uuid"}:
            return "uuid"
        if btype in {"text", "string"} and not length:
            return "text"
        return f"varchar({length or 255})"

    if target == "mssql":
        if btype in {"bit", "bool", "boolean"}:
            return "bit"
        if btype in {"tinyint", "uint8"}:
            return "tinyint"
        if btype in {"smallint", "int16"}:
            return "smallint"
        if btype in {"int", "integer", "int32", "int4"}:
            return "int"
        if btype in {"bigint", "int64", "int8"}:
            return "bigint"
        if btype in {"float", "float64", "double", "double precision"}:
            return "float"
        if btype in {"real", "float32"}:
            return "real"
        if btype in {"decimal", "numeric"}:
            return f"decimal({precision or 18},{scale if scale is not None else 4})"
        if btype in {"date"}:
            return "date"
        if btype in {"datetime", "datetime2", "datetime64", "timestamp"}:
            return "datetime2"
        if btype in {"uuid", "uniqueidentifier"}:
            return "uniqueidentifier"
        if btype in {"text", "json", "jsonb", "string"} and not length:
            return "nvarchar(max)"
        return f"nvarchar({length or 255})"

    raise ValueError(f"unsupported target: {target}")


def normalize_default(default: Any, target: str) -> Optional[str]:
    if default is None or str(default).strip() == "":
        return None
    text = str(default).strip()
    if text.upper() in {"NULL", "DEFAULT NULL"}:
        return None
    if target == "clickhouse" and text.upper() in {"CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP()"}:
        return "now()"
    if target in {"mysql", "postgres", "mssql"} and text.lower() == "now()":
        return "CURRENT_TIMESTAMP"
    return text


def clickhouse_type(
    column: Dict[str, Any],
    key_columns: Iterable[str],
    notes: Dict[str, List[str]],
    allow_key_nullability_coercion: bool = False,
) -> str:
    mapped = map_type(column.get("source_type") or column.get("type"), "clickhouse", column)
    name = column["name"]
    nullable = bool(column.get("nullable", True))
    if name in set(key_columns):
        if nullable:
            if not allow_key_nullability_coercion:
                raise ValueError(
                    f"ClickHouse key column {name!r} is nullable; confirm source semantics and use "
                    "--allow-key-nullability-coercion only when non-nullability is justified"
                )
            notes["risks"].append(f"{name}: key nullability was explicitly coerced to non-nullable")
        return mapped
    if nullable and not mapped.lower().startswith("nullable("):
        return f"Nullable({mapped})"
    return mapped


def choose_version_column(columns: List[Dict[str, Any]]) -> Optional[str]:
    preferred = [
        "inksaa_last_modified_timestamp",
        "cl_last_update_time",
        "updated_at",
        "last_updated_at",
        "modify_time",
        "modified_at",
        "report_build_time",
    ]
    names = {column["name"]: column for column in columns}
    for name in preferred:
        if name in names:
            return name
    for column in columns:
        if base_type(column.get("type") or column.get("source_type")) in {"datetime", "datetime2", "timestamp", "datetime64"}:
            return column["name"]
    return None


def build_create_table(
    schema: Dict[str, Any],
    target: str,
    env: str = "qa",
    database: Optional[str] = None,
    table: Optional[str] = None,
    partition_by: Optional[List[str]] = None,
    order_by: Optional[List[str]] = None,
    primary_key: Optional[List[str]] = None,
    clickhouse_engine: Optional[str] = None,
    clickhouse_cluster: Optional[str] = None,
    clickhouse_replication_path: Optional[str] = None,
    clickhouse_version_column: Optional[str] = None,
    allow_key_nullability_coercion: bool = False,
) -> Tuple[str, Dict[str, List[str]]]:
    target = target.lower()
    columns = schema.get("columns", [])
    table_name = table or schema.get("table_name") or "target_table"
    notes: Dict[str, List[str]] = {"assumptions": [], "risks": [], "type_mappings": []}
    if not columns:
        raise ValueError("schema contains no columns")
    if not isinstance(columns, list) or any(not isinstance(column, dict) for column in columns):
        raise ValueError("schema columns must be a list of column objects")
    column_names = [str(column.get("name") or "").strip() for column in columns]
    if any(not name for name in column_names):
        raise ValueError("every schema column must have a non-empty name")
    seen_names: Dict[str, str] = {}
    duplicate_names: List[str] = []
    for name in column_names:
        normalized = name.casefold()
        if normalized in seen_names and name not in duplicate_names:
            duplicate_names.append(name)
        else:
            seen_names[normalized] = name
    if duplicate_names:
        raise ValueError(f"schema contains duplicate column names: {', '.join(duplicate_names)}")

    pk = primary_key if primary_key is not None else schema.get("primary_key", [])
    if not pk:
        pk = [column["name"] for column in columns if column.get("primary_key")]
    indexes = schema.get("indexes", [])

    if target == "clickhouse":
        db = database or schema.get("database") or "default"
        partition_cols = partition_by if partition_by is not None else schema.get("partition_by", [])
        order_cols = order_by if order_by is not None else schema.get("order_by", [])
        if not order_cols:
            raise ValueError("ClickHouse ORDER BY must be supplied by the deployment profile or source DDL")
        profile_root = schema.get("settings") if isinstance(schema.get("settings"), dict) else {}
        profiles = profile_root.get("clickhouse_profiles") if isinstance(profile_root.get("clickhouse_profiles"), dict) else {}
        profile = profiles.get(env) if isinstance(profiles.get(env), dict) else {}
        engine_name = clickhouse_engine or profile.get("engine") or schema.get("engine")
        cluster_name = clickhouse_cluster if clickhouse_cluster is not None else profile.get("cluster", "")
        replication_path = clickhouse_replication_path or profile.get("replication_path")
        version_column = clickhouse_version_column or profile.get("version_column")
        if not engine_name:
            raise ValueError(
                "ClickHouse engine is unresolved; pass --engine or define settings.clickhouse_profiles.<env>.engine"
            )
        key_columns = set(order_cols) | set(partition_cols) | set(pk)
        column_lines = []
        for column in columns:
            mapped = clickhouse_type(column, key_columns, notes, allow_key_nullability_coercion)
            default = normalize_default(column.get("default"), target)
            default_sql = f" DEFAULT {default}" if default else ""
            comment_sql = f" COMMENT '{esc_comment(column.get('comment'))}'" if column.get("comment") else ""
            column_lines.append(f"    {quote_ident(column['name'], target)} {mapped}{default_sql}{comment_sql}")
            notes["type_mappings"].append(f"{column['name']}: {column.get('source_type') or column.get('type')} -> {mapped}")

        allowed_engines = {
            "MergeTree",
            "ReplacingMergeTree",
            "ReplicatedMergeTree",
            "ReplicatedReplacingMergeTree",
        }
        engine_text = str(engine_name).strip()
        if "(" in engine_text:
            engine = engine_text
        else:
            if engine_text not in allowed_engines:
                raise ValueError(f"unsupported ClickHouse engine profile: {engine_text!r}")
            if engine_text.startswith("Replicated"):
                if not replication_path:
                    raise ValueError("Replicated ClickHouse engines require an explicit replication path")
                replica_args = f"'{esc_comment(replication_path)}', '{{replica}}'"
                if engine_text == "ReplicatedReplacingMergeTree" and version_column:
                    replica_args += f", {version_column}"
                engine = f"{engine_text}({replica_args})"
            elif engine_text == "ReplacingMergeTree":
                engine = f"ReplacingMergeTree({version_column})" if version_column else "ReplacingMergeTree()"
            else:
                engine = "MergeTree"

        if cluster_name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(cluster_name)):
            raise ValueError("ClickHouse cluster must be a safe identifier")
        cluster_sql = f" ON CLUSTER {cluster_name}" if cluster_name else ""
        notes["risks"].append("ClickHouse ORDER BY controls sorting/deduplication behavior; it is not a uniqueness constraint")

        partition_sql = f"\nPARTITION BY {', '.join(partition_cols)}" if partition_cols else ""
        primary_sql = f"\nPRIMARY KEY ({', '.join(pk)})" if pk else ""
        sql = (
            f"CREATE TABLE {db}.{table_name}{cluster_sql}\n"
            "(\n"
            + ",\n".join(column_lines)
            + "\n)\n"
            f"ENGINE = {engine}"
            f"{partition_sql}\n"
            f"ORDER BY ({', '.join(order_cols)})"
            f"{primary_sql}\n"
            "SETTINGS index_granularity = 8192;"
        )
        return sql, notes

    column_lines = []
    comment_statements: List[str] = []
    for column in columns:
        mapped = map_type(column.get("source_type") or column.get("type"), target, column)
        nullable_sql = " NOT NULL" if not column.get("nullable", True) or column["name"] in pk else " NULL"
        default = normalize_default(column.get("default"), target)
        default_sql = f" DEFAULT {default}" if default else ""
        notes["type_mappings"].append(f"{column['name']}: {column.get('source_type') or column.get('type')} -> {mapped}")
        if target == "mysql":
            comment_sql = f" COMMENT '{esc_comment(column.get('comment'))}'" if column.get("comment") else ""
            column_lines.append(f"  {quote_ident(column['name'], target)} {mapped}{nullable_sql}{default_sql}{comment_sql}")
        else:
            column_lines.append(f"  {quote_ident(column['name'], target)} {mapped}{nullable_sql}{default_sql}")
            if column.get("comment"):
                ref = table_ref(schema, target, database, table)
                comment_statements.append(f"COMMENT ON COLUMN {ref}.{quote_ident(column['name'], target)} IS '{esc_comment(column.get('comment'))}';")

    constraints: List[str] = []
    if pk:
        constraints.append(f"  PRIMARY KEY ({', '.join(quote_ident(col, target) for col in pk)})")
    body_lines = column_lines + constraints
    sql = f"CREATE TABLE {table_ref(schema, target, database, table)} (\n" + ",\n".join(body_lines) + "\n)"

    if target == "mysql":
        table_comment = schema.get("table_comment")
        comment_sql = f" COMMENT='{esc_comment(table_comment)}'" if table_comment else ""
        index_parts = []
        for index in indexes:
            cols = ", ".join(quote_ident(col, target) for col in index.get("columns", []))
            if cols:
                index_parts.append(f"KEY {quote_ident(index.get('name') or ('idx_' + table_name), target)} ({cols})")
        if index_parts:
            sql = sql[:-2] + ",\n  " + ",\n  ".join(index_parts) + "\n)"
        sql += f" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4{comment_sql};"
        return sql, notes

    sql += ";"
    index_sql = []
    ref = table_ref(schema, target, database, table)
    for index in indexes:
        cols = ", ".join(quote_ident(col, target) for col in index.get("columns", []))
        if cols:
            index_sql.append(f"CREATE INDEX {quote_ident(index.get('name') or ('idx_' + table_name), target)} ON {ref} ({cols});")

    if target == "mssql":
        # SQL Server comments require sp_addextendedproperty; keep a review note instead of emitting verbose boilerplate.
        if comment_statements:
            notes["risks"].append("Column comments for MSSQL should be emitted as MS_Description extended properties during final review")
        comment_statements = []

    if target == "postgres" and schema.get("table_comment"):
        comment_statements.insert(0, f"COMMENT ON TABLE {ref} IS '{esc_comment(schema.get('table_comment'))}';")

    tail = "\n".join(index_sql + comment_statements)
    return sql + ("\n\n" + tail if tail else ""), notes


def render_output(sql: str, notes: Dict[str, List[str]], sql_only: bool) -> str:
    if sql_only:
        return sql
    sections = [sql]
    for title, key in [("Type mappings", "type_mappings"), ("Assumptions", "assumptions"), ("Risks", "risks")]:
        values = notes.get(key) or []
        if values:
            sections.append(title + ":\n" + "\n".join(f"- {value}" for value in values))
    return "\n\n".join(sections)


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema_json", type=Path)
    parser.add_argument("--target", required=True, choices=["mysql", "mssql", "clickhouse", "postgres"])
    parser.add_argument("--env", choices=["qa", "prod"], default="qa")
    parser.add_argument("--database")
    parser.add_argument("--table")
    parser.add_argument("--partition-by")
    parser.add_argument("--order-by")
    parser.add_argument("--primary-key")
    parser.add_argument("--engine", choices=["MergeTree", "ReplacingMergeTree", "ReplicatedMergeTree", "ReplicatedReplacingMergeTree"], help="Explicit ClickHouse engine profile")
    parser.add_argument("--cluster", help="Explicit ClickHouse cluster name; omit for no ON CLUSTER")
    parser.add_argument("--replication-path", help="Explicit ZooKeeper path for Replicated engines")
    parser.add_argument("--version-column", help="Explicit ReplacingMergeTree version column")
    parser.add_argument("--allow-key-nullability-coercion", action="store_true", help="Acknowledge conversion of nullable ClickHouse key columns to non-nullable")
    parser.add_argument("--all-tables", action="store_true", help="Generate DDL for every schema in tables[]")
    parser.add_argument("--cot-period-code-rule", action="store_true", help="When both period and code exist, use PARTITION BY period and ORDER BY (period, code)")
    parser.add_argument("--sql-only", action="store_true")
    parser.add_argument("--output", type=Path, help="Write generated DDL to this path using UTF-8")
    args = parser.parse_args()

    try:
        document = json.loads(args.schema_json.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("schema JSON root must be an object")
        if args.all_tables and "tables" in document:
            schemas = document["tables"]
        elif "tables" in document and document["tables"]:
            schemas = [document["tables"][0]]
        else:
            schemas = [document]
        if not isinstance(schemas, list) or any(not isinstance(schema, dict) for schema in schemas):
            raise ValueError("tables must be a list of schema objects")
        if not schemas:
            raise ValueError("schema contains no tables")

        outputs: List[str] = []
        for schema in schemas:
            partition_by = split_csv(args.partition_by) or None
            order_by = split_csv(args.order_by) or None
            if args.cot_period_code_rule:
                partition_by, order_by, _applied = apply_cot_period_code_rule(schema, partition_by, order_by)
            sql, notes = build_create_table(
                schema,
                target=args.target,
                env=args.env,
                database=args.database or schema.get("database"),
                table=args.table if len(schemas) == 1 else schema.get("table_name"),
                partition_by=partition_by,
                order_by=order_by,
                primary_key=split_csv(args.primary_key) or None,
                clickhouse_engine=args.engine,
                clickhouse_cluster=args.cluster,
                clickhouse_replication_path=args.replication_path,
                clickhouse_version_column=args.version_column,
                allow_key_nullability_coercion=args.allow_key_nullability_coercion,
            )
            outputs.append(render_output(sql, notes, args.sql_only))
        output = "\n\n".join(outputs)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        print(f"error: DDL was not generated: {detail}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
