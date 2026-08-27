#!/usr/bin/env python3
"""Regression-test deterministic job-log classifications with synthetic evidence only."""

from __future__ import annotations

import argparse
import json
from typing import Any

from analyze_data_job_log import analyze_log


CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "platform_params",
        "expected_id": "wrapped_single_params",
        "expected_category": "params",
        "log": """2026-08-27 INFO algorithm_io_mode=SINGLE body params received
Traceback (most recent call last):
  File \"plugin_main.py\", line 20, in run
    table = params[\"source_informations\"]
KeyError: 'source_informations'
""",
    },
    {
        "name": "gateway_initialization",
        "expected_id": "gateway_client_failure",
        "expected_category": "gateway",
        "log": """2026-08-27 INFO running env=qa params loaded
2026-08-27 ERROR gateway request failed
Traceback (most recent call last):
  File \"platform_client.py\", line 12, in connect
    raise RuntimeError('Gateway unavailable')
RuntimeError: GatewayUnavailable
""",
    },
    {
        "name": "hbase_write",
        "expected_id": "hbase_operation_failure",
        "expected_category": "hbase",
        "log": """2026-08-27 INFO running env=qa params table=fixture_source
2026-08-27 INFO gateway client ready
2026-08-27 ERROR hbase insert failed table=fixture_target
Traceback (most recent call last):
  File \"hbase_writer.py\", line 30, in write
    raise RuntimeError('HBaseTimeout')
RuntimeError: HBaseTimeout
""",
    },
    {
        "name": "fs_transfer",
        "expected_id": "fs_operation_failure",
        "expected_category": "fs",
        "log": """2026-08-27 INFO running env=qa params file=<FIXTURE_PATH>
2026-08-27 INFO gateway client ready
2026-08-27 ERROR fs upload failed path=<FIXTURE_PATH>
Traceback (most recent call last):
  File \"fs_writer.py\", line 18, in upload
    raise RuntimeError('FSUnavailable')
RuntimeError: FSUnavailable
""",
    },
    {
        "name": "clickhouse_target",
        "expected_id": "clickhouse_table_or_cluster",
        "expected_category": "clickhouse",
        "log": """2026-08-27 INFO running env=qa params table=fixture_output
2026-08-27 INFO hbase insert complete rows=2
Traceback (most recent call last):
  File \"clickhouse_writer.py\", line 42, in write
    raise RuntimeError('UNKNOWN_TABLE fixture_output')
RuntimeError: UNKNOWN_TABLE fixture_output
""",
    },
    {
        "name": "source_data_absence",
        "expected_id": "no_changed_data",
        "expected_category": "data_absence",
        "log": """2026-08-27 INFO running env=qa params period=2026P08
2026-08-27 INFO mysql source query complete rows=0
2026-08-27 WARNING Source table returns zero rows; no_changed_periods
""",
    },
    {
        "name": "deployment_import",
        "expected_id": "dependency_or_import",
        "expected_category": "environment",
        "log": """2026-08-27 INFO deployment stage=module_load running env=qa params loaded
Traceback (most recent call last):
  File \"plugin_main.py\", line 4, in <module>
    import fixture_dependency
ModuleNotFoundError: No module named 'fixture_dependency'
""",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    results: list[dict[str, Any]] = []
    for case in CASES:
        first = analyze_log(case["log"])
        second = analyze_log(case["log"])
        assert first == second, f"{case['name']}: classification was not deterministic"
        assert first["primary_pattern_id"] == case["expected_id"], (case["name"], first)
        assert first["primary_classification"] == case["expected_category"], (case["name"], first)
        results.append(
            {
                "case": case["name"],
                "status": "passed",
                "pattern_id": first["primary_pattern_id"],
                "category": first["primary_classification"],
            }
        )
    print(json.dumps({"status": "passed", "case_count": len(results), "cases": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
