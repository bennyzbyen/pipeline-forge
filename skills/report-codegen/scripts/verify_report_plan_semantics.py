#!/usr/bin/env python3
"""Validate every report output and the generated implementation contract."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from report_contract import validate_execution_contract


SUPPORTED_COMPONENT_KINDS = {"standard_report", "bysku_report_pipeline", "hbase_prepare_pipeline"}


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_list(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [clean_text(item) for item in value if clean_text(item)]


def add_issue(issues: List[Dict[str, str]], code: str, message: str, output: str = "") -> None:
    issue = {"code": code, "message": message}
    if output:
        issue["output"] = output
    issues.append(issue)


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            if node.value is None:
                break
            return ast.literal_eval(node.value)
    raise ValueError(f"literal assignment {name!r} not found in {path}")


def duplicates(values: Sequence[str]) -> List[str]:
    counts = Counter(value for value in values if value)
    return sorted(value for value, count in counts.items() if count > 1)


def is_specialized(plan: Mapping[str, Any]) -> bool:
    component_kind = clean_text((plan.get("summary") or {}).get("component_kind"))
    if component_kind == "hbase_prepare_pipeline":
        return True
    outputs = plan.get("outputs") if isinstance(plan.get("outputs"), list) else []
    output_text = " ".join(
        clean_text(value).lower()
        for output in outputs
        if isinstance(output, Mapping)
        for value in [output.get("target_name"), output.get("physical_table"), output.get("target_description")]
    )
    if "vehicle_verify" in output_text or "车辆核销" in output_text:
        return True
    output_names = {clean_text(output.get("target_name")).lower() for output in outputs if isinstance(output, Mapping)}
    return {
        "supervisor_portal_store",
        "supervisor_portal_store_sales",
        "supervisor_portal_salesman",
    }.issubset(output_names)


def validate_output(
    output: Mapping[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
) -> Dict[str, Any]:
    name = clean_text(output.get("target_name") or output.get("physical_table")) or "<missing>"
    error_before = len(errors)
    warning_before = len(warnings)
    target_name = clean_text(output.get("target_name"))
    physical_table = clean_text(output.get("physical_table"))
    storage = clean_text(output.get("storage"))
    if not target_name:
        add_issue(errors, "missing_target_name", "target_name is required", name)
    if not physical_table:
        add_issue(errors, "missing_physical_table", "physical_table is required", name)
    if not storage:
        add_issue(errors, "missing_target_storage", "storage is required", name)

    final_columns = clean_list(output.get("final_columns"))
    field_rules = output.get("field_rules") if isinstance(output.get("field_rules"), list) else []
    rule_columns = [clean_text(rule.get("target_field")) for rule in field_rules if isinstance(rule, Mapping)]
    if not final_columns:
        add_issue(errors, "missing_final_columns", "final_columns is empty", name)
    for column in duplicates(final_columns):
        add_issue(errors, "duplicate_final_column", f"final column is duplicated: {column}", name)
    for column in duplicates(rule_columns):
        add_issue(errors, "duplicate_field_rule", f"field rule target is duplicated: {column}", name)
    if output.get("field_count") != len(field_rules):
        add_issue(
            errors,
            "field_count_mismatch",
            f"field_count={output.get('field_count')!r}, actual rules={len(field_rules)}",
            name,
        )
    if rule_columns != final_columns:
        add_issue(
            errors,
            "field_rule_coverage_mismatch",
            "field rule target fields must exactly match final_columns in order",
            name,
        )
    for index, rule in enumerate(field_rules):
        if not isinstance(rule, Mapping):
            add_issue(errors, "invalid_field_rule", f"field_rules[{index}] is not an object", name)
            continue
        if not clean_text(rule.get("target_field")):
            add_issue(errors, "missing_rule_target", f"field_rules[{index}] has no target_field", name)
        logic_values = [
            rule.get("source_field"),
            rule.get("calculation_logic"),
            rule.get("eo_order_logic"),
            rule.get("dms_order_logic"),
        ]
        if not any(clean_text(value) for value in logic_values):
            add_issue(warnings, "empty_field_logic", f"field_rules[{index}] has no source or calculation logic", name)
    return {
        "output": name,
        "physical_table": physical_table,
        "final_column_count": len(final_columns),
        "field_rule_count": len(field_rules),
        "error_count": len(errors) - error_before,
        "warning_count": len(warnings) - warning_before,
    }


def validate_generated_files(
    project_dir: Path,
    plan: Mapping[str, Any],
    implementation_ready: bool,
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
) -> None:
    required = [
        project_dir / "data_utils" / "data_source.py",
        project_dir / "data_utils" / "data_process.py",
        project_dir / "data_utils" / "data_storage.py",
        project_dir / "params_configs" / "col_config.py",
        project_dir / "params_configs" / "execution_contract.py",
        project_dir / "IMPLEMENTATION_STATUS.md",
    ]
    for path in required:
        if not path.is_file():
            add_issue(errors, "missing_generated_file", f"required generated file is absent: {path.name}")
    if any(not path.is_file() for path in required):
        return

    implementation_text = "\n".join(
        (project_dir / "data_utils" / name).read_text(encoding="utf-8")
        for name in ["data_source.py", "data_process.py", "data_storage.py"]
    )
    placeholder_markers = ["NotImplementedError", "Placeholder source contract", "Placeholder transformation contract", "Placeholder storage contract"]
    markers_found = [marker for marker in placeholder_markers if marker in implementation_text]
    if implementation_ready and markers_found:
        add_issue(errors, "placeholder_in_ready_project", f"ready implementation contains placeholders: {markers_found}")
    elif markers_found:
        add_issue(warnings, "review_scaffold_only", f"generated project remains non-runnable: {markers_found}")

    expected_columns = {
        clean_text(output.get("target_name")): clean_list(output.get("final_columns"))
        for output in plan.get("outputs", [])
        if isinstance(output, Mapping)
    }
    expected_tables = {
        clean_text(output.get("target_name")): clean_text(output.get("physical_table")) or clean_text(output.get("target_name"))
        for output in plan.get("outputs", [])
        if isinstance(output, Mapping)
    }
    col_config = project_dir / "params_configs" / "col_config.py"
    if load_literal_assignment(col_config, "target_table_columns") != expected_columns:
        add_issue(errors, "generated_column_mismatch", "target_table_columns differs from report plan")
    if load_literal_assignment(col_config, "target_table_map") != expected_tables:
        add_issue(errors, "generated_target_mismatch", "target_table_map differs from report plan")
    generated_contract = load_literal_assignment(
        project_dir / "params_configs" / "execution_contract.py",
        "execution_contract",
    )
    if generated_contract != (plan.get("execution_contract") or {}):
        add_issue(errors, "generated_contract_mismatch", "generated execution_contract differs from report plan")


def validate_project(project_dir: Path) -> Dict[str, Any]:
    plan_path = project_dir / "report_codegen_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(plan_path)
    plan = load_json(plan_path)
    raw_outputs = plan.get("outputs")
    if not isinstance(raw_outputs, list):
        raise ValueError("report_codegen_plan.json outputs must be a list")
    if any(not isinstance(output, Mapping) for output in raw_outputs):
        raise ValueError("report_codegen_plan.json outputs contains a non-object item")
    outputs = list(raw_outputs)

    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    component_kind = clean_text((plan.get("summary") or {}).get("component_kind"))
    specialized = is_specialized(plan)
    if not component_kind and specialized:
        component_kind = "standard_report"
        add_issue(warnings, "component_kind_inferred", "legacy specialized plan omitted component_kind; inferred standard_report")
    if component_kind not in SUPPORTED_COMPONENT_KINDS:
        add_issue(errors, "unsupported_component_kind", f"unsupported component kind: {component_kind!r}")
    names = [clean_text(output.get("target_name")) for output in outputs]
    tables = [clean_text(output.get("physical_table")) for output in outputs]
    for name in duplicates(names):
        add_issue(errors, "duplicate_output_name", f"target_name is duplicated: {name}")
    for table in duplicates(tables):
        add_issue(warnings, "shared_physical_table", f"multiple logical outputs share physical table: {table}")

    output_results = [validate_output(output, errors, warnings) for output in outputs]
    summary = plan.get("summary") if isinstance(plan.get("summary"), Mapping) else {}
    if summary.get("output_count") != len(outputs):
        add_issue(errors, "summary_output_mismatch", f"summary.output_count={summary.get('output_count')!r}, actual={len(outputs)}")
    source_count = sum(len(items) for items in (plan.get("sources") or {}).values() if isinstance(items, list))
    if summary.get("source_count") != source_count:
        add_issue(errors, "summary_source_mismatch", f"summary.source_count={summary.get('source_count')!r}, actual={source_count}")

    execution_validation = (
        {"status": "specialized", "error_count": 0, "warning_count": 0, "errors": [], "warnings": []}
        if specialized
        else validate_execution_contract(plan.get("execution_contract"), outputs)
    )
    for issue in execution_validation.get("errors", []):
        add_issue(errors, f"execution_{issue.get('code')}", f"{issue.get('path')}: {issue.get('message')}")
    implementation_ready = specialized or execution_validation.get("status") == "passed"
    validate_generated_files(project_dir, plan, implementation_ready, errors, warnings)

    codegen_contract = plan.get("codegen_contract") if isinstance(plan.get("codegen_contract"), Mapping) else {}
    design_ready = codegen_contract.get("ready_for_codegen") is True
    if not design_ready:
        add_issue(warnings, "codegen_contract_blocked", "codegen_contract.ready_for_codegen is not true")
    deployment_ready = not errors and not warnings and design_ready and implementation_ready
    return {
        "project_dir": str(project_dir),
        "status": "passed" if not errors else "failed",
        "deployment_status": "ready" if deployment_ready else "review_required",
        "component_kind": component_kind,
        "specialized_implementation": specialized,
        "implementation_ready": implementation_ready,
        "output_count": len(outputs),
        "checked_output_count": len(output_results),
        "final_column_count": sum(item["final_column_count"] for item in output_results),
        "field_rule_count": sum(item["field_rule_count"] for item in output_results),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "execution_validation": execution_validation,
        "outputs": output_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="Generated report project directory.")
    parser.add_argument("--json-out", type=Path, help="Optional path for the JSON verification report.")
    parser.add_argument("--strict-deployment", action="store_true", help="Fail when warnings or deployment confirmations remain.")
    args = parser.parse_args()
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
