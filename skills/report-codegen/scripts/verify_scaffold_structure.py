#!/usr/bin/env python3
"""Verify scaffold entrypoint size, import compatibility, and template routing."""

from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict


SCRIPT_DIR = Path(__file__).resolve().parent
ENTRYPOINT = SCRIPT_DIR / "scaffold_report_project.py"
TEMPLATE_DIR = SCRIPT_DIR / "scaffold_templates"
ENTRYPOINT_LINE_LIMIT = 800
TEMPLATE_MODULE_LINE_LIMIT = 800

PUBLIC_FUNCTIONS = [
    "codegen_contract_is_blocked",
    "load_json",
    "project_root",
    "clean_target",
    "copy_minimal_project",
    "split_fields",
    "plan_is_vehicle",
    "plan_is_supervisor_portal",
    "plan_is_hbase_prepare_pipeline",
    "plan_has_specialized_implementation",
    "execution_contract_validation",
    "split_table_names",
    "canonical_source_name",
    "supervisor_canonical_source_name",
    "source_key",
    "source_range_config",
    "fs_source_key",
    "hbase_fields",
    "hbase_range",
    "mssql_fields",
    "mssql_range",
    "fs_fields",
    "write_col_config",
    "write_execution_contract_config",
    "infer_rowkey_rule",
    "write_rowkey_config",
    "write_db_config",
    "vehicle_output_targets",
    "write_vehicle_data_process",
    "write_supervisor_portal_data_process",
    "write_hbase_prepare_data_process",
    "write_contract_data_process",
    "write_data_process",
    "write_vehicle_data_source",
    "write_supervisor_portal_data_source",
    "write_hbase_prepare_data_source",
    "write_contract_data_source",
    "write_data_source",
    "write_supervisor_portal_data_storage",
    "write_hbase_prepare_data_storage",
    "write_contract_data_storage",
    "write_data_storage",
    "write_vehicle_data_storage",
    "write_implementation_status",
    "write_safe_scaffold_marker",
    "write_params_example",
    "scaffold",
    "main",
]

MOVED_FUNCTION_MODULES = {
    "vehicle_output_targets": "scaffold_templates.vehicle",
    "write_vehicle_data_process": "scaffold_templates.vehicle",
    "write_vehicle_data_source": "scaffold_templates.vehicle_source",
    "write_vehicle_data_storage": "scaffold_templates.vehicle_storage",
    "write_supervisor_portal_data_process": "scaffold_templates.supervisor",
    "write_supervisor_portal_data_source": "scaffold_templates.supervisor",
    "write_supervisor_portal_data_storage": "scaffold_templates.supervisor",
    "write_hbase_prepare_data_process": "scaffold_templates.hbase_prepare",
    "write_hbase_prepare_data_source": "scaffold_templates.hbase_prepare",
    "write_hbase_prepare_data_storage": "scaffold_templates.hbase_prepare",
    "write_contract_data_process": "scaffold_templates.contract",
    "write_contract_data_source": "scaffold_templates.contract",
    "write_contract_data_storage": "scaffold_templates.contract",
}

EXPECTED_PARAMETERS = {
    "vehicle_output_targets": ["plan"],
    "write_vehicle_data_process": ["target", "plan"],
    "write_vehicle_data_source": ["target"],
    "write_vehicle_data_storage": ["target"],
    "write_supervisor_portal_data_process": ["target"],
    "write_supervisor_portal_data_source": ["target"],
    "write_supervisor_portal_data_storage": ["target"],
    "write_hbase_prepare_data_process": ["target"],
    "write_hbase_prepare_data_source": ["target"],
    "write_hbase_prepare_data_storage": ["target"],
    "write_contract_data_process": ["target"],
    "write_contract_data_source": ["target"],
    "write_contract_data_storage": ["target"],
    "scaffold": ["plan_path", "target", "allow_blocked_scaffold"],
}

