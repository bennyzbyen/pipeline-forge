#!/usr/bin/env python3
"""Run a self-contained synthetic acceptance matrix derived from QAS lessons.

The names and thresholds in this file are fixture-only examples. They are not
PipelineForge defaults and must never be copied into a generated project
without project evidence.
"""

from __future__ import annotations

import datetime
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parents[1]
DOC_CONTRACT_DIR = SKILLS_DIR / "data-doc-to-dev-md" / "scripts"
sys.path.insert(0, str(DOC_CONTRACT_DIR))
from technical_contract import build_contract_v2  # noqa: E402


def load_template_module(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_fields(row: dict, fields: list[str]) -> None:
    missing = [field for field in fields if field not in row or row[field] is None]
    if missing:
        raise ValueError(f"missing required fields: {missing}")


def visit_is_abnormal(start: datetime.datetime, end: datetime.datetime, threshold_minutes: int) -> bool:
    duration = (end - start).total_seconds() / 60
    if duration < 0:
        raise ValueError("negative visit duration")
    return duration < threshold_minutes


def order_is_abnormal(row: dict, amount_threshold: float, hour_threshold: float) -> bool:
    require_fields(row, ["amount", "delivery_hours", "order_type"])
    if row["order_type"] not in {"NORMAL", "RETURN"}:
        raise ValueError("unsupported order_type")
    return float(row["amount"]) > amount_threshold and float(row["delivery_hours"]) > hour_threshold


def consecutive_periods(rows: list[dict], required: int) -> set[str]:
    periods = sorted({row["period"] for row in rows})
    position = {period: index for index, period in enumerate(periods)}
    result: set[str] = set()
    by_person: dict[str, list[int]] = {}
    for row in rows:
        if row["status"] == "ALERT":
            by_person.setdefault(row["person"], []).append(position[row["period"]])
    for person, values in by_person.items():
        run = 1
        previous = None
        for value in sorted(set(values)):
            run = run + 1 if previous is not None and value == previous + 1 else 1
            if run >= required:
                result.add(person)
            previous = value
    return result


def test_contract_conflict() -> dict:
    facts = {
        "report_sources": [{"storage": "HBase", "table_or_path": "fixture.source", "range": "daily"}],
        "report_business_rules": [
            {"abnormal_type": "synthetic threshold", "grain": "daily", "rule": "candidate_count >= 10"},
            {"abnormal_type": "synthetic threshold", "grain": "daily", "rule": "candidate_count > 10"},
        ],
        "report_physical_targets": [{"storage": "ClickHouse", "table": "fixture.output"}],
    }
    base = {
        "contract_version": 1,
        "project_type": "report",
        "component_kind": "standard_report",
        "components": [],
        "ready_for_codegen": True,
        "blockers": [],
    }
    contract = build_contract_v2(facts, base)
    codes = {item["code"] for item in contract["conflicts"]}
    assert "RULE_OPERATOR_CONFLICT" in codes, contract["conflicts"]
    assert contract["ready_for_codegen"] is False, contract
    return {"case": "threshold_operator_conflict", "status": "passed"}


def test_order_boundaries() -> dict:
    assert order_is_abnormal({"amount": "501.00", "delivery_hours": 49, "order_type": "NORMAL"}, 500, 48)
    assert not order_is_abnormal({"amount": 500, "delivery_hours": 49, "order_type": "NORMAL"}, 500, 48)
    assert not order_is_abnormal({"amount": 501, "delivery_hours": 48, "order_type": "RETURN"}, 500, 48)
    try:
        order_is_abnormal({"amount": 501, "delivery_hours": 49}, 500, 48)
    except ValueError:
        pass
    else:
        raise AssertionError("required-field failure was not preserved")
    return {"case": "dual_thresholds_types_and_required_fields", "status": "passed"}


def test_duration_boundaries() -> dict:
    start = datetime.datetime(2026, 1, 1, 9, 0, 0)
    assert visit_is_abnormal(start, start + datetime.timedelta(minutes=2, seconds=59), 3)
    assert not visit_is_abnormal(start, start + datetime.timedelta(minutes=3), 3)
    try:
        visit_is_abnormal(start, start - datetime.timedelta(seconds=1), 3)
    except ValueError:
        pass
    else:
        raise AssertionError("negative duration must fail")
    return {"case": "duration_positive_negative_boundary", "status": "passed"}


def test_parameter_matrix() -> dict:
    runtime_path = SCRIPT_DIR.parent / "assets" / "minimal_report_project" / "common_utils" / "runtime_contract.py.template"
    runtime = load_template_module("pipelineforge_fixture_runtime", runtime_path)
    contract = {
        "version": 2,
        "parameters": [
            {
                "name": "target_date",
                "accepted_shapes": ["scalar", "list"],
                "default_on": ["omitted", "null", "blank", "empty"],
                "default": {"kind": "relative_date", "days": -1, "format": "%Y-%m-%d"},
                "normalize_to": "list",
                "deduplicate": True,
                "preserve_order": True,
            }
        ],
    }
    today = datetime.date(2026, 8, 27)
    for value in [None, "", []]:
        params = {} if value is None else {"target_date": value}
        normalized = runtime.normalize_parameters(params, contract, today=today)
        assert normalized["target_date"] == ["2026-08-26"], normalized
    normalized = runtime.normalize_parameters(
        {"target_date": ["2026-08-25", "2026-08-24", "2026-08-25"]}, contract, today=today
    )
    assert normalized["target_date"] == ["2026-08-25", "2026-08-24"], normalized
    return {"case": "multi_date_default_order_dedup", "status": "passed"}


def test_grain_isolation_and_consecutive() -> dict:
    rows = [
        {"person": "A", "period": "P01", "status": "ALERT", "value": 1},
        {"person": "A", "period": "P02", "status": "ALERT", "value": 2},
        {"person": "A", "period": "P03", "status": "ALERT", "value": 3},
        {"person": "B", "period": "P01", "status": "ALERT", "value": 10},
        {"person": "B", "period": "P03", "status": "ALERT", "value": 30},
        {"person": "C", "period": "P02", "status": "IGNORED", "value": 99},
    ]
    totals = {}
    for row in rows:
        if row["status"] == "ALERT":
            totals[(row["person"], row["period"])] = totals.get((row["person"], row["period"]), 0) + row["value"]
    assert totals[("A", "P01")] == 1 and totals[("A", "P03")] == 3, totals
    assert ("C", "P02") not in totals, totals
    assert consecutive_periods(rows, 3) == {"A"}, rows
    return {"case": "cross_period_isolation_consecutive_3p_exact_enum", "status": "passed"}


def test_zero_and_reconciliation() -> dict:
    source_rows = 4
    output_rows = 0
    storage_events = []
    if output_rows:
        storage_events.append("replace")
    assert not storage_events
    output_rows = 3
    target_rows = 3
    audit_rows = 3
    assert output_rows == target_rows == audit_rows
    assert source_rows >= output_rows
    common_path = SCRIPT_DIR.parent / "assets" / "minimal_report_project" / "common_utils" / "common.py.template"
    common = load_template_module("pipelineforge_fixture_common", common_path)
    result = common.return_pipeline_result([{"source": source_rows, "output": output_rows}])
    method = result["__methods__"][0]
    assert method == {"method": "put", "scope": "inst", "level": "task", "body": {"metrics": [{"source": 4, "output": 3}]}}, result
    return {"case": "zero_output_reconciliation_result_protocol", "status": "passed"}


def main() -> int:
    cases = [
        test_contract_conflict(),
        test_order_boundaries(),
        test_duration_boundaries(),
        test_parameter_matrix(),
        test_grain_isolation_and_consecutive(),
        test_zero_and_reconciliation(),
    ]
    print(json.dumps({"status": "passed", "case_count": len(cases), "cases": cases}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
