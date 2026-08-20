#!/usr/bin/env python3
"""Scaffold a COT sync project from data-doc-to-dev-md structured facts."""

from __future__ import annotations

import argparse
import csv
import json
import pprint
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_UPDATE_COLUMNS = [
    "inksaa_last_modified_timestamp",
    "last_update_timestamp",
    "updated_at",
    "update_time",
    "modified_time",
]

DEFAULT_CODE_COLUMNS = [
    "code",
    "store_code",
    "main_store_code",
    "sp_code",
    "salesman_code",
    "visit_emp_code",
    "employee_code",
    "id",
    "inksaa_id",
]

DEFAULT_KEY_COLUMNS = [
    "id",
    "inksaa_id",
    "code",
    "store_code",
    "main_store_code",
    "salesman_code",
]

COT_TABLE_NAME_OVERRIDES = {
    "supervisor_assist_visit": "v_supervisor_assist_visit_2026",
    "rpt_exe_sales_assess_channel": "rpt_exe_sales_assess_channel_2022",
}

COT_WITH_PERIOD_TABLE_OVERRIDES = {
    "freshness_report",
    "rpt_exe_sales_assess_channel_2022",
    "supervisor_remake_remark",
    "v_supervisor_assist_visit_2026",
}

COT_WITHOUT_PERIOD_TABLE_OVERRIDES = {
    "rpt_exe_visit_frequency_by_people",
    "rpt_exe_visit_frequency_by_store",
    "rpt_exe_visit_planning_execute_rate",
    "rpt_exe_store_past_will",
    "rpt_ic_exe_visit_frequency_by_store",
    "cot_gps_tracking_report",
    "cot_gps_tracking_report_by_week",
    "wechat_authorization_info",
}

COT_STORE_REPORT_GENERATOR_TABLES = {
    "rpt_exe_store_past_will",
    "rpt_exe_visit_frequency_by_people",
    "rpt_exe_visit_frequency_by_store",
    "rpt_exe_visit_planning_execute_rate",
    "wechat_authorization_info",
    "rpt_exe_sales_assess_channel_2022",
    "rpt_ic_exe_visit_frequency_by_store",
}

COT_STORE_REPORT_TABLES = {
    "cot_gps_tracking_report",
    "cot_gps_tracking_report_by_week",
    "supervisor_remake_remark",
    "v_supervisor_assist_visit_2026",
}

COT_HBASE_TABLE_OVERRIDES = {
    "v_supervisor_assist_visit_2026": "l2_cot_exe_report.v_supervisor_assist_visit_2026",
    "rpt_exe_sales_assess_channel_2022": "l2_cot_exe_report.rpt_exe_sales_assess_channel_2022",
}

COT_HBASE_TRUNCATE_TABLES = {
    "l2_cot_exe_report.wechat_authorization_info",
}

COT_CLICKHOUSE_TRUNCATE_TABLES = {
    "wechat_authorization_info",
}

FIXED_PLATFORM_PACKAGE_DIRS = {"gateway", "hbase", "fs"}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def split_clickhouse_name(value: str) -> Tuple[str, str]:
    value = clean_text(value)
    if "." not in value:
        return "", value
    database, table = value.rsplit(".", 1)
    return database, table


def select_column(fields: List[str], candidates: List[str], fallback: str) -> str:
    lowered = {field.lower(): field for field in fields}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return fallback


