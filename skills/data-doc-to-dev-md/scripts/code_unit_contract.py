#!/usr/bin/env python3
"""Build and validate project-level and per-code-unit delivery contracts.

The module is intentionally independent from DOCX parsing.  It accepts normalized
waterline evidence when available and falls back to schedule evidence without
pretending that the number of schedules determines the number of code units.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from code_unit_evidence import enrich_schedule_waterlines


PLAN_VERSION = 1
CONFIRMATION_QUESTION_ID = "TC-CG-CODE-UNIT-CONFIRMATION"
CONFIRMATION_BLOCKER = (
    f"[{CONFIRMATION_QUESTION_ID}] Confirm the proposed code-unit count, waterline mapping, "
    "parameterization, and dependency boundaries before full code generation."
)
PLAN_STATUSES = {"proposed", "awaiting_user_confirmation", "confirmed"}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def slug(value: Any, fallback: str = "unit") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")
    return text or fallback


def unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def evidence_fingerprint(waterlines: list[dict[str, Any]]) -> str:
    boundary_view = []
    for item in sorted(waterlines, key=lambda row: row["waterline_id"]):
        boundary_view.append(
            {
                "waterline_id": item["waterline_id"],
                "codegen_route": item["codegen_route"],
                "codegen_route_candidates": item.get("codegen_route_candidates", []),
                "component_kind": item["component_kind"],
                "algorithm_key": item["algorithm_key"],
                "state_boundary": item["state_boundary"],
                "write_boundary": item["write_boundary"],
                "deployment_boundary": item["deployment_boundary"],
                "failure_boundary": item["failure_boundary"],
                "dependency_evidence": item.get("dependency_evidence", {}),
                "incompatible_with": sorted(item["incompatible_with"]),
            }
        )
    return hashlib.sha256(canonical(boundary_view).encode("utf-8")).hexdigest()


def _route(value: Any, project_type: str) -> str:
    normalized = clean(value).lower()
    aliases = {
        "report": "report-codegen",
        "report-codegen": "report-codegen",
        "data-sync": "data-sync-codegen",
        "sync": "data-sync-codegen",
        "data-sync-codegen": "data-sync-codegen",
    }
    if normalized in aliases:
        return aliases[normalized]
    return aliases.get(clean(project_type).lower(), normalized)


def _as_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return copy.deepcopy(value)
    return [copy.deepcopy(value)]


def _boundary(value: Any, group: Any = "") -> dict[str, Any]:
    result = _as_dict(value)
    if clean(group) and not clean(result.get("compatibility_group")):
        result["compatibility_group"] = clean(group)
    return result


def _normalize_waterline(raw: Mapping[str, Any], index: int, defaults: Mapping[str, Any]) -> dict[str, Any]:
    name = clean(raw.get("waterline_id") or raw.get("id") or raw.get("pipeline_name") or raw.get("task_name"))
    waterline_id = slug(name, f"waterline_{index + 1:03d}")
    project_type = clean(raw.get("project_type") or defaults.get("project_type"))
    route = _route(raw.get("codegen_route") or raw.get("handoff_to"), "")
    component_kind = clean(raw.get("component_kind") or defaults.get("component_kind") or "unclassified")
    algorithm = clean(
        raw.get("logic_signature")
        or raw.get("algorithm_key")
        or raw.get("algorithm")
        or raw.get("business_logic_group")
        or raw.get("transformation_family")
    )
    confidence = clean(raw.get("boundary_confidence") or raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium" if algorithm and route and component_kind != "unclassified" else "low"
    state_boundary = _boundary(
        raw.get("state_boundary") or raw.get("state") or raw.get("watermark"),
        raw.get("state_compatibility_group") or raw.get("watermark_group"),
    )
    write_boundary = _boundary(
        raw.get("write_boundary") or raw.get("write_transaction"),
        raw.get("write_compatibility_group") or raw.get("transaction_group"),
    )
    deployment_boundary = _boundary(raw.get("deployment_boundary"), raw.get("deployment_group"))
    failure_boundary = _boundary(raw.get("failure_boundary"), raw.get("failure_group"))
    blockers = [clean(item) for item in _as_list(raw.get("blockers")) if clean(item)]
    if confidence != "high":
        if not route:
            blockers.append("[routing] codegen_route requires confirmation")
        if not algorithm:
            blockers.append("[algorithm] shared business algorithm boundary is not evidenced")
        if not state_boundary:
            blockers.append("[state] state/watermark boundary is not evidenced")
        if not write_boundary:
            blockers.append("[writes] write transaction boundary is not evidenced")
        if not deployment_boundary:
            blockers.append("[deployment] deployment boundary is not evidenced")
        if not failure_boundary:
            blockers.append("[failure] failure-isolation boundary is not evidenced")
        if not isinstance(raw.get("dependency_evidence"), Mapping):
            blockers.append("[dependencies] dependency boundary is not evidenced")
    return {
        "waterline_id": waterline_id,
        "display_name": name or waterline_id,
        "description": clean(raw.get("description")),
        "schedule": clean(raw.get("schedule")),
        "codegen_route": route,
        "codegen_route_candidates": _as_list(raw.get("codegen_route_candidates")),
        "component_kind": component_kind,
        "algorithm_key": algorithm,
        "parameter_profile": _as_dict(raw.get("parameter_profile") or raw.get("parameters")),
        "parameterizable_fields": [clean(item) for item in _as_list(raw.get("parameterizable_fields")) if clean(item)],
        "sources": copy.deepcopy(raw.get("sources") or {}),
        "steps": copy.deepcopy(raw.get("steps") or []),
        "outputs": copy.deepcopy(raw.get("outputs") or {}),
        "writes": copy.deepcopy(raw.get("writes") or {}),
        "state_boundary": state_boundary,
        "write_boundary": write_boundary,
        "deployment_boundary": deployment_boundary,
        "failure_boundary": failure_boundary,
        "retry": _as_dict(raw.get("retry")),
        "rerun": _as_dict(raw.get("rerun")),
        "empty_output_semantics": _as_dict(raw.get("empty_output_semantics") or raw.get("empty_output")),
        "failure_semantics": _as_dict(raw.get("failure_semantics")),
        "tests": _as_list(raw.get("tests")),
        "depends_on": [slug(item) for item in _as_list(raw.get("depends_on")) if clean(item)],
        "dependency_evidence": _as_dict(raw.get("dependency_evidence")),
        "incompatible_with": [slug(item) for item in _as_list(raw.get("incompatible_with")) if clean(item)],
        "requires_independent_deployment": raw.get("requires_independent_deployment") is True,
        "requires_failure_isolation": raw.get("requires_failure_isolation") is True,
        "force_separate": raw.get("force_separate") is True,
        "boundary_confidence": confidence,
        "blockers": unique(blockers),
        "execution_contract": _as_dict(raw.get("execution_contract")),
        "covered_tables": [clean(item) for item in _as_list(raw.get("covered_tables")) if clean(item)],
        "provenance": copy.deepcopy(raw.get("provenance") or raw.get("source_context") or {}),
        "boundary_evidence": _as_dict(raw.get("boundary_evidence")),
    }


def derive_waterlines(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize explicit waterline contracts or conservatively derive candidates."""
    codegen = facts.get("codegen_contract") if isinstance(facts.get("codegen_contract"), Mapping) else {}
    defaults = {
        "project_type": codegen.get("project_type", ""),
        "component_kind": codegen.get("component_kind", "unclassified"),
    }
    explicit = facts.get("waterlines")
    if not isinstance(explicit, list):
        evidence = facts.get("code_unit_evidence") if isinstance(facts.get("code_unit_evidence"), Mapping) else {}
        explicit = evidence.get("waterlines")
    rows = explicit if isinstance(explicit, list) and explicit else []
    if not rows:
        schedules = facts.get("report_schedules") or facts.get("schedules") or []
        if isinstance(schedules, list):
            schedule_rows = [dict(item) for item in schedules if isinstance(item, Mapping)]
            rows = enrich_schedule_waterlines(facts, schedule_rows) if schedule_rows else []
    if not rows:
        components = codegen.get("components") if isinstance(codegen.get("components"), list) else []
        rows = [
            {
                "waterline_id": item.get("name") or f"legacy_component_{index + 1}",
                "description": item.get("role", "Legacy single-component delivery boundary."),
                "component_kind": item.get("kind") or defaults["component_kind"],
                "boundary_confidence": "low",
            }
            for index, item in enumerate(components)
            if isinstance(item, Mapping)
        ]
    if not rows:
        rows = [{"waterline_id": "project_delivery", "boundary_confidence": "low"}]
    normalized = [_normalize_waterline(row, index, defaults) for index, row in enumerate(rows)]
    seen: defaultdict[str, int] = defaultdict(int)
    for item in normalized:
        base = item["waterline_id"]
        seen[base] += 1
        if seen[base] > 1:
            item["waterline_id"] = f"{base}_{seen[base]}"
    return normalized


