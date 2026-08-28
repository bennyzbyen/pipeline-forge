#!/usr/bin/env python3
"""Select one confirmed code unit while retaining legacy-facts compatibility."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")


def boundary_fingerprint(waterlines: list[dict[str, Any]]) -> str:
    boundary_view = []
    for item in sorted(waterlines, key=lambda row: clean(row.get("waterline_id"))):
        boundary_view.append(
            {
                "waterline_id": clean(item.get("waterline_id")),
                "codegen_route": clean(item.get("codegen_route")),
                "codegen_route_candidates": item.get("codegen_route_candidates") or [],
                "component_kind": clean(item.get("component_kind")),
                "algorithm_key": clean(item.get("algorithm_key")),
                "state_boundary": item.get("state_boundary") or {},
                "write_boundary": item.get("write_boundary") or {},
                "deployment_boundary": item.get("deployment_boundary") or {},
                "failure_boundary": item.get("failure_boundary") or {},
                "dependency_evidence": item.get("dependency_evidence") or {},
                "incompatible_with": sorted(item.get("incompatible_with") or []),
            }
        )
    payload = json.dumps(boundary_view, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_code_unit(facts: Mapping[str, Any], code_unit_id: str, expected_route: str) -> dict[str, Any] | None:
    if not any(key in facts for key in ("project_contract", "code_unit_plan", "code_units")):
        return None
    plan = facts.get("code_unit_plan")
    units = facts.get("code_units")
    waterlines = facts.get("waterlines")
    if not isinstance(plan, Mapping) or not isinstance(units, list) or not isinstance(waterlines, list):
        raise ValueError("two-level code-unit contract is incomplete")
    if plan.get("status") != "confirmed":
        raise ValueError(
            f"code_unit_plan is {plan.get('status')!r}; full code generation requires explicit user confirmation"
        )
    stored = clean(plan.get("boundary_evidence_fingerprint"))
    current = boundary_fingerprint(waterlines)
    if stored and stored != current:
        raise ValueError("code-unit confirmation is stale because boundary evidence changed; rebuild and reconfirm")
    if plan.get("confirmed_count") != len(units):
        raise ValueError("confirmed_count does not match code_units length")
    if code_unit_id:
        matches = [item for item in units if slug(item.get("code_unit_id")) == slug(code_unit_id)]
    elif len(units) == 1:
        matches = units
    else:
        raise ValueError("--code-unit-id is required for a project with multiple confirmed code units")
    if not matches:
        raise ValueError(f"unknown code_unit_id: {code_unit_id}")
    unit = copy.deepcopy(matches[0])
    if clean(unit.get("codegen_route")) != expected_route:
        raise ValueError(
            f"code unit {unit.get('code_unit_id')} routes to {unit.get('codegen_route')}, not {expected_route}"
        )
    return unit
