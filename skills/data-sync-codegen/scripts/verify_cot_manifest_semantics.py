#!/usr/bin/env python3
"""Validate every generated COT table against manifest and runtime configuration."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


VALID_SYNC_MODES = {"with_period", "without_period"}
VALID_SOURCE_GROUPS = {"report_ps_p", "store_report", "store_report_generator"}
RUNTIME_KEYS = (
    "mysql_table",
    "last_update_time_column",
    "period_column",
    "code_column",
    "key_column",
    "hbase_table",
    "rowkey_rule_columns",
    "hbase_delete_request_contract",
    "clickhouse_table",
    "source_group",
    "sync_mode",
    "contract_issues",
    "runtime_enabled",
)


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def load_literal_assignment(path: Path, assignment_name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == assignment_name for target in targets):
            value_node = node.value
            if value_node is None:
                break
            return ast.literal_eval(value_node)
    raise ValueError(f"literal assignment {assignment_name!r} not found in {path}")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_list(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [clean_text(item) for item in value if clean_text(item)]


def add_issue(
    issues: List[Dict[str, str]],
    code: str,
    message: str,
    table: str = "",
) -> None:
    issue = {"code": code, "message": message}
    if table:
        issue["table"] = table
    issues.append(issue)


def duplicates(values: Iterable[str]) -> List[str]:
    counts = Counter(value for value in values if value)
    return sorted(value for value, count in counts.items() if count > 1)


def validate_summary(
    manifest: Mapping[str, Any],
    tables: Sequence[Mapping[str, Any]],
    errors: List[Dict[str, str]],
) -> None:
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    actual_with = sum(1 for table in tables if table.get("sync_mode") == "with_period")
    actual_without = sum(1 for table in tables if table.get("sync_mode") == "without_period")
    expected = {
        "table_count": len(tables),
        "with_period_count": actual_with,
        "without_period_count": actual_without,
    }
    for key, actual in expected.items():
        if summary.get(key) != actual:
            add_issue(errors, "summary_mismatch", f"summary.{key}={summary.get(key)!r}, expected {actual}")


def validate_unique_targets(
    tables: Sequence[Mapping[str, Any]],
    errors: List[Dict[str, str]],
) -> None:
    for field in ("mysql_table", "hbase_table", "clickhouse_full_name"):
        repeated = duplicates(clean_text(table.get(field)) for table in tables)
        for value in repeated:
            add_issue(errors, "duplicate_target", f"{field} is used more than once: {value}")


def validate_table(
    table: Mapping[str, Any],
    runtime: Mapping[str, Any],
    rowkey_rules: Mapping[str, Any],
    contract_ready: bool,
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    deployment_blockers: List[Dict[str, str]],
) -> Dict[str, Any]:
    table_name = clean_text(table.get("mysql_table"))
    table_errors_before = len(errors)
    table_warnings_before = len(warnings)
    if not table_name:
        add_issue(errors, "missing_table_name", "mysql_table is required")
        table_name = "<missing>"

    sync_mode = clean_text(table.get("sync_mode"))
    if sync_mode not in VALID_SYNC_MODES:
        add_issue(errors, "invalid_sync_mode", f"unsupported sync_mode: {sync_mode!r}", table_name)

    for key in ("last_update_time_column", "hbase_table", "clickhouse_table", "source_group"):
        if not clean_text(table.get(key)):
            add_issue(errors, "missing_required_value", f"{key} is required", table_name)
    if clean_text(table.get("source_group")) not in VALID_SOURCE_GROUPS:
        add_issue(
            errors,
            "invalid_source_group",
            f"unsupported source_group: {table.get('source_group')!r}",
            table_name,
        )

    fields = clean_list(table.get("fields"))
    field_set = set(fields)
    if not fields:
        target = errors if contract_ready else warnings
        add_issue(target, "missing_field_dictionary", "field dictionary is empty", table_name)
    elif len(fields) != len(field_set):
        add_issue(errors, "duplicate_fields", "field dictionary contains duplicate column names", table_name)

    required_columns = [clean_text(table.get("last_update_time_column"))]
    if sync_mode == "with_period":
        required_columns.extend(
            [clean_text(table.get("period_column")), clean_text(table.get("code_column"))]
        )
        if not clean_text(table.get("period_column")) or not clean_text(table.get("code_column")):
            add_issue(errors, "missing_period_dispatch", "with-period table needs period_column and code_column", table_name)
    elif sync_mode == "without_period":
        required_columns.append(clean_text(table.get("key_column")))
        if not clean_text(table.get("key_column")):
            add_issue(errors, "missing_key_column", "without-period table needs key_column", table_name)

    rowkey_columns = clean_list(table.get("rowkey_rule_columns"))
    if not rowkey_columns:
        add_issue(errors, "missing_rowkey", "rowkey_rule_columns is empty", table_name)
    required_columns.extend(rowkey_columns)
    expected_contract_issues: List[str] = []
    if not fields:
        expected_contract_issues.append("missing_field_dictionary")
    else:
        if any(not column for column in required_columns):
            expected_contract_issues.append("missing_required_column_name")
        for column in dict.fromkeys(column for column in required_columns if column):
            if column not in field_set:
                expected_contract_issues.append(f"column_not_in_fields:{column}")
    if clean_list(table.get("contract_issues")) != expected_contract_issues:
        add_issue(
            errors,
            "stale_contract_issues",
            f"contract_issues must equal derived blockers: expected={expected_contract_issues}, actual={table.get('contract_issues')!r}",
            table_name,
        )
    expected_runtime_enabled = not expected_contract_issues
    if table.get("runtime_enabled") is not expected_runtime_enabled:
        add_issue(
            errors,
            "runtime_guard_mismatch",
            f"runtime_enabled must be {expected_runtime_enabled} for the derived table contract",
            table_name,
        )
    if fields:
        for column in sorted(set(column for column in required_columns if column)):
            if column not in field_set:
                add_issue(errors, "column_not_in_fields", f"configured column is absent from fields: {column}", table_name)

    runtime_item = runtime.get(table_name)
    if not isinstance(runtime_item, Mapping):
        add_issue(errors, "missing_runtime_config", "table is absent from plugin_config.table_configs", table_name)
    else:
        for key in RUNTIME_KEYS:
            manifest_value = table.get(key)
            runtime_value = runtime_item.get(key)
            if manifest_value != runtime_value:
                add_issue(
                    errors,
                    "runtime_manifest_mismatch",
                    f"{key} differs: manifest={manifest_value!r}, runtime={runtime_value!r}",
                    table_name,
                )

    hbase_table = clean_text(table.get("hbase_table"))
    rowkey_rule = rowkey_rules.get(hbase_table)
    if not isinstance(rowkey_rule, Mapping):
        add_issue(errors, "missing_rowkey_rule", f"no rowkey rule for HBase target {hbase_table}", table_name)
        confirmed = False
    else:
        confirmed = rowkey_rule.get("confirmed") is True
        if clean_text(rowkey_rule.get("source_table")) != table_name:
            add_issue(errors, "rowkey_source_mismatch", "rowkey source_table does not match manifest", table_name)
        if clean_text(rowkey_rule.get("sync_mode")) != sync_mode:
            add_issue(errors, "rowkey_mode_mismatch", "rowkey sync_mode does not match manifest", table_name)
        if clean_list(rowkey_rule.get("columns")) != rowkey_columns:
            add_issue(errors, "rowkey_columns_mismatch", "rowkey columns differ from runtime manifest", table_name)
        prefix = rowkey_rule.get("prefix") if isinstance(rowkey_rule.get("prefix"), Mapping) else {}
        if prefix.get("enabled") is True:
            if prefix.get("type") not in {"last_char", "hash_mod", "none"}:
                add_issue(errors, "invalid_rowkey_prefix", f"unsupported prefix type: {prefix.get('type')!r}", table_name)
            if not isinstance(prefix.get("mod"), int) or prefix.get("mod", 0) <= 0:
                add_issue(errors, "invalid_rowkey_prefix", "enabled rowkey prefix needs a positive integer mod", table_name)
        if not confirmed:
            add_issue(deployment_blockers, "rowkey_unconfirmed", "rowkey rule still has confirmed=false", table_name)

    request_contract = table.get("hbase_delete_request_contract") if isinstance(table.get("hbase_delete_request_contract"), Mapping) else {}
    if sync_mode == "with_period":
        expected_prefixes = [str(item) for item in range(10)]
        if clean_list(request_contract.get("row_prefixs")) != expected_prefixes:
            add_issue(errors, "hbase_final_request_mismatch", "final HBase delete request must use row prefixes 0-9", table_name)
        if request_contract.get("validate_after_wrapper_defaults") is not True:
            add_issue(deployment_blockers, "hbase_final_request_unvalidated", "validate the final HBase request after wrapper defaults", table_name)

    return {
        "table": table_name,
        "sync_mode": sync_mode,
        "field_count": len(fields),
        "rowkey_columns": rowkey_columns,
        "rowkey_confirmed": confirmed,
        "error_count": len(errors) - table_errors_before,
        "warning_count": len(warnings) - table_warnings_before,
    }


def validate_project(project_dir: Path) -> Dict[str, Any]:
    manifest_path = project_dir / "cot_sync_manifest.json"
    plugin_config_path = project_dir / "cot_config" / "plugin_config.py"
    rowkey_config_path = project_dir / "cot_config" / "rowkey_config.py"
    for path in (manifest_path, plugin_config_path, rowkey_config_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest = load_json(manifest_path)
    raw_tables = manifest.get("tables")
    if not isinstance(raw_tables, list):
        raise ValueError("cot_sync_manifest.json tables must be a list")
    tables = [table for table in raw_tables if isinstance(table, Mapping)]
    if len(tables) != len(raw_tables):
        raise ValueError("cot_sync_manifest.json tables contains a non-object item")

    runtime = load_literal_assignment(plugin_config_path, "table_configs")
    rowkey_rules = load_literal_assignment(rowkey_config_path, "hbase_rowkey_rules")
    if not isinstance(runtime, Mapping) or not isinstance(rowkey_rules, Mapping):
        raise ValueError("generated table_configs and hbase_rowkey_rules must be mappings")

    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    deployment_blockers: List[Dict[str, str]] = []
    validate_summary(manifest, tables, errors)
    validate_unique_targets(tables, errors)

    contract = manifest.get("codegen_contract") if isinstance(manifest.get("codegen_contract"), Mapping) else {}
    contract_ready = contract.get("ready_for_codegen") is True
    table_results = [
        validate_table(table, runtime, rowkey_rules, contract_ready, errors, warnings, deployment_blockers)
        for table in tables
    ]

    manifest_names = {clean_text(table.get("mysql_table")) for table in tables}
    runtime_names = {clean_text(name) for name in runtime}
    for name in sorted(manifest_names - runtime_names):
        add_issue(errors, "manifest_only_table", "table exists only in manifest", name)
    for name in sorted(runtime_names - manifest_names):
        add_issue(errors, "runtime_only_table", "table exists only in runtime config", name)

    expected_with = {result["table"] for result in table_results if result["sync_mode"] == "with_period"}
    expected_without = {result["table"] for result in table_results if result["sync_mode"] == "without_period"}
    actual_with = set(load_literal_assignment(plugin_config_path, "with_period_tables"))
    actual_without = set(load_literal_assignment(plugin_config_path, "without_period_tables"))
    if expected_with != actual_with:
        add_issue(errors, "with_period_set_mismatch", f"with_period_tables differs: expected={sorted(expected_with)}, actual={sorted(actual_with)}")
    if expected_without != actual_without:
        add_issue(errors, "without_period_set_mismatch", f"without_period_tables differs: expected={sorted(expected_without)}, actual={sorted(actual_without)}")

    questions = clean_list(manifest.get("questions"))
    for question in questions:
        add_issue(deployment_blockers, "open_question", question)
    if not contract_ready:
        add_issue(warnings, "codegen_contract_blocked", "codegen_contract.ready_for_codegen is not true")

    if contract.get("contract_version", 1) == 1:
        add_issue(deployment_blockers, "legacy_codegen_contract_v1", "strict deployment requires codegen contract v2")
    validation_result = contract.get("validation_result") if isinstance(contract.get("validation_result"), Mapping) else {}
    for item in validation_result.get("errors", []) or []:
        add_issue(errors, f"contract_{item.get('code')}", f"{item.get('path')}: {item.get('message')}")
    for item in validation_result.get("deployment_blockers", []) or []:
        add_issue(deployment_blockers, f"contract_{item.get('code')}", f"{item.get('path')}: {item.get('message')}")
    runtime_contract = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), Mapping) else {}
    for key in ("python_min", "entrypoint", "result_protocol", "environment_connection_matrix", "safe_log_policy"):
        if not runtime_contract.get(key):
            add_issue(deployment_blockers, "runtime_contract_incomplete", f"runtime_contract.{key} is required")
    write_contracts = manifest.get("write_contracts")
    if not isinstance(write_contracts, list) or not write_contracts:
        add_issue(deployment_blockers, "write_contract_undeclared", "strict deployment requires target write and recovery contracts")
    deployment_ready = not errors and not deployment_blockers and contract_ready
    return {
        "project_dir": str(project_dir),
        "status": "failed" if errors else "passed",
        "deployment_status": "ready" if deployment_ready else "review_required",
        "table_count": len(table_results),
        "checked_table_count": len(table_results),
        "with_period_count": len(expected_with),
        "without_period_count": len(expected_without),
        "confirmed_rowkey_count": sum(1 for result in table_results if result["rowkey_confirmed"]),
        "error_count": len(errors),
        "deployment_blocker_count": len(deployment_blockers),
        "warning_count": len(warnings),
        "errors": errors,
        "deployment_blockers": deployment_blockers,
        "warnings": warnings,
        "tables": table_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="Generated COT project directory.")
    parser.add_argument("--json-out", type=Path, help="Optional path for the JSON verification report.")
    parser.add_argument(
        "--strict-deployment",
        action="store_true",
        help="Fail when ERROR or DEPLOYMENT_BLOCKER findings remain; warnings are non-blocking.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_project(args.project_dir.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    if result["status"] != "passed":
        return 1
    if args.strict_deployment and result["deployment_status"] != "ready":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
