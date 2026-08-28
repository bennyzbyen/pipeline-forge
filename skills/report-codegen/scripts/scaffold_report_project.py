#!/usr/bin/env python3
"""Scaffold a report project from report_codegen_plan.json."""

from __future__ import annotations

import argparse
import json
import pprint
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping

from report_contract import validate_execution_contract
from scaffold_templates.contract import (
    write_contract_data_process,
    write_contract_data_source,
    write_contract_data_storage,
)
from scaffold_templates.generic import (
    write_generic_data_process,
    write_generic_data_source,
    write_generic_data_storage,
)
from scaffold_templates.hbase_prepare import (
    write_hbase_prepare_data_process,
    write_hbase_prepare_data_source,
    write_hbase_prepare_data_storage,
)
from scaffold_templates.source_config import (
    FIXED_PLATFORM_PACKAGE_DIRS,
    SUPERVISOR_HBASE_CANONICAL_NAMES,
    SUPERVISOR_HBASE_FIELD_OVERRIDES,
    SUPERVISOR_HBASE_RANGE_OVERRIDES,
    SUPERVISOR_MSSQL_FIELD_OVERRIDES,
    SUPERVISOR_MSSQL_RANGE_OVERRIDES,
    SUPERVISOR_MSSQL_RENAME_MAP,
    VEHICLE_FS_FIELD_OVERRIDES,
    VEHICLE_HBASE_FIELD_OVERRIDES,
    VEHICLE_HBASE_RANGE_OVERRIDES,
    VEHICLE_RENAME_MAP,
)
from scaffold_templates.supervisor import (
    write_supervisor_portal_data_process,
    write_supervisor_portal_data_source,
    write_supervisor_portal_data_storage,
)
from scaffold_templates.vehicle import vehicle_output_targets, write_vehicle_data_process
from scaffold_templates.vehicle_source import write_vehicle_data_source
from scaffold_templates.vehicle_storage import write_vehicle_data_storage


