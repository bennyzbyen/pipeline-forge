#!/usr/bin/env python3
"""Scaffold a report project from report_codegen_plan.json."""

from __future__ import annotations

import argparse
import json
import pprint
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from report_contract import validate_execution_contract


TABLE_NAME_RE = re.compile(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+|/[^\s,;]+")

VEHICLE_HBASE_FIELD_OVERRIDES = {
    "l0_mdp.mars_calendar": ["dataid", "m_year", "m_period"],
    "l0_dtr_order.t5_eo_erp_sales_order_line_p": [
        "mars_order_header_no",
        "order_created_at",
        "first_complete_time",
        "order_status",
        "order_source",
        "sold_to_code",
        "sold_to_name",
        "mars_store_code",
        "bmp_eo_order_category",
        "original_amount",
        "pt_sum",
        "coupon_amt",
        "mars_sku_no",
        "bmp_mars_sku_no",
    ],
    "l0_store_center.store_details_p": [
        "mars_region_name",
        "mars_province_name",
        "mars_city_cluster_name",
        "mars_city_name",
        "region_name",
        "region_category",
        "digital_district",
        "code",
        "store_name",
        "channel_name",
        "channel_level2_name",
        "store_channel_name",
        "rtm_channel_name",
        "digital",
        "store_manager_code",
        "store_manager_name",
    ],
    "l2_cot_exe_report.rpt_exe_sales_assess_channel": [
        "salesman_code",
        "salesman_type",
        "sale_role",
        "mars_region_name",
        "mars_province_name",
        "mars_city_cluster_name",
        "mars_city_name",
    ],
    "l1_mdp.vehicle_info_p": [
        "CustomerNo",
        "PlateNo",
        "PersonalNo",
        "SalesmanNo",
        "SalesmanNo2",
        "VehicleStatus",
        "DataType",
        "ModifyDate",
        "CreateDate",
        "PINNo",
    ],
    "l0_customer_center.locust_customer_md": [
        "customer_type_code",
        "mars_geo_region_name",
        "mars_geo_province_name",
        "mars_geo_city_clusters_name",
        "mars_geo_city_name",
        "division",
        "code",
        "name",
    ],
    "l0_product_center.locust_product_md": ["prod_code", "subsegment"],
}

VEHICLE_HBASE_RANGE_OVERRIDES = {
    "l0_mdp.mars_calendar": {"start_time": None, "end_time": None, "row_prefixs": False, "is_row_prefixs": None},
    "l0_dtr_order.t5_eo_erp_sales_order_line_p": {
        "start_time": "P",
        "end_time": "P",
        "row_prefixs": True,
        "is_row_prefixs": "YES",
    },
    "l0_store_center.store_details_p": {
        "start_time": "period",
        "end_time": "period",
        "row_prefixs": False,
        "is_row_prefixs": None,
    },
    "l2_cot_exe_report.rpt_exe_sales_assess_channel": {
        "start_time": "P",
        "end_time": "P",
        "row_prefixs": True,
        "is_row_prefixs": "YES",
    },
    "l1_mdp.vehicle_info_p": {
        "start_time": "period",
        "end_time": "period",
        "row_prefixs": True,
        "is_row_prefixs": "YES",
    },
    "l0_customer_center.locust_customer_md": {
        "start_time": None,
        "end_time": None,
        "row_prefixs": False,
        "is_row_prefixs": None,
    },
    "l0_product_center.locust_product_md": {
        "start_time": None,
        "end_time": None,
        "row_prefixs": False,
        "is_row_prefixs": None,
    },
}

VEHICLE_RENAME_MAP = {
    "l0_customer_center.locust_customer_md": {"code": "customer_code"},
    "l2_cot_exe_report.rpt_exe_sales_assess_channel": {"salesman_code": "store_manager_code"},
    "l1_mdp.vehicle_info_p": {
        "PlateNo": "vehicle_num",
        "VehicleStatus": "vehicle_status",
        "DataType": "vehicle_tool",
        "PersonalNo": "store_manager_code",
        "CustomerNo": "customer_code",
    },
}

VEHICLE_FS_FIELD_OVERRIDES = {
    "dms_order": [
        "mars_store_code",
        "org_mars_order_header_no",
        "org_dtr_created_at",
        "update_time",
        "marsk",
        "reason_for_reversal",
        "qct_total",
        "sales_amount",
        "org_coupon_amt",
        "supplier_code",
        "supplier_name",
        "org_dtr_source_type",
        "category",
    ],
    "dms_md": ["code", "status", "belongs_to_code", "belongs_to_name"],
}

SUPERVISOR_HBASE_CANONICAL_NAMES = {
    "l0_eo.order_detail_sync": "l0_eo.order_details_sync",
    "l2_cot_exe_report.rpt_exe_visit_planning_execute_rate_2025": "l2_cot_exe_report.rpt_exe_visit_planning_execute_rate",
}

SUPERVISOR_HBASE_FIELD_OVERRIDES = {
    "l0_eo.order_details_sync": [
        "customers_code",
        "order_date",
        "order_status",
        "order_pt_sum",
        "product_std_code",
    ],
    "l2_cot_exe_report.rpt_exe_visit_planning_execute_rate": [
        "store_code",
        "today_executed",
        "planning_date",
        "visit_emp_segment",
    ],
    "l0_cot_visit.store_planning": [
        "store_code",
        "planning_date",
        "user_segment",
    ],
    "l0_user_center.user_information": [
        "emp_code",
        "emp_name",
        "level_code",
        "emp_type_name",
        "parent_emp_code",
        "parent_emp_name",
        "ad_account",
        "mars_geo_code1",
        "mars_geo_name1",
        "mars_geo_code2",
        "mars_geo_name2",
        "mars_geo_code3",
        "mars_geo_name3",
        "mars_geo_code4",
        "mars_geo_name4",
        "status",
        "org_code_ hierachy",
        "org_name_ hierachy",
        "roles_code",
        "roles_name",
        "is_cheetah",
        "is_vehicle",
        "is_wholesale",
        "is_lst",
        "user_channel",
        "created",
        "updated",
        "id",
        "segment",
    ],
    "l0_product_center.locust_product_md": ["prod_code", "segment", "subsegment"],
}

SUPERVISOR_HBASE_RANGE_OVERRIDES = {
    "l0_eo.order_details_sync": {"start_time": "p_start", "end_time": "p_end", "row_prefixs": True},
    "l2_cot_exe_report.rpt_exe_visit_planning_execute_rate": {
        "start_time": "period",
        "end_time": "period",
        "row_prefixs": True,
    },
    "l0_cot_visit.store_planning": {"start_time": "currentday", "end_time": "currentday", "row_prefixs": True},
    "l0_user_center.user_information": {"start_time": None, "end_time": None, "row_prefixs": False},
    "l0_product_center.locust_product_md": {"start_time": None, "end_time": None, "row_prefixs": False},
}

SUPERVISOR_MSSQL_FIELD_OVERRIDES = {
    "topic_supervisor_portal.store_details": [
        "mars_region_code",
        "mars_province_code",
        "mars_city_cluster_code",
        "mars_city_code",
        "region_code",
        "chain_brand_code",
        "nation_hq_code",
        "city_hq_code",
        "ka_type_code",
        "channel_code",
        "channel_level2_code",
        "store_channel_code",
        "rtm_channel_code",
        "mars_region_name",
        "mars_province_name",
        "mars_city_cluster_name",
        "mars_city_name",
        "region_name",
        "chain_brand_name",
        "nation_hq_name",
        "ka_type_name",
        "city_hq_name",
        "code",
        "store_name",
        "cover_mode",
        "channel_name",
        "channel_level2_name",
        "store_channel_name",
        "store_level",
        "wal_mart",
        "salesman_code",
        "salesman_name",
        "state",
        "digital",
        "rtm_channel_name",
        "store_kk",
        "store_manager_code",
        "store_manager_name",
        "closed_date",
    ],
    "topic_supervisor_portal.eo_order_detail_pool": [
        "store_code",
        "create_time",
        "order_state",
        "pt_sum",
        "product_code",
    ],
    "topic_supervisor_portal.fts_store_visit_log": ["store_id", "created_timestamp", "status"],
}

SUPERVISOR_MSSQL_RANGE_OVERRIDES = {
    "topic_supervisor_portal.store_details": {"time_col": None},
    "topic_supervisor_portal.eo_order_detail_pool": {
        "time_col": "create_time",
        "start_time": "current_date",
        "end_time": "current_date",
    },
    "topic_supervisor_portal.fts_store_visit_log": {
        "time_col": "created_timestamp",
        "start_time": "p_start_time",
        "end_time": "current_date",
    },
}

SUPERVISOR_MSSQL_RENAME_MAP = {
    "topic_supervisor_portal.store_details": {"code": "store_code"},
    "store_details": {"code": "store_code"},
}

FIXED_PLATFORM_PACKAGE_DIRS = {"gateway", "hbase", "fs"}


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


def vehicle_output_targets(plan: Dict[str, Any]) -> Dict[str, str]:
    targets = {"detail": "", "presale": "", "instock": ""}
    for output in plan.get("outputs", []):
        name = output.get("target_name", "")
        columns = set(output.get("final_columns", []))
        if "order_code" in columns and "vehicle_status" in columns:
            targets["detail"] = name
        elif "48_delivery_incentive_amount" in columns:
            targets["presale"] = name
        elif "incentive_amount" in columns and "vehicle_customer_code" in columns:
            targets["instock"] = name
    targets["detail"] = targets["detail"] or "clickhouse_vehicle_verify_detail"
    targets["presale"] = targets["presale"] or "clickhouse_vehicle_verify_sum_ps_fs"
    targets["instock"] = targets["instock"] or "clickhouse_vehicle_verify_sum_fs"
    return targets


def write_vehicle_data_process(target: Path, plan: Dict[str, Any]) -> None:
    targets = vehicle_output_targets(plan)
    content = f'''# coding: utf-8
from common_utils.all_modules import Dict, logger, np, pd
from params_configs.col_config import rename_map, target_table_columns


DETAIL_TARGET = {targets["detail"]!r}
PRESALE_TARGET = {targets["presale"]!r}
INSTOCK_TARGET = {targets["instock"]!r}
''' + r'''


def _blankish(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return series.isna() | text.isin(["", "无", "nan", "NaN", "None", "none"])


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _ensure_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    for column in columns:
        if column not in df.columns:
            df[column] = np.nan
    return df


class DataProcess:
    """Build vehicle-verification outputs using requirement-defined joins and KPIs."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        logger.info("Initializing vehicle verification DataProcess")
        self.source_data = source_data
        self.time_range = time_range
        self.params = params
        self.period = str(time_range.get("period") or "").strip()
        self.P = str(time_range.get("P") or time_range.get("period") or "").strip()
        self._data: Dict[str, pd.DataFrame] = {}
        self.df_details = pd.DataFrame(columns=target_table_columns.get(DETAIL_TARGET, []))
        self.df_summary_presale = pd.DataFrame(columns=target_table_columns.get(PRESALE_TARGET, []))
        self.df_summary_instock = pd.DataFrame(columns=target_table_columns.get(INSTOCK_TARGET, []))

    def _source(self, key: str) -> pd.DataFrame:
        df = self.source_data.get(key)
        if df is None:
            return pd.DataFrame()
        df = df.copy()
        mapping = rename_map.get(key, {})
        if mapping:
            df = df.rename(columns=mapping)
        return df

    @property
    def eo_line(self):
        return self._data.get("eo_line", pd.DataFrame())

    @property
    def store_detail(self):
        return self._data.get("store_detail", pd.DataFrame())

    @property
    def sales_assess_channel(self):
        return self._data.get("sales_assess_channel", pd.DataFrame())

    @property
    def vehicle_info(self):
        return self._data.get("vehicle_info", pd.DataFrame())

    @property
    def customer_md(self):
        return self._data.get("customer_md", pd.DataFrame())

    @property
    def dms_order(self):
        return self._data.get("dms_order", pd.DataFrame())

    @property
    def dms_md(self):
        return self._data.get("dms_md", pd.DataFrame())

    @property
    def product_md(self):
        return self._data.get("product_md", pd.DataFrame())

    def data_clean(self):
        logger.info("transform_start step=vehicle_source_clean")
        eo_line = self._source("l0_dtr_order.t5_eo_erp_sales_order_line_p")
        eo_input_rows = len(eo_line)
        if not eo_line.empty:
            if {"order_status", "bmp_eo_order_category"}.issubset(eo_line.columns):
                # Requirement: only delivered/received NDT orders enter vehicle reconciliation.
                eo_line = eo_line[
                    eo_line["order_status"].astype(str).isin(["4516", "4508"])
                    & (eo_line["bmp_eo_order_category"].astype(str) == "NDT")
                ].copy()

            product_md = self._source("l0_product_center.locust_product_md")
            if not product_md.empty and {"subsegment", "prod_code"}.issubset(product_md.columns):
                exclude_skus = product_md.loc[
                    product_md["subsegment"].isin(["Chips", "Cereals", "薯片", "谷物"]),
                    "prod_code",
                ].dropna().astype(str).unique()
                if len(exclude_skus) and {"order_source", "mars_sku_no", "bmp_mars_sku_no"}.issubset(eo_line.columns):
                    # Requirement: EO and ERP orders identify the comparable SKU in different columns.
                    match_sku = np.where(
                        eo_line["order_source"].astype(str) == "EO订单",
                        eo_line["mars_sku_no"].astype(str),
                        np.where(
                            eo_line["order_source"].astype(str) == "ERP订单",
                            eo_line["bmp_mars_sku_no"].astype(str),
                            "",
                        ),
                    )
                    eo_line = eo_line[~np.isin(match_sku, exclude_skus)].copy()
            self._data["product_md"] = product_md
        else:
            self._data["product_md"] = self._source("l0_product_center.locust_product_md")
        self._data["eo_line"] = eo_line
        logger.info(
            "transform_complete step=vehicle_eo_filter input_rows={} output_rows={}",
            eo_input_rows,
            len(eo_line),
        )

        store_detail = self._source("l0_store_center.store_details_p")
        store_input_rows = len(store_detail)
        if not store_detail.empty:
            # Requirement: the report population is traditional-channel presale or current-sale stores.
            if "digital" in store_detail.columns:
                store_detail = store_detail[store_detail["digital"].isin(["预售", "现售"])].copy()
            if "channel_name" in store_detail.columns:
                store_detail = store_detail[store_detail["channel_name"] == "传统渠道"].copy()
        self._data["store_detail"] = store_detail
        logger.info(
            "transform_complete step=vehicle_store_scope input_rows={} output_rows={}",
            store_input_rows,
            len(store_detail),
        )

        self._data["sales_assess_channel"] = self._source("l2_cot_exe_report.rpt_exe_sales_assess_channel")
        self._data["vehicle_info"] = self._clean_vehicle_info(self._source("l1_mdp.vehicle_info_p"))

        customer_md = self._source("l0_customer_center.locust_customer_md")
        if not customer_md.empty:
            if "customer_type_code" in customer_md.columns:
                customer_md = customer_md[customer_md["customer_type_code"] == "DT"].copy()
            if "division" in customer_md.columns:
                customer_md = customer_md[customer_md["division"].astype(str) == "51"].copy()
        self._data["customer_md"] = customer_md

        dms_order = self.source_data.get("dms_order", pd.DataFrame()).copy()
        if not dms_order.empty and "category" in dms_order.columns:
            dms_order = dms_order[~dms_order["category"].isin(["Chips", "Cereals", "薯片", "谷物"])].copy()
        self._data["dms_order"] = dms_order

        dms_md = self.source_data.get("dms_md", pd.DataFrame()).copy()
        if not dms_md.empty and "code" in dms_md.columns:
            dms_md = dms_md.rename(columns={"code": "customer_code"})
        self._data["dms_md"] = dms_md
        return self

    def _clean_vehicle_info(self, df_vehicle_raw: pd.DataFrame) -> pd.DataFrame:
        columns = ["store_manager_code", "vehicle_tool", "vehicle_num", "vehicle_status", "customer_code"]
        if df_vehicle_raw.empty:
            return pd.DataFrame(columns=columns)

        id_vars = ["customer_code", "vehicle_status", "vehicle_tool", "vehicle_num", "PINNo", "ModifyDate", "CreateDate"]
        value_vars = ["store_manager_code", "SalesmanNo", "SalesmanNo2"]
        df_vehicle_raw = _ensure_columns(df_vehicle_raw, id_vars + value_vars)

        df_melt = pd.melt(
            df_vehicle_raw,
            id_vars=id_vars,
            value_vars=value_vars,
            var_name="source_role",
            value_name="final_manager_code",
        )
        df_melt = df_melt.rename(columns={"final_manager_code": "store_manager_code"}).drop(columns=["source_role"])
        df_melt = df_melt[~_blankish(df_melt["store_manager_code"])].copy()
        if df_melt.empty:
            return pd.DataFrame(columns=columns)

        df_melt["is_running"] = np.where(df_melt["vehicle_status"].astype(str).str.strip() == "行驶", 1, 0)
        modify_text = df_melt["ModifyDate"].astype(str).str.strip()
        df_melt["ModifyDate"] = np.where(
            modify_text.isin(["", "nan", "NaN", "None", "none"]),
            df_melt["CreateDate"],
            df_melt["ModifyDate"],
        )
        df_melt["ModifyDate"] = pd.to_datetime(df_melt["ModifyDate"], errors="coerce")
        df_melt = df_melt.sort_values(
            by=["store_manager_code", "is_running", "ModifyDate"],
            ascending=[True, False, False],
        )
        df_unique = df_melt.drop_duplicates(subset=["store_manager_code"], keep="first").copy()

        plate = df_unique["vehicle_num"].astype(str).str.strip()
        pin = df_unique["PINNo"].astype(str).str.strip()
        no_plate_mask = (plate == "") | (plate == "无") | plate.str.lower().isin(["nan", "none"])
        three_wheel_mask = df_unique["vehicle_tool"].isin(["经销商三轮车", "销售三轮车"])
        df_unique["vehicle_num"] = np.where(no_plate_mask & three_wheel_mask, pin, plate)
        df_unique["vehicle_num"] = df_unique["vehicle_num"].replace(
            {"": np.nan, "无": np.nan, "nan": np.nan, "NaN": np.nan, "None": np.nan, "none": np.nan}
        )
        return df_unique[columns].reset_index(drop=True)

    def _get_eo_orders_only(self) -> pd.DataFrame:
        columns = [
            "code", "order_code", "order_created_time", "order_delivered_time",
            "sold_to_code", "sold_to_name", "order_source",
            "total_amount", "order_gsv", "order_advance_amount",
        ]
        if self.eo_line.empty:
            return pd.DataFrame(columns=columns)
        header = _ensure_columns(
            self.eo_line.copy(),
            [
                "mars_store_code", "mars_order_header_no", "order_created_at", "first_complete_time",
                "sold_to_code", "sold_to_name", "original_amount", "pt_sum", "coupon_amt",
            ],
        )
        df = pd.DataFrame(
            {
                "code": header["mars_store_code"],
                "order_code": header["mars_order_header_no"],
                "order_created_time": pd.to_datetime(header["order_created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_time": pd.to_datetime(header["first_complete_time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sold_to_code": header["sold_to_code"],
                "sold_to_name": header["sold_to_name"],
                "order_source": "EO订单",
                "total_amount": _to_number(header["original_amount"]),
                "order_gsv": _to_number(header["pt_sum"]),
                "order_advance_amount": _to_number(header["coupon_amt"]),
            }
        )
        group_keys = [
            "code", "order_code", "order_created_time", "order_delivered_time",
            "sold_to_code", "sold_to_name", "order_source",
        ]
        df = df.groupby(group_keys, as_index=False, dropna=False)[["total_amount", "order_gsv", "order_advance_amount"]].sum()
        for column in ["total_amount", "order_gsv", "order_advance_amount"]:
            df[column] = df[column].round(2)
        return df

    def _get_dms_orders_only(self) -> pd.DataFrame:
        columns = [
            "code", "order_code", "order_created_time", "order_delivered_time", "marsk",
            "reason_for_reversal", "total_amount", "order_gsv", "order_advance_amount",
            "sold_to_code", "sold_to_name", "order_source",
        ]
        if self.dms_order.empty:
            return pd.DataFrame(columns=columns)
        df_dms = _ensure_columns(
            self.dms_order.copy(),
            [
                "org_mars_order_header_no", "org_dtr_created_at", "update_time", "marsk",
                "reason_for_reversal", "supplier_code", "supplier_name", "mars_store_code",
                "org_dtr_source_type", "qct_total", "sales_amount", "org_coupon_amt",
            ],
        )
        amount_cols = ["qct_total", "sales_amount", "org_coupon_amt"]
        for column in amount_cols:
            df_dms[column] = _to_number(df_dms[column])
        group_keys = [
            "org_mars_order_header_no", "org_dtr_created_at", "update_time", "marsk",
            "reason_for_reversal", "supplier_code", "supplier_name", "mars_store_code",
            "org_dtr_source_type",
        ]
        df_header = df_dms.groupby(group_keys, as_index=False, dropna=False)[amount_cols].sum()
        marsk = np.select(
            [df_header["marsk"].astype(str) == "0", df_header["marsk"].astype(str) == "1"],
            ["新增单", "冲销单"],
            default=df_header["marsk"].astype(str),
        )
        order_source = np.where(df_header["org_dtr_source_type"].astype(str) == "0", "EO订单", "ERP订单")
        return pd.DataFrame(
            {
                "code": df_header["mars_store_code"],
                "order_code": df_header["org_mars_order_header_no"],
                "order_created_time": pd.to_datetime(df_header["org_dtr_created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_time": pd.to_datetime(df_header["update_time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "marsk": marsk,
                "reason_for_reversal": df_header["reason_for_reversal"],
                "total_amount": df_header["qct_total"].round(2),
                "order_gsv": df_header["sales_amount"].round(2),
                "order_advance_amount": df_header["org_coupon_amt"].round(2),
                "sold_to_code": df_header["supplier_code"],
                "sold_to_name": df_header["supplier_name"],
                "order_source": order_source,
            }
        )

    def combine_all_orders(self):
        logger.info("Build detail table from store base and order streams")
        eo_orders = self._get_eo_orders_only()
        dms_orders = self._get_dms_orders_only()
        non_empty = [df for df in [eo_orders, dms_orders] if not df.empty]
        all_orders = pd.concat(non_empty, axis=0, ignore_index=True, sort=False) if non_empty else pd.DataFrame(columns=["code"])
        base = self.store_detail.copy()
        if base.empty:
            base = pd.DataFrame(columns=["code"])
        # Requirement: store scope owns output coverage, including stores with no matching order.
        self.df_details = pd.merge(base, all_orders, on="code", how="left")
        logger.info(
            "transform_complete step=vehicle_order_join stores={} orders={} output_rows={}",
            len(base),
            len(all_orders),
            len(self.df_details),
        )
        period_value = self.P or self.period
        self.df_details["period"] = period_value
        self.df_details["year"] = str(period_value)[:4]
        return self

    def combine_sales_assess(self):
        if self.sales_assess_channel.empty or self.df_details.empty:
            return self
        assess = _ensure_columns(
            self.sales_assess_channel.copy(),
            ["store_manager_code", "salesman_type", "sale_role"],
        )[["store_manager_code", "salesman_type", "sale_role"]].drop_duplicates("store_manager_code")
        self.df_details = pd.merge(
            self.df_details.drop(columns=["salesman_type", "sale_role"], errors="ignore"),
            assess,
            on="store_manager_code",
            how="left",
        )
        return self

    def combine_vehicle_info(self):
        if self.df_details.empty:
            return self
        if self.vehicle_info.empty:
            self.df_details["vehicle_tool"] = "公共交通或其他"
            self.df_details["vehicle_num"] = np.nan
            self.df_details["vehicle_status"] = "空"
            return self
        vehicle_ref = self.vehicle_info[["store_manager_code", "vehicle_tool", "vehicle_num", "vehicle_status"]]
        self.df_details = pd.merge(self.df_details, vehicle_ref, on="store_manager_code", how="left")
        self.df_details["vehicle_tool"] = self.df_details["vehicle_tool"].fillna("公共交通或其他")
        self.df_details["vehicle_status"] = self.df_details["vehicle_status"].fillna("空")
        if "vehicle_num" in self.df_details.columns:
            self.df_details.loc[_blankish(self.df_details["vehicle_num"]), "vehicle_status"] = "空"
        return self

    def calculate_kpi(self):
        if self.df_details.empty:
            return self
        df = self.df_details
        df = _ensure_columns(df, ["order_code", "total_amount", "order_gsv", "order_advance_amount", "sold_to_code", "sold_to_name"])
        order_empty = _blankish(df["order_code"])
        total_amount = _to_number(df["total_amount"])
        order_gsv = _to_number(df["order_gsv"])
        ratio = np.round(np.divide(total_amount, order_gsv, out=np.zeros(len(df)), where=order_gsv.to_numpy() != 0) - 1, 4)
        is_diff = (ratio > 0.4) | (ratio < -0.4)
        df["is_difference_order"] = np.where(order_empty, None, np.where(is_diff, "是", "否"))
        df["order_difference_amount"] = np.where(order_empty, np.nan, np.where(is_diff, total_amount, 0))

        start_time = pd.to_datetime(df.get("order_created_time"), errors="coerce")
        end_time = pd.to_datetime(df.get("order_delivered_time"), errors="coerce")
        duration_hours = (end_time - start_time).dt.total_seconds() / 3600
        df["is_48_deliver"] = np.where(order_empty, None, np.where((duration_hours < 48) & duration_hours.notna(), "是", "否"))
        df["is_advance_order"] = np.where(order_empty, None, np.where(_to_number(df["order_advance_amount"]) > 0, "是", "否"))

        dt_codes = self.customer_md["customer_code"].dropna().unique() if "customer_code" in self.customer_md.columns else []
        d2_codes = self.dms_md["customer_code"].dropna().unique() if "customer_code" in self.dms_md.columns else []
        sold_to = df["sold_to_code"]
        df["customer_type"] = np.select(
            [np.isin(sold_to, dt_codes), np.isin(sold_to, d2_codes)],
            ["经销商", "二分商"],
            default=None,
        )
        df["order_customer_code"] = df["sold_to_code"]
        df["order_customer_name"] = df["sold_to_name"]
        if not self.dms_md.empty and {"customer_code", "status", "belongs_to_code", "belongs_to_name"}.issubset(self.dms_md.columns):
            valid_rel = self.dms_md[self.dms_md["status"].astype(str) == "1"].drop_duplicates("customer_code")
            code_map = valid_rel.set_index("customer_code")["belongs_to_code"]
            name_map = valid_rel.set_index("customer_code")["belongs_to_name"]
            d2_mask = df["customer_type"] == "二分商"
            mapped_code = df["sold_to_code"].map(code_map)
            mapped_name = df["sold_to_code"].map(name_map)
            df["order_customer_code"] = np.where(d2_mask & mapped_code.notna(), mapped_code, df["order_customer_code"])
            df["order_customer_name"] = np.where(d2_mask & mapped_name.notna(), mapped_name, df["order_customer_name"])
        self.df_details = df
        return self

    def finalize_detail(self):
        for column in target_table_columns.get(DETAIL_TARGET, []):
            if column not in self.df_details.columns:
                self.df_details[column] = np.nan
        self.df_details = self.df_details.reindex(columns=target_table_columns.get(DETAIL_TARGET, []))
        return self

    def calculate_summary_presale(self):
        final_columns = target_table_columns.get(PRESALE_TARGET, [])
        if self.df_details.empty:
            self.df_summary_presale = pd.DataFrame(columns=final_columns)
            return self
        df_base = self.df_details[~_blankish(self.df_details["order_code"])].copy()
        if df_base.empty:
            self.df_summary_presale = pd.DataFrame(columns=final_columns)
            return self

        if not self.customer_md.empty and "customer_code" in self.customer_md.columns:
            cust_ref = self.customer_md.drop_duplicates("customer_code").set_index("customer_code")
            geo_map = {
                "mars_geo_region_name": "customer_region_name",
                "mars_geo_province_name": "customer_province_name",
                "mars_geo_city_clusters_name": "customer_city_cluster_name",
                "mars_geo_city_name": "customer_city_name",
            }
            for src, target in geo_map.items():
                if src in cust_ref.columns:
                    df_base[target] = df_base["order_customer_code"].map(cust_ref[src])

        def aggregate(target_df: pd.DataFrame, group_keys: list, district_label=None) -> pd.DataFrame:
            target_df = target_df.copy()
            for key in group_keys:
                if key not in target_df.columns:
                    target_df[key] = np.nan
            normal_mask = target_df["is_difference_order"] == "否"
            target_df["valid_order_cnt"] = np.where(normal_mask, 1, 0)
            target_df["valid_48_cnt"] = np.where(normal_mask & (target_df["is_48_deliver"] == "是"), 1, 0)
            target_df["valid_gsv"] = np.where(normal_mask, _to_number(target_df["order_gsv"]), 0)
            target_df["valid_advance"] = np.where(normal_mask, _to_number(target_df["order_advance_amount"]), 0)
            target_df["presale_store"] = np.where(target_df["digital"] == "预售", target_df["code"], np.nan)
            target_df["instock_store"] = np.where(target_df["digital"] == "现售", target_df["code"], np.nan)
            result = target_df.groupby(group_keys, as_index=False, dropna=False).agg(
                {
                    "code": "nunique",
                    "presale_store": "nunique",
                    "instock_store": "nunique",
                    "total_amount": "sum",
                    "order_difference_amount": "sum",
                    "valid_order_cnt": "sum",
                    "valid_48_cnt": "sum",
                    "valid_gsv": "sum",
                    "valid_advance": "sum",
                }
            )
            result["48_delivery_rate"] = (result["valid_48_cnt"] / result["valid_order_cnt"].replace(0, np.nan)).fillna(0).round(4)
            result["order_gsv"] = result["valid_gsv"].round(2)
            result["order_advance_amount"] = result["valid_advance"].round(2)
            result["total_amount"] = result["total_amount"].round(2)
            result["order_difference_amount"] = result["order_difference_amount"].round(2)
            result["48_delivery_incentive_amount"] = np.where(
                result["48_delivery_rate"] >= 0.8,
                (result["order_gsv"] * result["48_delivery_rate"] * 0.02).round(2),
                np.nan,
            )
            result = result.rename(
                columns={
                    "code": "store_count_sys",
                    "presale_store": "store_num_cheetah",
                    "instock_store": "store_num_lbcx",
                }
            )
            if district_label:
                result["digital_district"] = district_label
            return result

        scope = (
            ((df_base["digital_district"] == "预售片区") & df_base["digital"].isin(["预售", "现售"]))
            | ((df_base["digital_district"] == "现售片区") & (df_base["digital"] == "预售"))
        )
        base_keys = [
            "year", "period", "sold_to_code", "sold_to_name", "order_customer_code", "order_customer_name",
            "channel_name", "rtm_channel_name", "customer_region_name", "customer_province_name",
            "customer_city_cluster_name", "customer_city_name",
        ]
        result_1 = aggregate(df_base[scope], base_keys + ["digital_district"])
        result_2 = aggregate(df_base[scope], base_keys, district_label="预售片区+现售片区整体")
        self.df_summary_presale = pd.concat([result_1, result_2], axis=0, ignore_index=True).reindex(columns=final_columns)
        return self

    def calculate_summary_instock(self):
        final_columns = target_table_columns.get(INSTOCK_TARGET, [])
        if self.df_details.empty:
            self.df_summary_instock = pd.DataFrame(columns=final_columns)
            return self
        scope = (
            (self.df_details["digital_district"] == "现售片区")
            & (self.df_details["digital"] == "现售")
            & (~_blankish(self.df_details["order_code"]))
        )
        df_scope = self.df_details[scope].copy()
        if df_scope.empty:
            self.df_summary_instock = pd.DataFrame(columns=final_columns)
            return self

        if not self.sales_assess_channel.empty:
            assess = _ensure_columns(
                self.sales_assess_channel.copy(),
                ["store_manager_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"],
            )[["store_manager_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"]].drop_duplicates("store_manager_code")
            assess = assess.rename(
                columns={
                    "mars_region_name": "salesman_region_name",
                    "mars_province_name": "salesman_province_name",
                    "mars_city_cluster_name": "salesman_city_cluster_name",
                    "mars_city_name": "salesman_city_name",
                }
            )
            df_scope = pd.merge(df_scope, assess, on="store_manager_code", how="left")

        if not self.vehicle_info.empty:
            valid_vehicle = self.vehicle_info.dropna(subset=["customer_code"]).copy()
            if not valid_vehicle.empty:
                valid_vehicle["vehicle_num"] = valid_vehicle["vehicle_num"].replace(["无", ""], np.nan)
                by_num = valid_vehicle.dropna(subset=["vehicle_num"]).drop_duplicates("vehicle_num").set_index("vehicle_num")["customer_code"]
                by_mgr = valid_vehicle.dropna(subset=["store_manager_code"]).drop_duplicates("store_manager_code").set_index("store_manager_code")["customer_code"]
                customer_by_num = df_scope["vehicle_num"].map(by_num) if "vehicle_num" in df_scope.columns else pd.Series(np.nan, index=df_scope.index)
                customer_by_mgr = df_scope["store_manager_code"].map(by_mgr) if "store_manager_code" in df_scope.columns else pd.Series(np.nan, index=df_scope.index)
                candidate_code = customer_by_num.combine_first(customer_by_mgr)
                dealer_vehicle = df_scope["vehicle_tool"].isin(["经销商四轮车", "经销商二轮车", "经销商三轮车"])
                df_scope["vehicle_customer_code"] = np.where(dealer_vehicle & candidate_code.notna(), candidate_code, None)
                if not self.customer_md.empty and {"customer_code", "name"}.issubset(self.customer_md.columns):
                    name_map = self.customer_md.drop_duplicates("customer_code").set_index("customer_code")["name"]
                    df_scope["vehicle_customer_name"] = df_scope["vehicle_customer_code"].map(name_map)

        group_keys = [
            "year", "period", "salesman_region_name", "salesman_province_name", "salesman_city_cluster_name",
            "salesman_city_name", "digital_district", "store_manager_code", "store_manager_name", "salesman_type",
            "sale_role", "channel_name", "rtm_channel_name", "digital", "vehicle_tool", "vehicle_num",
            "vehicle_status", "vehicle_customer_code", "vehicle_customer_name",
        ]
        for key in group_keys:
            if key not in df_scope.columns:
                df_scope[key] = np.nan
        self.df_summary_instock = df_scope.groupby(group_keys, as_index=False, dropna=False).agg(
            {"code": "nunique", "total_amount": "sum", "order_gsv": "sum", "order_advance_amount": "sum"}
        )
        self.df_summary_instock = self.df_summary_instock.rename(columns={"code": "store_count_sys"})
        self.df_summary_instock["incentive_amount"] = (_to_number(self.df_summary_instock["order_gsv"]) * 0.02).round(2)
        for column in ["total_amount", "order_gsv", "order_advance_amount"]:
            self.df_summary_instock[column] = _to_number(self.df_summary_instock[column]).round(2)
        self.df_summary_instock = self.df_summary_instock.reindex(columns=final_columns)
        return self

    def handle_missing_values(self):
        for column in ["order_source", "vehicle_status", "marsk"]:
            if column in self.df_details.columns:
                self.df_details[column] = self.df_details[column].fillna("空")
        if "vehicle_status" in self.df_summary_instock.columns:
            self.df_summary_instock["vehicle_status"] = self.df_summary_instock["vehicle_status"].fillna("空")
        return self

    def run(self) -> Dict[str, pd.DataFrame]:
        (
            self.data_clean()
            .combine_all_orders()
            .combine_sales_assess()
            .combine_vehicle_info()
            .calculate_kpi()
            .finalize_detail()
            .calculate_summary_instock()
            .calculate_summary_presale()
            .handle_missing_values()
        )
        return {
            DETAIL_TARGET: self.df_details,
            PRESALE_TARGET: self.df_summary_presale,
            INSTOCK_TARGET: self.df_summary_instock,
        }
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")


def write_supervisor_portal_data_process(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, np, pd
from params_configs.col_config import target_table_columns


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _ensure_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    for column in columns:
        if column not in df.columns:
            df[column] = np.nan
    return df


class DataProcess:
    """Build supervisor-portal outputs while preserving report grain and defaults."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params
        self.current_date = str(time_range.get("current_date") or "")
        self.p_start_time = str(time_range.get("p_start_time") or self.current_date)
        self.p_end_time = str(time_range.get("p_end_time") or self.current_date)

    def _source(self, *names: str) -> pd.DataFrame:
        for name in names:
            if name in self.source_data:
                return self.source_data[name].copy()
        for key, value in self.source_data.items():
            key_tail = str(key).split(".")[-1]
            for name in names:
                if key_tail == name or str(key).endswith(name):
                    return value.copy()
        return pd.DataFrame()

    def _previous(self, name: str, columns: list) -> pd.DataFrame:
        injected = self.params.get(name)
        if isinstance(injected, pd.DataFrame):
            df = injected.copy()
            for column in columns:
                if column not in df.columns:
                    df[column] = np.nan
            return df[columns].copy()
        return pd.DataFrame(columns=columns)

    def _safe_divide(self, numerator, denominator):
        # Requirement: zero or missing denominators yield 0 and KPI values use four decimals.
        denominator = _to_number(denominator)
        numerator = _to_number(numerator)
        return (numerator / denominator.replace(0, np.nan)).fillna(0).round(4)

    def _base_store(self) -> pd.DataFrame:
        df = self._source("topic_supervisor_portal.store_details", "store_details")
        if df.empty:
            return pd.DataFrame(columns=["store_code"])
        if "code" in df.columns and "store_code" not in df.columns:
            df = df.rename(columns={"code": "store_code"})
        if "cover_mode" in df.columns:
            # Requirement: only the three documented sugar-and-chocolate coverage modes are in scope.
            cover = df["cover_mode"].astype(str)
            df = df[
                cover.str.contains("糖巧固定覆盖", na=False)
                | cover.str.contains("糖巧非固定覆盖", na=False)
                | cover.str.contains("糖巧线路外覆盖", na=False)
            ].copy()
        if {"state", "closed_date"}.issubset(df.columns):
            # Requirement: closed stores remain visible only when closure is after the R2P boundary.
            r2p = str(self.time_range.get("r2p") or "")
            state_text = df["state"].astype(str)
            df = df[(state_text == "1") | ((state_text == "0") & (df["closed_date"].astype(str) > r2p))].copy()
        return df.drop_duplicates("store_code") if "store_code" in df.columns else df

    def _product_dimensions(self) -> pd.DataFrame:
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if product.empty:
            return pd.DataFrame({"segment": ["空"], "subsegment": ["空"]})
        product = _ensure_columns(product, ["segment", "subsegment"])
        segment = self.params.get("segment")
        subsegment = self.params.get("subsegment")
        if segment:
            product = product[product["segment"].isin(segment if isinstance(segment, list) else [segment])]
        if subsegment:
            product = product[product["subsegment"].isin(subsegment if isinstance(subsegment, list) else [subsegment])]
        dims = product[["segment", "subsegment"]].drop_duplicates().reset_index(drop=True)
        if dims.empty:
            dims = pd.DataFrame(columns=["segment", "subsegment"])
        dims.loc[len(dims)] = ["空", "空"]
        return dims.drop_duplicates().reset_index(drop=True)

    def _today_sales(self) -> pd.Series:
        orders = self._source("topic_supervisor_portal.eo_order_detail_pool", "eo_order_detail_pool")
        if orders.empty:
            return pd.Series(dtype=float, name="today_sales")
        orders = _ensure_columns(orders, ["store_code", "create_time", "order_state", "pt_sum"])
        orders["create_time"] = pd.to_datetime(orders["create_time"], errors="coerce")
        start = pd.to_datetime(self.current_date)
        end = start.replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["create_time"] >= start)
            & (orders["create_time"] <= end)
            & (~orders["order_state"].astype(str).isin(["4509", "4512", "已取消", "已拒收"]))
        ].copy()
        valid["pt_sum"] = _to_number(valid["pt_sum"])
        result = valid.groupby("store_code")["pt_sum"].sum()
        result.name = "today_sales"
        return result

    def _pty_sales(self) -> pd.Series:
        orders = self._source("l0_eo.order_details_sync", "l0_eo.order_detail_sync", "order_details_sync", "order_detail_sync")
        if orders.empty:
            return pd.Series(dtype=float, name="pty_sales")
        if "customers_code" in orders.columns and "store_code" not in orders.columns:
            orders = orders.rename(columns={"customers_code": "store_code"})
        orders = _ensure_columns(orders, ["store_code", "order_date", "order_status", "order_pt_sum"])
        orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        end = pd.to_datetime(self.time_range.get("yester_day") or self.current_date).replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["order_date"] >= start)
            & (orders["order_date"] <= end)
            & (~orders["order_status"].astype(str).isin(["已取消", "已拒收", "4509", "4512"]))
        ].copy()
        valid["order_pt_sum"] = _to_number(valid["order_pt_sum"])
        result = valid.groupby("store_code")["order_pt_sum"].sum()
        result.name = "pty_sales"
        return result

    def _today_sales_by_product(self) -> pd.DataFrame:
        orders = self._source("topic_supervisor_portal.eo_order_detail_pool", "eo_order_detail_pool")
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if orders.empty:
            return pd.DataFrame(columns=["store_code", "segment", "subsegment", "today_sales"])
        orders = _ensure_columns(orders, ["store_code", "create_time", "order_state", "pt_sum", "product_code"])
        product = _ensure_columns(product, ["prod_code", "segment", "subsegment"])
        orders["create_time"] = pd.to_datetime(orders["create_time"], errors="coerce")
        start = pd.to_datetime(self.current_date)
        end = start.replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["create_time"] >= start)
            & (orders["create_time"] <= end)
            & (~orders["order_state"].astype(str).isin(["4509", "4512", "已取消", "已拒收"]))
        ].copy()
        valid = valid.merge(product[["prod_code", "segment", "subsegment"]], left_on="product_code", right_on="prod_code", how="left")
        valid[["segment", "subsegment"]] = valid[["segment", "subsegment"]].fillna("空")
        valid["pt_sum"] = _to_number(valid["pt_sum"])
        return valid.groupby(["store_code", "segment", "subsegment"], dropna=False)["pt_sum"].sum().reset_index(name="today_sales")

    def _pty_sales_by_product(self) -> pd.DataFrame:
        orders = self._source("l0_eo.order_details_sync", "l0_eo.order_detail_sync", "order_details_sync", "order_detail_sync")
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if orders.empty:
            return pd.DataFrame(columns=["store_code", "segment", "subsegment", "pty_sales"])
        if "customers_code" in orders.columns and "store_code" not in orders.columns:
            orders = orders.rename(columns={"customers_code": "store_code"})
        product = _ensure_columns(product, ["prod_code", "segment", "subsegment"])
        orders = _ensure_columns(orders, ["store_code", "order_date", "order_status", "order_pt_sum", "product_std_code"])
        orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        end = pd.to_datetime(self.time_range.get("yester_day") or self.current_date).replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["order_date"] >= start)
            & (orders["order_date"] <= end)
            & (~orders["order_status"].astype(str).isin(["已取消", "已拒收", "4509", "4512"]))
        ].copy()
        valid = valid.merge(product[["prod_code", "segment", "subsegment"]], left_on="product_std_code", right_on="prod_code", how="left")
        valid[["segment", "subsegment"]] = valid[["segment", "subsegment"]].fillna("空")
        valid["order_pt_sum"] = _to_number(valid["order_pt_sum"])
        return valid.groupby(["store_code", "segment", "subsegment"], dropna=False)["order_pt_sum"].sum().reset_index(name="pty_sales")

    def _visit_flags(self):
        visit = self._source("topic_supervisor_portal.fts_store_visit_log", "fts_store_visit_log")
        if visit.empty:
            return pd.DataFrame(columns=["store_code", "today_is_visited"]), pd.Series(dtype=int, name="ptd_total_visits")
        if "store_id" in visit.columns and "store_code" not in visit.columns:
            visit = visit.rename(columns={"store_id": "store_code"})
        visit = _ensure_columns(visit, ["store_code", "created_timestamp", "status"])
        visit["created_timestamp"] = pd.to_datetime(visit["created_timestamp"], errors="coerce")
        today = pd.to_datetime(self.current_date)
        today_end = today.replace(hour=23, minute=59, second=59)
        p_start = pd.to_datetime(self.p_start_time)
        valid = visit[visit["status"].astype(str).isin(["2", "2.0"])].copy()
        today_df = valid[(valid["created_timestamp"] >= today) & (valid["created_timestamp"] <= today_end)]
        today_flag = pd.DataFrame({"store_code": today_df["store_code"].dropna().unique(), "today_is_visited": 1})
        ptd = valid[(valid["created_timestamp"] >= p_start) & (valid["created_timestamp"] <= today_end)].copy()
        ptd["visit_date"] = ptd["created_timestamp"].dt.date
        ptd_total = ptd[["store_code", "visit_date"]].drop_duplicates().groupby("store_code").size()
        ptd_total.name = "ptd_total_visits"
        return today_flag, ptd_total

    def _plan_flags(self):
        plan = self._source("l0_cot_visit.store_planning", "store_planning")
        exec_rate = self._source("l2_cot_exe_report.rpt_exe_visit_planning_execute_rate", "rpt_exe_visit_planning_execute_rate")
        today = pd.to_datetime(self.current_date).date()
        if not plan.empty:
            plan = _ensure_columns(plan, ["store_code", "planning_date", "user_segment"])
            if "user_segment" in plan.columns:
                plan = plan[plan["user_segment"].astype(str) == "MW"].copy()
            plan["planning_date"] = pd.to_datetime(plan["planning_date"], errors="coerce").dt.date
            today_plan = plan[plan["planning_date"] == today]
            today_flag = pd.DataFrame({"store_code": today_plan["store_code"].dropna().unique(), "today_is_visit_planned": 1})
        else:
            today_flag = pd.DataFrame(columns=["store_code", "today_is_visit_planned"])

        if exec_rate.empty:
            empty = pd.Series(dtype=int)
            empty.name = "pty_total_planned_visits"
            return today_flag, empty, empty.rename("pty_planned_visits_completed")
        exec_rate = _ensure_columns(exec_rate, ["store_code", "planning_date", "today_executed", "visit_emp_segment"])
        if "visit_emp_segment" in exec_rate.columns:
            exec_rate = exec_rate[exec_rate["visit_emp_segment"].astype(str) == "MW"].copy()
        exec_rate["planning_date"] = pd.to_datetime(exec_rate["planning_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        yesterday = pd.to_datetime(self.time_range.get("yester_day") or self.current_date)
        scoped = exec_rate[(exec_rate["planning_date"] >= start) & (exec_rate["planning_date"] <= yesterday)].copy()
        total = scoped.groupby("store_code").size()
        total.name = "pty_total_planned_visits"
        completed = scoped[scoped["today_executed"].astype(str).isin(["1", "1.0"])].groupby("store_code").size()
        completed.name = "pty_planned_visits_completed"
        return today_flag, total, completed

    def _calculate_is_store_activated(self, df: pd.DataFrame) -> pd.DataFrame:
        df = _ensure_columns(df, ["rtm_channel_code", "channel_code", "store_channel_code"])
        cond1 = df["rtm_channel_code"].astype(str) == "FT-TT"
        cond2 = df["rtm_channel_code"].astype(str) == "WS"
        cond3 = (df["channel_code"].astype(str) == "MT") & (df["rtm_channel_code"].astype(str) == "FT-Non KA")
        cond4 = (df["store_channel_code"].astype(str) != "PlatformOwned") & (df["rtm_channel_code"].astype(str) == "O2O前置仓")
        df["is_store_activated"] = np.where(cond1 | cond2 | cond3 | cond4, 1, 0).astype(int)
        return df

    def _build_store(self) -> pd.DataFrame:
        df = self._base_store()
        if df.empty:
            return self._finalize("supervisor_portal_store", df)
        today_sales = self._today_sales()
        pty_sales = self._pty_sales()
        today_visited, ptd_total_visits = self._visit_flags()
        today_plan, pty_total_plans, pty_completed_plans = self._plan_flags()
        previous = self._previous("previous_store", ["store_code", "today_sales", "today_is_visit_planned", "today_is_visited", "today_order_placed"])
        if not previous.empty:
            previous = previous.rename(columns={
                "today_sales": "yesterday_sales",
                "today_is_visit_planned": "yesterday_is_visit_planned",
                "today_is_visited": "yesterday_is_visited",
                "today_order_placed": "yesterday_order_placed",
            })
            df = df.merge(previous, on="store_code", how="left")
        for series in [today_sales, pty_sales, ptd_total_visits, pty_total_plans, pty_completed_plans]:
            if not series.empty:
                df = df.merge(series.reset_index(), on="store_code", how="left")
        for flag_df in [today_visited, today_plan]:
            if not flag_df.empty:
                df = df.merge(flag_df, on="store_code", how="left")
        defaults = {
            "today_sales": 0,
            "yesterday_sales": 0,
            "pty_sales": 0,
            "today_is_visit_planned": 0,
            "today_is_visited": 0,
            "yesterday_is_visit_planned": 0,
            "yesterday_is_visited": 0,
            "pty_total_visits": 0,
            "pty_planned_visits_completed": 0,
            "pty_total_planned_visits": 0,
            "yesterday_order_placed": 0,
        }
        for column, value in defaults.items():
            if column not in df.columns:
                df[column] = value
            df[column] = _to_number(df[column])
        df["ptd_sales"] = _to_number(df["today_sales"]) + _to_number(df["pty_sales"])
        df["ptd_total_visits"] = _to_number(df["ptd_total_visits"])
        df["ptd_planned_visits_completed"] = np.where(
            (_to_number(df["today_is_visit_planned"]) == 1) & (_to_number(df["today_is_visited"]) == 1),
            _to_number(df["pty_planned_visits_completed"]) + 1,
            _to_number(df["pty_planned_visits_completed"]),
        )
        df["ptd_total_planned_visits"] = np.where(
            _to_number(df["today_is_visit_planned"]) == 1,
            _to_number(df["pty_total_planned_visits"]) + 1,
            _to_number(df["pty_total_planned_visits"]),
        )
        df = self._calculate_is_store_activated(df)
        df["today_order_placed"] = np.where(_to_number(df["today_sales"]) > 0, 1, 0)
        df["pty_order_placed"] = np.where(_to_number(df["pty_sales"]) > 0, 1, 0)
        df["ptd_orde_placed"] = np.where(_to_number(df["ptd_sales"]) > 0, 1, 0)
        return self._finalize("supervisor_portal_store", df)

    def _build_store_sales(self) -> pd.DataFrame:
        base = self._base_store()
        dims = self._product_dimensions()
        if base.empty:
            return self._finalize("supervisor_portal_store_sales", base)
        base = base.merge(dims, how="cross")
        previous = self._previous("previous_store_sales", ["store_code", "segment", "subsegment", "today_sales"])
        if not previous.empty:
            previous = previous.rename(columns={"today_sales": "yesterday_sales"})
            base = base.merge(previous, on=["store_code", "segment", "subsegment"], how="left")
        for df_sales in [self._today_sales_by_product(), self._pty_sales_by_product()]:
            if not df_sales.empty:
                base = base.merge(df_sales, on=["store_code", "segment", "subsegment"], how="left")
        for column in ["today_sales", "yesterday_sales", "pty_sales"]:
            if column not in base.columns:
                base[column] = 0
            base[column] = _to_number(base[column])
        base["ptd_sales"] = base["today_sales"] + base["pty_sales"]
        base = self._calculate_is_store_activated(base)
        return self._finalize("supervisor_portal_store_sales", base)

    def _aggregate_common(self, df: pd.DataFrame, group_keys: list, target_name: str) -> pd.DataFrame:
        if df.empty:
            return self._finalize(target_name, df)
        df = _ensure_columns(df, group_keys + [
            "state", "digital", "is_store_activated", "today_sales", "yesterday_sales", "pty_sales", "ptd_sales",
            "today_is_visited", "today_is_visit_planned", "yesterday_is_visited", "yesterday_is_visit_planned",
            "pty_total_visits", "pty_planned_visits_completed", "pty_total_planned_visits",
            "ptd_total_visits", "ptd_planned_visits_completed", "ptd_total_planned_visits",
            "today_order_placed", "yesterday_order_placed", "pty_order_placed", "ptd_orde_placed",
        ])
        active = _to_number(df["is_store_activated"]) == 1
        valid = df["state"].astype(str).isin(["1", "1.0"])
        digital = df["digital"].isin(["现售", "预售"])
        work = df.copy()
        work["_today_order_count"] = np.where(valid & active & digital & (_to_number(work["today_order_placed"]) == 1), 1, 0)
        work["_yesterday_order_count"] = np.where(valid & active & digital & (_to_number(work["yesterday_order_placed"]) == 1), 1, 0)
        work["_pty_order_count"] = np.where(valid & active & digital & (_to_number(work["pty_order_placed"]) == 1), 1, 0)
        work["_ptd_order_count"] = np.where(valid & active & digital & (_to_number(work["ptd_orde_placed"]) == 1), 1, 0)
        work["_today_digital_visit"] = np.where(valid & active & digital & (_to_number(work["today_is_visited"]) == 1), 1, 0)
        work["_yesterday_digital_visit"] = np.where(valid & active & digital & (_to_number(work["yesterday_is_visited"]) == 1), 1, 0)
        agg = work.groupby(group_keys, dropna=False).agg(
            today_sales=("today_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            yesterday_sales=("yesterday_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            pty_sales=("pty_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            ptd_sales=("ptd_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            today_visit_store_count=("today_is_visited", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            today_planned_visits_completed_store_count=("today_is_visited", lambda x: ((_to_number(x[valid.loc[x.index]]) == 1) & (_to_number(work.loc[x.index, "today_is_visit_planned"]) == 1)).sum()),
            today_visit_plan_store_count=("today_is_visit_planned", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            yesterday_visit_store_count=("yesterday_is_visited", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            yesterday_planned_visits_completed_store_count=("yesterday_is_visited", lambda x: ((_to_number(x[valid.loc[x.index]]) == 1) & (_to_number(work.loc[x.index, "yesterday_is_visit_planned"]) == 1)).sum()),
            yesterday_visit_plan_store_count=("yesterday_is_visit_planned", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            pty_total_visits=("pty_total_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            pty_planned_visits_completed=("pty_planned_visits_completed", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            pty_total_planned_visits=("pty_total_planned_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_total_visits=("ptd_total_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_planned_visits_completed=("ptd_planned_visits_completed", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_total_planned_visits=("ptd_total_planned_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            today_order_store_count=("_today_order_count", "sum"),
            yesterday_order_store_count=("_yesterday_order_count", "sum"),
            pty_order_store_count=("_pty_order_count", "sum"),
            ptd_order_store_count=("_ptd_order_count", "sum"),
            today_digital_visit_store_count=("_today_digital_visit", "sum"),
            yesterday_digital_visit_store_count=("_yesterday_digital_visit", "sum"),
            pty_digital_visit_store_count=("pty_total_visits", lambda x: _to_number(x[valid.loc[x.index] & active.loc[x.index] & digital.loc[x.index]]).sum()),
            ptd_digital_visit_store_count=("ptd_total_visits", lambda x: _to_number(x[valid.loc[x.index] & active.loc[x.index] & digital.loc[x.index]]).sum()),
        ).reset_index()
        agg["today_visit_plan_execution_rate"] = self._safe_divide(agg["today_planned_visits_completed_store_count"], agg["today_visit_plan_store_count"])
        agg["yesterday_visit_plan_execution_rate"] = self._safe_divide(agg["yesterday_planned_visits_completed_store_count"], agg["yesterday_visit_plan_store_count"])
        agg["pty_visit_plan_execution_rate"] = self._safe_divide(agg["pty_planned_visits_completed"], agg["pty_total_planned_visits"])
        agg["ptd_visit_plan_execution_rate"] = self._safe_divide(agg["ptd_planned_visits_completed"], agg["ptd_total_planned_visits"])
        agg["today_store_activation_rate"] = self._safe_divide(agg["today_order_store_count"], agg["today_digital_visit_store_count"])
        agg["yesterday_store_activation_rate"] = self._safe_divide(agg["yesterday_order_store_count"], agg["yesterday_digital_visit_store_count"])
        agg["pty_store_activation_rate"] = self._safe_divide(agg["pty_order_store_count"], agg["pty_digital_visit_store_count"])
        agg["ptd_store_activation_rate"] = self._safe_divide(agg["ptd_order_store_count"], agg["ptd_digital_visit_store_count"])
        return self._finalize(target_name, agg)

    def _aggregate_sales(self, df: pd.DataFrame, group_keys: list, target_name: str) -> pd.DataFrame:
        if df.empty:
            return self._finalize(target_name, df)
        df = _ensure_columns(df, group_keys + ["is_store_activated", "today_sales", "yesterday_sales", "pty_sales", "ptd_sales"])
        scoped = df[_to_number(df["is_store_activated"]) == 1].copy()
        result = scoped.groupby(group_keys, dropna=False).agg(
            today_sales=("today_sales", "sum"),
            yesterday_sales=("yesterday_sales", "sum"),
            pty_sales=("pty_sales", "sum"),
            ptd_sales=("ptd_sales", "sum"),
        ).reset_index()
        return self._finalize(target_name, result)

    def _user_information(self) -> pd.DataFrame:
        return self._finalize("user_information", self._source("l0_user_center.user_information", "user_information"))

    def _finalize(self, target_name: str, df: pd.DataFrame) -> pd.DataFrame:
        columns = target_table_columns.get(target_name, [])
        df = df.copy()
        for column in columns:
            if column not in df.columns:
                df[column] = np.nan
        final = df.reindex(columns=columns)
        logger.info("Built output {} rows={} columns={}", target_name, len(final), len(final.columns))
        return final

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=supervisor_portal layer=data_process")
        store = self._build_store()
        store_sales = self._build_store_sales()
        outputs = {
            "supervisor_portal_store": store,
            "supervisor_portal_store_sales": store_sales,
            "supervisor_portal_salesman": self._aggregate_common(
                store,
                ["store_manager_code", "store_manager_name"],
                "supervisor_portal_salesman",
            ),
            "supervisor_portal_salesman_sales": self._aggregate_sales(
                store_sales,
                ["store_manager_code", "store_manager_name", "rtm_channel_name", "segment", "subsegment"],
                "supervisor_portal_salesman_sales",
            ),
            "supervisor_portal_mars_geo": self._aggregate_common(
                store,
                ["mars_region_code", "mars_province_code", "mars_city_cluster_code", "mars_city_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"],
                "supervisor_portal_mars_geo",
            ),
            "supervisor_portal_mars_geo_sales": self._aggregate_sales(
                store_sales,
                ["mars_region_code", "mars_province_code", "mars_city_cluster_code", "mars_city_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name", "rtm_channel_name", "segment", "subsegment"],
                "supervisor_portal_mars_geo_sales",
            ),
            "user_information": self._user_information(),
        }
        return outputs
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")


def write_hbase_prepare_data_process(target: Path) -> None:
    content = '''# coding: utf-8
import time

from common_utils.all_modules import Dict, logger, pd
from params_configs.db_config import (
    pipeline_api_key,
    pipeline_base_url,
    pipeline_process_uids,
    pipeline_user_name,
)


try:
    import requests
except Exception:
    requests = None


class DataProcess:
    """Optionally activate downstream pipelines after HBase data is prepared."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def _run_one_pipeline(self, process_uid: str):
        injected = self.params.get("pipeline_client")
        if injected is not None:
            return injected.run(process_uid)
        if requests is None:
            raise RuntimeError("requests is unavailable; install it or inject pipeline_client for pipeline activation.")
        if not pipeline_base_url or pipeline_base_url.startswith("<"):
            raise RuntimeError("pipeline_base_url is a placeholder; fill deployment config before activation.")
        headers = {
            "Api-Key": pipeline_api_key,
            "X-Username": pipeline_user_name,
            "Content-Type": "application/json",
        }
        url = f"{pipeline_base_url}/build/projects/deliverables/processes/run"
        response = requests.post(url, params={"process_uid": process_uid}, headers=headers, verify=False)
        response.raise_for_status()
        result = response.json()
        if not result.get("successful"):
            raise RuntimeError(f"pipeline activation failed: {result}")
        return result

    def _activate_pipelines(self):
        process_uids = self.params.get("pipeline_process_uids") or pipeline_process_uids
        metrics = []
        for process_uid in process_uids:
            last_error = None
            for attempt in range(1, 7):
                try:
                    result = self._run_one_pipeline(str(process_uid))
                    metrics.append({"process_uid": str(process_uid), "status": "success", "result": result})
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "stage_retry stage=pipeline_activation uid={} attempt={} max_attempts=6 delay_seconds={} error_type={}",
                        process_uid,
                        attempt,
                        10 if attempt < 6 else 0,
                        type(exc).__name__,
                    )
                    if attempt < 6:
                        time.sleep(10)
            else:
                raise RuntimeError(f"pipeline activation failed for {process_uid}: {last_error}")
        return metrics

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=hbase_prepare layer=data_process")
        if self.params.get("is_run_pipeline", False):
            metrics = self._activate_pipelines()
            self.source_data["pipeline_metrics"] = pd.DataFrame(metrics)
        return self.source_data
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")


def write_contract_data_process(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from data_utils.contract_runtime import execute_contract
from params_configs.execution_contract import execution_contract


class DataProcess:
    """Execute a validated, normalized report transformation contract."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=contract_report layer=data_process")
        return execute_contract(self.source_data, self.time_range, self.params, execution_contract)
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")


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
    content = f'''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import field_rules, target_table_columns


class DataProcess:
    """Placeholder transformation contract for plan-driven report outputs."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=report layer=data_process")
        for target_name in {outputs!r}:
            logger.info("planned output {{}} fields={{}}", target_name, len(field_rules.get(target_name, [])))
        raise NotImplementedError(
            "Report scaffold only: implement source cleaning, joins, KPI formulas, "
            "aggregations, and final column ordering before deployment. "
            "See IMPLEMENTATION_STATUS.md and params_configs/col_config.py."
        )
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")


def write_vehicle_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from common_utils.all_modules import logger, pd
from gateway.client import GateWayClient
from params_configs.col_config import fs_source_config, hbase_export_cols, hbase_export_range
from params_configs.db_config import app_key, app_secret, env, fs_root_dir


class DataSource:
    """Read vehicle-verification sources for the resolved reporting range."""

    def __init__(self, params: dict):
        self.params = params
        self.period = params.get("period")
        self.current_date = params.get("current_date")

    def _gateway_client(self):
        if self.params.get("gateway_client") is not None:
            return self.params["gateway_client"]
        return GateWayClient(app_key, app_secret, env=env)

    def _hbase_client(self):
        if self.params.get("hbase_client") is not None:
            return self.params["hbase_client"]
        client = self._gateway_client()
        try:
            return client.getHbaseClient(fs_root_dir=fs_root_dir)
        except TypeError:
            return client.getHbaseClient()

    def _fs_client(self):
        if self.params.get("fs_client") is not None:
            return self.params["fs_client"]
        return self._gateway_client().getFsClient()

    def read_hbase_2_df(
        self,
        table_name: str,
        columns: List[str],
        row_start: Optional[str] = None,
        row_stop: Optional[str] = None,
        row_prefixs: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        injected = self.params.get("hbase_data", {})
        if table_name in injected:
            df = injected[table_name].copy()
        else:
            hbase_client = self._hbase_client()
            df = hbase_client.query_df(
                hbase_table_name=table_name,
                columns=columns,
                row_start=row_start,
                row_stop=row_stop,
                row_prefixs=row_prefixs,
            )
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns]

    def _target_p_from_param(self, period: str) -> Tuple[str, str]:
        value = str(period or "").strip()
        if not value:
            return "", ""
        if "P" in value:
            target_p = value
            target_period = value.replace("P", "")
        elif len(value) >= 6:
            target_period = value
            target_p = f"{value[:4]}P{value[-2:]}"
        else:
            target_p = value
            target_period = value.replace("P", "")
        return target_p, target_period

    def get_period_details(self, calendar_df: pd.DataFrame, period=None) -> dict:
        required = ["dataid", "m_year", "m_period"]
        for column in required:
            if column not in calendar_df.columns:
                raise ValueError(f"mars_calendar missing required column: {column}")
        calendar_df = calendar_df[required].copy()
        calendar_df["dataid"] = calendar_df["dataid"].astype(str)
        calendar_df["p"] = calendar_df["m_year"].astype(str) + "P" + calendar_df["m_period"].astype(str).str.zfill(2)

        if period:
            target_p, target_period = self._target_p_from_param(period)
        else:
            current_date = str(self.current_date or datetime.datetime.now().strftime("%Y%m%d"))
            current_rows = calendar_df.loc[calendar_df["dataid"] == current_date]
            if current_rows.empty:
                raise ValueError(f"mars_calendar has no current_date row: {current_date}")
            current_p = current_rows["p"].iloc[0]
            periods = calendar_df[["p"]].drop_duplicates().sort_values("p").reset_index(drop=True)
            periods["prev_p"] = periods["p"].shift(1)
            matched = periods.loc[periods["p"] == current_p]
            if matched.empty or pd.isna(matched["prev_p"].iloc[0]):
                raise ValueError(f"Cannot derive previous period from current period: {current_p}")
            target_p = matched["prev_p"].iloc[0]
            target_period = target_p.replace("P", "")

        period_rows = calendar_df.loc[calendar_df["p"] == target_p]
        if period_rows.empty:
            raise ValueError(f"mars_calendar has no rows for target period: {target_p}")
        time_range = {
            "P": target_p,
            "period": target_period,
            "p_start_date": period_rows["dataid"].min(),
            "p_end_date": period_rows["dataid"].max(),
        }
        logger.info(
            "time_range_resolved component=vehicle period={} P={} start={} end={}",
            time_range.get("period"),
            time_range.get("P"),
            time_range.get("p_start_date"),
            time_range.get("p_end_date"),
        )
        return time_range

    def _read_calendar(self) -> Tuple[pd.DataFrame, dict]:
        columns = hbase_export_cols.get("l0_mdp.mars_calendar", ["dataid", "m_year", "m_period"])
        calendar_df = self.read_hbase_2_df("l0_mdp.mars_calendar", columns)
        time_range = self.get_period_details(calendar_df, period=self.period)
        return calendar_df, time_range

    def _range_value(self, time_range: dict, key):
        if key is None:
            return None
        return time_range.get(str(key), str(key))

    def _read_hbase_with_range(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        start_key = fetch_range.get("start_time")
        end_key = fetch_range.get("end_time")
        row_start = self._range_value(time_range, start_key)
        row_stop = self._range_value(time_range, end_key)
        row_prefixs = None
        if fetch_range.get("row_prefixs") or fetch_range.get("is_row_prefixs"):
            row_prefixs = [str(index) for index in range(10)]
        if row_start is not None and row_stop is not None:
            row_stop = f"{row_stop}Z"
        logger.info(
            "source_read_start storage=hbase table={} selected_columns={} range_start={} range_end={} row_prefix_mode={}",
            table_name,
            len(columns),
            row_start,
            row_stop,
            bool(row_prefixs),
        )
        return self.read_hbase_2_df(table_name, columns, row_start=row_start, row_stop=row_stop, row_prefixs=row_prefixs)

    def fetch_hbase_tables(self, time_range: dict, calendar_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {"l0_mdp.mars_calendar": calendar_df}
        for table_name, columns in hbase_export_cols.items():
            if table_name == "l0_mdp.mars_calendar":
                continue
            df_map[table_name] = self._read_hbase_with_range(
                table_name,
                columns,
                hbase_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("HBase table={} rows={}", table_name, len(df_map[table_name]))
        return df_map

    def _safe_read_csv(self, fs_client, fs_path: str, local_dir: str, columns: List[str]) -> Optional[pd.DataFrame]:
        file_name = os.path.basename(fs_path)
        local_path = os.path.join(local_dir, file_name)
        try:
            fs_client.copy_to_local(fs_path, local_path)
            return pd.read_csv(local_path, sep="\\t", dtype=str, usecols=columns, engine="c", low_memory=False)
        except Exception as exc:
            logger.error("Failed to process FS file {}: {}", fs_path, exc)
            return None
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def _render_fs_path(self, path: str, time_range: dict) -> str:
        return (
            str(path or "")
            .replace("{Period}", time_range.get("P", ""))
            .replace("{period}", time_range.get("period", ""))
            .replace("{P}", time_range.get("P", ""))
        )

    def fetch_fs_data(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        injected = self.params.get("fs_data", {})
        df_fs_map: Dict[str, pd.DataFrame] = {}
        fs_client = None
        for key, config in fs_source_config.items():
            columns = list(config.get("fields", []))
            if key in injected:
                df = injected[key].copy()
                for column in columns:
                    if column not in df.columns:
                        df[column] = None
                df_fs_map[key] = df[columns] if columns else df
                logger.info("Loaded injected FS data key={} rows={}", key, len(df_fs_map[key]))
                continue

            if fs_client is None:
                fs_client = self._fs_client()
            fs_dir = self._render_fs_path(config.get("path", ""), time_range)
            logger.info("Reading FS key={} path={} columns={}", key, fs_dir, len(columns))
            if hasattr(fs_client, "exists") and not fs_client.exists(fs_dir):
                logger.warning("FS path does not exist: {}", fs_dir)
                df_fs_map[key] = pd.DataFrame(columns=columns)
                continue
            with tempfile.TemporaryDirectory() as tmp_dir:
                files = fs_client.listdir(fs_dir)
                frames = []
                for file_name in files:
                    fs_path = f"{fs_dir.rstrip('/')}/{file_name}"
                    df = self._safe_read_csv(fs_client, fs_path, tmp_dir, columns)
                    if df is not None and not df.empty:
                        frames.append(df)
                df_fs_map[key] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
                logger.info("FS key={} rows={}", key, len(df_fs_map[key]))
        return df_fs_map

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=vehicle layer=data_source")
        calendar_df, time_range = self._read_calendar()
        source_data: Dict[str, pd.DataFrame] = {}
        source_data.update(self.fetch_hbase_tables(time_range, calendar_df))
        source_data.update(self.fetch_fs_data(time_range))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")


def write_supervisor_portal_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import threading
from typing import Dict, List, Optional, Tuple

from common_utils.all_modules import logger, pd
from gateway.client import GateWayClient
from params_configs.col_config import (
    hbase_export_cols,
    hbase_export_range,
    mssql_columns_rename,
    mssql_export_cols,
    mssql_export_range,
)
from params_configs.db_config import app_key, app_secret, fs_root_dir, mssql_token, mssql_url


class DataSource:
    """Read supervisor-portal sources for the resolved reporting range."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        current_date = str(self.params.get("current_date") or datetime.datetime.now().strftime("%Y-%m-%d"))[:10]
        current_dt = pd.to_datetime(current_date)
        currentday = current_dt.strftime("%Y%m%d")
        yesterday_dt = current_dt - pd.Timedelta(days=1)
        period = str(self.params.get("period") or self.params.get("P") or "")
        p_start = str(self.params.get("p_start") or self.params.get("p_start_date") or "")
        p_end = str(self.params.get("p_end") or self.params.get("p_end_date") or "")
        time_range = {
            "current_date": current_dt.strftime("%Y-%m-%d"),
            "currentday": currentday,
            "yesterday": yesterday_dt.strftime("%Y%m%d"),
            "yester_day": yesterday_dt.strftime("%Y-%m-%d"),
            "period": period,
            "P": period,
            "p_start": p_start or period,
            "p_end": p_end or period,
            "p_start_time": str(self.params.get("p_start_time") or (pd.to_datetime(p_start).strftime("%Y-%m-%d") if p_start else current_dt.strftime("%Y-%m-%d"))),
            "p_end_time": str(self.params.get("p_end_time") or current_dt.strftime("%Y-%m-%d")),
            "r2p": str(self.params.get("r2p") or p_start or currentday),
        }
        logger.info(
            "time_range_resolved component=supervisor_portal period={} current_date={} start={} end={}",
            time_range.get("period"),
            time_range.get("current_date"),
            time_range.get("p_start_time"),
            time_range.get("p_end_time"),
        )
        return time_range

    def _gateway_client(self):
        if self.params.get("gateway_client") is not None:
            return self.params["gateway_client"]
        return GateWayClient(app_key, app_secret)

    def _hbase_client(self):
        if self.params.get("hbase_client") is not None:
            return self.params["hbase_client"]
        return self._gateway_client().getHbaseClient(fs_root_dir)

    def read_hbase_2_df(
        self,
        table_name: str,
        columns: List[str],
        row_start: Optional[str] = None,
        row_stop: Optional[str] = None,
        row_prefixs: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        injected = self.params.get("hbase_data", {})
        if table_name in injected:
            df = injected[table_name].copy()
        else:
            df = self._hbase_client().query_df(
                hbase_table_name=table_name,
                columns=columns,
                row_start=row_start,
                row_stop=row_stop,
                row_prefixs=row_prefixs,
            )
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns] if columns else df

    def _range_value(self, time_range: dict, key):
        if key is None:
            return None
        return time_range.get(str(key), str(key))

    def _read_hbase_with_range(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        row_start = self._range_value(time_range, fetch_range.get("start_time"))
        row_stop = self._range_value(time_range, fetch_range.get("end_time"))
        row_prefixs = [str(index) for index in range(10)] if fetch_range.get("row_prefixs") else None
        if row_start is not None and row_stop is not None:
            row_stop = f"{row_stop}Z"
        logger.info(
            "source_read_start storage=hbase table={} selected_columns={} range_start={} range_end={} row_prefix_mode={}",
            table_name,
            len(columns),
            row_start,
            row_stop,
            bool(row_prefixs),
        )
        return self.read_hbase_2_df(table_name, columns, row_start=row_start, row_stop=row_stop, row_prefixs=row_prefixs)

    def fetch_hbase_tables(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {}
        threads = []

        def worker(table_name: str):
            df_map[table_name] = self._read_hbase_with_range(
                table_name,
                hbase_export_cols.get(table_name, []),
                hbase_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("HBase table={} rows={}", table_name, len(df_map[table_name]))

        for table_name in hbase_export_cols:
            thread = threading.Thread(target=worker, args=(table_name,))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        return df_map

    def _mssql_client(self):
        if self.params.get("mssql_client") is not None:
            return self.params["mssql_client"]
        raise RuntimeError(
            "No mssql_client supplied. Fill mssql_url/mssql_token and adapt _mssql_client for the deployment runtime."
        )

    def _mssql_sql(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> str:
        select_cols = ", ".join(columns) if columns else "*"
        time_col = fetch_range.get("time_col")
        if time_col:
            start_time = pd.to_datetime(time_range[fetch_range["start_time"]]).strftime("%Y-%m-%d %H:%M:%S")
            end_time = pd.to_datetime(time_range[fetch_range["end_time"]]).replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            return f"SELECT {select_cols} FROM {table_name} WHERE {time_col} BETWEEN '{start_time}' AND '{end_time}'"
        r2p = time_range.get("r2p", "")
        return (
            f"SELECT {select_cols} FROM {table_name} "
            "WHERE (cover_mode LIKE '%糖巧固定覆盖%' OR cover_mode LIKE '%糖巧非固定覆盖%' OR cover_mode LIKE '%糖巧线路外覆盖%') "
            f"AND (state = 1 OR (state = 0 AND closed_date > '{r2p}'))"
        )

    def read_mssql_2_df(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        injected = self.params.get("mssql_data", {})
        if table_name in injected:
            df = injected[table_name].copy()
        else:
            client = self._mssql_client()
            sql = self._mssql_sql(table_name, columns, fetch_range, time_range)
            logger.info(
                "source_query storage=mssql table={} selected_columns={} predicate={}",
                table_name,
                len(columns),
                "time_range" if fetch_range.get("time_col") else "coverage_and_state",
            )
            if hasattr(client, "read_sql"):
                df = client.read_sql(sql)
            elif hasattr(client, "query_df"):
                df = client.query_df(sql)
            else:
                raise RuntimeError("mssql_client must provide read_sql(sql) or query_df(sql).")
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        if table_name in mssql_columns_rename:
            df = df.rename(columns=mssql_columns_rename[table_name])
        return df

    def fetch_mssql_tables(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {}
        threads = []

        def worker(table_name: str):
            df_map[table_name] = self.read_mssql_2_df(
                table_name,
                mssql_export_cols.get(table_name, []),
                mssql_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("MSSQL table={} rows={}", table_name, len(df_map[table_name]))

        for table_name in mssql_export_cols:
            thread = threading.Thread(target=worker, args=(table_name,))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        return df_map

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=supervisor_portal layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        source_data.update(self.fetch_hbase_tables(time_range))
        source_data.update(self.fetch_mssql_tables(time_range))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")


def write_hbase_prepare_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import os

from common_utils.all_modules import Dict, List, Tuple, datetime, logger, pd
from params_configs.col_config import (
    hbase_export_cols,
    hbase_prepare_default_export_cols,
    hbase_prepare_subsegment_filter,
    hbase_prepare_table,
)
from params_configs.db_config import app_key, app_secret, fs_root_dir, fs_save_source_dir


try:
    from gateway.client import GateWayClient
except Exception:
    GateWayClient = None


class DataSource:
    """Export confirmed HBase source rows to FS for downstream report components."""

    def __init__(self, params: dict):
        self.params = params
        self.current_date = params.get("current_date")
        self.fs_root_dir = params.get("fs_root_dir") or fs_root_dir
        self.fs_save_source_dir = params.get("fs_save_source_dir") or fs_save_source_dir

    def _gateway_client(self):
        injected = self.params.get("gateway_client")
        if injected is not None:
            return injected
        if GateWayClient is None:
            raise RuntimeError("gateway.client.GateWayClient is unavailable; install/copy fixed gateway package or inject clients.")
        return GateWayClient(app_key, app_secret)

    def _hbase_client(self):
        injected = self.params.get("hbase_client")
        if injected is not None:
            return injected
        return self._gateway_client().getHbaseClient(self.fs_root_dir)

    def _fs_client(self):
        injected = self.params.get("fs_client")
        if injected is not None:
            return injected
        return self._gateway_client().getFsClient()

    def _read_hbase_df(self, table_name: str, columns: List[str], row_start=None, row_stop=None) -> pd.DataFrame:
        injected_data = self.params.get("hbase_data", {})
        if table_name in injected_data:
            df = injected_data[table_name].copy()
            if row_start is not None:
                for period_column in ["P", "Period", "period"]:
                    if period_column in df.columns:
                        df = df[df[period_column].astype(str) == str(row_start)]
                        break
            for column in columns:
                if column not in df.columns:
                    df[column] = None
            return df[columns]
        client = self._hbase_client()
        row_prefixs = [str(index) for index in range(10)]
        df = client.query_df(
            hbase_table_name=table_name,
            columns=columns,
            row_start=row_start,
            row_stop=row_stop,
            row_prefixs=row_prefixs,
        )
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns]

    def _calendar_periods(self) -> dict:
        current_date = self.current_date or datetime.datetime.now().strftime("%Y-%m-%d")
        calendar_table = "l0_cmt.date"
        calendar_columns = hbase_export_cols.get(calendar_table, ["NatureDate", "Period"])
        df_calendar = self._read_hbase_df(calendar_table, calendar_columns)
        if df_calendar.empty:
            period = str(self.params.get("period") or "")
            return {"r13p": [period] if period else [], "period": [period] if period else [], "mars_calendar": df_calendar}

        df_calendar = df_calendar.copy()
        df_calendar["NatureDate"] = df_calendar["NatureDate"].astype(str)
        calendar = df_calendar[df_calendar["NatureDate"] <= str(current_date)]
        calendar = calendar.drop_duplicates(subset="Period")
        periods = [str(value) for value in calendar["Period"].dropna().tolist()]
        # Requirement: initialization exports the 13 completed periods before the current period.
        r13p = periods[-14:-1]
        return {
            "r13p": r13p,
            "period": [r13p[-1]] if r13p else [],
            "mars_calendar": df_calendar,
        }

    def _period_list(self, time_range: dict) -> List[str]:
        specific_range = self.params.get("specific_range")
        if specific_range:
            return [str(value) for value in specific_range]
        export_mode = self.params.get("export_mode", "daily")
        # Requirement: init backfills R13P; daily mode exports only the latest completed period.
        if export_mode == "init":
            return [str(value) for value in time_range.get("r13p", []) if str(value)]
        return [str(value) for value in time_range.get("period", []) if str(value)]

    def _export_period(self, period: str) -> dict:
        table_name = self.params.get("hbase_table") or hbase_prepare_table
        columns = self.params.get("hbase_export_cols") or hbase_prepare_default_export_cols
        if not table_name or not columns:
            raise RuntimeError("Missing hbase prepare table or export columns.")
        df = self._read_hbase_df(table_name, list(columns), row_start=period, row_stop=f"{period}Z")
        input_rows = len(df)
        # Requirement: the downstream calculation consumes only configured subsegments aggregated by store.
        if "SubSegmentID" in df.columns:
            df = df[df["SubSegmentID"].astype(str).isin(hbase_prepare_subsegment_filter)]
        if "SelloutAmount" in df.columns:
            df["SelloutAmount"] = pd.to_numeric(df["SelloutAmount"], errors="coerce").fillna(0.0)
        if {"StoreID", "SelloutAmount"}.issubset(df.columns):
            df = df.groupby(["StoreID"], as_index=False).agg({"SelloutAmount": "sum"})
        logger.info(
            "transform_complete step=hbase_prepare_filter_aggregate period={} input_rows={} output_rows={}",
            period,
            input_rows,
            len(df),
        )

        file_name = f"cmt_sellout_{period}.csv.gz"
        local_dir = self.params.get("local_output_dir") or "."
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, file_name)
        df.to_csv(local_path, index=False, compression="gzip")

        fs_path = f"{self.fs_save_source_dir}/{file_name}"
        if not self.params.get("skip_fs_upload", False):
            fs_client = self._fs_client()
            fs_client.copy_from_local(local_path, fs_path, overwrite=True)
        if not self.params.get("keep_local_files", False):
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass
        logger.info("Exported HBase table={} period={} rows={} fs_path={}", table_name, period, len(df), fs_path)
        return {"period": period, "source_table": table_name, "rows": len(df), "fs_path": fs_path}

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=hbase_prepare layer=data_source")
        time_range = self._calendar_periods()
        metrics = [self._export_period(period) for period in self._period_list(time_range)]
        return {"export_metrics": pd.DataFrame(metrics)}, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")


def write_contract_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import os
import tempfile

from common_utils.all_modules import Dict, List, Tuple, logger, pd
from gateway.client import GateWayClient
from params_configs.db_config import app_key, app_secret, env, fs_root_dir
from params_configs.execution_contract import execution_contract


class DataSource:
    """Load normalized contract sources through explicit adapters or injected fixtures."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        current_date = str(self.params.get("current_date") or datetime.datetime.now().strftime("%Y-%m-%d"))
        period = str(self.params.get("period") or self.params.get("P") or "")
        values = {"current_date": current_date, "period": period, "P": str(self.params.get("P") or period)}
        values.update(self.params.get("time_range") or {})
        return values

    def _gateway_client(self):
        if self.params.get("gateway_client") is not None:
            return self.params["gateway_client"]
        return GateWayClient(app_key, app_secret, env=env)

    def _hbase_client(self):
        if self.params.get("hbase_client") is not None:
            return self.params["hbase_client"]
        client = self._gateway_client()
        try:
            return client.getHbaseClient(fs_root_dir=fs_root_dir)
        except TypeError:
            return client.getHbaseClient()

    def _fs_client(self):
        if self.params.get("fs_client") is not None:
            return self.params["fs_client"]
        return self._gateway_client().getFsClient()

    def _injected(self, source_name: str, config: dict):
        location = str(config.get("location") or source_name)
        for container_name in ["source_data", f"{config.get('kind')}_data"]:
            container = self.params.get(container_name) or {}
            if source_name in container:
                return container[source_name].copy()
            if location in container:
                return container[location].copy()
        return None

    def _normalize(self, source_name: str, config: dict, df: pd.DataFrame) -> pd.DataFrame:
        columns = list(config.get("columns") or [])
        if df is None:
            return pd.DataFrame(columns=columns)
        missing = [column for column in columns if column not in df.columns]
        if missing:
            raise ValueError(f"source {source_name} missing configured columns: {missing}")
        return df.loc[:, columns].copy()

    def _range_value(self, value, time_range: dict):
        if value is None:
            return None
        text = str(value)
        if text.startswith("time_range."):
            key = text.split(".", 1)[1]
            if key not in time_range:
                raise ValueError(f"source range key is missing: {text}")
            return time_range[key]
        if text.startswith("params."):
            key = text.split(".", 1)[1]
            if key not in self.params:
                raise ValueError(f"source range key is missing: {text}")
            return self.params[key]
        return value

    def _read_hbase(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        fetch_range = config.get("range") or {}
        row_start = self._range_value(fetch_range.get("start"), time_range)
        row_stop = self._range_value(fetch_range.get("stop"), time_range)
        row_prefixs = fetch_range.get("row_prefixs")
        logger.info("source_read_start storage=hbase source={} columns={} ranged={}", source_name, len(config.get("columns") or []), bool(row_start or row_stop))
        df = self._hbase_client().query_df(
            hbase_table_name=config["location"],
            columns=list(config.get("columns") or []),
            row_start=row_start,
            row_stop=row_stop,
            row_prefixs=row_prefixs,
        )
        return self._normalize(source_name, config, df)

    def _render_path(self, path: str, time_range: dict) -> str:
        result = str(path or "")
        for key, value in time_range.items():
            result = result.replace("{" + str(key) + "}", str(value))
        return result

    def _read_fs(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        fs_client = self._fs_client()
        fs_path = self._render_path(config["location"], time_range)
        file_format = str(config.get("format") or "csv").lower()
        separator = str(config.get("separator") or ("\\t" if file_format in {"tsv", "txt"} else ","))
        remote_files = fs_client.listdir(fs_path) if hasattr(fs_client, "listdir") else [fs_path]
        frames = []
        with tempfile.TemporaryDirectory() as temp_dir:
            for remote_name in remote_files:
                remote_name = str(remote_name)
                remote_path = remote_name if remote_name.startswith("/") else f"{fs_path.rstrip('/')}/{remote_name}"
                local_path = os.path.join(temp_dir, os.path.basename(remote_path))
                fs_client.copy_to_local(remote_path, local_path)
                if file_format == "parquet":
                    frame = pd.read_parquet(local_path, columns=list(config.get("columns") or []))
                else:
                    frame = pd.read_csv(local_path, sep=separator, usecols=list(config.get("columns") or []), low_memory=False)
                frames.append(frame)
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=config.get("columns") or [])
        return self._normalize(source_name, config, df)

    def _read_callable(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        reader_name = f"{config.get('kind')}_reader"
        reader = self.params.get(reader_name)
        if not callable(reader):
            raise RuntimeError(f"source {source_name} requires callable params[{reader_name!r}] or injected data")
        return self._normalize(source_name, config, reader(config, time_range))

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=contract_report layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        for source_name, config in (execution_contract.get("sources") or {}).items():
            kind = config.get("kind")
            if kind == "injected":
                df = self._injected(source_name, config)
                if df is None:
                    raise RuntimeError(f"injected source is required: {source_name}")
                source_data[source_name] = self._normalize(source_name, config, df)
            elif kind == "hbase":
                source_data[source_name] = self._read_hbase(source_name, config, time_range)
            elif kind == "fs":
                source_data[source_name] = self._read_fs(source_name, config, time_range)
            elif kind in {"mssql", "mysql"}:
                source_data[source_name] = self._read_callable(source_name, config, time_range)
            else:
                raise ValueError(f"unsupported source kind: {kind}")
            logger.info("source_read_complete source={} rows={} columns={}", source_name, len(source_data[source_name]), len(source_data[source_name].columns))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")


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

    content = '''# coding: utf-8