def _compatibility_value(boundary: Mapping[str, Any]) -> str:
    return clean(boundary.get("compatibility_group") or boundary.get("id") or boundary.get("key"))


def _automatic_group_key(item: Mapping[str, Any]) -> tuple[str, ...]:
    unknown_suffix = item["waterline_id"]
    algorithm = clean(item.get("algorithm_key")) or f"unknown:{unknown_suffix}"
    state = _compatibility_value(item.get("state_boundary") or {}) or f"unknown:{unknown_suffix}"
    write = _compatibility_value(item.get("write_boundary") or {}) or f"unknown:{unknown_suffix}"
    deployment = _compatibility_value(item.get("deployment_boundary") or {})
    failure = _compatibility_value(item.get("failure_boundary") or {})
    if item.get("force_separate") or item.get("requires_independent_deployment") or item.get("requires_failure_isolation"):
        failure = f"isolated:{unknown_suffix}"
    return (
        clean(item.get("codegen_route")),
        clean(item.get("component_kind")),
        algorithm,
        state,
        write,
        deployment,
        failure,
    )


def _merge_named_maps(values: Iterable[Any]) -> Any:
    items = list(values)
    if not items:
        return {}
    if all(isinstance(item, Mapping) for item in items):
        merged: dict[str, Any] = {}
        for item in items:
            for key, value in item.items():
                if key not in merged:
                    merged[str(key)] = copy.deepcopy(value)
                elif canonical(merged[str(key)]) != canonical(value):
                    merged[f"{key}_{len(merged) + 1}"] = copy.deepcopy(value)
        return merged
    return unique(item for value in items for item in _as_list(value))