PUBLIC_CONSTANTS = [
    "VEHICLE_HBASE_FIELD_OVERRIDES",
    "VEHICLE_HBASE_RANGE_OVERRIDES",
    "VEHICLE_RENAME_MAP",
    "VEHICLE_FS_FIELD_OVERRIDES",
    "SUPERVISOR_HBASE_CANONICAL_NAMES",
    "SUPERVISOR_HBASE_FIELD_OVERRIDES",
    "SUPERVISOR_HBASE_RANGE_OVERRIDES",
    "SUPERVISOR_MSSQL_FIELD_OVERRIDES",
    "SUPERVISOR_MSSQL_RANGE_OVERRIDES",
    "SUPERVISOR_MSSQL_RENAME_MAP",
    "FIXED_PLATFORM_PACKAGE_DIRS",
]


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def longest_multiline_literal(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lengths = [
        node.end_lineno - node.lineno + 1
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.end_lineno is not None
    ]
    return max(lengths, default=0)


def verify_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--help"],
        cwd=SCRIPT_DIR,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    for option in ["--plan", "--target", "--allow-blocked-scaffold"]:
        if option not in result.stdout:
            raise AssertionError(f"CLI help lost option: {option}")


def verify_generic_dispatch(scaffold_module: object) -> None:
    with tempfile.TemporaryDirectory(prefix="report_scaffold_structure_") as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "data_utils").mkdir()
        scaffold_module.write_data_process(
            project_dir,
            {"outputs": [{"target_name": "compat_output"}]},
        )
        content = (project_dir / "data_utils" / "data_process.py").read_text(encoding="utf-8")
        if "for target_name in ['compat_output']:" not in content:
            raise AssertionError("generic process dispatch lost planned output names")


def main() -> int:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import scaffold_report_project as scaffold_module

    entrypoint_lines = line_count(ENTRYPOINT)
    if entrypoint_lines > ENTRYPOINT_LINE_LIMIT:
        raise AssertionError(
            f"entrypoint has {entrypoint_lines} lines; limit is {ENTRYPOINT_LINE_LIMIT}"
        )
    if longest_multiline_literal(ENTRYPOINT) > 40:
        raise AssertionError("entrypoint contains a large embedded template literal")

    missing_functions = [
        name for name in PUBLIC_FUNCTIONS if not callable(getattr(scaffold_module, name, None))
    ]
    if missing_functions:
        raise AssertionError(f"public functions are no longer importable: {missing_functions}")

    missing_constants = [name for name in PUBLIC_CONSTANTS if not hasattr(scaffold_module, name)]
    if missing_constants:
        raise AssertionError(f"public constants are no longer importable: {missing_constants}")

    for name, expected_module in MOVED_FUNCTION_MODULES.items():
        actual_module = getattr(scaffold_module, name).__module__
        if actual_module != expected_module:
            raise AssertionError(f"{name} is defined in {actual_module}, expected {expected_module}")

    for name, expected_parameters in EXPECTED_PARAMETERS.items():
        actual_parameters = list(inspect.signature(getattr(scaffold_module, name)).parameters)
        if actual_parameters != expected_parameters:
            raise AssertionError(
                f"{name} parameters changed: {actual_parameters}, expected {expected_parameters}"
            )

    template_lines: Dict[str, int] = {}
    for path in sorted(TEMPLATE_DIR.glob("*.py")):
        count = line_count(path)
        template_lines[path.name] = count
        if count > TEMPLATE_MODULE_LINE_LIMIT:
            raise AssertionError(
                f"template module {path.name} has {count} lines; limit is {TEMPLATE_MODULE_LINE_LIMIT}"
            )

    verify_generic_dispatch(scaffold_module)
    verify_cli_help()
    result: Dict[str, object] = {
        "status": "passed",
        "entrypoint_lines": entrypoint_lines,
        "entrypoint_line_limit": ENTRYPOINT_LINE_LIMIT,
        "public_function_count": len(PUBLIC_FUNCTIONS),
        "public_constant_count": len(PUBLIC_CONSTANTS),
        "template_module_lines": template_lines,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