from common_utils.all_modules import Dict, List, Optional, Tuple, logger, pd
from params_configs.col_config import fs_source_config, hbase_export_cols, hbase_export_range


class DataSource:
    """Placeholder source contract for a plan-driven report component."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        return {
            "current_date": self.params.get("current_date", ""),
            "period": self.params.get("period", ""),
            "P": self.params.get("period", ""),
        }

    def _read_hbase(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        logger.info("planned HBase read table={} columns={} range={}", table_name, len(columns), fetch_range)
        return pd.DataFrame(columns=columns)

    def _read_fs(self, key: str, config: dict, time_range: dict) -> pd.DataFrame:
        logger.info("planned FS read key={} path={} columns={}", key, config.get("path"), len(config.get("fields", [])))
        return pd.DataFrame(columns=config.get("fields", []))

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=report layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        for table_name, columns in hbase_export_cols.items():
            source_data[table_name] = self._read_hbase(table_name, columns, hbase_export_range.get(table_name, {}), time_range)
        for key, config in fs_source_config.items():
            source_data[key] = self._read_fs(key, config, time_range)
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")


def write_supervisor_portal_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import hashlib
import time

from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map, target_table_columns


class DataStorage:
    """Replace supervisor-portal ClickHouse outputs using confirmed predicates."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params
        self.current_date = str(time_range.get("current_date") or "")

    def _get_clickhouse_client(self):
        injected_client = self.params.get("clickhouse_client")
        if injected_client is None:
            raise RuntimeError("No clickhouse_client supplied. Fill deployment ClickHouse client before running writes.")
        return injected_client

    def _generate_batch_id(self) -> str:
        return hashlib.md5(str(time.time()).encode("utf-8")).hexdigest()

    def _command(self, client, sql: str):
        operation = sql.strip().split(maxsplit=1)[0].upper() if sql.strip() else "UNKNOWN"
        logger.info("target_command storage=clickhouse operation={} statement_length={}", operation, len(sql))
        if hasattr(client, "command"):
            return client.command(sql)
        if hasattr(client, "execute"):
            return client.execute(sql)
        raise RuntimeError("clickhouse_client must provide command(sql) or execute(sql).")

    def _query_df(self, client, sql: str) -> pd.DataFrame:
        if hasattr(client, "query_df"):
            return client.query_df(sql)
        if hasattr(client, "query_dataframe"):
            return client.query_dataframe(sql)
        return pd.DataFrame()

    def _insert_dataframe(self, client, table_name: str, df: pd.DataFrame):
        if hasattr(client, "insert_df"):
            return client.insert_df(table_name, df)
        if hasattr(client, "insert_dataframe"):
            return client.insert_dataframe(table_name, df)
        raise RuntimeError("clickhouse_client must provide insert_df(table, df) or insert_dataframe(table, df).")

    def _next_batch_row_id(self, client) -> int:
        df_max = self._query_df(client, "select max(id) as id from supervisor_portal.supervisor_portal_batch")
        if df_max.empty or pd.isna(df_max.iloc[0].get("id")):
            return 1
        return int(df_max.iloc[0]["id"]) + 1

    def _insert_batch_status(self, client, row_id: int, table_name: str, batch_id: str, status: str, timestamp: str):
        sql = (
            "INSERT INTO supervisor_portal.supervisor_portal_batch "
            "(id, table_name, batch_id, status, last_update_time) "
            f"VALUES({row_id}, '{table_name}', '{batch_id}', '{status}', '{timestamp}')"
        )
        self._command(client, sql)

    def _update_batch_status(self, client, table_name: str, batch_id: str, status: str, timestamp: str):
        sql = (
            "ALTER TABLE supervisor_portal.supervisor_portal_batch "
            f"UPDATE status = '{status}', last_update_time = '{timestamp}' "
            f"WHERE batch_id = '{batch_id}' and table_name = '{table_name}'"
        )
        self._command(client, sql)

    def _previous_batch(self, client, table_name: str, status: str):
        sql = (
            "select batch_id from supervisor_portal.supervisor_portal_batch "
            f"where status = '{status}' and table_name = '{table_name}' order by id desc limit 1"
        )
        df_batch = self._query_df(client, sql)
        if df_batch.empty:
            return None
        return df_batch.iloc[0].get("batch_id")

    def _upload_one(self, client, target_name: str, df: pd.DataFrame):
        physical_table = target_table_map.get(target_name, target_name)
        clickhouse_table = physical_table.split(".")[-1]
        final_columns = target_table_columns.get(target_name, [])
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} reason=empty_output", target_name)
            return {"target": physical_table, "rows": 0, "status": "skipped_empty"}
        df = df.copy()
        batch_id = self._generate_batch_id()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for column in final_columns:
            if column not in df.columns:
                df[column] = None
        if "batch_id" in final_columns:
            df["batch_id"] = batch_id
        if "last_update_time" in final_columns:
            df["last_update_time"] = timestamp
        if "date" in final_columns:
            df["date"] = self.current_date
        if final_columns:
            df = df.reindex(columns=final_columns)

        row_id = self._next_batch_row_id(client)
        old_finished_batch = self._previous_batch(client, clickhouse_table, "2")
        old_cancelled_batch = self._previous_batch(client, clickhouse_table, "3")
        self._insert_batch_status(client, row_id, clickhouse_table, batch_id, "1", timestamp)
        logger.info("Inserting ClickHouse table={} rows={}", physical_table, len(df))
        self._insert_dataframe(client, physical_table, df)
        finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._update_batch_status(client, clickhouse_table, batch_id, "2", finish_time)
        if old_finished_batch:
            self._update_batch_status(client, clickhouse_table, old_finished_batch, "3", finish_time)
        if old_cancelled_batch:
            delete_sql = f"DELETE FROM supervisor_portal.{clickhouse_table} where batch_id = '{old_cancelled_batch}'"
            self._command(client, delete_sql)
        return {"target": physical_table, "rows": len(df), "status": "inserted", "batch_id": batch_id}

    def run(self):
        logger.info("component_start component=supervisor_portal layer=data_storage")
        client = self._get_clickhouse_client()
        metrics = []
        for target_name, df in self.outputs.items():
            metrics.append(self._upload_one(client, target_name, df))
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")


