#!/usr/bin/env python3
"""Verify that multi-schedule evidence is not collapsed without safe merge evidence."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from code_unit_contract import apply_proposal, validate_code_unit_contract
from code_unit_selection import select_code_unit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True, help="Existing structured_facts.json regression evidence.")
    args = parser.parse_args()
    original = json.loads(args.facts.read_text(encoding="utf-8"))
    facts = copy.deepcopy(original)
    for key in ("project_contract", "code_unit_plan", "code_units", "waterlines"):
        facts.pop(key, None)
    schedules = facts.get("report_schedules") or facts.get("schedules") or []
    if not isinstance(schedules, list) or len(schedules) < 2:
        raise ValueError("regression evidence must contain at least two schedules")
    apply_proposal(facts)
    plan = facts["code_unit_plan"]
    validation = validate_code_unit_contract(facts)
    assert validation["status"] == "passed", validation
    assert plan["status"] == "awaiting_user_confirmation", plan
    assert plan["proposed_count"] > 1, plan
    assert len(plan["covered_waterlines"]) == len(facts["waterlines"]), plan
    assert plan["confidence"] == "low", plan
    assert all(item.get("algorithm_key") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("parameter_profile") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("state_boundary") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("write_boundary") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("deployment_boundary") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("failure_boundary") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("dependency_evidence") for item in facts["waterlines"]), facts["waterlines"]
    assert all(item.get("blockers") for item in facts["code_units"]), facts["code_units"]
    assert any(item.get("outputs") for item in facts["waterlines"]), facts["waterlines"]
    unresolved_routes = [item for item in facts["waterlines"] if not item.get("codegen_route")]
    assert all(item.get("codegen_route_candidates") for item in unresolved_routes), unresolved_routes
    try:
        select_code_unit(facts, "", "report-codegen")
    except ValueError:
        pass
    else:
        raise AssertionError("unconfirmed schedule-derived plan must reject codegen")
    print(
        json.dumps(
            {
                "status": "passed",
                "schedule_evidence_count": len(schedules),
                "proposed_count": plan["proposed_count"],
                "confidence": plan["confidence"],
                "algorithm_boundary_count": sum(bool(item.get("algorithm_key")) for item in facts["waterlines"]),
                "parameter_profile_count": sum(bool(item.get("parameter_profile")) for item in facts["waterlines"]),
                "unit_scoped_output_count": sum(len(item.get("outputs") or {}) for item in facts["waterlines"]),
                "route_candidates_audited": len(unresolved_routes),
                "proposal_blocker_count": sum(len(item.get("blockers") or []) for item in facts["code_units"]),
                "hardcoded_business_rules": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
