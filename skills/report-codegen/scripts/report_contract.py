#!/usr/bin/env python3
"""Validate the normalized, non-executable DSL used by generic report projects."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence, Set


SUPPORTED_SOURCE_KINDS = {"hbase", "fs", "mssql", "mysql", "injected"}
SUPPORTED_STEP_OPS = {
    "select",
    "filter",
    "rename",
    "derive",
    "join",
    "aggregate",
    "union",
    "deduplicate",
    "project",
}
SUPPORTED_FILTER_OPERATORS = {
    "eq",
    "ne",
    "in",
    "not_in",
    "gt",
    "ge",
    "lt",
    "le",
    "isnull",
    "notnull",
    "contains",
}
SUPPORTED_EXPRESSION_OPS = {
    "copy",
    "literal",
    "coalesce",
    "add",
    "subtract",
    "multiply",
    "divide",
    "concat",
}
SUPPORTED_AGGREGATIONS = {"sum", "count", "nunique", "min", "max", "mean", "first", "last"}
SUPPORTED_WRITE_MODES = {"append", "replace_where"}
SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def string_list(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [clean_text(item) for item in value if clean_text(item)]


def add_issue(issues: List[Dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def valid_value_from(value: Any) -> bool:
    text = clean_text(value)
    root, separator, key = text.partition(".")
    return separator == "." and root in {"time_range", "params"} and bool(key)


def validate_expression(expression: Any, path: str, errors: List[Dict[str, str]]) -> None:
    if not isinstance(expression, Mapping):
        add_issue(errors, "invalid_expression", path, "expression must be an object")
        return
    op = clean_text(expression.get("op"))
    if op not in SUPPORTED_EXPRESSION_OPS:
        add_issue(errors, "unsupported_expression", f"{path}.op", f"unsupported expression op: {op!r}")
        return
    if op == "copy" and not clean_text(expression.get("column")):
        add_issue(errors, "missing_expression_column", path, "copy requires column")
    elif op == "coalesce" and not string_list(expression.get("columns")):
        add_issue(errors, "missing_expression_columns", path, "coalesce requires columns")
    elif op in {"add", "subtract", "multiply", "divide"}:
        operands = expression.get("operands")
        if not isinstance(operands, list) or len(operands) < 2:
            add_issue(errors, "missing_expression_operands", path, f"{op} requires at least two operands")
    elif op == "concat":
        operands = expression.get("operands")
        if not isinstance(operands, list) or not operands:
            add_issue(errors, "missing_expression_operands", path, "concat requires operands")
    for index, operand in enumerate(expression.get("operands") or []):
        if not isinstance(operand, Mapping):
            continue
        operand_keys = {key for key in ("column", "value", "value_from") if key in operand}
        if len(operand_keys) != 1:
            add_issue(errors, "invalid_operand", f"{path}.operands[{index}]", "operand needs exactly one of column, value, or value_from")
        if "value_from" in operand and not valid_value_from(operand.get("value_from")):
            add_issue(errors, "invalid_value_from", f"{path}.operands[{index}]", "value_from must use time_range.<key> or params.<key>")
    if "value_from" in expression and not valid_value_from(expression.get("value_from")):
        add_issue(errors, "invalid_value_from", f"{path}.value_from", "value_from must use time_range.<key> or params.<key>")


def validate_step(
    step: Mapping[str, Any],
    index: int,
    available: Set[str],
    errors: List[Dict[str, str]],
) -> str:
    path = f"execution_contract.steps[{index}]"
    step_id = clean_text(step.get("id"))
    op = clean_text(step.get("op"))
    if not step_id:
        add_issue(errors, "missing_step_id", f"{path}.id", "step id is required")
    elif step_id in available:
        add_issue(errors, "duplicate_step_id", f"{path}.id", f"duplicate step/source id: {step_id}")
    if op not in SUPPORTED_STEP_OPS:
        add_issue(errors, "unsupported_step", f"{path}.op", f"unsupported step op: {op!r}")
        return step_id

    if op in {"select", "filter", "rename", "derive", "aggregate", "deduplicate", "project"}:
        input_name = clean_text(step.get("input") or step.get("source"))
        if input_name not in available:
            add_issue(errors, "unknown_step_input", path, f"input/source is not available yet: {input_name!r}")
    if op in {"select", "project"} and not string_list(step.get("columns")):
        add_issue(errors, "missing_step_columns", path, f"{op} requires columns")
    if op == "filter":
        conditions = step.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            add_issue(errors, "missing_filter_conditions", path, "filter requires conditions")
        else:
            for condition_index, condition in enumerate(conditions):
                condition_path = f"{path}.conditions[{condition_index}]"
                if not isinstance(condition, Mapping):
                    add_issue(errors, "invalid_filter_condition", condition_path, "condition must be an object")
                    continue
                if not clean_text(condition.get("column")):
                    add_issue(errors, "missing_filter_column", condition_path, "condition column is required")
                operator = clean_text(condition.get("operator"))
                if operator not in SUPPORTED_FILTER_OPERATORS:
                    add_issue(errors, "unsupported_filter_operator", condition_path, f"unsupported operator: {operator!r}")
                if operator not in {"isnull", "notnull"} and "value" not in condition and not clean_text(condition.get("value_from")):
                    add_issue(errors, "missing_filter_value", condition_path, "condition needs value or value_from")
                if condition.get("value_from") and not valid_value_from(condition.get("value_from")):
                    add_issue(errors, "invalid_value_from", condition_path, "value_from must use time_range.<key> or params.<key>")
    if op == "rename":
        mapping = step.get("columns")
        if not isinstance(mapping, Mapping) or not mapping:
            add_issue(errors, "missing_rename_mapping", path, "rename requires a non-empty columns mapping")
    if op == "derive":
        expressions = step.get("columns")
        if not isinstance(expressions, Mapping) or not expressions:
            add_issue(errors, "missing_derive_expressions", path, "derive requires a non-empty columns mapping")
        else:
            for name, expression in expressions.items():
                if not clean_text(name):
                    add_issue(errors, "missing_derived_column", path, "derived column name is empty")
                validate_expression(expression, f"{path}.columns.{name}", errors)
    if op == "join":
        left = clean_text(step.get("left"))
        right = clean_text(step.get("right"))
        for side, value in (("left", left), ("right", right)):
            if value not in available:
                add_issue(errors, "unknown_join_input", f"{path}.{side}", f"join input is not available yet: {value!r}")
        on = string_list(step.get("on"))
        left_on = string_list(step.get("left_on"))
        right_on = string_list(step.get("right_on"))
        if not on and (not left_on or len(left_on) != len(right_on)):
            add_issue(errors, "invalid_join_keys", path, "join needs on, or equal-length left_on/right_on")
        if clean_text(step.get("how") or "left") not in {"left", "right", "inner", "outer"}:
            add_issue(errors, "invalid_join_type", path, "join how must be left/right/inner/outer")
    if op == "aggregate":
        aggregations = step.get("aggregations")
        if not isinstance(aggregations, Mapping) or not aggregations:
            add_issue(errors, "missing_aggregations", path, "aggregate requires aggregations")
        else:
            for name, aggregation in aggregations.items():
                aggregation_path = f"{path}.aggregations.{name}"
                if not isinstance(aggregation, Mapping):
                    add_issue(errors, "invalid_aggregation", aggregation_path, "aggregation must be an object")
                    continue
                if clean_text(aggregation.get("agg")) not in SUPPORTED_AGGREGATIONS:
                    add_issue(errors, "unsupported_aggregation", aggregation_path, f"unsupported aggregation: {aggregation.get('agg')!r}")
                if clean_text(aggregation.get("agg")) != "count" and not clean_text(aggregation.get("column")):
                    add_issue(errors, "missing_aggregation_column", aggregation_path, "aggregation column is required")
    if op == "union":
        inputs = string_list(step.get("inputs"))
        if len(inputs) < 2:
            add_issue(errors, "missing_union_inputs", path, "union requires at least two inputs")
        for input_name in inputs:
            if input_name not in available:
                add_issue(errors, "unknown_union_input", path, f"union input is not available yet: {input_name!r}")
    if op == "deduplicate" and not string_list(step.get("subset")):
        add_issue(errors, "missing_deduplicate_subset", path, "deduplicate requires subset")
    return step_id


def validate_execution_contract(contract: Any, plan_outputs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if not isinstance(contract, Mapping):
        add_issue(errors, "missing_execution_contract", "execution_contract", "execution_contract must be an object")
        return {"status": "failed", "error_count": len(errors), "warning_count": 0, "errors": errors, "warnings": []}

    if contract.get("version") != 1:
        add_issue(errors, "unsupported_contract_version", "execution_contract.version", "version must be 1")

    sources = contract.get("sources")
    if not isinstance(sources, Mapping) or not sources:
        add_issue(errors, "missing_contract_sources", "execution_contract.sources", "at least one source is required")
        sources = {}
    available: Set[str] = set()
    for source_name, source in sources.items():
        path = f"execution_contract.sources.{source_name}"
        name = clean_text(source_name)
        if not name:
            add_issue(errors, "missing_source_name", path, "source name is empty")
            continue
        if not isinstance(source, Mapping):
            add_issue(errors, "invalid_source", path, "source must be an object")
            continue
        kind = clean_text(source.get("kind"))
        if kind not in SUPPORTED_SOURCE_KINDS:
            add_issue(errors, "unsupported_source_kind", f"{path}.kind", f"unsupported source kind: {kind!r}")
        if kind != "injected" and not clean_text(source.get("location")):
            add_issue(errors, "missing_source_location", f"{path}.location", "non-injected source needs location")
        if not string_list(source.get("columns")):
            add_issue(errors, "missing_source_columns", f"{path}.columns", "source columns are required")
        available.add(name)

    steps = contract.get("steps")
    if not isinstance(steps, list) or not steps:
        add_issue(errors, "missing_contract_steps", "execution_contract.steps", "at least one transformation step is required")
        steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            add_issue(errors, "invalid_step", f"execution_contract.steps[{index}]", "step must be an object")
            continue
        step_id = validate_step(step, index, available, errors)
        if step_id:
            available.add(step_id)

    expected_outputs = {
        clean_text(output.get("target_name") or output.get("physical_table")): string_list(output.get("final_columns"))
        for output in plan_outputs
        if clean_text(output.get("target_name") or output.get("physical_table"))
    }
    contract_outputs = contract.get("outputs")
    if not isinstance(contract_outputs, Mapping):
        add_issue(errors, "missing_contract_outputs", "execution_contract.outputs", "outputs must be an object")
        contract_outputs = {}
    if set(contract_outputs) != set(expected_outputs):
        add_issue(
            errors,
            "output_set_mismatch",
            "execution_contract.outputs",
            f"contract outputs must exactly match plan outputs: expected={sorted(expected_outputs)}, actual={sorted(contract_outputs)}",
        )
    for output_name, output in contract_outputs.items():
        path = f"execution_contract.outputs.{output_name}"
        if not isinstance(output, Mapping):
            add_issue(errors, "invalid_contract_output", path, "output must be an object")
            continue
        input_name = clean_text(output.get("input"))
        if input_name not in available:
            add_issue(errors, "unknown_output_input", f"{path}.input", f"output input is not available: {input_name!r}")
        columns = string_list(output.get("columns"))
        expected_columns = expected_outputs.get(clean_text(output_name), [])
        if columns != expected_columns:
            add_issue(
                errors,
                "output_columns_mismatch",
                f"{path}.columns",
                f"columns must exactly match final_columns: expected={expected_columns}, actual={columns}",
            )

    writes = contract.get("writes")
    if not isinstance(writes, Mapping):
        add_issue(errors, "missing_contract_writes", "execution_contract.writes", "writes must be an object")
        writes = {}
    if set(writes) != set(expected_outputs):
        add_issue(
            errors,
            "write_set_mismatch",
            "execution_contract.writes",
            f"writes must exactly match plan outputs: expected={sorted(expected_outputs)}, actual={sorted(writes)}",
        )
    physical_tables = {
        clean_text(output.get("target_name") or output.get("physical_table")): clean_text(output.get("physical_table"))
        for output in plan_outputs
    }
    for output_name, write in writes.items():
        path = f"execution_contract.writes.{output_name}"
        if not isinstance(write, Mapping):
            add_issue(errors, "invalid_write", path, "write must be an object")
            continue
        if clean_text(write.get("kind") or "clickhouse") != "clickhouse":
            add_issue(errors, "unsupported_write_kind", path, "generic execution contract currently supports ClickHouse writes")
        mode = clean_text(write.get("mode"))
        if mode not in SUPPORTED_WRITE_MODES:
            add_issue(errors, "unsupported_write_mode", path, f"unsupported write mode: {mode!r}")
        write_table = clean_text(write.get("table"))
        if write_table != physical_tables.get(clean_text(output_name), ""):
            add_issue(errors, "write_table_mismatch", path, "write table must exactly match plan physical_table")
        if not SQL_IDENTIFIER_RE.fullmatch(write_table):
            add_issue(errors, "unsafe_write_table", f"{path}.table", "write table must be a safe database.table identifier")
        if mode == "replace_where":
            predicate = write.get("predicate")
            if not isinstance(predicate, Mapping):
                add_issue(errors, "missing_replace_predicate", path, "replace_where requires predicate")
            else:
                predicate_column = clean_text(predicate.get("column"))
                if not predicate_column:
                    add_issue(errors, "missing_predicate_column", path, "replace predicate column is required")
                elif not SQL_IDENTIFIER_RE.fullmatch(predicate_column):
                    add_issue(errors, "unsafe_predicate_column", path, "replace predicate column must be a safe identifier")
                if not clean_text(predicate.get("value_from")):
                    add_issue(errors, "missing_predicate_value", path, "replace predicate value_from is required")
                elif not valid_value_from(predicate.get("value_from")):
                    add_issue(errors, "invalid_value_from", path, "write value_from must use time_range.<key> or params.<key>")

    return {
        "status": "passed" if not errors else "failed",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