def write_hbase_prepare_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd


class DataStorage:
    """Report HBase-prepare outputs without adding an unsupported target writer."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def run(self):
        logger.info("component_start component=hbase_prepare layer=data_storage")
        metrics = []
        for name, df in self.outputs.items():
            rows = 0 if df is None else len(df)
            logger.info("prepared output={} rows={}", name, rows)
            metrics.append({"output": name, "rows": rows, "status": "prepared"})
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")


def write_contract_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import re

from common_utils.all_modules import Dict, logger, pd
from params_configs.execution_contract import execution_contract


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*$")


class DataStorage:
    """Write contract outputs with explicit append or replace predicates."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def _client(self):
        client = self.params.get("clickhouse_client")
        if client is None:
            raise RuntimeError("A clickhouse_client must be supplied for contract report writes.")
        return client

    def _identifier(self, value: str) -> str:
        value = str(value or "")
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"unsafe SQL identifier in execution contract: {value!r}")
        return value

    def _value_from(self, value_from: str):
        root, _, key = str(value_from or "").partition(".")
        values = self.time_range if root == "time_range" else self.params if root == "params" else None
        if values is None or not key or key not in values:
            raise ValueError(f"write predicate value is missing: {value_from!r}")
        return values[key]

    def _literal(self, value) -> str:
        if value is None:
            raise ValueError("replace predicate value cannot be null")
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    def _command(self, client, sql: str):
        logger.info("target_command storage=clickhouse operation={} statement_length={}", sql.split(maxsplit=1)[0], len(sql))
        if hasattr(client, "command"):
            return client.command(sql)
        if hasattr(client, "execute"):
            return client.execute(sql)
        raise RuntimeError("clickhouse_client must provide command(sql) or execute(sql)")

    def _insert(self, client, table: str, df: pd.DataFrame):
        if hasattr(client, "insert_df"):
            return client.insert_df(table, df)
        if hasattr(client, "insert_dataframe"):
            return client.insert_dataframe(table, df)
        raise RuntimeError("clickhouse_client must provide insert_df(table, df) or insert_dataframe(table, df)")

    def _write_one(self, client, output_name: str, df: pd.DataFrame, write: dict):
        table = self._identifier(write.get("table"))
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} reason=empty_output", output_name)
            return {"output": output_name, "target": table, "rows": 0, "status": "skipped_empty"}
        mode = write.get("mode")
        if mode == "replace_where":
            predicate = write.get("predicate") or {}
            column = self._identifier(predicate.get("column"))
            value = self._value_from(predicate.get("value_from"))
            sql = f"ALTER TABLE {table} DELETE WHERE {column} = {self._literal(value)}"
            self._command(client, sql)
        elif mode != "append":
            raise ValueError(f"unsupported write mode: {mode}")
        logger.info("target_insert storage=clickhouse output={} target={} rows={}", output_name, table, len(df))
        self._insert(client, table, df)
        return {"output": output_name, "target": table, "rows": len(df), "status": "inserted", "mode": mode}

    def run(self):
        logger.info("component_start component=contract_report layer=data_storage")
        client = self._client()
        writes = execution_contract.get("writes") or {}
        return [self._write_one(client, name, self.outputs[name], writes[name]) for name in writes]
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")


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

    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map


