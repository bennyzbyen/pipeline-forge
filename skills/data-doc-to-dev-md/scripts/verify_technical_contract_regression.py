#!/usr/bin/env python3
"""Regression-test technical contract v2 and legacy v1 compatibility."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from extract_docx_bundle import build_codegen_contract, build_question_groups_v2, write_questions_v2
from technical_contract import build_contract_v2, validate_contract


def complete_facts() -> dict:
    semantics = {
        "omitted": "automatic range",
        "null": "automatic range",
        "blank": "automatic range",
        "empty": "automatic range",
        "scalar": "one explicit range",
        "list": "ordered explicit ranges",
        "invalid": "raise ValueError",
    }
    return {
        "report_sources": [
            {
                "storage": "HBase",
                "table_or_path": "fixture.source",
                "range": "one business date",
                "fields": ["business_date", "value"],
                "final_request_validation": "assert wrapper final request equals the declared range and prefixes",
            }
        ],
        "report_field_mappings": [
            {
                "inferred_physical_table": "fixture.output",
                "fields": [
                    {
                        "target_field": "business_date",
                        "field_name": "business date",
                        "source_table": "fixture.source",
                        "source_field": "business_date",
                        "calculation_logic": "copy source field",
                        "field_type": "Date",
                    },
                    {
                        "target_field": "value",
                        "field_name": "metric value",
                        "source_table": "fixture.source",
                        "source_field": "value",
                        "calculation_logic": "copy source field",
                        "field_type": "Int64",
                    },
                ],
            }
        ],
        "report_physical_targets": [
            {
                "storage": "ClickHouse",
                "table": "fixture.output",
                "write_contract": {
                    "write_mode": "replace_where",
                    "replacement_predicate": "business_date = params.target_date",
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
                    "replacement_safety": {"strategy": "recoverable_replace"},
                    "audit_contract": {"run_id": "shared"},
                    "status": "confirmed",
                },
            }
        ],
        "parameter_contracts": [
            {
                "name": "target_date",
                "type": "date-list",
                "accepted_shapes": ["scalar", "list"],
                "semantics": semantics,
                "status": "confirmed",
            }
        ],
        "runtime_contract": {
            "python_min": "3.8",
            "entrypoint": "plugin_main.py",
            "result_protocol": {"method": "put", "scope": "inst", "level": "task", "body_key": "metrics"},
            "environment_connection_matrix": {"qa": {"connection_mode": "managed"}},
            "safe_log_policy": {"log_credentials": False, "log_parameter_values": False},
            "status": "confirmed",
        },
    }


def main() -> int:
    legacy = validate_contract({"contract_version": 1, "ready_for_codegen": True})
    assert legacy["status"] == "passed", legacy
    assert legacy["deployment_status"] == "review_required", legacy
    assert legacy["deployment_blockers"][0]["code"] == "LEGACY_CONTRACT_V1_DEPLOYMENT", legacy

    base = {
        "contract_version": 1,
        "project_type": "report",
        "component_kind": "standard_report",
        "components": [],
        "ready_for_codegen": True,
        "blockers": [],
    }
    complete = build_contract_v2(complete_facts(), base)
    assert complete["contract_version"] == 2, complete
    assert complete["ready_for_codegen"] is True, complete
    assert complete["validation_result"]["deployment_status"] == "ready", complete["validation_result"]
    semantic_question_contract = copy.deepcopy(complete)
    semantic_question_contract["open_questions"] = [
        {
            "id": "TC-CG-CODE-UNIT-CONFIRMATION",
            "category": "blocking_codegen",
            "text": "Confirm the proposed code-unit mapping.",
            "status": "open",
        }
    ]
    semantic_validation = validate_contract(semantic_question_contract)
    assert semantic_validation["status"] == "passed", semantic_validation

    conflicting_facts = complete_facts()
    conflicting_facts["conflicts"] = [
        {
            "kind": "field_rule_conflict",
            "target": "fixture.output",
            "field": "value",
            "first_logic": "value >= 10",
            "second_logic": "value > 10",
        }
    ]
    conflicting = build_contract_v2(conflicting_facts, base)
    assert conflicting["ready_for_codegen"] is False, conflicting
    assert conflicting["validation_result"]["status"] == "failed", conflicting["validation_result"]
    conflict_question_id = conflicting["conflicts"][0]["question_id"]
    assert conflict_question_id.startswith("TC-CG-X"), conflict_question_id
    assert any(item["id"] == conflict_question_id for item in conflicting["open_questions"]), conflicting["open_questions"]

    first_questions = build_question_groups_v2([], [], {})
    second_questions = build_question_groups_v2([], [], {})
    assert first_questions == second_questions, (first_questions, second_questions)
    question_ids = [
        item["id"]
        for category in ("blocking_codegen", "deployment_confirmation", "non_blocking")
        for item in first_questions[category]
    ]
    assert len(question_ids) == len(set(question_ids)), question_ids
    assert {"TC-CG-015", "TC-DP-001", "TC-DP-002"}.issubset(question_ids), question_ids
    question_contract = build_codegen_contract({}, first_questions)
    assert question_contract["open_questions"], question_contract
    assert all(blocker.startswith("[TC-CG-") for blocker in question_contract["blockers"]), question_contract["blockers"]
    with TemporaryDirectory(prefix="pipelineforge-question-id-") as temp_dir:
        questions_path = Path(temp_dir) / "questions.md"
        write_questions_v2(questions_path, first_questions)
        rendered = questions_path.read_text(encoding="utf-8")
        assert "[TC-CG-015]" in rendered, rendered
        assert "[TC-DP-001]" in rendered, rendered

    print(json.dumps({"status": "passed", "case_count": 5}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
