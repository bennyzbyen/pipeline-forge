#!/usr/bin/env python3
"""Exercise generated generic standard/bySKU report projects without external services."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from scaffold_report_project import scaffold
from verify_codegen_observability import verify as verify_observability
from verify_report_plan_semantics import validate_project


COMPONENT_KINDS = ("standard_report", "bysku_report_pipeline")


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.events: List[Any] = []

    def command(self, sql: str):
        self.events.append(("command", sql))

    def insert_df(self, table: str, df: pd.DataFrame):
        self.events.append(("insert_df", table, df.copy()))


def fake_insert_file(client, table: str, file_path: str, column_names: List[str], database: str, settings: Dict[str, Any]):
    client.events.append(("insert_file", database, table, list(column_names), Path(file_path).read_bytes(), dict(settings)))


def build_plan(component_kind: str) -> Dict[str, Any]:
    columns = ["region", "period", "revenue", "store_count", "avg_revenue"]
    rules = [
        {"target_field": column, "source_field": column, "calculation_logic": "normalized execution contract"}
        for column in columns
    ]
    contract = {
        "version": 2,
        "parameters": [
            {
                "name": "target_date",
                "type": "date-list",
                "accepted_shapes": ["scalar", "list"],
                "default_on": ["omitted", "null", "blank", "empty"],
                "default": {"kind": "relative_date", "days": -1, "format": "%Y-%m-%d"},
                "normalize_to": "list",
                "deduplicate": True,
                "preserve_order": True,
                "semantics": {
                    "omitted": "default to T-1",
                    "null": "default to T-1",
                    "blank": "default to T-1",
                    "empty": "default to T-1",
                    "scalar": "normalize to a one-item list",
                    "list": "preserve order and deduplicate",
                    "invalid": "raise ValueError",
                },
            }
        ],
        "runtime": {
            "python_min": "3.8",
            "entrypoint": "plugin_main.py",
            "default_environment": "qa",
            "result_protocol": {"method": "put", "scope": "inst", "level": "task", "body_key": "metrics"},
            "environment_connection_matrix": {
                "dev": {"connection_mode": "direct"},
                "qa": {"connection_mode": "managed"},
                "prod": {"connection_mode": "managed"},
            },
            "safe_log_policy": {"log_credentials": False, "log_parameter_values": False},
        },
        "sources": {
            "orders": {
                "kind": "injected",
                "columns": ["store_code", "period", "amount", "quantity", "status"],
            },
            "stores": {
                "kind": "injected",
                "columns": ["store_code", "region"],
            },
        },
        "steps": [
            {
                "id": "period_orders",
                "op": "filter",
                "input": "orders",
                "conditions": [
                    {"column": "period", "operator": "eq", "value_from": "time_range.period"},
                    {"column": "status", "operator": "eq", "value": "valid"},
                ],
            },
            {
                "id": "valued_orders",
                "op": "derive",
                "input": "period_orders",
                "columns": {
                    "revenue": {
                        "op": "multiply",
                        "operands": [{"column": "amount"}, {"column": "quantity"}],
                    }
                },
            },
            {
                "id": "joined_orders",
                "op": "join",
                "left": "valued_orders",
                "right": "stores",
                "on": ["store_code"],
                "how": "inner",
            },
            {
                "id": "region_summary",
                "op": "aggregate",
                "input": "joined_orders",
                "group_by": ["region", "period"],
                "aggregations": {
                    "revenue": {"column": "revenue", "agg": "sum"},
                    "store_count": {"column": "store_code", "agg": "nunique"},
                },
            },
            {
                "id": "region_kpis",
                "op": "derive",
                "input": "region_summary",
                "columns": {
                    "avg_revenue": {
                        "op": "divide",
                        "operands": [{"column": "revenue"}, {"column": "store_count"}],
                        "fill_value": 0,
                    }
                },
            },
            {
                "id": "final_output",
                "op": "project",
                "input": "region_kpis",
                "columns": columns,
            },
        ],
        "outputs": {
            "region_sales": {
                "input": "final_output",
                "columns": columns,
            }
        },
        "writes": {
            "region_sales": {
                "kind": "clickhouse",
                "table": "qa.region_sales",
                "mode": "replace_where",
                "predicate": {"column": "period", "value_from": "time_range.period"},
                "columns": columns,
                "column_types": ["String", "String", "Decimal(18,2)", "UInt64", "Decimal(18,2)"],
                "transport": "insert_file" if component_kind == "bysku_report_pipeline" else "insert_df",
                "empty_output_policy": "block_destructive_replace",
                "staging_wire_format": {
                    "encoding": "utf-8",
                    "bom": False,
                    "header": False,
                    "null": "\\N",
                    "datetime_precision": "seconds",
                    "integer_format": "integer",
                    "explicit_columns": True,
                },
                "replacement_safety": {
                    "strategy": "delete_then_insert",
                    "non_atomic_risk_acknowledged": True,
                },
            }
        },
    }
    return {
        "summary": {
            "source_count": 2,
            "physical_target_count": 1,
            "logical_target_count": 1,
            "output_count": 1,
            "schedule_count": 1,
            "component_kind": component_kind,
            "design_ready_for_codegen": True,
            "implementation_ready": True,
            "ready_for_codegen": True,
        },
        "sources": {
            "hbase": [],
            "fs": [],
            "mssql": [],
            "mysql": [],
            "other": [
                {"table_or_path": "orders", "table_names": ["orders"], "fields": contract["sources"]["orders"]["columns"]},
                {"table_or_path": "stores", "table_names": ["stores"], "fields": contract["sources"]["stores"]["columns"]},
            ],
        },
        "physical_targets": [{"table": "qa.region_sales", "storage": "clickhouse", "description": "fixture"}],
        "logical_targets": [{"target_name": "region_sales", "storage": "clickhouse", "description": "fixture"}],
        "outputs": [
            {
                "target_name": "region_sales",
                "target_description": "fixture",
                "physical_table": "qa.region_sales",
                "storage": "clickhouse",
                "field_count": len(rules),
                "final_columns": columns,
                "field_rules": rules,
            }
        ],
        "schedules": [{}],
        "component_hints": [],
        "codegen_contract": {
            "contract_version": 2,
            "project_type": "report",
            "component_kind": component_kind,
            "ready_for_codegen": True,
            "blockers": [],
            "validation_result": {
                "status": "passed",
                "deployment_status": "ready",
                "errors": [],
                "deployment_blockers": [],
                "warnings": [],
            },
        },
        "execution_contract": contract,
        "execution_validation": {"status": "passed", "error_count": 0, "warning_count": 0, "errors": [], "warnings": []},
        "handoff_readiness": [],
        "inferences": [],
    }


def purge_generated_modules() -> None:
    prefixes = ("common_utils", "data_utils", "gateway", "params_configs")
    for name in list(sys.modules):
        if name in prefixes or name.startswith(tuple(prefix + "." for prefix in prefixes)):
            sys.modules.pop(name, None)


def run_case(component_kind: str, temp_root: Path) -> Dict[str, Any]:
    case_dir = temp_root / component_kind
    plan_path = case_dir / "input_plan.json"
    project_dir = case_dir / "project"
    case_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(build_plan(component_kind), ensure_ascii=False, indent=2), encoding="utf-8")
    scaffold(plan_path, project_dir)

    verification = validate_project(project_dir)
    assert verification["status"] == "passed", verification
    assert verification["implementation_ready"] is True, verification
    assert verification["deployment_status"] == "ready", verification
    observability = verify_observability(project_dir)
    assert observability["status"] == "passed", observability
    for name in ["data_source.py", "data_process.py", "data_storage.py"]:
        content = (project_dir / "data_utils" / name).read_text(encoding="utf-8")
        assert "NotImplementedError" not in content, name

    purge_generated_modules()
    sys.path.insert(0, str(project_dir))
    try:
        DataSource = importlib.import_module("data_utils.data_source").DataSource
        DataProcess = importlib.import_module("data_utils.data_process").DataProcess
        DataStorage = importlib.import_module("data_utils.data_storage").DataStorage
        runtime_contract = importlib.import_module("common_utils.runtime_contract")

        fixed_today = __import__("datetime").date(2026, 8, 27)
        normalized = runtime_contract.normalize_parameters({}, build_plan(component_kind)["execution_contract"], today=fixed_today)
        assert normalized["target_date"] == ["2026-08-26"], normalized
        normalized = runtime_contract.normalize_parameters(
            {"target_date": ["2026-08-25", "2026-08-24", "2026-08-25"]},
            build_plan(component_kind)["execution_contract"],
            today=fixed_today,
        )
        assert normalized["target_date"] == ["2026-08-25", "2026-08-24"], normalized
        try:
            runtime_contract.normalize_parameters({"target_date": {"bad": True}}, build_plan(component_kind)["execution_contract"], today=fixed_today)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid non-empty target_date shape must fail")

        params = {
            "period": "2026P01",
            "current_date": "2026-01-31",
            "source_data": {
                "orders": pd.DataFrame(
                    [
                        {"store_code": "S1", "period": "2026P01", "amount": 10.0, "quantity": 2, "status": "valid"},
                        {"store_code": "S2", "period": "2026P01", "amount": 5.0, "quantity": 3, "status": "valid"},
                        {"store_code": "S1", "period": "2026P01", "amount": 99.0, "quantity": 1, "status": "cancelled"},
                        {"store_code": "S3", "period": "2025P13", "amount": 8.0, "quantity": 1, "status": "valid"},
                    ]
                ),
                "stores": pd.DataFrame(
                    [
                        {"store_code": "S1", "region": "East"},
                        {"store_code": "S2", "region": "East"},
                        {"store_code": "S3", "region": "West"},
                    ]
                ),
            },
            "clickhouse_insert_file": fake_insert_file,
        }
        source_data, time_range = DataSource(params).run()
        outputs = DataProcess(source_data, time_range, params).run()
        result = outputs["region_sales"]
        assert list(result.columns) == ["region", "period", "revenue", "store_count", "avg_revenue"], result
        assert len(result) == 1, result
        row = result.iloc[0]
        assert row["region"] == "East", result
        assert row["revenue"] == 35.0, result
        assert row["store_count"] == 2, result
        assert row["avg_revenue"] == 17.5, result

        client = FakeClickHouseClient()
        params["clickhouse_client"] = client
        metrics = DataStorage(outputs, time_range, params).run()
        expected_insert_event = "insert_file" if component_kind == "bysku_report_pipeline" else "insert_df"
        assert [event[0] for event in client.events] == ["command", expected_insert_event], client.events
        assert "DELETE WHERE period = '2026P01'" in client.events[0][1], client.events
        assert metrics[0]["rows"] == 1, metrics
        if component_kind == "bysku_report_pipeline":
            payload = client.events[1][4]
            assert not payload.startswith(b"\xef\xbb\xbf"), payload
            assert b"region,period" not in payload, payload
            assert b",2," in payload and b",2.0," not in payload, payload

            wire_client = FakeClickHouseClient()
            wire_params = dict(params, clickhouse_client=wire_client)
            nullable_result = result.copy()
            nullable_result.loc[0, "region"] = None
            DataStorage({"region_sales": nullable_result}, time_range, wire_params).run()
            assert b"\\N," in wire_client.events[1][4], wire_client.events[1][4]

        empty_client = FakeClickHouseClient()
        empty_params = dict(params, clickhouse_client=empty_client)
        empty_metrics = DataStorage({"region_sales": result.iloc[0:0]}, time_range, empty_params).run()
        assert not empty_client.events, empty_client.events
        assert empty_metrics[0]["status"] == "skipped_empty", empty_metrics
    finally:
        sys.path.remove(str(project_dir))
        purge_generated_modules()

    return {
        "component_kind": component_kind,
        "status": "passed",
        "output_rows": 1,
        "output_columns": 5,
        "write_event_count": 2,
        "empty_output_write_event_count": 0,
        "observability_status": observability["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component-kind", choices=[*COMPONENT_KINDS, "all"], default="all")
    args = parser.parse_args()
    selected = COMPONENT_KINDS if args.component_kind == "all" else (args.component_kind,)
    with tempfile.TemporaryDirectory(prefix="report_contract_semantics_") as temp_dir:
        results = [run_case(component_kind, Path(temp_dir)) for component_kind in selected]
    print(json.dumps({"status": "passed", "case_count": len(results), "cases": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
