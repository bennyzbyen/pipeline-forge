#!/usr/bin/env python3
"""Apply a selected sync code unit and write its immutable audit artifacts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Mapping


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def table_name(value: Any) -> str:
    text = clean_text(value)
    return text.rsplit(".", 1)[-1] if text else ""


def unit_codegen_contract(unit: Dict[str, Any], legacy: Dict[str, Any]) -> Dict[str, Any]:
    readiness = unit.get("readiness") if isinstance(unit.get("readiness"), dict) else {}
    execution = unit.get("execution_contract") if isinstance(unit.get("execution_contract"), dict) else {}
    ready = readiness.get("ready_for_codegen") is True
    return {
        **legacy,
        "project_type": "data-sync",
        "component_kind": unit.get("component_kind", "cot_table_sync"),
        "components": [
            {
                "name": unit.get("code_unit_id", ""),
                "kind": unit.get("component_kind", "cot_table_sync"),
                "role": unit.get("split_reason", "Confirmed code-unit execution boundary."),
                "status": "confirmed" if ready else "blocked",
            }
        ],
        "runtime_contract": execution.get("runtime_contract") or legacy.get("runtime_contract", {}),
        "write_contracts": execution.get("write_contracts") or legacy.get("write_contracts", []),
        "ready_for_codegen": ready,
        "blockers": list(readiness.get("blockers") or []),
        "conflicts": list(unit.get("conflicts") or []),
        "validation_result": {
            "status": "passed",
            "deployment_status": "ready" if ready else "review_required",
            "errors": [],
            "deployment_blockers": [],
            "warnings": [],
        },
        "selected_code_unit_id": unit.get("code_unit_id", ""),
    }


def facts_for_code_unit(facts: Dict[str, Any], unit: Dict[str, Any]) -> Dict[str, Any]:
    selected = copy.deepcopy(facts)
    covered = {clean_text(item).lower() for item in unit.get("covered_tables", []) if clean_text(item)}
    execution = unit.get("execution_contract") if isinstance(unit.get("execution_contract"), dict) else {}
    for item in execution.get("tables", []) if isinstance(execution.get("tables"), list) else []:
        if isinstance(item, str):
            covered.add(clean_text(item).lower())
        elif isinstance(item, Mapping):
            for key in ("table", "source_table", "target_table"):
                if clean_text(item.get(key)):
                    covered.add(clean_text(item.get(key)).lower())
    if covered:
        selected["cot_report_tables"] = [
            row
            for row in selected.get("cot_report_tables", [])
            if {
                clean_text(row.get("clickhouse_table")).lower(),
                clean_text(row.get("source_hbase_table")).lower(),
                table_name(row.get("clickhouse_table")).lower(),
            }.intersection(covered)
        ]
    selected["codegen_contract"] = unit_codegen_contract(unit, selected.get("codegen_contract", {}))
    return selected


def write_code_unit_artifacts(output_dir: Path, unit: Dict[str, Any] | None) -> None:
    if not unit:
        return
    (output_dir / "CODE_UNIT_CONTRACT.json").write_text(
        json.dumps(
            {"snapshot_mode": "read_only", "code_unit_id": unit.get("code_unit_id", ""), "contract": unit},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = output_dir / "tests"
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
    assert (root / "cot_config" / "plugin_config.py").exists()
'''
    (tests_dir / "test_code_unit_contract.py").write_text(content, encoding="utf-8")
