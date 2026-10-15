#!/usr/bin/env python3
"""Offline ClickHouse field-contract and deployment-profile reconciliation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import parse_existing_ddl as parser


def select_table(document: dict, database: str, table: str) -> dict:
    tables = document.get("tables", [document])
    matches = [t for t in tables if (t.get("database") or t.get("schema")) == database
               and t.get("table_name") == table]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one exported table {database}.{table}; found {len(matches)}")
    return matches[0]


def profile_from_table(table: dict) -> dict:
    engine = str(table.get("engine") or "")
    match = re.fullmatch(r"(MergeTree|ReplacingMergeTree|ReplicatedMergeTree|ReplicatedReplacingMergeTree)(?:\((.*)\))?", engine, re.S)
    if not match:
        raise ValueError(f"unsupported deployment engine: {engine}")
    name, raw_args = match.groups()
    args = parser.split_top_level(raw_args or "")
    replicated = name.startswith("Replicated")
    replacing = "Replacing" in name
    expected = (2 if replicated else 0) + (1 if replacing else 0)
    if len(args) != expected:
        raise ValueError("deployment engine arguments/version are unresolved")
    profile = {
        "engine": name,
        "cluster": table.get("cluster", ""),
        "cluster_status": table.get("cluster_status", "not_exported_or_absent"),
        "partition_by": copy.deepcopy(table.get("partition_by", [])),
        "order_by": copy.deepcopy(table.get("order_by", [])),
        "primary_key": copy.deepcopy(table.get("primary_key", [])),
        "table_settings": copy.deepcopy(table.get("table_settings", {})),
        "source": table.get("source"),
        "source_database": table.get("database") or table.get("schema"),
        "source_table": table["table_name"],
    }
    if replacing:
        profile["version_column"] = args[-1].strip("`")
    if replicated:
        if not re.fullmatch(r"'(?:''|[^'])*'", args[0]):
            raise ValueError("replication path must be explicit")
        profile["replication_path"] = args[0][1:-1].replace("''", "'")
        profile["replica_expression"] = args[1]
    return profile


def bind_profile(schema: dict, export: dict, database: str, env: str) -> dict:
    """Bind columns from the current source to one exact historical deployment table."""
    result = copy.deepcopy(schema)
    baseline = select_table(export, database, schema["table_name"])
    result.setdefault("settings", {}).setdefault("clickhouse_profiles", {})[env] = profile_from_table(baseline)
    return result


def apply_scope(schemas: list[dict], manifest: dict) -> list[dict]:
    """Require one explicit create/skip decision for each input table."""
    entries = manifest.get("tables", [])
    lookup = {}
    for entry in entries:
        key = (entry.get("database"), entry.get("table_name"))
        if key in lookup or entry.get("action") not in {"create", "skip"} or not entry.get("reason"):
            raise ValueError("scope requires unique database/table, create/skip action, and reason")
        lookup[key] = entry
    keys = [(s.get("database") or s.get("schema"), s["table_name"]) for s in schemas]
    if len(set(keys)) != len(keys) or set(keys) != set(lookup):
        raise ValueError("scope must cover exactly the input tables")
    return [copy.deepcopy(s) for s, key in zip(schemas, keys) if lookup[key]["action"] == "create"]


def normalize_expression(value: Any) -> str:
    """Normalize whitespace outside quoted literals without changing literal content."""
    text = str(value if value is not None else "")
    result = []
    quote = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            result.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                result.append(text[index])
            elif char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                    result.append(text[index])
                else:
                    quote = None
        elif char in "'\"":
            quote = char
            result.append(char)
        elif not char.isspace() and char != "`":
            result.append(char)
        index += 1
    return "".join(result)


def compare_schemas(before: dict, after: dict) -> dict:
    old_names = [c["name"] for c in before["columns"]]
    new_names = [c["name"] for c in after["columns"]]
    if len(set(old_names)) != len(old_names) or len(set(new_names)) != len(new_names):
        raise ValueError("duplicate columns cannot be reconciled")
    old, new = ({c["name"]: c for c in schema["columns"]} for schema in (before, after))
    changes = []
    for name in old_names:
        if name not in new:
            continue
        for attribute in ("source_type", "nullable", "default", "comment", "on_update", "auto_increment"):
            a, b = old[name].get(attribute), new[name].get(attribute)
            if attribute == "default":
                a = None if str(a).upper() == "NULL" else a
                b = None if str(b).upper() == "NULL" else b
            if attribute in {"source_type", "default", "on_update"}:
                equal = normalize_expression(a) == normalize_expression(b)
            else:
                equal = a == b
            if not equal:
                changes.append({"column": name, "attribute": attribute, "before": a, "after": b})
    configuration = []
    for attribute in ("engine", "cluster", "partition_by", "order_by", "primary_key", "table_settings"):
        a, b = before.get(attribute), after.get(attribute)
        if attribute == "engine":
            a, b = normalize_expression(a), normalize_expression(b)
        if attribute == "table_settings":
            a = {k: normalize_expression(v) for k, v in (a or {}).items()}
            b = {k: normalize_expression(v) for k, v in (b or {}).items()}
        if a != b:
            configuration.append({"attribute": attribute, "before": a, "after": b})
    return {"added": [n for n in new_names if n not in old],
            "removed": [n for n in old_names if n not in new],
            "common_column_order_changed": [n for n in old_names if n in new] != [n for n in new_names if n in old],
            "column_changes": changes, "configuration_changes": configuration}


def has_changes(diff: dict) -> bool:
    return any(bool(value) for value in diff.values())


def main() -> int:
    import generate_ddl as generator
    generator.configure_stdout_utf8()
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, required=True, help="Current source CREATE TABLE SQL")
    cli.add_argument("--target", type=Path, required=True, help="One proposed ClickHouse CREATE TABLE SQL")
    cli.add_argument("--baseline", type=Path, required=True, help="QA or PROD CSV export")
    cli.add_argument("--baseline-database", required=True)
    cli.add_argument("--env", choices=["qa", "prod"], required=True)
    cli.add_argument("--audit-schema", type=Path, help="Explicit additional target column contracts: columns[]")
    cli.add_argument("--allow-key-nullability-coercion", action="store_true")
    cli.add_argument("--cluster", help="Explicit cluster override, including empty string for confirmed absence")
    cli.add_argument("--replication-path", help="Explicit new-table path when reusing a replicated profile")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    try:
        source_text, target_text = parser.read_sql(args.source), parser.read_sql(args.target)
        for text in (source_text, target_text):
            mask = parser.top_level_mask(re.sub(r"(?m)^\s*--[^\n]*", "", text))
            if len(re.findall(r"\bCREATE\s+TABLE\b", mask, re.I)) != 1:
                raise ValueError("review requires exactly one CREATE TABLE per SQL input")
        source = parser.parse_sql(source_text, str(args.source))
        target = parser.parse_sql(target_text, str(args.target))
        if source["table_name"] != target["table_name"]:
            raise ValueError("source/target table binding differs")
        export = parser.parse_csv_export(args.baseline)
        baseline = select_table(export, args.baseline_database, source["table_name"])
        expected_schema = bind_profile(source, export, args.baseline_database, args.env)
        audit_columns = []
        if args.audit_schema:
            audit_columns = json.loads(args.audit_schema.read_text(encoding="utf-8-sig"))["columns"]
            expected_schema["columns"].extend(copy.deepcopy(audit_columns))
        expected_sql, notes = generator.build_create_table(
            expected_schema, "clickhouse", env=args.env,
            database=target.get("database") or target.get("schema"),
            clickhouse_cluster=args.cluster, clickhouse_replication_path=args.replication_path,
            allow_key_nullability_coercion=args.allow_key_nullability_coercion)
        expected = parser.parse_sql(expected_sql)
        validation = compare_schemas(expected, target)
        inputs = [args.source, args.target, args.baseline] + ([args.audit_schema] if args.audit_schema else [])
        record = {"status": "FAIL" if has_changes(validation) else "PASS", "stage": "offline_review_failed" if has_changes(validation) else "offline_reconciled",
                  "environment": args.env, "binding": {"baseline_database": args.baseline_database, "table": source["table_name"]},
                  "counts": {"source": len(source["columns"]), "audit": len(audit_columns), "target": len(target["columns"])},
                  "contract_diff": validation, "baseline_diff": compare_schemas(baseline, target),
                  "notes": notes, "export_warnings": export.get("warnings", []),
                  "inputs": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
                  "not_performed": ["server identity/version checks", "DDL execution", "source NULL/value checks", "data import"]}
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": record["status"], "counts": record["counts"]}, ensure_ascii=False))
        return 1 if record["status"] == "FAIL" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        try:
            args.output.write_text(json.dumps({"status": "ERROR", "stage": "offline_review_incomplete", "error": str(exc)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(f"error: DDL review was not completed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
