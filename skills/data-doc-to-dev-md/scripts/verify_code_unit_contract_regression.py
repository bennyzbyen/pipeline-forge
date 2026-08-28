#!/usr/bin/env python3
"""Deterministic regression coverage for dynamic code-unit planning."""

from __future__ import annotations

import copy
import json

from code_unit_contract import (
    apply_proposal,
    confirm_code_unit_plan,
    validate_code_unit_contract,
)
from code_unit_selection import select_code_unit
from code_unit_render import render_code_unit_plan_markdown
from manage_code_unit_plan import render_questions_audit


def execution_contract(output: str) -> dict:
    return {
        "version": 2,
        "sources": {"source": {"kind": "injected", "columns": ["id", "period", "value"]}},
        "steps": [{"id": f"build_{output}", "op": "project", "input": "source", "columns": ["id", "period", "value"]}],
        "outputs": {output: {"input": f"build_{output}", "columns": ["id", "period", "value"]}},
        "writes": {
            output: {
                "kind": "clickhouse",
                "table": f"fixture.{output}",
                "mode": "replace_where",
                "predicate": {"column": "period", "value_from": "time_range.period"},
                "columns": ["id", "period", "value"],
                "column_types": ["String", "String", "Int64"],
                "transport": "insert_df",
                "empty_output_policy": "block_destructive_replace",
                "staging_wire_format": {"encoding": "utf-8", "header": False, "null": "\\N", "explicit_columns": True},
                "replacement_safety": {"strategy": "recoverable_replace"},
            }
        },
        "state": {"watermark": "period"},
        "retry": {"max_attempts": 2},
        "rerun": {"mode": "explicit_period"},
        "empty_output_semantics": {"replace": "blocked"},
        "failure_semantics": {"partial_write": "fail"},
    }


def waterline(
    name: str,
    algorithm: str,
    *,
    parameter: str = "",
    state_group: str = "shared_state",
    write_group: str = "shared_write",
) -> dict:
    return {
        "waterline_id": name,
        "codegen_route": "report-codegen",
        "component_kind": "standard_report",
        "logic_signature": algorithm,
        "parameter_profile": {"period_mode": parameter} if parameter else {},
        "parameterizable_fields": ["period_mode"] if parameter else [],
        "state_compatibility_group": state_group,
        "write_compatibility_group": write_group,
        "deployment_group": "shared_deployment",
        "failure_group": "shared_failure",
        "boundary_confidence": "high",
        "execution_contract": execution_contract(name),
        "tests": [{"name": f"test_{name}"}],
    }


def facts(waterlines: list[dict]) -> dict:
    return {
        "codegen_contract": {
            "contract_version": 2,
            "project_type": "report",
            "component_kind": "standard_report",
            "components": [],
            "ready_for_codegen": True,
            "blockers": [],
            "open_questions": [],
        },
        "waterlines": waterlines,
    }


def confirm_identity(payload: dict) -> dict:
    return {
        "units": [
            {
                "code_unit_id": item["code_unit_id"],
                "covered_waterlines": item["covered_waterlines"],
                "codegen_route": item["codegen_route"],
                "component_kind": item["component_kind"],
            }
            for item in payload["code_unit_plan"]["proposed_mapping"]
        ]
    }


