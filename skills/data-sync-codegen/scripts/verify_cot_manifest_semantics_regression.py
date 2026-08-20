#!/usr/bin/env python3
"""Regression-test positive and blocked all-table manifest contracts offline."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

from scaffold_cot_sync_project import scaffold_project
from verify_cot_manifest_semantics import validate_project


def facts_for(table_name: str, fields: list[str]) -> Dict[str, Any]:
    return {
        "codegen_contract": {
            "project_type": "data-sync",
            "component_kind": "cot_table_sync",
            "ready_for_codegen": True,
            "blockers": [],
        },
        "cot_report_tables": [
            {
                "business_desc": "fixture table",
                "report_type": "截P报表" if table_name.endswith("_p") else "执行报表",
                "source_range": "2026P01~",
                "source_hbase_table": f"l2_fixture.{table_name}",
                "clickhouse_table": f"cot_report_2026.{table_name}",
            }
        ],
        "field_dictionaries": [
            {
                "inferred_data_utilization": table_name,
                "first_fields": fields,
            }
        ],
        "target_mappings": [
            {
                "data_utilization": table_name,
                "catalog": table_name,
                "hbase_target": f"hbase_{table_name}",
                "clickhouse_target": f"clickhouse_{table_name}",
            }
        ],
        "schedules": [
            {
                "data_utilization": table_name,
                "task_name": "incr_sync_hbase_and_clickhouse",
                "schedule": "daily",
            }
        ],
    }


def generate(facts: Dict[str, Any], target: Path) -> None:
    facts_path = target.parent / f"{target.name}_facts.json"
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    scaffold_project(
        SimpleNamespace(
            structured_facts=facts_path,
            output_dir=target,
            extracted_tables=None,
            project_name=target.name,
            force=True,
            allow_blocked_scaffold=False,
        )
    )


def run_regression() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cot_manifest_semantics_") as temp_dir:
        root = Path(temp_dir)
        good_project = root / "good_project"
        generate(
            facts_for(
                "fixture_report_p",
                ["id", "inksaa_last_modified_timestamp", "period", "code", "amount"],
            ),
            good_project,
        )
        good = validate_project(good_project)
        assert good["status"] == "passed", good
        assert good["checked_table_count"] == 1, good
        assert good["tables"][0]["error_count"] == 0, good
        good_manifest = json.loads((good_project / "cot_sync_manifest.json").read_text(encoding="utf-8"))
        assert good_manifest["tables"][0]["runtime_enabled"] is True, good_manifest
        assert good_manifest["tables"][0]["contract_issues"] == [], good_manifest

        blocked_project = root / "blocked_project"
        generate(
            facts_for(
                "freshness_report",
                ["id", "inksaa_last_modified_timestamp", "store_code", "amount"],
            ),
            blocked_project,
        )
        blocked = validate_project(blocked_project)
        assert blocked["status"] == "failed", blocked
        error_codes = {item["code"] for item in blocked["errors"]}
        assert "column_not_in_fields" in error_codes, blocked
        blocked_manifest = json.loads((blocked_project / "cot_sync_manifest.json").read_text(encoding="utf-8"))
        table = blocked_manifest["tables"][0]
        assert table["runtime_enabled"] is False, table
        assert "column_not_in_fields:period" in table["contract_issues"], table

    return {
        "status": "passed",
        "case_count": 2,
        "cases": [
            {"case": "valid_all_table_contract", "status": "passed", "checked_tables": 1},
            {
                "case": "invalid_period_contract_runtime_guard",
                "status": "passed",
                "expected_verifier_status": "failed",
                "runtime_enabled": False,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
