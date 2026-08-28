#!/usr/bin/env python3
"""Enrich schedule-derived waterlines with auditable boundary evidence.

The enrichment is deliberately conservative: it links generic requirement
facts by identifiers, descriptions, temporal grain, field mappings, and
contract targets. It never turns an unconfirmed inference into production
readiness, and it contains no project-specific table names or unit counts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping


ROUTE_REPORT = "report-codegen"
ROUTE_SYNC = "data-sync-codegen"
GENERIC_TOKENS = {
    "abnormal",
    "by",
    "cal",
    "clickhouse",
    "code",
    "data",
    "day",
    "daily",
    "incr",
    "job",
    "p",
    "period",
    "pipeline",
    "qas",
    "report",
    "sync",
    "table",
    "task",
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = canonical(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(copy.deepcopy(value))
    return result


def slug(value: Any, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")
    return normalized or fallback


def tokens(*values: Any) -> set[str]:
    result: set[str] = set()
    for value in values:
        text = clean(value).lower()
        result.update(
            item
            for item in re.findall(r"[a-z0-9]+", text)
            if len(item) > 1 and item not in GENERIC_TOKENS
        )
        for chinese in re.findall(r"[\u4e00-\u9fff]+", text):
            if len(chinese) >= 2:
                result.add(chinese)
                result.update(chinese[index : index + 2] for index in range(len(chinese) - 1))
    return result


def identifier_tokens(*values: Any) -> set[str]:
    return {
        item
        for value in values
        for item in re.findall(r"[a-z0-9]+", clean(value).lower())
        if len(item) > 1 and item not in GENERIC_TOKENS
    }


def overlap_score(left: Iterable[str], right: Iterable[str]) -> int:
    return len(set(left).intersection(right))


def temporal_grain(*values: Any) -> str:
    text = " ".join(clean(value).lower() for value in values if clean(value))
    identifier = "_".join(re.findall(r"[a-z0-9]+", text))
    if re.search(r"(?:^|_)(?:daily|day|date)(?:_|$)", identifier) or any(
        marker in text for marker in ("by day", "每日", "每天", "昨日", "t-1")
    ):
        return "daily"
    if re.search(r"(?:^|_)(?:period|ptd)(?:_|$)", identifier) or any(
        marker in text for marker in ("byp", "by p", "按p", "当p", "截p", "ptd")
    ):
        return "period"
    if any(marker in text for marker in ("hourly", "每小时", "分钟")):
        return "intraday"
    if any(marker in text for marker in ("full", "全量")):
        return "full"
    return "unknown"


def waterline_grain(row: Mapping[str, Any]) -> str:
    identity_grain = temporal_grain(row.get("waterline_id"), row.get("pipeline_name"), row.get("task_name"))
    if identity_grain != "unknown":
        return identity_grain
    return temporal_grain(row.get("description"), row.get("schedule"), row.get("source_context"))


def algorithm_family(row: Mapping[str, Any]) -> str:
    base = slug(row.get("task_name") or row.get("pipeline_name") or row.get("waterline_id"), "waterline")
    suffixes = ("_daily", "_day", "_date", "_period", "_ptd")
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if base.endswith(suffix):
                base = base[: -len(suffix)].rstrip("_")
                changed = True
                break
    return base or "waterline"


def _physical_name(item: Mapping[str, Any]) -> str:
    return clean(item.get("physical_table") or item.get("table") or item.get("target"))


def _target_name(item: Mapping[str, Any]) -> str:
    return clean(item.get("target_name") or item.get("name") or _physical_name(item))


def _matches_name(candidate: Any, names: set[str]) -> bool:
    value = clean(candidate).lower()
    short = value.rsplit(".", 1)[-1]
    return bool(value and (value in names or short in names))


def _target_records(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    logical = [item for item in facts.get("report_targets", []) if isinstance(item, Mapping)]
    physical = [item for item in facts.get("report_physical_targets", []) if isinstance(item, Mapping)]
    mappings = [item for item in facts.get("report_field_mappings", []) if isinstance(item, Mapping)]
    writes = []
    codegen = facts.get("codegen_contract") if isinstance(facts.get("codegen_contract"), Mapping) else {}
    writes.extend(item for item in codegen.get("write_contracts", []) if isinstance(item, Mapping))
    records: list[dict[str, Any]] = []
    for index, item in enumerate(logical):
        record = copy.deepcopy(dict(item))
        record["target_name"] = _target_name(item)
        record["physical_table"] = _physical_name(item)
        if not record["physical_table"]:
            logical_tokens = tokens(record["target_name"], record.get("description"))
            matches = [
                candidate
                for candidate in physical
                if overlap_score(logical_tokens, tokens(_physical_name(candidate), candidate.get("description"))) >= 2
            ]
            if len(matches) == 1:
                record["physical_table"] = _physical_name(matches[0])
                record["physical_evidence"] = copy.deepcopy(dict(matches[0]))
        names = {
            clean(record["target_name"]).lower(),
            clean(record["physical_table"]).lower(),
            clean(record["physical_table"]).lower().rsplit(".", 1)[-1],
        }
        matching_mappings = [
            candidate
            for candidate in mappings
            if any(
                _matches_name(candidate.get(key), names)
                for key in ("inferred_target_name", "inferred_physical_table", "declared_table")
            )
        ]
        matching_writes = [candidate for candidate in writes if _matches_name(candidate.get("target"), names)]
        record["field_mappings"] = unique(matching_mappings)
        record["write_contracts"] = unique(matching_writes)
        record["grain"] = temporal_grain(record["target_name"], record["physical_table"], record.get("description"))
        record["record_id"] = slug(record["target_name"] or record["physical_table"], f"target_{index + 1:03d}")
        records.append(record)
    if not records:
        for index, item in enumerate(facts.get("cot_report_tables", []) or []):
            if not isinstance(item, Mapping):
                continue
            table = clean(item.get("clickhouse_table") or item.get("source_hbase_table"))
            records.append(
                {
                    **copy.deepcopy(dict(item)),
                    "target_name": table,
                    "physical_table": table,
                    "description": clean(item.get("description")),
                    "grain": temporal_grain(table, item.get("description")),
                    "record_id": slug(table, f"target_{index + 1:03d}"),
                    "field_mappings": [],
                    "write_contracts": [],
                }
            )
    return records


def _row_key(row: Mapping[str, Any], index: int) -> str:
    return slug(row.get("waterline_id") or row.get("pipeline_name") or row.get("task_name"), f"waterline_{index + 1:03d}")


def _row_tokens(row: Mapping[str, Any]) -> set[str]:
    return identifier_tokens(
        row.get("waterline_id"),
        row.get("pipeline_name"),
        row.get("task_name"),
        row.get("description"),
    )


def _target_tokens(target: Mapping[str, Any]) -> set[str]:
    return identifier_tokens(target.get("target_name"), target.get("physical_table"))


def assign_targets(
    rows: list[Mapping[str, Any]],
    targets: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str], list[str]]:
    assignments: dict[str, list[dict[str, Any]]] = {
        _row_key(row, index): [] for index, row in enumerate(rows)
    }
    specific_rows: set[str] = set()
    assigned_target_ids: set[str] = set()
    unresolved: list[str] = []
    row_meta = []
    for index, row in enumerate(rows):
        row_meta.append(
            {
                "key": _row_key(row, index),
                "tokens": _row_tokens(row),
                "grain": waterline_grain(row),
                "data_utilization": clean(row.get("data_utilization")).lower(),
            }
        )
    for target in targets:
        scores = []
        target_tokens = _target_tokens(target)
        target_du = clean(target.get("data_utilization")).lower()
        for meta in row_meta:
            if target_du and meta["data_utilization"] and target_du != meta["data_utilization"]:
                continue
            scores.append((overlap_score(meta["tokens"], target_tokens), meta["key"]))
        scores.sort(reverse=True)
        if scores and scores[0][0] >= 2 and (len(scores) == 1 or scores[0][0] > scores[1][0]):
            assignments[scores[0][1]].append(copy.deepcopy(target))
            specific_rows.add(scores[0][1])
            assigned_target_ids.add(target["record_id"])
    for target in targets:
        if target["record_id"] in assigned_target_ids:
            continue
        target_du = clean(target.get("data_utilization")).lower()
        candidates = [
            meta
            for meta in row_meta
            if meta["key"] not in specific_rows
            and (not target_du or not meta["data_utilization"] or target_du == meta["data_utilization"])
            and target.get("grain") != "unknown"
            and meta["grain"] == target.get("grain")
        ]
        if len(candidates) == 1:
            assignments[candidates[0]["key"]].append(copy.deepcopy(target))
            assigned_target_ids.add(target["record_id"])
        else:
            unresolved.append(target["record_id"])
    return assignments, specific_rows, unresolved


def _rule_rows(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(dict(item))
        for key in ("report_business_rules", "report_kpi_rules")
        for item in facts.get(key, []) or []
        if isinstance(item, Mapping) and any(clean(item.get(field)) for field in ("rule", "calculation_logic", "formula"))
    ]


def select_rules(
    row: Mapping[str, Any],
    selected_targets: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    specific: bool,
) -> list[dict[str, Any]]:
    target_tokens = set().union(*(_target_tokens(item) for item in selected_targets)) if selected_targets else set()
    direct = [
        item
        for item in rules
        if overlap_score(target_tokens, tokens(item.get("output_table"), item.get("target"))) >= 2
    ]
    if direct or specific:
        return unique(direct)
    grain = waterline_grain(row)
    return unique(
        item
        for item in rules
        if grain != "unknown" and temporal_grain(item.get("grain"), item.get("output_table"), item.get("source_context")) == grain
    )


def _source_records(
    facts: Mapping[str, Any],
    row: Mapping[str, Any],
    targets: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    source_candidates = [item for item in facts.get("report_sources", []) or [] if isinstance(item, Mapping)]
    evidence_texts = [clean(item.get("source")) for item in rules if clean(item.get("source"))]
    identity_match_tokens = _row_tokens(row)
    for target in targets:
        identity_match_tokens.update(_target_tokens(target))
    evidence_identifier_tokens = set().union(*(identifier_tokens(value) for value in evidence_texts)) if evidence_texts else set()

    def strongly_matches(left: str, right: str) -> bool:
        normalized_left = clean(left).lower()
        normalized_right = clean(right).lower()
        if not normalized_left or not normalized_right:
            return False
        if len(normalized_left) >= 4 and normalized_left in normalized_right:
            return True
        if len(normalized_right) >= 4 and normalized_right in normalized_left:
            return True
        return overlap_score(identifier_tokens(normalized_left), identifier_tokens(normalized_right)) >= 2

    selected = []
    for source in source_candidates:
        source_identity_tokens = identifier_tokens(source.get("table_or_path"), source.get("description"))
        join_filter_tokens = identifier_tokens(source.get("join_filter"))
        source_text = " ".join(clean(source.get(key)) for key in ("table_or_path", "description", "join_filter"))
        if (
            overlap_score(evidence_identifier_tokens, source_identity_tokens) >= 2
            or overlap_score(identity_match_tokens, source_identity_tokens) >= 2
            or overlap_score(identity_match_tokens, join_filter_tokens) >= 2
            or any(strongly_matches(value, source_text) for value in evidence_texts)
        ):
            selected.append(copy.deepcopy(dict(source)))
    result: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(unique(selected)):
        key = slug(source.get("description") or source.get("table_or_path"), f"source_{index + 1:03d}")
        result[key] = {
            "kind": clean(source.get("storage")) or "unclassified",
            "location": clean(source.get("description") or source.get("table_or_path")),
            "logical_name": clean(source.get("table_or_path")),
            "selection": clean(source.get("range") or source.get("join_filter")),
            "evidence": copy.deepcopy(source),
        }
    for value in evidence_texts:
        if any(value in canonical(item) for item in result.values()):
            continue
        key = slug(value, f"requirement_source_{len(result) + 1:03d}")
        result[key] = {
            "kind": "requirement_evidence",
            "location": value,
            "logical_name": value,
            "selection": "",
            "evidence_status": "needs_physical_source_confirmation",
        }
    return result


def _output_contract(targets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for target in targets:
        name = clean(target.get("target_name") or target.get("physical_table"))
        mappings = target.get("field_mappings") or []
        fields = [
            clean(field.get("target_field") or field.get("field_name"))
            for mapping in mappings
            for field in mapping.get("fields", []) or []
            if isinstance(field, Mapping) and clean(field.get("target_field") or field.get("field_name"))
        ]
        result[name] = {
            "target_name": name,
            "physical_table": clean(target.get("physical_table")),
            "storage": clean(target.get("storage")),
            "description": clean(target.get("description")),
            "columns": unique(fields),
            "input": "",
            "evidence_status": "needs_executable_step_binding",
        }
    return result


def _write_contract(targets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for target in targets:
        name = clean(target.get("target_name") or target.get("physical_table"))
        write_evidence = (target.get("write_contracts") or [{}])[0]
        result[name] = {
            "kind": clean(write_evidence.get("storage_kind") or target.get("storage")),
            "table": clean(write_evidence.get("target") or target.get("physical_table")),
            "mode": clean(write_evidence.get("write_mode")),
            "predicate": copy.deepcopy(write_evidence.get("replacement_predicate") or {}),
            "columns": copy.deepcopy(write_evidence.get("ordered_columns") or []),
            "empty_output_policy": clean(write_evidence.get("empty_output_policy")),
            "evidence_status": clean(write_evidence.get("status")) or "needs_confirmation",
        }
    return result


def _step_contract(rules: list[dict[str, Any]], targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for index, rule in enumerate(rules):
        steps.append(
            {
                "id": f"requirement_rule_{index + 1:03d}",
                "op": "requirement_rule",
                "name": clean(rule.get("abnormal_type") or rule.get("name") or rule.get("scenario")),
                "expression": clean(rule.get("rule") or rule.get("calculation_logic") or rule.get("formula")),
                "grain": clean(rule.get("grain")),
                "source": clean(rule.get("source")),
                "output_evidence": clean(rule.get("output_table")),
                "evidence_status": "needs_executable_operation_mapping",
            }
        )
    if not steps:
        mapping_count = sum(len(item.get("field_mappings") or []) for item in targets)
        if mapping_count:
            steps.append(
                {
                    "id": "field_mapping_review",
                    "op": "field_mapping_review",
                    "mapping_count": mapping_count,
                    "evidence_status": "needs_executable_operation_mapping",
                }
            )
    return steps


def _route_decision(
    facts: Mapping[str, Any],
    row: Mapping[str, Any],
    targets: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    explicit = clean(row.get("codegen_route") or row.get("handoff_to")).lower()
    if explicit in {"report", ROUTE_REPORT}:
        return ROUTE_REPORT, "standard_report", [{"route": ROUTE_REPORT, "reason": "explicit waterline route", "confidence": "high"}]
    if explicit in {"sync", "data-sync", ROUTE_SYNC}:
        return ROUTE_SYNC, "cot_table_sync", [{"route": ROUTE_SYNC, "reason": "explicit waterline route", "confidence": "high"}]
    identity = " ".join(clean(row.get(key)).lower() for key in ("waterline_id", "pipeline_name", "task_name"))
    description = clean(row.get("description")).lower()
    sync_score = (3 if "sync" in identity or "同步" in identity else 0) + (1 if "incr" in identity or "increment" in identity else 0)
    report_score = 0
    if any(marker in description for marker in ("报表", "report", "kpi", "指标", "分析")):
        report_score += 5
    if rules:
        report_score += 3
    if any(target.get("field_mappings") for target in targets):
        report_score += 2
    candidates = []
    if report_score:
        candidates.append({"route": ROUTE_REPORT, "score": report_score, "reason": "report/rule/field-mapping evidence"})
    if sync_score:
        candidates.append({"route": ROUTE_SYNC, "score": sync_score, "reason": "sync/incremental task identity"})
    project_type = clean((facts.get("codegen_contract") or {}).get("project_type")) if isinstance(facts.get("codegen_contract"), Mapping) else ""
    project_route = ROUTE_REPORT if project_type == "report" else (ROUTE_SYNC if project_type == "data-sync" else "")
    if project_route and not any(item["route"] == project_route for item in candidates):
        candidates.append({"route": project_route, "score": 1, "reason": "project-level route candidate only"})
    candidates.sort(key=lambda item: (-item["score"], item["route"]))
    if candidates and (len(candidates) == 1 or candidates[0]["score"] - candidates[1]["score"] >= 2):
        route = candidates[0]["route"]
        return route, "standard_report" if route == ROUTE_REPORT else "cot_table_sync", candidates
    return "", "unclassified", candidates


def _algorithm_key(row: Mapping[str, Any], rules: list[dict[str, Any]], targets: list[dict[str, Any]]) -> tuple[str, str]:
    family = algorithm_family(row)
    signature_evidence = [
        clean(item.get("rule") or item.get("calculation_logic") or item.get("formula"))
        for item in rules
        if clean(item.get("rule") or item.get("calculation_logic") or item.get("formula"))
    ]
    if not signature_evidence:
        signature_evidence = [
            clean(field.get("calculation_logic"))
            for target in targets
            for mapping in target.get("field_mappings") or []
            for field in mapping.get("fields", []) or []
            if isinstance(field, Mapping) and clean(field.get("calculation_logic"))
        ]
    if not signature_evidence:
        return family, "identity_only"
    digest = hashlib.sha256(canonical(unique(signature_evidence)).encode("utf-8")).hexdigest()[:10]
    return f"{family}:{digest}", "requirement_logic"


def _dependency_evidence(
    key: str,
    sources: Mapping[str, Any],
    assignments: Mapping[str, list[dict[str, Any]]],
) -> tuple[list[str], dict[str, Any]]:
    source_blob = canonical(
        [
            {
                "location": item.get("location", ""),
                "logical_name": item.get("logical_name", ""),
            }
            for item in sources.values()
            if isinstance(item, Mapping)
        ]
    ).lower()
    dependencies = []
    matches = []
    for owner, targets in assignments.items():
        if owner == key:
            continue
        for target in targets:
            names = {
                clean(target.get("target_name")).lower(),
                clean(target.get("physical_table")).lower(),
                clean(target.get("physical_table")).lower().rsplit(".", 1)[-1],
            }
            matched = [name for name in names if name and name in source_blob]
            if matched:
                dependencies.append(owner)
                matches.append({"waterline_id": owner, "matched_targets": sorted(set(matched))})
    return sorted(set(dependencies)), {
        "status": "inferred" if dependencies else "not_identified",
        "matches": matches,
        "confirmation_required": True,
    }


def enrich_schedule_waterlines(
    facts: Mapping[str, Any],
    schedule_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return enriched copies of schedule rows for generic code-unit planning."""
    rows = [copy.deepcopy(dict(item)) for item in schedule_rows]
    targets = _target_records(facts)
    assignments, specific_rows, unresolved_targets = assign_targets(rows, targets)
    all_rules = _rule_rows(facts)
    enriched = []
    for index, row in enumerate(rows):
        key = _row_key(row, index)
        selected_targets = assignments.get(key, [])
        selected_rules = select_rules(row, selected_targets, all_rules, key in specific_rows)
        route, component_kind, route_candidates = _route_decision(facts, row, selected_targets, selected_rules)
        algorithm, algorithm_source = _algorithm_key(row, selected_rules, selected_targets)
        grain = waterline_grain(row)
        sources = _source_records(facts, row, selected_targets, selected_rules)
        steps = _step_contract(selected_rules, selected_targets)
        outputs = _output_contract(selected_targets)
        writes = _write_contract(selected_targets)
        dependencies, dependency_evidence = _dependency_evidence(key, sources, assignments)
        write_modes = sorted({clean(item.get("mode")) for item in writes.values() if clean(item.get("mode"))})
        storage_kinds = sorted({clean(item.get("kind")).lower() for item in writes.values() if clean(item.get("kind"))})
        state_boundary = {
            "compatibility_group": f"{algorithm_family(row)}:{grain}",
            "mode": "scheduled_window" if grain != "unknown" else "unconfirmed",
            "temporal_grain": grain,
            "schedule": clean(row.get("schedule")),
            "watermark": "",
            "evidence_status": "inferred" if grain != "unknown" else "missing",
        }
        write_boundary = {
            "compatibility_group": ":".join(storage_kinds + (write_modes or ["mode_unconfirmed"])) or "write_unconfirmed",
            "targets": [clean(item.get("physical_table") or item.get("target_name")) for item in selected_targets],
            "storage_kinds": storage_kinds,
            "write_modes": write_modes,
            "parameterized_targets": True,
            "evidence_status": "confirmed" if writes and write_modes else ("inferred" if writes else "missing"),
        }
        data_utilization = clean(row.get("data_utilization"))
        deployment_boundary = {
            "compatibility_group": slug(f"{route or 'route_unconfirmed'}_{data_utilization or 'project'}"),
            "schedule": clean(row.get("schedule")),
            "independent_deployment": None,
            "evidence_status": "inferred",
        }
        failure_boundary = {
            "compatibility_group": slug(f"{route or 'route_unconfirmed'}_{data_utilization or 'project'}"),
            "failure_isolation": None,
            "partial_failure_semantics": "",
            "evidence_status": "missing",
        }
        blockers = []
        if not route:
            candidate_names = ", ".join(item["route"] for item in route_candidates) or "none"
            blockers.append(f"[routing] codegen_route requires confirmation; candidates: {candidate_names}")
        if algorithm_source == "identity_only":
            blockers.append("[algorithm] executable algorithm evidence is not linked; identity-derived family requires confirmation")
        if not sources:
            blockers.append("[sources] no unit-scoped source evidence is linked")
        if not steps:
            blockers.append("[steps] no unit-scoped transformation evidence is linked")
        elif any(item.get("evidence_status") != "confirmed" for item in steps):
            blockers.append("[steps] requirement rules or field mappings still need executable operation mapping")
        if not outputs:
            blockers.append("[outputs] no unit-scoped target evidence is linked")
        elif any(not item.get("input") for item in outputs.values()):
            blockers.append("[outputs] target evidence still needs executable step binding")
        if not writes:
            blockers.append("[writes] no unit-scoped write target evidence is linked")
        elif not write_modes:
            blockers.append("[writes] write mode and replacement transaction semantics require confirmation")
        if not state_boundary["watermark"]:
            blockers.append("[state] watermark/incremental window semantics require confirmation")
        blockers.append("[deployment] deployment and rerun isolation boundary requires confirmation")
        blockers.append("[failure] failure-isolation and partial-failure semantics require confirmation")
        if dependency_evidence["status"] == "not_identified":
            blockers.append("[dependencies] upstream/downstream relationship requires confirmation")
        confidence = "medium" if route and algorithm_source == "requirement_logic" and outputs else "low"
        parameter_profile = {
            "data_utilization": data_utilization,
            "task_name": clean(row.get("task_name")),
            "schedule": clean(row.get("schedule")),
            "temporal_grain": grain,
            "output_targets": [clean(item.get("physical_table") or item.get("target_name")) for item in selected_targets],
        }
        enriched.append(
            {
                **row,
                "waterline_id": key,
                "codegen_route": route,
                "codegen_route_candidates": route_candidates,
                "component_kind": component_kind,
                "algorithm_key": algorithm,
                "algorithm_evidence": {"source": algorithm_source, "rule_count": len(selected_rules)},
                "parameter_profile": parameter_profile,
                "parameterizable_fields": ["schedule", "temporal_grain", "output_targets"],
                "sources": sources,
                "steps": steps,
                "outputs": outputs,
                "writes": writes,
                "state_boundary": state_boundary,
                "write_boundary": write_boundary,
                "deployment_boundary": deployment_boundary,
                "failure_boundary": failure_boundary,
                "retry": {"status": "unconfirmed"},
                "rerun": {"status": "unconfirmed", "temporal_grain": grain},
                "empty_output_semantics": {"status": "unconfirmed"},
                "failure_semantics": {"status": "unconfirmed"},
                "depends_on": dependencies,
                "dependency_evidence": dependency_evidence,
                "covered_tables": [clean(item.get("physical_table") or item.get("target_name")) for item in selected_targets],
                "boundary_evidence": {
                    "algorithm": {"status": "inferred", "source": algorithm_source},
                    "parameters": {"status": "inferred", "profile": parameter_profile},
                    "state": {"status": state_boundary["evidence_status"]},
                    "write": {"status": write_boundary["evidence_status"], "target_count": len(writes)},
                    "deployment": {"status": "inferred"},
                    "failure": {"status": "missing"},
                    "dependencies": dependency_evidence,
                    "unassigned_project_targets": unresolved_targets,
                },
                "boundary_confidence": confidence,
                "blockers": unique(blockers),
            }
        )
    return enriched