def _combined_execution_contract(waterlines: list[dict[str, Any]], override: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if override:
        return copy.deepcopy(dict(override))
    explicit = [item["execution_contract"] for item in waterlines if item.get("execution_contract")]
    if explicit and all(canonical(item) == canonical(explicit[0]) for item in explicit):
        return copy.deepcopy(explicit[0])
    return {
        "version": 2,
        "sources": _merge_named_maps(item.get("sources") for item in waterlines),
        "steps": unique(step for item in waterlines for step in _as_list(item.get("steps"))),
        "outputs": _merge_named_maps(item.get("outputs") for item in waterlines),
        "writes": _merge_named_maps(item.get("writes") for item in waterlines),
        "state": _merge_named_maps(item.get("state_boundary") for item in waterlines),
        "retry": _merge_named_maps(item.get("retry") for item in waterlines),
        "rerun": _merge_named_maps(item.get("rerun") for item in waterlines),
        "empty_output_semantics": _merge_named_maps(item.get("empty_output_semantics") for item in waterlines),
        "failure_semantics": _merge_named_maps(item.get("failure_semantics") for item in waterlines),
    }


def _contract_complete(contract: Mapping[str, Any], route: str) -> list[str]:
    blockers: list[str] = []
    if not route:
        blockers.append("codegen_route is not confirmed")
    if route == "report-codegen":
        for key in ("sources", "steps", "outputs", "writes"):
            if not contract.get(key):
                blockers.append(f"execution_contract.{key} is incomplete")
    elif route == "data-sync-codegen":
        if not (contract.get("tables") or contract.get("sources")):
            blockers.append("execution_contract.tables or sources is incomplete")
        if not (contract.get("writes") or contract.get("targets")):
            blockers.append("execution_contract.writes or targets is incomplete")
    return blockers


def _make_unit(
    unit_id: str,
    waterlines: list[dict[str, Any]],
    *,
    status: str,
    mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mapping = mapping or {}
    route_values = unique(clean(item.get("codegen_route")) for item in waterlines if clean(item.get("codegen_route")))
    route_candidates = unique(
        copy.deepcopy(candidate)
        for item in waterlines
        for candidate in item.get("codegen_route_candidates", [])
    )
    kind_values = unique(clean(item.get("component_kind")) for item in waterlines if clean(item.get("component_kind")))
    route = clean(mapping.get("codegen_route")) or (route_values[0] if len(route_values) == 1 else "")
    component_kind = clean(mapping.get("component_kind")) or (kind_values[0] if len(kind_values) == 1 else "unclassified")
    contract = _combined_execution_contract(waterlines, mapping.get("execution_contract") if isinstance(mapping.get("execution_contract"), Mapping) else None)
    inherited_blockers = [blocker for waterline in waterlines for blocker in waterline.get("blockers", [])]
    if status == "confirmed" and clean(mapping.get("codegen_route")):
        inherited_blockers = [item for item in inherited_blockers if not clean(item).startswith("[routing]")]
    blockers = unique(
        [clean(item) for item in _as_list(mapping.get("blockers")) if clean(item)]
        + inherited_blockers
        + (_contract_complete(contract, route) if status == "confirmed" else [])
    )
    profiles = [
        {"waterline_id": item["waterline_id"], "profile": item["parameter_profile"]}
        for item in waterlines
        if item.get("parameter_profile")
    ]
    algorithms = unique(clean(item.get("algorithm_key")) for item in waterlines if clean(item.get("algorithm_key")))
    confidence_values = {item.get("boundary_confidence") for item in waterlines}
    confidence = "low" if "low" in confidence_values else ("medium" if "medium" in confidence_values else "high")
    parameterization = _as_dict(mapping.get("parameterization")) or {
        "strategy": "profiles" if len(profiles) > 1 else ("single_profile" if profiles else "none_confirmed"),
        "profile_count": len(profiles),
        "parameterizable_fields": unique(
            field for item in waterlines for field in item.get("parameterizable_fields", [])
        ),
    }
    split_reason = clean(mapping.get("split_reason"))
    if not split_reason:
        split_reason = (
            "Shared algorithm and compatible state, write, deployment, and failure boundaries; differences are parameterized."
            if len(waterlines) > 1 and len(algorithms) == 1
            else "Independent algorithm, state, write, deployment, failure-isolation, or insufficient-boundary-evidence group."
        )
    covered_tables = unique(
        [clean(item) for item in _as_list(mapping.get("covered_tables")) if clean(item)]
        + [table for waterline in waterlines for table in waterline.get("covered_tables", [])]
    )
    tests = unique(
        [copy.deepcopy(item) for item in _as_list(mapping.get("tests"))]
        + [copy.deepcopy(test) for waterline in waterlines for test in waterline.get("tests", [])]
    )
    ready = status == "confirmed" and not blockers
    return {
        "code_unit_id": slug(unit_id),
        "status": status,
        "codegen_route": route,
        "codegen_route_candidates": route_candidates,
        "component_kind": component_kind,
        "covered_waterlines": [item["waterline_id"] for item in waterlines],
        "waterline_bindings": [
            {
                "waterline_id": item["waterline_id"],
                "schedule": item["schedule"],
                "parameter_profile": item["parameter_profile"],
                "execution_slice": clean(mapping.get("execution_slice")),
            }
            for item in waterlines
        ],
        "parameter_profiles": profiles,
        "parameterization": parameterization,
        "split_reason": split_reason,
        "confidence": clean(mapping.get("confidence")) or confidence,
        "depends_on": unique(
            [slug(item) for item in _as_list(mapping.get("depends_on")) if clean(item)]
            + [dependency for item in waterlines for dependency in item.get("depends_on", [])]
        ),
        "covered_tables": covered_tables,
        "execution_contract": contract,
        "state": copy.deepcopy(contract.get("state") or {}),
        "retry": copy.deepcopy(contract.get("retry") or {}),
        "rerun": copy.deepcopy(contract.get("rerun") or {}),
        "empty_output_semantics": copy.deepcopy(contract.get("empty_output_semantics") or {}),
        "failure_semantics": copy.deepcopy(contract.get("failure_semantics") or {}),
        "tests": tests,
        "readiness": {
            "ready_for_codegen": ready,
            "blockers": blockers,
        },
        "blockers": blockers,
    }


def _proposal_groups(waterlines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: defaultdict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in waterlines:
        grouped[_automatic_group_key(item)].append(item)
    return list(grouped.values())


def _dependency_graph(units: list[dict[str, Any]]) -> list[dict[str, str]]:
    owner = {
        waterline: unit["code_unit_id"]
        for unit in units
        for waterline in unit.get("covered_waterlines", [])
    }
    edges: list[dict[str, str]] = []
    for unit in units:
        for dependency in unit.get("depends_on", []):
            target = owner.get(dependency, dependency)
            if target and target != unit["code_unit_id"]:
                edges.append({"from": target, "to": unit["code_unit_id"]})
    return unique(edges)


def _shared_project_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "documents": copy.deepcopy(facts.get("documents") or []),
        "field_dictionary_count": len(facts.get("field_dictionaries") or []),
        "source_count": len(facts.get("report_sources") or []),
        "global_parameters": copy.deepcopy(facts.get("parameter_contracts") or []),
        "evidence_policy": clean(facts.get("merge_policy")),
    }


def build_code_unit_proposal(facts: Mapping[str, Any]) -> dict[str, Any]:
    waterlines = derive_waterlines(facts)
    units = [
        _make_unit(f"code_unit_{index + 1:03d}", group, status="proposed")
        for index, group in enumerate(_proposal_groups(waterlines))
    ]
    confidence_values = {item.get("boundary_confidence") for item in waterlines}
    confidence = "low" if "low" in confidence_values else ("medium" if "medium" in confidence_values else "high")
    fingerprint = evidence_fingerprint(waterlines)
    codegen = facts.get("codegen_contract") if isinstance(facts.get("codegen_contract"), Mapping) else {}
    project_contract = {
        "contract_version": PLAN_VERSION,
        "status": "awaiting_user_confirmation",
        "project_metadata": {
            "project_type": clean(codegen.get("project_type")),
            "legacy_component_kind": clean(codegen.get("component_kind")),
        },
        "evidence": _shared_project_facts(facts),
        "shared_contracts": {
            "field_contracts": copy.deepcopy(codegen.get("field_contracts") or []),
            "source_contracts": copy.deepcopy(codegen.get("source_contracts") or []),
            "parameter_contracts": copy.deepcopy(codegen.get("parameter_contracts") or []),
        },
        "confirmed_code_unit_count": None,
        "confirmed_mapping": [],
        "dependency_graph": _dependency_graph(units),
        "user_overrides": [],
        "boundary_evidence_fingerprint": fingerprint,
        "overall_readiness": "awaiting_user_confirmation",
    }
    plan = {
        "plan_version": PLAN_VERSION,
        "status": "awaiting_user_confirmation",
        "proposed_count": len(units),
        "confirmed_count": None,
        "covered_waterlines": [item["waterline_id"] for item in waterlines],
        "parameterization": [
            {"code_unit_id": unit["code_unit_id"], **unit["parameterization"]} for unit in units
        ],
        "split_reason": "Code units are grouped only when algorithm, route, state, write, deployment, and failure boundaries are compatible; parameter-only differences remain profiles.",
        "confidence": confidence,
        "proposed_mapping": [
            {
                "code_unit_id": unit["code_unit_id"],
                "covered_waterlines": unit["covered_waterlines"],
                "codegen_route": unit["codegen_route"],
                "codegen_route_candidates": unit.get("codegen_route_candidates", []),
                "component_kind": unit["component_kind"],
                "parameterization": unit["parameterization"],
                "split_reason": unit["split_reason"],
                "confidence": unit["confidence"],
                "depends_on": unit["depends_on"],
            }
            for unit in units
        ],
        "confirmed_mapping": [],
        "dependency_graph": _dependency_graph(units),
        "unresolved_questions": [CONFIRMATION_BLOCKER],
        "boundary_evidence_fingerprint": fingerprint,
        "confirmation_audit": [],
    }
    return {
        "project_contract": project_contract,
        "code_unit_plan": plan,
        "code_units": units,
        "waterlines": waterlines,
    }


def apply_proposal(facts: dict[str, Any]) -> dict[str, Any]:
    proposal = build_code_unit_proposal(facts)
    facts["project_contract"] = proposal["project_contract"]
    facts["code_unit_plan"] = proposal["code_unit_plan"]
    facts["code_units"] = proposal["code_units"]
    facts["waterlines"] = proposal["waterlines"]
    codegen = facts.get("codegen_contract")
    if isinstance(codegen, dict):
        codegen["legacy_ready_for_codegen_before_code_unit_confirmation"] = codegen.get("ready_for_codegen") is True
        codegen["ready_for_codegen"] = False
        codegen["blockers"] = unique([*(codegen.get("blockers") or []), CONFIRMATION_BLOCKER])
        codegen["code_unit_plan_status"] = "awaiting_user_confirmation"
        open_questions = codegen.get("open_questions")
        if isinstance(open_questions, list) and not any(
            isinstance(item, Mapping) and item.get("id") == CONFIRMATION_QUESTION_ID
            for item in open_questions
        ):
            open_questions.append(
                {
                    "id": CONFIRMATION_QUESTION_ID,
                    "category": "blocking_codegen",
                    "text": CONFIRMATION_BLOCKER.split("] ", 1)[-1],
                    "status": "open",
                }
            )
    return facts


def _merge_errors(waterlines: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids = {item["waterline_id"] for item in waterlines}
    routes = {clean(item.get("codegen_route")) for item in waterlines if clean(item.get("codegen_route"))}
    if len(routes) > 1:
        errors.append(f"incompatible codegen routes cannot share one code unit: {sorted(routes)}")
    for item in waterlines:
        if item.get("requires_independent_deployment") and len(waterlines) > 1:
            errors.append(f"{item['waterline_id']} requires independent deployment")
        if item.get("requires_failure_isolation") and len(waterlines) > 1:
            errors.append(f"{item['waterline_id']} requires failure isolation")
        conflicts = ids.intersection(item.get("incompatible_with", []))
        if conflicts:
            errors.append(f"{item['waterline_id']} is incompatible with {sorted(conflicts)}")
    for field, label in [
        ("state_boundary", "state/watermark"),
        ("write_boundary", "write transaction"),
        ("deployment_boundary", "deployment"),
        ("failure_boundary", "failure isolation"),
    ]:
        groups = {
            _compatibility_value(item.get(field) or {})
            for item in waterlines
            if _compatibility_value(item.get(field) or {})
        }
        if len(groups) > 1:
            errors.append(f"incompatible {label} groups cannot share one code unit: {sorted(groups)}")
    return errors


def _validate_mapping(mapping: Mapping[str, Any], waterlines: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    units = mapping.get("units")
    if not isinstance(units, list) or not units:
        return ["confirmation mapping must contain a non-empty units list"]
    known = {item["waterline_id"]: item for item in waterlines}
    coverage: defaultdict[str, list[str]] = defaultdict(list)
    unit_ids: set[str] = set()
    for index, raw in enumerate(units):
        if not isinstance(raw, Mapping):
            errors.append(f"units[{index}] must be an object")
            continue
        unit_id = slug(raw.get("code_unit_id"), f"code_unit_{index + 1:03d}")
        if unit_id in unit_ids:
            errors.append(f"duplicate code_unit_id: {unit_id}")
        unit_ids.add(unit_id)
        ids = [slug(item) for item in _as_list(raw.get("covered_waterlines")) if clean(item)]
        if not ids:
            errors.append(f"{unit_id} covers no waterlines")
            continue
        unknown = [item for item in ids if item not in known]
        if unknown:
            errors.append(f"{unit_id} references unknown waterlines: {unknown}")
            continue
        for waterline_id in ids:
            coverage[waterline_id].append(unit_id)
        errors.extend(f"{unit_id}: {message}" for message in _merge_errors([known[item] for item in ids]))
    missing = sorted(set(known) - set(coverage))
    if missing:
        errors.append(f"confirmation mapping does not cover waterlines: {missing}")
    for waterline_id, owners in coverage.items():
        if len(owners) <= 1:
            continue
        duplicate_units = [raw for raw in units if slug(raw.get("code_unit_id")) in owners]
        slices = [clean(raw.get("execution_slice")) for raw in duplicate_units]
        if not all(slices) or len(slices) != len(set(slices)):
            errors.append(
                f"{waterline_id} is assigned to multiple code units without distinct execution_slice values"
            )
    return unique(errors)


def confirm_code_unit_plan(
    facts: dict[str, Any],
    mapping: Mapping[str, Any],
    *,
    actor: str = "user",
    note: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    waterlines = derive_waterlines(facts)
    errors = _validate_mapping(mapping, waterlines)
    if errors:
        raise ValueError("Invalid code-unit confirmation: " + "; ".join(errors))
    by_id = {item["waterline_id"]: item for item in waterlines}
    confirmed_units: list[dict[str, Any]] = []
    for index, raw in enumerate(mapping["units"]):
        unit_id = slug(raw.get("code_unit_id"), f"code_unit_{index + 1:03d}")
        selected = [by_id[slug(item)] for item in _as_list(raw.get("covered_waterlines"))]
        confirmed_units.append(_make_unit(unit_id, selected, status="confirmed", mapping=raw))
    fingerprint = evidence_fingerprint(waterlines)
    when = timestamp or datetime.now(timezone.utc).isoformat()
    previous_plan = facts.get("code_unit_plan") if isinstance(facts.get("code_unit_plan"), Mapping) else {}
    audit = copy.deepcopy(previous_plan.get("confirmation_audit") or [])
    audit.append(
        {
            "timestamp": when,
            "actor": actor,
            "action": "confirmed_code_unit_mapping",
            "note": note,
            "requested_count": len(confirmed_units),
            "mapping": [
                {
                    "code_unit_id": item["code_unit_id"],
                    "covered_waterlines": item["covered_waterlines"],
                    "execution_slice": clean(raw.get("execution_slice")),
                }
                for item, raw in zip(confirmed_units, mapping["units"])
            ],
        }
    )
    proposed_count = previous_plan.get("proposed_count") or len(_proposal_groups(waterlines))
    confirmed_mapping = [
        {
            "code_unit_id": unit["code_unit_id"],
            "covered_waterlines": unit["covered_waterlines"],
            "codegen_route": unit["codegen_route"],
            "component_kind": unit["component_kind"],
            "parameterization": unit["parameterization"],
            "split_reason": unit["split_reason"],
            "depends_on": unit["depends_on"],
            "ready_for_codegen": unit["readiness"]["ready_for_codegen"],
        }
        for unit in confirmed_units
    ]
    facts["waterlines"] = waterlines
    facts["code_units"] = confirmed_units
    facts["code_unit_plan"] = {
        **copy.deepcopy(dict(previous_plan)),
        "plan_version": PLAN_VERSION,
        "status": "confirmed",
        "proposed_count": proposed_count,
        "confirmed_count": len(confirmed_units),
        "covered_waterlines": [item["waterline_id"] for item in waterlines],
        "confirmed_mapping": confirmed_mapping,
        "dependency_graph": _dependency_graph(confirmed_units),
        "unresolved_questions": [],
        "boundary_evidence_fingerprint": fingerprint,
        "confirmation_audit": audit,
    }
    previous_project = facts.get("project_contract") if isinstance(facts.get("project_contract"), Mapping) else {}
    overrides = copy.deepcopy(previous_project.get("user_overrides") or [])
    if len(confirmed_units) != proposed_count or note:
        overrides.append(
            {
                "timestamp": when,
                "proposed_count": proposed_count,
                "confirmed_count": len(confirmed_units),
                "note": note,
            }
        )
    facts["project_contract"] = {
        **copy.deepcopy(dict(previous_project)),
        "contract_version": PLAN_VERSION,
        "status": "confirmed",
        "confirmed_code_unit_count": len(confirmed_units),
        "confirmed_mapping": confirmed_mapping,
        "dependency_graph": _dependency_graph(confirmed_units),
        "user_overrides": overrides,
        "boundary_evidence_fingerprint": fingerprint,
        "overall_readiness": (
            "ready_for_codegen"
            if all(item["readiness"]["ready_for_codegen"] for item in confirmed_units)
            else "partially_blocked"
        ),
    }
    codegen = facts.get("codegen_contract")
    if isinstance(codegen, dict):
        codegen["blockers"] = [
            item for item in codegen.get("blockers", []) if CONFIRMATION_QUESTION_ID not in clean(item)
        ]
        for question in codegen.get("open_questions", []) or []:
            if isinstance(question, dict) and question.get("id") == CONFIRMATION_QUESTION_ID:
                question["status"] = "resolved"
        codegen["code_unit_plan_status"] = "confirmed"
        codegen["confirmed_code_unit_count"] = len(confirmed_units)
        codegen["ready_for_codegen"] = all(
            item["readiness"]["ready_for_codegen"] for item in confirmed_units
        )
    return facts


def validate_code_unit_contract(facts: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    plan = facts.get("code_unit_plan")
    units = facts.get("code_units")
    project = facts.get("project_contract")
    if plan is None and units is None and project is None:
        return {
            "status": "legacy_compatible",
            "legacy": True,
            "error_count": 0,
            "warning_count": 0,
            "errors": [],
            "warnings": ["Legacy single-component structured_facts has no two-level code-unit contract."],
        }
    if not isinstance(plan, Mapping):
        errors.append("code_unit_plan must be an object")
        plan = {}
    if not isinstance(project, Mapping):
        errors.append("project_contract must be an object")
        project = {}
    if not isinstance(units, list) or not units:
        errors.append("code_units must be a non-empty list")
        units = []
    status = clean(plan.get("status"))
    if status not in PLAN_STATUSES:
        errors.append(f"unsupported code_unit_plan.status: {status!r}")
    waterlines = derive_waterlines(facts)
    current_fingerprint = evidence_fingerprint(waterlines)
    stored_fingerprint = clean(plan.get("boundary_evidence_fingerprint"))
    if stored_fingerprint and stored_fingerprint != current_fingerprint:
        errors.append("boundary evidence changed after planning; confirmation is invalid and must be rebuilt")
    unit_ids = [clean(item.get("code_unit_id")) for item in units if isinstance(item, Mapping)]
    if len(unit_ids) != len(set(unit_ids)):
        errors.append("code_unit_id values must be unique")
    if status == "confirmed":
        if plan.get("confirmed_count") != len(units):
            errors.append("confirmed_count does not match code_units length")
        if project.get("confirmed_code_unit_count") != len(units):
            errors.append("project_contract confirmed count does not match code_units length")
        mapping = {
            "units": [
                {
                    "code_unit_id": item.get("code_unit_id"),
                    "covered_waterlines": item.get("covered_waterlines"),
                    "execution_slice": next(
                        (
                            clean(binding.get("execution_slice"))
                            for binding in item.get("waterline_bindings", [])
                            if isinstance(binding, Mapping) and clean(binding.get("execution_slice"))
                        ),
                        "",
                    ),
                }
                for item in units
                if isinstance(item, Mapping)
            ]
        }
        errors.extend(_validate_mapping(mapping, waterlines))
    elif any(
        isinstance(item, Mapping) and item.get("readiness", {}).get("ready_for_codegen") is True
        for item in units
    ):
        errors.append("unconfirmed code units cannot be ready_for_codegen")
    for index, item in enumerate(units):
        if not isinstance(item, Mapping):
            errors.append(f"code_units[{index}] must be an object")
            continue
        if status == "confirmed" and clean(item.get("status")) != "confirmed":
            errors.append(f"code_units[{index}].status must be confirmed")
        if status == "confirmed" and not clean(item.get("codegen_route")):
            errors.append(f"code_units[{index}].codegen_route is missing")
        readiness = item.get("readiness") if isinstance(item.get("readiness"), Mapping) else {}
        if readiness.get("ready_for_codegen") and readiness.get("blockers"):
            errors.append(f"code_units[{index}] is ready while blockers remain")
        if status == "confirmed" and not readiness.get("ready_for_codegen"):
            warnings.append(f"{item.get('code_unit_id')} is confirmed but not ready for codegen")
    return {
        "status": "failed" if errors else "passed",
        "legacy": False,
        "error_count": len(unique(errors)),
        "warning_count": len(unique(warnings)),
        "errors": unique(errors),
        "warnings": unique(warnings),
    }
