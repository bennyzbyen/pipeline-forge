#!/usr/bin/env python3
"""Select one confirmed, independently ready Data Doc code-unit contract."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from code_unit_contract import clean, slug, validate_code_unit_contract


def select_code_unit(facts: Mapping[str, Any], code_unit_id: str = "", expected_route: str = "") -> dict[str, Any] | None:
    if not any(key in facts for key in ("project_contract", "code_unit_plan", "code_units")):
        return None
    validation = validate_code_unit_contract(facts)
    if validation["status"] != "passed":
        raise ValueError("invalid code-unit contract: " + "; ".join(validation["errors"]))
    plan = facts["code_unit_plan"]
    if plan.get("status") != "confirmed":
        raise ValueError(
            f"code_unit_plan is {plan.get('status')!r}; full code generation requires explicit user confirmation"
        )
    units = facts["code_units"]
    if code_unit_id:
        matches = [item for item in units if clean(item.get("code_unit_id")) == slug(code_unit_id)]
    elif len(units) == 1:
        matches = list(units)
    else:
        raise ValueError("--code-unit-id is required when a confirmed project contains multiple code units")
    if not matches:
        raise ValueError(f"unknown code_unit_id: {code_unit_id}")
    unit = copy.deepcopy(matches[0])
    if expected_route and clean(unit.get("codegen_route")) != expected_route:
        raise ValueError(
            f"code unit {unit.get('code_unit_id')} routes to {unit.get('codegen_route')}, not {expected_route}"
        )
    readiness = unit.get("readiness") if isinstance(unit.get("readiness"), Mapping) else {}
    if readiness.get("ready_for_codegen") is not True or readiness.get("blockers"):
        raise ValueError(
            f"code unit {unit.get('code_unit_id')} is not ready for codegen: "
            + "; ".join(str(item) for item in readiness.get("blockers", []) or ["readiness not confirmed"])
        )
    return unit