def main() -> int:
    # 1. One waterline and one algorithm proposes one unit.
    single = facts([waterline("daily", "shared_kpi")])
    apply_proposal(single)
    assert single["code_unit_plan"]["proposed_count"] == 1, single["code_unit_plan"]
    assert single["code_unit_plan"]["status"] == "awaiting_user_confirmation"

    # 2. Parameter-only differences stay in one unit with two profiles/bindings.
    parameterized = facts(
        [waterline("daily", "shared_kpi", parameter="date"), waterline("period", "shared_kpi", parameter="period")]
    )
    apply_proposal(parameterized)
    assert parameterized["code_unit_plan"]["proposed_count"] == 1, parameterized["code_unit_plan"]
    unit = parameterized["code_units"][0]
    assert len(unit["waterline_bindings"]) == 2, unit
    assert len(unit["parameter_profiles"]) == 2, unit

    # 3. Incompatible algorithm/state/write boundaries propose independent units.
    incompatible = facts(
        [
            waterline("a", "algorithm_a", state_group="state_a"),
            waterline("b", "algorithm_b", state_group="state_b"),
            waterline("c", "algorithm_c", write_group="write_c"),
        ]
    )
    apply_proposal(incompatible)
    assert incompatible["code_unit_plan"]["proposed_count"] == 3, incompatible["code_unit_plan"]

    # 4. Insufficient boundary evidence remains awaiting confirmation and codegen refuses it.
    uncertain = facts([{"waterline_id": "unknown_boundary", "schedule": "daily"}])
    apply_proposal(uncertain)
    assert uncertain["code_unit_plan"]["confidence"] == "low", uncertain["code_unit_plan"]
    assert uncertain["code_units"][0]["blockers"], uncertain["code_units"][0]
    assert any(item.startswith("[routing]") for item in uncertain["code_units"][0]["blockers"]), uncertain["code_units"][0]
    try:
        select_code_unit(uncertain, "", "report-codegen")
    except ValueError as exc:
        assert "confirmation" in str(exc).lower(), exc
    else:
        raise AssertionError("awaiting_user_confirmation must reject codegen selection")

    # 5a. A proposed three-unit plan can be user-confirmed as two when hard boundaries remain compatible.
    override_base = facts(
        [waterline("a", "algorithm_a"), waterline("b", "algorithm_b"), waterline("c", "algorithm_c")]
    )
    apply_proposal(override_base)
    assert override_base["code_unit_plan"]["proposed_count"] == 3
    merged = copy.deepcopy(override_base)
    confirm_code_unit_plan(
        merged,
        {
            "units": [
                {
                    "code_unit_id": "ab",
                    "covered_waterlines": ["a", "b"],
                    "codegen_route": "report-codegen",
                    "component_kind": "standard_report",
                    "split_reason": "User confirmed one branching implementation with shared state and write semantics.",
                },
                {
                    "code_unit_id": "c",
                    "covered_waterlines": ["c"],
                    "codegen_route": "report-codegen",
                    "component_kind": "standard_report",
                },
            ]
        },
        note="Merge suggested three units into two.",
        timestamp="2026-08-28T00:00:00+00:00",
    )
    assert merged["code_unit_plan"]["confirmed_count"] == 2, merged["code_unit_plan"]
    assert validate_code_unit_contract(merged)["status"] == "passed"
    assert "### Confirmation Audit" in render_code_unit_plan_markdown(merged)
    assert "resolved by explicit user confirmation" in render_questions_audit(merged).lower()

    # 5b. The same proposal can be split into four execution slices with audited duplicate binding.
    split = copy.deepcopy(override_base)
    confirm_code_unit_plan(
        split,
        {
            "units": [
                {
                    "code_unit_id": "a_extract",
                    "covered_waterlines": ["a"],
                    "execution_slice": "extract",
                    "codegen_route": "report-codegen",
                    "component_kind": "standard_report",
                },
                {
                    "code_unit_id": "a_publish",
                    "covered_waterlines": ["a"],
                    "execution_slice": "publish",
                    "depends_on": ["a_extract"],
                    "codegen_route": "report-codegen",
                    "component_kind": "standard_report",
                },
                {"code_unit_id": "b", "covered_waterlines": ["b"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
                {"code_unit_id": "c", "covered_waterlines": ["c"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
            ]
        },
        note="Split waterline a into extract and publish execution slices.",
        timestamp="2026-08-28T00:00:01+00:00",
    )
    assert split["code_unit_plan"]["confirmed_count"] == 4, split["code_unit_plan"]
    assert validate_code_unit_contract(split)["status"] == "passed"

    # Changed boundary evidence invalidates an earlier confirmation.
    stale = copy.deepcopy(merged)
    stale["waterlines"][0]["state_boundary"]["compatibility_group"] = "changed_state"
    stale_result = validate_code_unit_contract(stale)
    assert stale_result["status"] == "failed", stale_result
    assert any("changed" in item for item in stale_result["errors"]), stale_result

    # 7. Legacy single-component facts remain accepted.
    legacy = {"codegen_contract": {"contract_version": 1, "project_type": "report", "ready_for_codegen": True}}
    legacy_result = validate_code_unit_contract(legacy)
    assert legacy_result["status"] == "legacy_compatible", legacy_result

    print(json.dumps({"status": "passed", "case_count": 8}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