def read_field_csv(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        field_key = "字段" if "字段" in reader.fieldnames else reader.fieldnames[0]
        fields = []
        for row in reader:
            field_name = clean_text(row.get(field_key, ""))
            if field_name:
                fields.append(field_name)
        return unique(fields)


def build_field_map(facts: Dict[str, Any], extracted_tables: Optional[Path]) -> Dict[str, List[str]]:
    field_map: Dict[str, List[str]] = {}
    for item in facts.get("field_dictionaries", []):
        data_utilization = clean_text(item.get("inferred_data_utilization"))
        if not data_utilization:
            continue
        fields: List[str] = []
        if extracted_tables:
            csv_name = clean_text(item.get("csv"))
            fields = read_field_csv(extracted_tables / csv_name)
        if not fields:
            fields = [clean_text(value) for value in item.get("first_fields", [])]
        field_map[data_utilization] = unique(fields)
    return field_map


def normalize_cot_table_name(doc_table: str) -> str:
    return COT_TABLE_NAME_OVERRIDES.get(doc_table, doc_table)


def is_with_period(row: Dict[str, Any], source_table: str, fields: List[str]) -> bool:
    if source_table in COT_WITH_PERIOD_TABLE_OVERRIDES:
        return True
    if source_table in COT_WITHOUT_PERIOD_TABLE_OVERRIDES:
        return False

    report_type = clean_text(row.get("report_type"))
    business_desc = clean_text(row.get("business_desc"))
    hbase_table = clean_text(row.get("source_hbase_table"))
    if source_table.endswith("_p"):
        return True
    if "截P" in report_type or "截P" in business_desc or "收集项" in business_desc:
        return True
    if hbase_table.endswith("_p") or "_2026_p" in hbase_table:
        return True
    return False


def build_schedule_map(facts: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for schedule in facts.get("schedules", []):
        data_utilization = clean_text(schedule.get("data_utilization"))
        if data_utilization:
            result[data_utilization] = schedule
    return result


def build_target_mapping(facts: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in facts.get("target_mappings", []):
        data_utilization = clean_text(item.get("data_utilization"))
        if data_utilization:
            result[data_utilization] = item
    return result


def classify_source_group(source_table: str, with_period: bool) -> str:
    if source_table in COT_STORE_REPORT_GENERATOR_TABLES:
        return "store_report_generator"
    if source_table in COT_STORE_REPORT_TABLES:
        return "store_report"
    if with_period:
        return "report_ps_p"
    if source_table.startswith(("rpt_", "cot_", "supervisor_", "wechat_", "freshness_")):
        return "store_report_generator"
    return "report_ps_p"


def find_table_contract_issues(config: Dict[str, Any]) -> List[str]:
    """Return deterministic per-table blockers without guessing replacement columns."""
    fields = unique(clean_text(value) for value in config.get("fields", []))
    if not fields:
        return ["missing_field_dictionary"]

    required_columns = [clean_text(config.get("last_update_time_column"))]
    if config.get("sync_mode") == "with_period":
        required_columns.extend(
            [clean_text(config.get("period_column")), clean_text(config.get("code_column"))]
        )
    else:
        required_columns.append(clean_text(config.get("key_column")))
    required_columns.extend(clean_text(value) for value in config.get("rowkey_rule_columns", []))

    issues: List[str] = []
    if any(not column for column in required_columns):
        issues.append("missing_required_column_name")
    for column in unique(required_columns):
        if column not in fields:
            issues.append(f"column_not_in_fields:{column}")
    return unique(issues)


def build_table_configs(facts: Dict[str, Any], extracted_tables: Optional[Path]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    field_map = build_field_map(facts, extracted_tables)
    schedule_map = build_schedule_map(facts)
    target_map = build_target_mapping(facts)
    configs: Dict[str, Dict[str, Any]] = {}
    questions: List[str] = []

    for row in facts.get("cot_report_tables", []):
        clickhouse_full = clean_text(row.get("clickhouse_table"))
        clickhouse_database, doc_source_table = split_clickhouse_name(clickhouse_full)
        if not doc_source_table:
            continue

        source_table = normalize_cot_table_name(doc_source_table)
        fields = field_map.get(doc_source_table, [])
        with_period = is_with_period(row, source_table, fields)
        update_column = select_column(fields, DEFAULT_UPDATE_COLUMNS, "inksaa_last_modified_timestamp")
        period_column = select_column(fields, ["period"], "period") if with_period else ""
        code_column = select_column(fields, DEFAULT_CODE_COLUMNS, "code")
        key_column = select_column(fields, DEFAULT_KEY_COLUMNS, "id")

        if with_period:
            rowkey_rule_columns = [period_column, code_column]
        else:
            rowkey_rule_columns = [key_column]

        if not fields:
            questions.append(f"{source_table}: field dictionary was not available; verify update column and rowkey columns.")
        if with_period and code_column in {"id", "inksaa_id"}:
            questions.append(f"{source_table}: code column was inferred as {code_column}; verify COT rowkey business key.")
        if update_column == "inksaa_last_modified_timestamp" and update_column not in fields:
            questions.append(f"{source_table}: update timestamp column was defaulted to {update_column}; verify source schema.")

        mapping = target_map.get(doc_source_table, {})
        schedule = schedule_map.get(doc_source_table, {})
        hbase_table = COT_HBASE_TABLE_OVERRIDES.get(source_table, clean_text(row.get("source_hbase_table")))
        config = {
            "business_desc": clean_text(row.get("business_desc")),
            "report_type": clean_text(row.get("report_type")),
            "source_range": clean_text(row.get("source_range")),
            "source_group": classify_source_group(source_table, with_period),
            "sync_mode": "with_period" if with_period else "without_period",
            "document_table": doc_source_table,
            "mysql_table": source_table,
            "last_update_time_column": update_column,
            "period_column": period_column,
            "code_column": code_column,
            "key_column": key_column,
            "hbase_table": hbase_table,
            "rowkey_rule_columns": rowkey_rule_columns,
            "clickhouse_database": clickhouse_database,
            "clickhouse_table": source_table,
            "clickhouse_full_name": f"{clickhouse_database}.{source_table}" if clickhouse_database else source_table,
            "clickhouse_table_name": source_table,
            "dataengine_catalog": clean_text(mapping.get("catalog")) or source_table,
            "dataengine_hbase_target": clean_text(mapping.get("hbase_target")),
            "dataengine_clickhouse_target": clean_text(mapping.get("clickhouse_target")),
            "schedule": schedule,
            "fields": fields,
        }
        config["contract_issues"] = find_table_contract_issues(config)
        config["runtime_enabled"] = not config["contract_issues"]
        if config["contract_issues"]:
            questions.append(
                f"{source_table}: runtime is disabled until table contract issues are resolved: "
                + ", ".join(config["contract_issues"])
                + "."
            )
        configs[source_table] = config

    return configs, unique(questions)


def copy_template_tree(template_root: Path, output_dir: Path, force: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in template_root.rglob("*"):
        relative = source.relative_to(template_root)
        if source.is_dir():
            (output_dir / relative).mkdir(parents=True, exist_ok=True)
            continue
        target_name = relative.name.removesuffix(".template")
        target = output_dir / relative.parent / target_name
        if relative.parts and relative.parts[0] in FIXED_PLATFORM_PACKAGE_DIRS and target.exists():
            continue
        if target.exists() and not force:
            raise FileExistsError(f"{target} already exists. Re-run with --force to overwrite generated scaffold files.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def py_literal(value: Any) -> str:
    return pprint.pformat(value, width=120, sort_dicts=True)


def render_plugin_config(configs: Dict[str, Dict[str, Any]], project_name: str) -> str:
    with_period_tables = [name for name, item in configs.items() if item["sync_mode"] == "with_period"]
    without_period_tables = [name for name, item in configs.items() if item["sync_mode"] == "without_period"]
    store_report_generator_table_list = [
        name for name, item in configs.items() if item["source_group"] == "store_report_generator"
    ]
    store_report_table_list = [name for name, item in configs.items() if item["source_group"] == "store_report"]
    ck_legacy_database_tables = [
        item["clickhouse_table"] for item in configs.values() if item["clickhouse_database"] == "cot_report"
    ]
    ck_truncate_list = [name for name in ck_legacy_database_tables if name in COT_CLICKHOUSE_TRUNCATE_TABLES]
    hbase_truncate_list = [name for name in COT_HBASE_TRUNCATE_TABLES if name in {item["hbase_table"] for item in configs.values()}]
    runtime_table_configs = {
        name: {
            "mysql_table": item["mysql_table"],
            "last_update_time_column": item["last_update_time_column"],
            "period_column": item["period_column"],
            "code_column": item["code_column"],
            "key_column": item["key_column"],
            "hbase_table": item["hbase_table"],
            "rowkey_rule_columns": item["rowkey_rule_columns"],
            "clickhouse_table": item["clickhouse_table"],
            "source_group": item["source_group"],
            "sync_mode": item["sync_mode"],
            "contract_issues": item["contract_issues"],
            "runtime_enabled": item["runtime_enabled"],
        }
        for name, item in configs.items()
    }

    return f'''import os

from loguru import logger


env = os.environ.get("running_env") or "qa"
logger.info("running env: {{}}", env)

fs_root_dir = "/datahub/project_storage/{project_name}"

App_key = "<APP_KEY>"
App_secret = "<APP_SECRET>"

mysql_report_ps_p_url = "mysql+pymysql://<USER>:<PASSWORD>@<HOST>:<PORT>/report_ps_p?charset=utf8mb4"
mysql_store_report_generator_url = "mysql+pymysql://<USER>:<PASSWORD>@<HOST>:<PORT>/store_report_generator?charset=utf8mb4"
mysql_store_report_url = "mysql+pymysql://<USER>:<PASSWORD>@<HOST>:<PORT>/store_report?charset=utf8mb4"

mysql_report_ps_p_params = {{
    "host": "<MYSQL_HOST>",
    "port": 19923,
    "user": "<MYSQL_USER>",
    "password": "<MYSQL_PASSWORD>",
    "db": "report_ps_p",
    "charset": "utf8",
}}
mysql_store_report_generator_params = {{
    "host": "<MYSQL_HOST>",
    "port": 19923,
    "user": "<MYSQL_USER>",
    "password": "<MYSQL_PASSWORD>",
    "db": "store_report_generator",
    "charset": "utf8",
}}
mysql_store_report_params = {{
    "host": "<MYSQL_HOST>",
    "port": 19923,
    "user": "<MYSQL_USER>",
    "password": "<MYSQL_PASSWORD>",
    "db": "store_report",
    "charset": "utf8",
}}

cluster = "" if env in {{"qa", "uat"}} else "<CLICKHOUSE_CLUSTER>"

table_configs = {py_literal(runtime_table_configs)}

store_report_generator_table_list = {py_literal(store_report_generator_table_list)}
store_report_table_list = {py_literal(store_report_table_list)}
ck_legacy_database_tables = {py_literal(ck_legacy_database_tables)}
ck_truncate_list = {py_literal(ck_truncate_list)}
hbase_truncate_list = {py_literal(hbase_truncate_list)}

without_period_tables = {py_literal(without_period_tables)}
with_period_tables = {py_literal(with_period_tables)}
'''


def build_example_params(configs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not configs:
        return {}
    preferred = next((item for item in configs.values() if item["sync_mode"] == "with_period"), next(iter(configs.values())))
    source_info = {
        "mysql_table": preferred["mysql_table"],
        "last_update_time_column": preferred["last_update_time_column"],
        "batch_size": 100000,
        "receiver_emails": [],
    }
    if preferred["sync_mode"] == "with_period":
        source_info.update(
            {
                "period_column": preferred["period_column"],
                "period": ["<PERIOD>"],
                "code_column": preferred["code_column"],
            }
        )
    else:
        source_info["key_column"] = preferred["key_column"]
    return {
        "source_informations": source_info,
        "hbase_informations": {
            "hbase_table": preferred["hbase_table"],
            "rowkey_rule_columns": preferred["rowkey_rule_columns"],
        },
        "clickhouse_information": {
            "clickhouse_table": preferred["clickhouse_table"],
        },
    }


def render_rowkey_config(configs: Dict[str, Dict[str, Any]]) -> str:
    rules: Dict[str, Dict[str, Any]] = {}
    for source_table, item in configs.items():
        hbase_table = clean_text(item.get("hbase_table"))
        rowkey_columns = list(item.get("rowkey_rule_columns") or [])
        rules[hbase_table or source_table] = {
            "source_table": source_table,
            "sync_mode": item.get("sync_mode", ""),
            "candidate_columns": rowkey_columns,
            "columns": rowkey_columns,
            "separator": "",
            "prefix": {
                "enabled": True,
                "type": "last_char",
                "source": "joined_rowkey",
                "mod": 10,
            },
            "date_format": "",
            "example": "",
            "confirmed": False,
            "fill_notes": [
                "COT scaffold inferred columns from the field dictionary and sync mode.",
                "Confirm columns with requirement docs, production code, or deployment logs before production.",
                "If columns are changed here, also update cot_config.plugin_config.table_configs or runtime params.",
                "Default prefix mirrors current scaffold behavior: joined rowkey last character + joined rowkey.",
            ],
        }

    return f'''# coding: utf-8
"""HBase rowkey rules to confirm before deployment.

This file is the manual review surface for COT sync rowkeys.

Runtime note:
- The generated sync code currently reads rowkey columns from
  `cot_config.plugin_config.table_configs[*]["rowkey_rule_columns"]`
  or from `params["hbase_informations"]["rowkey_rule_columns"]`.
- After editing this file, copy the confirmed columns/prefix rule back to
  `plugin_config.py` or the runtime params used by DataEngine.

How to fill each rule:
- columns: exact exported DataFrame columns, in rowkey order.
- separator: string used to join columns; current COT scaffold uses "".
- prefix.enabled: true when HBase rowkey needs a leading bucket/hash prefix.
- prefix.type: current scaffold default is "last_char".
- prefix.source: current scaffold default is "joined_rowkey".
- prefix.mod: bucket count, usually 10 for row prefixes 0-9.
- date_format: fill only when date/period must be reformatted before joining.
- example: one real expected rowkey from requirement docs, production code, or deployment logs.
- confirmed: keep false until verified.

Do not guess rowkey rules. If confirmed=false, treat HBase write behavior as a
deployment confirmation item.
"""

hbase_rowkey_rules = {py_literal(rules)}
'''


def write_manifest(
    output_dir: Path,
    configs: Dict[str, Dict[str, Any]],
    questions: List[str],
    codegen_contract: Dict[str, Any],
) -> None:
    manifest = {
        "summary": {
            "table_count": len(configs),
            "with_period_count": len([item for item in configs.values() if item["sync_mode"] == "with_period"]),
            "without_period_count": len([item for item in configs.values() if item["sync_mode"] == "without_period"]),
        },
        "codegen_contract": codegen_contract,
        "tables": list(configs.values()),
        "questions": questions,
    }
    (output_dir / "cot_sync_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "params.example.json").write_text(
        json.dumps(build_example_params(configs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    question_lines = ["# Open Questions", ""]
    if questions:
        question_lines.extend(f"- {item}" for item in questions)
    else:
        question_lines.append("- No open questions detected by the scaffold script.")
    (output_dir / "questions.md").write_text("\n".join(question_lines) + "\n", encoding="utf-8")

    verification = [
        "# Verification Notes",
        "",
        "- Local check: run `python -m py_compile` for generated Python files.",
        "- Local check: parse `params.example.json` and `cot_sync_manifest.json` as JSON.",
        "- Contract check: run `verify_cot_manifest_semantics.py --project-dir <project>` to validate every table; add `--strict-deployment` only for deployment review.",
        "- Deployment check: verify logs for source table, sync mode, period/timestamp range, exported rows, HBase rows, ClickHouse rows, and final DataEngine metrics.",
        "- Credentials are placeholders; fill app keys, database hosts, passwords, and cluster only in the deployment environment.",
    ]
    (output_dir / "verification.md").write_text("\n".join(verification) + "\n", encoding="utf-8")


def scaffold_project(args: argparse.Namespace) -> None:
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    template_root = skill_dir / "assets" / "minimal_sync_project"

    facts = load_json(args.structured_facts)
    codegen_contract = facts.get("codegen_contract", {})
    if codegen_contract and (
        codegen_contract.get("project_type") != "data-sync"
        or codegen_contract.get("component_kind") == "bysku_report_pipeline"
    ):
        raise ValueError(
            "codegen_contract routes this design package to report-codegen, not data-sync-codegen."
        )
    if codegen_contract and not codegen_contract.get("ready_for_codegen", False) and not args.allow_blocked_scaffold:
        blockers = "; ".join(str(item) for item in codegen_contract.get("blockers", [])) or "unresolved design blockers"
        raise ValueError(
            "codegen_contract blocks full scaffolding: "
            f"{blockers}. Re-run with --allow-blocked-scaffold only for an explicitly requested safe scaffold."
        )
    configs, questions = build_table_configs(facts, args.extracted_tables)

    copy_template_tree(template_root, args.output_dir, args.force)
    config_path = args.output_dir / "cot_config" / "plugin_config.py"
    config_path.write_text(render_plugin_config(configs, args.project_name), encoding="utf-8")
    rowkey_config_path = args.output_dir / "cot_config" / "rowkey_config.py"
    rowkey_config_path.write_text(render_rowkey_config(configs), encoding="utf-8")
    write_manifest(args.output_dir, configs, questions, facts.get("codegen_contract", {}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structured-facts", type=Path, required=True, help="Path to structured_facts.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Target project directory to scaffold.")
    parser.add_argument("--extracted-tables", type=Path, default=None, help="Optional extracted_tables directory with embedded CSV field dictionaries.")
    parser.add_argument("--project-name", default="cot_2026_sync", help="Project storage name used in placeholder fs_root_dir.")
    parser.add_argument("--force", action="store_true", help="Overwrite files generated by this scaffold.")
    parser.add_argument(
        "--allow-blocked-scaffold",
        action="store_true",
        help="Generate a safe placeholder scaffold even when codegen_contract is blocked.",
    )
    return parser.parse_args()


def main() -> None:
    scaffold_project(parse_args())


if __name__ == "__main__":
    main()
