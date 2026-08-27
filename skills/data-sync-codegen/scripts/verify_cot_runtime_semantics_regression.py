#!/usr/bin/env python3
"""Generate a synthetic COT scaffold and exercise its fake runtime offline."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from verify_cot_manifest_semantics_regression import facts_for, generate
from verify_cot_runtime_semantics import run_verification


def run_regression() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="cot_runtime_semantics_") as temp_dir:
        project_dir = Path(temp_dir) / "synthetic_project"
        facts = facts_for(
            "ic_detail_gb_p",
            ["id", "inksaa_last_modified_timestamp", "period", "code", "amount"],
        )
        without_period_facts = facts_for(
            "rpt_exe_visit_frequency_by_people",
            ["id", "inksaa_last_modified_timestamp", "store_code", "amount"],
        )
        for key in ("cot_report_tables", "field_dictionaries", "target_mappings", "schedules"):
            facts[key].extend(without_period_facts[key])
        generate(
            facts,
            project_dir,
        )
        result = run_verification(project_dir)
        assert result["status"] == "ok", result
        assert result["case_count"] == 7, result
        cases = result["cases"]
        assert isinstance(cases, list), result
        case_names = {case["case"] for case in cases}
        assert case_names == {
            "plugin_main_defaults",
            "hbase_final_request",
            "with_period_manual",
            "with_period_incremental",
            "with_period_no_changes",
            "without_period_changed",
            "without_period_no_changes",
        }, result

    return {
        "status": "passed",
        "case_count": len(case_names),
        "cases": sorted(case_names),
        "external_service_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