class DataStorage:
    """Placeholder storage contract for plan-driven report outputs."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def run(self):
        logger.info("component_start component=report layer=data_storage")
        for target_name, df in self.outputs.items():
            physical_table = target_table_map.get(target_name, target_name)
            logger.info("planned ClickHouse write target={} physical={} rows={}", target_name, physical_table, len(df))
        raise NotImplementedError(
            "Report scaffold only: implement ClickHouse delete/insert and any FS evidence writes before deployment."
        )
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")


def write_vehicle_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import os

from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map
from params_configs.db_config import clickhouse_connect_params, cluster


try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None


class DataStorage:
    """Replace vehicle-verification ClickHouse outputs by reporting period."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params
        self.period = str(time_range.get("P") or time_range.get("period") or "").strip()

    def _get_clickhouse_client(self):
        injected_client = self.params.get("clickhouse_client")
        if injected_client is not None:
            return injected_client
        if clickhouse_connect is None:
            raise RuntimeError("clickhouse_connect is not installed and no clickhouse_client was supplied.")
        if clickhouse_connect_params.get("CLICKHOUSE_HOST", "").startswith("<"):
            raise RuntimeError("ClickHouse connection placeholders must be filled before deployment.")
        return clickhouse_connect.get_client(
            host=clickhouse_connect_params["CLICKHOUSE_HOST"],
            port=int(clickhouse_connect_params["CLICKHOUSE_PORT"]),
            user=clickhouse_connect_params["CLICKHOUSE_USER"],
            password=clickhouse_connect_params["CLICKHOUSE_PASSWORD"],
            database=clickhouse_connect_params["CLICKHOUSE_DB"],
        )

    def _delete_period(self, client, table_name: str):
        if not self.period:
            raise ValueError("time_range must provide P or period before writing ClickHouse targets.")
        # Safety: period replacement deletes stale rows before inserting the complete non-empty output.
        delete_sql = f"ALTER TABLE {table_name} {cluster} DELETE WHERE period = '{self.period}'"
        logger.info("target_replace storage=clickhouse target={} predicate=period period={}", table_name, self.period)
        client.command(delete_sql)

    def _insert_dataframe(self, client, table_name: str, df: pd.DataFrame):
        logger.info("Inserting ClickHouse table={} rows={}", table_name, len(df))
        if hasattr(client, "insert_df"):
            client.insert_df(table_name, df)
            return
        if hasattr(client, "insert_dataframe"):
            client.insert_dataframe(table_name, df)
            return
        raise RuntimeError("ClickHouse client must support insert_df or insert_dataframe.")

    def _replace_period(self, client, target_name: str, df: pd.DataFrame):
        table_name = target_table_map.get(target_name, target_name)
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} target={} reason=empty_output", target_name, table_name)
            return {"target": table_name, "rows": 0, "status": "skipped_empty"}
        self._delete_period(client, table_name)
        self._insert_dataframe(client, table_name, df)
        return {"target": table_name, "rows": len(df), "status": "inserted"}

    def run(self):
        logger.info("component_start component=vehicle layer=data_storage")
        client = self._get_clickhouse_client()
        metrics = []
        for target_name, df in self.outputs.items():
            metrics.append(self._replace_period(client, target_name, df))
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")


def write_implementation_status(target: Path, plan: Dict[str, Any]) -> None:
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


def scaffold(plan_path: Path, target: Path, allow_blocked_scaffold: bool = False) -> None:
    plan = load_json(plan_path)
    codegen_contract = plan.get("codegen_contract", {})
    if codegen_contract and codegen_contract.get("project_type") != "report":
        raise ValueError(
            "codegen_contract routes this design package to data-sync-codegen, not report-codegen."
        )
    if codegen_contract and not codegen_contract.get("ready_for_codegen", False) and not allow_blocked_scaffold:
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
    clean_target(target)
    copy_minimal_project(target)
    write_col_config(target, plan)
    write_execution_contract_config(target, plan)
    write_rowkey_config(target, plan)
    write_db_config(target, plan)
    write_data_source(target, plan)
    write_data_process(target, plan)
    write_data_storage(target, plan)
    write_implementation_status(target, plan)
    write_params_example(target, plan)
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