TABLE_NAME_RE = re.compile(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+|/[^\s,;]+")


def codegen_contract_is_blocked(contract: Mapping[str, Any]) -> bool:
    if not contract:
        return False
    validation = contract.get("validation_result") if isinstance(contract.get("validation_result"), Mapping) else {}
    conflicts = contract.get("conflicts", []) or []
    unresolved_conflicts = not isinstance(conflicts, list) or any(
        not isinstance(item, Mapping)
        or str(item.get("status") or "").strip().lower() != "resolved"
        for item in conflicts
    )
    return bool(
        contract.get("ready_for_codegen") is not True
        or contract.get("blockers")
        or validation.get("status") == "failed"
        or validation.get("errors")
        or unresolved_conflicts
    )


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def clean_target(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)


def copy_minimal_project(target: Path) -> None:
    asset_root = project_root() / "assets" / "minimal_report_project"
    for source in asset_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(asset_root)
        if relative.name.endswith(".template"):
            relative = relative.with_name(relative.name[: -len(".template")])
        destination = target / relative
        if relative.parts and relative.parts[0] in FIXED_PLATFORM_PACKAGE_DIRS and destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def split_fields(fields: List[str]) -> List[str]:
    values: List[str] = []
    for value in fields:
        normalized = str(value or "").replace("->", " ")
        for item in normalized.split():
            item = item.strip()
            if item and item not in values:
                values.append(item)
    return values


def plan_is_vehicle(plan: Dict[str, Any]) -> bool:
    outputs = plan.get("outputs", [])
    output_text = " ".join(
        str(value or "").lower()
        for output in outputs
        for value in [
            output.get("target_name"),
            output.get("physical_table"),
            output.get("target_description"),
        ]
    )
    if "vehicle_verify" in output_text or "车辆核销" in output_text:
        return True

    source_text = json.dumps(plan.get("sources", {}), ensure_ascii=False).lower()
    vehicle_source_markers = [
        "l1_mdp.vehicle_info_p",
        "l0_dtr_order.t5_eo_erp_sales_order_line_p",
        "dms_sellout",
        "dms_soldto_subd_config",
    ]
    return any(marker in source_text for marker in vehicle_source_markers)


def plan_is_supervisor_portal(plan: Dict[str, Any]) -> bool:
    output_names = {
        str(output.get("target_name") or "").lower()
        for output in plan.get("outputs", [])
    }
    required = {
        "supervisor_portal_store",
        "supervisor_portal_store_sales",
        "supervisor_portal_salesman",
    }
    return required.issubset(output_names)


def plan_is_hbase_prepare_pipeline(plan: Dict[str, Any]) -> bool:
    if plan.get("summary", {}).get("component_kind") == "hbase_prepare_pipeline":
        return True
    target_text = json.dumps(plan.get("physical_targets", []) + plan.get("logical_targets", []), ensure_ascii=False).lower()
    schedule_text = json.dumps(plan.get("schedules", []), ensure_ascii=False).lower()
    source_text = json.dumps(plan.get("sources", {}), ensure_ascii=False).lower()
    prepare_markers = ["init_data_source", "period_export_execute", "cal_store_yield_grade"]
    return "hbase" in target_text and (
        any(marker in schedule_text for marker in prepare_markers) or "l0_cmt.sellout" in source_text
    )


def plan_has_specialized_implementation(plan: Dict[str, Any]) -> bool:
    return plan_is_vehicle(plan) or plan_is_supervisor_portal(plan) or plan_is_hbase_prepare_pipeline(plan)


def execution_contract_validation(plan: Dict[str, Any]) -> Dict[str, Any]:
    if plan_has_specialized_implementation(plan):
        return {"status": "specialized", "error_count": 0, "warning_count": 0, "errors": [], "warnings": []}
    return validate_execution_contract(plan.get("execution_contract"), plan.get("outputs", []))


def split_table_names(value: Any) -> List[str]:
    names: List[str] = []
    for part in re.split(r"[\r\n]+", str(value or "")):
        matches = TABLE_NAME_RE.findall(part)
        candidates = matches or [part]
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if normalized and normalized not in names:
                names.append(normalized)
    return names


def canonical_source_name(name: str) -> str:
    if name.startswith("l2_cot_exe_report.rpt_exe_sales_assess_channel_"):
        return "l2_cot_exe_report.rpt_exe_sales_assess_channel"
    return name


def supervisor_canonical_source_name(name: str) -> str:
    return SUPERVISOR_HBASE_CANONICAL_NAMES.get(name, name)


def source_key(source: Dict[str, Any]) -> str:
    names = source.get("table_names") or [source.get("table_or_path", "")]
    for value in names:
        for name in split_table_names(value):
            return canonical_source_name(name)
    return canonical_source_name(str(source.get("table_or_path", "")).strip())


def source_range_config(source: Dict[str, Any]) -> Dict[str, Any]:
    value = str(source.get("range", ""))
    if "Pn-1" in value or "P" in value:
        return {"start_time": "P", "end_time": "P", "row_prefixs": True}
    return {"start_time": None, "end_time": None, "row_prefixs": False}


def fs_source_key(source: Dict[str, Any], index: int) -> str:
    path = str(source.get("table_or_path", "")).lower()
    if "dms_sellout" in path:
        return "dms_order"
    if "dms_soldto_subd_config" in path:
        return "dms_md"
    return f"fs_source_{index + 1}"


def hbase_fields(source: Dict[str, Any], vehicle_plan: bool, supervisor_plan: bool = False) -> List[str]:
    key = source_key(source)
    if vehicle_plan and key in VEHICLE_HBASE_FIELD_OVERRIDES:
        return VEHICLE_HBASE_FIELD_OVERRIDES[key]
    if supervisor_plan:
        key = supervisor_canonical_source_name(key)
        if key in SUPERVISOR_HBASE_FIELD_OVERRIDES:
            return SUPERVISOR_HBASE_FIELD_OVERRIDES[key]
    return split_fields(source.get("fields", []))


def hbase_range(source: Dict[str, Any], vehicle_plan: bool, supervisor_plan: bool = False) -> Dict[str, Any]:
    key = source_key(source)
    if vehicle_plan and key in VEHICLE_HBASE_RANGE_OVERRIDES:
        return VEHICLE_HBASE_RANGE_OVERRIDES[key]
    if supervisor_plan:
        key = supervisor_canonical_source_name(key)
        if key in SUPERVISOR_HBASE_RANGE_OVERRIDES:
            return SUPERVISOR_HBASE_RANGE_OVERRIDES[key]
    return source_range_config(source)


def mssql_fields(source: Dict[str, Any], supervisor_plan: bool = False) -> List[str]:
    key = source_key(source)
    if supervisor_plan and key in SUPERVISOR_MSSQL_FIELD_OVERRIDES:
        return SUPERVISOR_MSSQL_FIELD_OVERRIDES[key]
    return split_fields(source.get("fields", []))


def mssql_range(source: Dict[str, Any], supervisor_plan: bool = False) -> Dict[str, Any]:
    key = source_key(source)
    if supervisor_plan and key in SUPERVISOR_MSSQL_RANGE_OVERRIDES:
        return SUPERVISOR_MSSQL_RANGE_OVERRIDES[key]
    value = str(source.get("range", ""))
    if "当天" in value:
        return {"time_col": "<TIME_COLUMN>", "start_time": "current_date", "end_time": "current_date"}
    if "当P" in value:
        return {"time_col": "<TIME_COLUMN>", "start_time": "p_start_time", "end_time": "p_end_time"}
    return {"time_col": None}


def fs_fields(key: str, source: Dict[str, Any], vehicle_plan: bool) -> List[str]:
    if vehicle_plan and key in VEHICLE_FS_FIELD_OVERRIDES:
        return VEHICLE_FS_FIELD_OVERRIDES[key]
    return split_fields(source.get("fields", []))


def write_col_config(target: Path, plan: Dict[str, Any]) -> None:
    vehicle_plan = plan_is_vehicle(plan)
    supervisor_plan = plan_is_supervisor_portal(plan)
    hbase_prepare_plan = plan_is_hbase_prepare_pipeline(plan)
    hbase_sources = plan["sources"].get("hbase", [])
    mssql_sources = plan["sources"].get("mssql", [])
    fs_sources = plan["sources"].get("fs", [])
    hbase_export_cols = {
        supervisor_canonical_source_name(source_key(item)) if supervisor_plan else source_key(item): hbase_fields(item, vehicle_plan, supervisor_plan)
        for item in hbase_sources
    }
    hbase_export_range = {
        supervisor_canonical_source_name(source_key(item)) if supervisor_plan else source_key(item): hbase_range(item, vehicle_plan, supervisor_plan)
        for item in hbase_sources
    }
    mssql_export_cols = {source_key(item): mssql_fields(item, supervisor_plan) for item in mssql_sources}
    mssql_export_range = {source_key(item): mssql_range(item, supervisor_plan) for item in mssql_sources}
    fs_source_config = {
        fs_source_key(item, index): {
            "path": item.get("table_or_path", ""),
            "description": item.get("description", ""),
            "fields": fs_fields(fs_source_key(item, index), item, vehicle_plan),
            "join_filter": item.get("join_filter", ""),
        }
        for index, item in enumerate(fs_sources)
    }
    target_table_columns = {item["target_name"]: item.get("final_columns", []) for item in plan.get("outputs", [])}
    target_table_map = {
        item["target_name"]: item.get("physical_table") or item["target_name"]
        for item in plan.get("outputs", [])
    }
    field_rules = {item["target_name"]: item.get("field_rules", []) for item in plan.get("outputs", [])}
    source_filters = {
        (supervisor_canonical_source_name(source_key(item)) if supervisor_plan else source_key(item)): item.get("join_filter", "")
        for group in plan.get("sources", {}).values()
        for item in group
    }
    rename_map = VEHICLE_RENAME_MAP if vehicle_plan else {}
    mssql_columns_rename = SUPERVISOR_MSSQL_RENAME_MAP if supervisor_plan else {}
    prepare_source_table = ""
    if hbase_prepare_plan:
        for item in hbase_sources:
            key = source_key(item)
            if "sellout" in key.lower():
                prepare_source_table = key
                break
        if not prepare_source_table and hbase_sources:
            prepare_source_table = source_key(hbase_sources[0])
    prepare_default_cols = hbase_export_cols.get(prepare_source_table, []) if prepare_source_table else []

    content = "\n".join(
        [
            "# coding: utf-8",
            "# Generated from report_codegen_plan.json. Fill project-specific transformations in data_utils/data_process.py.",
            f"hbase_export_cols = {hbase_export_cols!r}",
            "",
            f"hbase_export_range = {hbase_export_range!r}",
            "",
            f"mssql_export_cols = {mssql_export_cols!r}",
            "",
            f"mssql_export_range = {mssql_export_range!r}",
            "",
            f"mssql_columns_rename = {mssql_columns_rename!r}",
            "",
            f"fs_source_config = {fs_source_config!r}",
            "",
            f"target_table_columns = {target_table_columns!r}",
            "",
            f"target_table_map = {target_table_map!r}",
            "",
            f"field_rules = {field_rules!r}",
            "",
            f"source_filters = {source_filters!r}",
            "",
            f"rename_map = {rename_map!r}",
            "",
            f"hbase_prepare_table = {prepare_source_table!r}",
            "",
            f"hbase_prepare_default_export_cols = {prepare_default_cols!r}",
            "",
            "hbase_prepare_subsegment_filter = ['1', '2', '3', '6', '7']",
            "",
        ]
    )
    (target / "params_configs" / "col_config.py").write_text(content, encoding="utf-8")


def write_execution_contract_config(target: Path, plan: Dict[str, Any]) -> None:
    contract_literal = pprint.pformat(plan.get("execution_contract") or {}, width=120, sort_dicts=False)
    content = (
        "# coding: utf-8\n"
        '"""Normalized report execution contract; contains data only, never executable expressions."""\n\n'
        f"execution_contract = {contract_literal}\n"
    )
    (target / "params_configs" / "execution_contract.py").write_text(content, encoding="utf-8")


def infer_rowkey_rule(target_name: str, final_columns: List[str]) -> Dict[str, Any]:
    columns = set(final_columns)
    if "period" in columns and "code" in columns:
        candidates = ["period", "code"]
    elif "period" in columns and "store_code" in columns:
        candidates = ["period", "store_code"]
    elif "P" in columns and "code" in columns:
        candidates = ["P", "code"]
    elif "date" in columns and "code" in columns:
        candidates = ["date", "code"]
    elif "id" in columns:
        candidates = ["id"]
    else:
        candidates = []
    return {
        "target_name": target_name,
        "candidate_columns": candidates,
        "columns": [],
        "separator": "_",
        "prefix": {
            "enabled": False,
            "type": "",
            "source_column": "",
            "mod": 10,
        },
        "date_format": "",
        "example": "",
        "confirmed": False,
        "fill_notes": [
            "Fill columns with the exact DataFrame column names used to build the HBase rowkey, in order.",
            "Set prefix.enabled=true only when deployment requires first-byte/hash prefix; then fill type/source_column/mod.",
            "Set date_format only when a date/period column must be reformatted before joining the rowkey.",
            "Fill example with one real expected rowkey from requirements or deployment logs.",
            "Keep confirmed=false until the rule is verified by requirement docs, production code, or deployment logs.",
        ],
    }


def write_rowkey_config(target: Path, plan: Dict[str, Any]) -> None:
    rules: Dict[str, Any] = {}
    for output in plan.get("outputs", []):
        storage = str(output.get("storage") or "").lower()
        physical_table = str(output.get("physical_table") or output.get("target_name") or "")
        target_name = str(output.get("target_name") or physical_table)
        if "hbase" not in storage and not physical_table.lower().startswith(("l1_", "l2_", "l3_")):
            continue
        rules[physical_table or target_name] = infer_rowkey_rule(target_name, output.get("final_columns", []))

    rules_literal = pprint.pformat(rules, width=120, sort_dicts=False)
    content = f'''# coding: utf-8
"""HBase rowkey rules that must be confirmed before deployment.

How to fill each rule:
- columns: exact output DataFrame columns, in rowkey order.
- separator: string used to join column values, usually "_" or "".
- prefix.enabled: true only if the platform table requires a leading hash/salt prefix.
- prefix.type: supported notes include "mod", "hash_mod", or project-specific text.
- prefix.source_column: column used to calculate the prefix when enabled.
- prefix.mod: modulo bucket count, commonly 10 when row_prefixs are 0-9.
- date_format: fill only when the source date/period must be reformatted before joining.
- example: one real expected rowkey from requirement docs, production code, or deployment logs.
- confirmed: keep false until verified by docs/code/logs.

Do not guess rowkey rules. If this file still has confirmed=false, treat HBase
write behavior as a deployment confirmation item.
"""

hbase_rowkey_rules = {rules_literal}
'''
    (target / "params_configs" / "rowkey_config.py").write_text(content, encoding="utf-8")


def write_db_config(target: Path, plan: Dict[str, Any]) -> None:
    database = "<CLICKHOUSE_DB>"
    for item in plan.get("physical_targets", []):
        if item.get("database"):
            database = item["database"]
            break
    content = f'''# coding: utf-8
import os

env = os.environ.get("running_env") or "uat"

app_key = "<APP_KEY>"
app_secret = "<APP_SECRET>"
fs_root_dir = "/datahub/project_storage/<PROJECT_NAME>"
fs_save_report_dir = "/datahub/project_storage/<PROJECT_NAME>/supervisor_portal"
fs_save_source_dir = "/datahub/project_storage/<PROJECT_NAME>/cmt_sellout"
pipeline_base_url = "<DATAHUB_PIPELINE_BASE_URL>"
pipeline_user_name = "<PIPELINE_USERNAME>"
pipeline_api_key = "<PIPELINE_API_KEY>"
pipeline_process_uids = []

clickhouse_connect_params = {{
    "CLICKHOUSE_HOST": "<CLICKHOUSE_HOST>",
    "CLICKHOUSE_PORT": "8123",
    "CLICKHOUSE_USER": "<CLICKHOUSE_USER>",
    "CLICKHOUSE_PASSWORD": "<CLICKHOUSE_PASSWORD>",
    "CLICKHOUSE_DB": "{database}",
}}
cluster = "" if env in {{"uat", "qa"}} else "ON CLUSTER <CLUSTER_NAME>"

mssql_url = "<MSSQL_SQLALCHEMY_URL>"
mssql_token = "<MSSQL_TOKEN>"
'''
    (target / "params_configs" / "db_config.py").write_text(content, encoding="utf-8")


def write_data_process(target: Path, plan: Dict[str, Any]) -> None:
    if plan_is_vehicle(plan):
        write_vehicle_data_process(target, plan)
        return
    if plan_is_supervisor_portal(plan):
        write_supervisor_portal_data_process(target)
        return
    if plan_is_hbase_prepare_pipeline(plan):
        write_hbase_prepare_data_process(target)
        return
    if execution_contract_validation(plan).get("status") == "passed":
        write_contract_data_process(target)
        return

    outputs = [item["target_name"] for item in plan.get("outputs", [])]
    write_generic_data_process(target, outputs)


def write_data_source(target: Path, plan: Dict[str, Any]) -> None:
    if plan_is_vehicle(plan):
        write_vehicle_data_source(target)
        return
    if plan_is_supervisor_portal(plan):
        write_supervisor_portal_data_source(target)
        return
    if plan_is_hbase_prepare_pipeline(plan):
        write_hbase_prepare_data_source(target)
        return
    if execution_contract_validation(plan).get("status") == "passed":
        write_contract_data_source(target)
        return

    write_generic_data_source(target)


def write_data_storage(target: Path, plan: Dict[str, Any]) -> None:
    if plan_is_vehicle(plan):
        write_vehicle_data_storage(target)
        return
    if plan_is_supervisor_portal(plan):
        write_supervisor_portal_data_storage(target)
        return
    if plan_is_hbase_prepare_pipeline(plan):
        write_hbase_prepare_data_storage(target)
        return
    if execution_contract_validation(plan).get("status") == "passed":
        write_contract_data_storage(target)
        return

    write_generic_data_storage(target)


def write_implementation_status(
    target: Path,
    plan: Dict[str, Any],
    safe_scaffold: bool = False,
) -> None:
    vehicle_plan = plan_is_vehicle(plan)
    supervisor_plan = plan_is_supervisor_portal(plan)
    hbase_prepare_plan = plan_is_hbase_prepare_pipeline(plan)
    contract_plan = execution_contract_validation(plan).get("status") == "passed"
    if vehicle_plan:
        source_item = "- [x] Vehicle DataSource implements calendar period derivation, HBase range reads, and FS period-path reads; fill gateway credentials or inject clients before deployment."
        process_item = "- [x] Vehicle DataProcess implements EO/DMS detail, store joins, vehicle/customer mapping, KPI fields, and summaries."
        storage_item = "- [x] Vehicle DataStorage implements replace-period ClickHouse delete and DataFrame insert pattern."
        filter_item = "- [ ] Implement all source filters and joins from `source_filters`."
        columns_item = "- [x] Each output is reindexed to `target_table_columns` final column order."
    elif supervisor_plan:
        source_item = "- [x] Supervisor Portal DataSource implements HBase range reads, MSSQL table reads, source filters, and injected-client test paths."
        process_item = "- [x] Supervisor Portal DataProcess implements store, store-sales, salesman, geo, salesman-sales, geo-sales, and user-information output frames."
        storage_item = "- [x] Supervisor Portal DataStorage implements batch_id status lifecycle and ClickHouse DataFrame insert pattern."
        filter_item = "- [x] Main Supervisor Portal source filters are implemented; verify runtime table names and date windows from deployment logs."
        columns_item = "- [x] Each output is reindexed to `target_table_columns` final column order."
    elif hbase_prepare_plan:
        source_item = "- [x] HBase prepare DataSource exports selected HBase periods to compressed FS CSV files; fill gateway credentials or inject clients before deployment."
        process_item = "- [x] DataProcess optionally activates downstream DataHub pipeline process UIDs when `is_run_pipeline` is true."
        storage_item = "- [x] DataStorage is intentionally no-op because this component prepares FS source files and triggers downstream pipeline rather than writing ClickHouse."
        filter_item = "- [x] HBase prepare source filter keeps configured SubSegmentID values and aggregates SelloutAmount by StoreID when those fields exist."
        columns_item = "- [x] Final source export columns are controlled by `hbase_prepare_default_export_cols` and runtime `hbase_export_cols` params."
    elif contract_plan:
        source_item = "- [x] DataSource implements normalized HBase/FS adapters, explicit MSSQL/MySQL reader injection, and fixture injection."
        process_item = "- [x] DataProcess executes the validated non-eval transformation DSL in `params_configs/execution_contract.py`."
        storage_item = "- [x] DataStorage implements explicit ClickHouse append/replace_where writes and skips destructive replacement for empty outputs."
        filter_item = "- [x] Filters, joins, derivations, aggregations, deduplication, and projections are defined by the normalized execution contract."
        columns_item = "- [x] Contract outputs must exactly match every `target_table_columns` final column list."
    else:
        source_item = "- [ ] Implement real HBase/FS/DataEngine source reads in `data_utils/data_source.py`."
        process_item = "- [ ] Implement field rules from `field_rules` for every target output."
        storage_item = "- [ ] Implement target-period delete and ClickHouse insert for every target table."
        filter_item = "- [ ] Implement all source filters and joins from `source_filters`."
        columns_item = "- [ ] Preserve each `target_table_columns` list as final output column order."
    extra_items = []
    if supervisor_plan:
        extra_items.append(
            "- [ ] Supervisor Portal `sv_store_display_rack` is a separate project path when the document includes it; generate or review that project separately."
        )
    lines = [
        "# Implementation Status",
        "",
        *(
            [
                "**SAFE_SCAFFOLD: runtime is disabled. Resolve contract blockers and regenerate without `--allow-blocked-scaffold`.**",
                "",
            ]
            if safe_scaffold
            else []
        ),
        "This project was generated as a structured scaffold from `report_codegen_plan.json`.",
        "It is not production-equivalent until the unchecked items below are implemented and log-validated.",
        "",
        "## Planned Outputs",
        "",
    ]
    for output in plan.get("outputs", []):
        lines.append(
            f"- `{output.get('target_name', '')}` -> `{output.get('physical_table', '')}` "
            f"({len(output.get('final_columns', []))} columns)"
        )
    lines.extend(
        [
            "",
            "## Required Before Deployment",
            "",
            source_item,
            filter_item,
            process_item,
            columns_item,
            storage_item,
            *extra_items,
            "- [ ] Validate deployed logs: source row counts, filtered row counts, output row counts, delete target/predicate summary, insert target, and final metrics.",
            "",
        ]
    )
    (target / "IMPLEMENTATION_STATUS.md").write_text("\n".join(lines), encoding="utf-8")


def write_safe_scaffold_marker(target: Path) -> None:
    marker = {
        "status": "SAFE_SCAFFOLD",
        "runtime_enabled": False,
        "reason": "Explicit review-only scaffold generated from a blocked or invalid contract.",
    }
    (target / "SAFE_SCAFFOLD.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_params_example(target: Path, plan: Dict[str, Any]) -> None:
    if plan_is_hbase_prepare_pipeline(plan):
        params = {
            "current_date": "",
            "period": "",
            "running_env": "uat",
            "receiver_emails": [],
            "export_mode": "daily",
            "specific_range": None,
            "is_run_pipeline": False,
            "hbase_export_cols": ["StoreID", "SubSegmentID", "SelloutAmount"],
            "skip_fs_upload": False,
        }
    elif execution_contract_validation(plan).get("status") == "passed":
        params = {
            "current_date": "",
            "period": "",
            "time_range": {},
            "source_data": {
                name: f"<inject pandas.DataFrame with columns: {', '.join(config.get('columns') or [])}>"
                for name, config in (plan.get("execution_contract", {}).get("sources") or {}).items()
            },
            "clickhouse_client": "<inject client object at runtime; not JSON-serializable>",
        }
    else:
        return
    (target / "params.example.json").write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_code_unit_snapshot(target: Path, plan: Dict[str, Any]) -> None:
    unit = plan.get("code_unit_contract")
    if not isinstance(unit, dict) or not unit:
        return
    snapshot = {
        "snapshot_mode": "read_only",
        "code_unit_id": unit.get("code_unit_id", ""),
        "contract": unit,
    }
    (target / "CODE_UNIT_CONTRACT.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_code_unit_test(target: Path, plan: Dict[str, Any]) -> None:
    unit = plan.get("code_unit_contract")
    if not isinstance(unit, dict) or not unit:
        return
    tests_dir = target / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    expected_id = json.dumps(str(unit.get("code_unit_id", "")))
    expected_ready = unit.get("readiness", {}).get("ready_for_codegen") is True
    readiness_assertion = "is True" if expected_ready else "is False"
    safety_assertions = (
        "    assert not (root / \"SAFE_SCAFFOLD.json\").exists()\n"
        if expected_ready
        else """    safe = json.loads((root / \"SAFE_SCAFFOLD.json\").read_text(encoding=\"utf-8\"))
    assert safe[\"status\"] == \"SAFE_SCAFFOLD\"
    assert safe[\"runtime_enabled\"] is False
"""
    )
    content = f'''import json
from pathlib import Path


def test_confirmed_code_unit_snapshot_and_entrypoint():
    root = Path(__file__).resolve().parents[1]
    snapshot = json.loads((root / "CODE_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
    assert snapshot["snapshot_mode"] == "read_only"
    assert snapshot["code_unit_id"] == {expected_id}
    assert snapshot["contract"]["status"] == "confirmed"
    assert snapshot["contract"]["readiness"]["ready_for_codegen"] {readiness_assertion}
{safety_assertions.rstrip()}
    assert (root / "plugin_main.py").exists()
    assert (root / "params_configs" / "execution_contract.py").exists()
'''
    (tests_dir / "test_code_unit_contract.py").write_text(content, encoding="utf-8")


def scaffold(plan_path: Path, target: Path, allow_blocked_scaffold: bool = False) -> None:
    plan = load_json(plan_path)
    codegen_contract = plan.get("codegen_contract", {})
    if codegen_contract and codegen_contract.get("project_type") != "report":
        raise ValueError(
            "codegen_contract routes this design package to data-sync-codegen, not report-codegen."
        )
    contract_blocked = codegen_contract_is_blocked(codegen_contract)
    if contract_blocked and not allow_blocked_scaffold:
        blockers = "; ".join(str(item) for item in codegen_contract.get("blockers", [])) or "unresolved design blockers"
        raise ValueError(
            "codegen_contract blocks full scaffolding: "
            f"{blockers}. Re-run with --allow-blocked-scaffold only for an explicitly requested safe scaffold."
        )
    execution_validation = execution_contract_validation(plan)
    if execution_validation.get("status") == "failed" and not allow_blocked_scaffold:
        details = "; ".join(
            f"{item.get('path')}: {item.get('message')}"
            for item in execution_validation.get("errors", [])[:8]
        )
        raise ValueError(
            "generic report full scaffolding requires a valid normalized execution_contract: "
            f"{details}. Re-run with --allow-blocked-scaffold only for a non-runnable review scaffold."
        )
    safe_scaffold = bool(
        allow_blocked_scaffold
        and (
            contract_blocked
            or execution_validation.get("status") == "failed"
        )
    )
    clean_target(target)
    if safe_scaffold:
        write_safe_scaffold_marker(target)
    copy_minimal_project(target)
    write_col_config(target, plan)
    write_execution_contract_config(target, plan)
    write_rowkey_config(target, plan)
    write_db_config(target, plan)
    write_data_source(target, plan)
    write_data_process(target, plan)
    write_data_storage(target, plan)
    write_implementation_status(target, plan, safe_scaffold=safe_scaffold)
    write_params_example(target, plan)
    write_code_unit_snapshot(target, plan)
    write_code_unit_test(target, plan)
    (target / "report_codegen_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a report project from report_codegen_plan.json.")
    parser.add_argument("--plan", required=True, help="Path to report_codegen_plan.json.")
    parser.add_argument("--target", required=True, help="Target project directory.")
    parser.add_argument(
        "--allow-blocked-scaffold",
        action="store_true",
        help="Generate a safe placeholder scaffold even when codegen_contract is blocked.",
    )
    args = parser.parse_args()
    scaffold(
        Path(args.plan).expanduser().resolve(),
        Path(args.target).expanduser().resolve(),
        allow_blocked_scaffold=args.allow_blocked_scaffold,
    )
    print(f"project: {Path(args.target).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
