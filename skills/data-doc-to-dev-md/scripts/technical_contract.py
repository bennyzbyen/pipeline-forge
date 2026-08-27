#!/usr/bin/env python3
"""Build and validate PipelineForge technical contracts.

Contract v2 keeps code-generation readiness separate from deployment safety.
Readers accept legacy v1 contracts, but strict deployment validation blocks
them until the missing runtime, parameter, source, and write decisions are
made explicit.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = 2
SEVERITIES = {"ERROR", "DEPLOYMENT_BLOCKER", "WARNING"}
QUESTION_ID_PATTERN = re.compile(r"^TC-(?:CG|DP|NB)-(?:\d{3}|X[A-F0-9]{6})$")
QUESTION_CATEGORIES = {"blocking_codegen", "deployment_confirmation", "non_blocking"}
VALIDATION_GATES = [
    {
        "code": "CONTRACT-VERSION",
        "severity": "ERROR",
        "description": "The contract version is supported and structurally valid.",
    },
    {
        "code": "FIELD-ROLE",
        "severity": "ERROR",
        "description": "Physical source, logical, and target fields are distinct and conflicting evidence is unresolved.",
    },
    {
        "code": "SOURCE-RANGE",
        "severity": "DEPLOYMENT_BLOCKER",
        "description": "Each source declares an exact location, grain, time/range semantics, and final request behavior.",
    },
    {
        "code": "RULE-OPERATOR",
        "severity": "ERROR",
        "description": "Threshold operators, values, evaluation grain, and detail scope do not conflict.",
    },
    {
        "code": "PARAMETER-MATRIX",
        "severity": "DEPLOYMENT_BLOCKER",
        "description": "Omitted, null, blank, empty, scalar, list, and invalid parameter shapes have explicit semantics.",
    },
    {
        "code": "RUNTIME-PROFILE",
        "severity": "DEPLOYMENT_BLOCKER",
        "description": "Python compatibility, result protocol, safe logging, and environment connections are declared.",
    },
    {
        "code": "WRITE-SAFETY",
        "severity": "DEPLOYMENT_BLOCKER",
        "description": "Ordered columns, wire format, empty-output behavior, and replacement recovery are declared.",
    },
]


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = clean(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def provenance(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_index": item.get("source_doc_index"),
        "document": clean(item.get("source_doc_name")),
        "evidence_file": clean(item.get("source_csv") or item.get("csv")),
        "sheet": clean(item.get("source_sheet") or item.get("sheet")),
        "evidence_kind": clean(item.get("source_kind")),
    }


def storage_kind(value: Any, location: Any = "") -> str:
    text = f"{clean(value)} {clean(location)}".lower()
    if "hbase" in text:
        return "hbase"
    if "clickhouse" in text:
        return "clickhouse"
    if "mssql" in text or "sql server" in text:
        return "mssql"
    if "mysql" in text:
        return "mysql"
    if "gateway" in text or "文件" in text or clean(location).startswith(("/", "\\")):
        return "fs"
    return "other"


def looks_physical(value: Any) -> bool:
    text = clean(value)
    return bool(
        text
        and (
            re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", text)
            or text.startswith(("/", "\\"))
            or re.fullmatch(r"[A-Za-z0-9_\-]+", text)
        )
    )


def source_location(source: Mapping[str, Any]) -> tuple[str, str]:
    candidates = [
        source.get("physical_table"),
        source.get("table"),
        source.get("path"),
        source.get("description"),
        source.get("table_or_path"),
    ]
    for candidate in candidates:
        if looks_physical(candidate):
            return clean(candidate), "confirmed"
    fallback = clean(source.get("table_or_path") or source.get("description"))
    return fallback, "needs_confirmation" if fallback else "missing"


def predicates(expression: Any) -> list[dict[str, str]]:
    text = clean(expression).replace("≥", ">=").replace("≤", "<=").replace("＞", ">").replace("＜", "<")
    pattern = re.compile(
        r"(?P<subject>[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fffA-Za-z0-9_（）() /+\-]{1,40}?)\s*"
        r"(?P<operator>>=|<=|!=|<>|==|>|<|=)\s*"
        r"(?P<value>-?\d+(?:\.\d+)?\s*(?:%|分钟|分|min|m|家|单|元)?)",
        re.IGNORECASE,
    )
    return [
        {
            "subject": clean(match.group("subject")),
            "operator": match.group("operator"),
            "value": clean(match.group("value")),
        }
        for match in pattern.finditer(text)
    ]


def field_roles(field: Mapping[str, Any]) -> list[str]:
    roles: list[str] = []
    if clean(field.get("target_field")):
        roles.append("output")
    logic = clean(field.get("calculation_logic") or field.get("rule")).lower()
    if any(marker in logic for marker in ["过滤", "筛选", " where ", "filter"]):
        roles.append("filter")
    if any(marker in logic for marker in ["关联", "连接", " join "]):
        roles.append("join")
    if logic and not re.fullmatch(r"取(?:数据源|[^的]{0,20})的字段\s*[A-Za-z0-9_]+", logic):
        roles.append("calculation")
    return unique(roles)


def build_field_contracts(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for mapping_index, mapping in enumerate(facts.get("report_field_mappings", []) or [], start=1):
        target = clean(
            mapping.get("inferred_physical_table")
            or mapping.get("inferred_target_name")
            or mapping.get("declared_table")
        )
        for field_index, field in enumerate(mapping.get("fields", []) or [], start=1):
            source_field = clean(field.get("source_field"))
            target_field = clean(field.get("target_field"))
            logic = clean(
                field.get("calculation_logic")
                or field.get("eo_order_logic")
                or field.get("dms_order_logic")
            )
            status = "confirmed" if target_field and (source_field or logic) else "needs_confirmation"
            contracts.append(
                {
                    "id": f"field_{mapping_index:03d}_{field_index:03d}",
                    "target": target,
                    "physical_source_table": clean(field.get("source_table")),
                    "physical_source_field": source_field,
                    "logical_field": clean(field.get("field_name")),
                    "target_field": target_field,
                    "type": clean(field.get("field_type")),
                    "required": None,
                    "roles": field_roles(field),
                    "expression": logic,
                    "status": status,
                    "provenance": provenance(mapping),
                }
            )
    return contracts


def build_source_contracts(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    raw_sources = list(facts.get("report_sources", []) or [])
    if not raw_sources:
        raw_sources = list(facts.get("cot_report_tables", []) or [])
    for index, source in enumerate(raw_sources, start=1):
        location, status = source_location(source)
        required_columns = source.get("fields") or source.get("source_fields") or []
        if isinstance(required_columns, str):
            required_columns = unique(re.split(r"[,，;；\s]+", required_columns))
        contracts.append(
            {
                "id": f"source_{index:03d}",
                "logical_name": clean(source.get("table_or_path") or source.get("name") or source.get("report_table")),
                "storage_kind": storage_kind(source.get("storage"), location),
                "exact_location": location,
                "location_status": status,
                "grain": clean(source.get("grain")),
                "business_time_field": clean(source.get("business_time_field") or source.get("time_field")),
                "required_columns": [clean(item) for item in required_columns if clean(item)],
                "missing_policy": clean(source.get("missing_policy")),
                "range_contract": {
                    "selection": clean(source.get("range") or source.get("source_range")),
                    "rowkey": clean(source.get("rowkey") or source.get("rowkey_rule")),
                    "index": clean(source.get("index") or source.get("index_name")),
                    "file_path": location if storage_kind(source.get("storage"), location) == "fs" else "",
                    "final_request_validation": clean(source.get("final_request_validation")),
                },
                "status": "confirmed" if status == "confirmed" else "needs_confirmation",
                "provenance": provenance(source),
            }
        )
    return contracts


def build_rule_contracts(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    rule_sets = [
        ("business_rule", facts.get("report_business_rules", []) or []),
        ("kpi_rule", facts.get("report_kpi_rules", []) or []),
    ]
    index = 0
    for kind, items in rule_sets:
        for item in items:
            index += 1
            expression = clean(item.get("rule") or item.get("aggregation_logic"))
            parsed = predicates(expression)
            contracts.append(
                {
                    "id": f"rule_{index:03d}",
                    "kind": kind,
                    "name": clean(item.get("abnormal_type") or item.get("kpi")),
                    "candidate_set": clean(item.get("source") or item.get("source_table")),
                    "evaluation_grain": clean(item.get("grain")),
                    "expression": expression,
                    "predicates": parsed,
                    "detail_scope": clean(item.get("output_table")),
                    "id_assignment": clean(item.get("id_assignment")),
                    "status": "confirmed" if expression else "needs_confirmation",
                    "provenance": provenance(item),
                }
            )
    return contracts


def parameter_shape_matrix(item: Mapping[str, Any]) -> dict[str, str]:
    semantics = item.get("semantics") if isinstance(item.get("semantics"), Mapping) else {}
    return {
        shape: clean(semantics.get(shape) or item.get(shape))
        for shape in ["omitted", "null", "blank", "empty", "scalar", "list", "invalid"]
    }


def build_parameter_contracts(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = facts.get("parameter_contracts") or facts.get("report_parameters") or facts.get("parameters") or []
    if isinstance(raw, Mapping):
        raw = [dict(value, name=key) if isinstance(value, Mapping) else {"name": key, "default": value} for key, value in raw.items()]
    contracts: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        contracts.append(
            {
                "id": f"parameter_{index:03d}",
                "name": clean(item.get("name") or item.get("parameter")),
                "type": clean(item.get("type")),
                "required": item.get("required"),
                "accepted_shapes": list(item.get("accepted_shapes") or []),
                "semantics": parameter_shape_matrix(item),
                "deduplicate": item.get("deduplicate"),
                "preserve_order": item.get("preserve_order"),
                "status": clean(item.get("status")) or "needs_confirmation",
                "provenance": provenance(item),
            }
        )
    return contracts


def build_runtime_contract(facts: Mapping[str, Any]) -> dict[str, Any]:
    raw = facts.get("runtime_contract") or facts.get("report_runtime_contract") or {}
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "python_min": clean(raw.get("python_min")),
        "entrypoint": clean(raw.get("entrypoint")),
        "result_protocol": raw.get("result_protocol") or {},
        "environment_connection_matrix": raw.get("environment_connection_matrix") or {},
        "source_modes": raw.get("source_modes") or {},
        "output_modes": raw.get("output_modes") or {},
        "safe_log_policy": raw.get("safe_log_policy") or {},
        "status": clean(raw.get("status")) or "needs_confirmation",
    }


def mapping_for_target(facts: Mapping[str, Any], table: str, description: str) -> Mapping[str, Any]:
    mappings = facts.get("report_field_mappings", []) or []
    for mapping in mappings:
        candidates = {
            clean(mapping.get("inferred_physical_table")),
            clean(mapping.get("inferred_target_name")),
            clean(mapping.get("declared_table")),
            clean(mapping.get("inferred_target_description")),
        }
        if table in candidates or description in candidates:
            return mapping
    return mappings[0] if len(mappings) == 1 else {}


def build_write_contracts(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets = facts.get("report_physical_targets") or facts.get("report_clickhouse_targets") or facts.get("target_mappings") or []
    contracts: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        table = clean(target.get("table") or target.get("physical_table") or target.get("target_table") or target.get("target_name"))
        description = clean(target.get("description"))
        mapping = mapping_for_target(facts, table, description)
        fields = mapping.get("fields", []) if isinstance(mapping, Mapping) else []
        ordered_columns = [clean(field.get("target_field")) for field in fields if clean(field.get("target_field"))]
        column_types = [clean(field.get("field_type")) for field in fields if clean(field.get("target_field"))]
        raw = target.get("write_contract") if isinstance(target.get("write_contract"), Mapping) else {}
        contracts.append(
            {
                "id": f"write_{index:03d}",
                "target": table,
                "storage_kind": storage_kind(target.get("storage"), table),
                "ordered_columns": ordered_columns,
                "column_types": column_types,
                "write_mode": clean(raw.get("write_mode") or target.get("write_mode")),
                "replacement_predicate": clean(raw.get("replacement_predicate") or target.get("delete_condition")),
                "empty_output_policy": clean(raw.get("empty_output_policy")) or "block_destructive_replace",
                "staging_wire_format": raw.get("staging_wire_format") or {},
                "replacement_safety": raw.get("replacement_safety") or {},
                "audit_contract": raw.get("audit_contract") or {},
                "status": clean(raw.get("status")) or "needs_confirmation",
                "provenance": provenance(target),
            }
        )
    return contracts


def conflict_key(conflict: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        clean(conflict.get("kind")),
        clean(conflict.get("target")),
        clean(conflict.get("field")),
    )


def detect_contract_conflicts(facts: Mapping[str, Any], fields: list[dict[str, Any]], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in facts.get("conflicts", []) or []:
        key = conflict_key(item)
        if key in seen:
            continue
        seen.add(key)
        conflicts.append(
            {
                "code": "EVIDENCE_CONFLICT",
                "kind": key[0] or "document_conflict",
                "target": key[1],
                "field": key[2],
                "first_value": clean(item.get("first_logic") or item.get("first_value")),
                "second_value": clean(item.get("second_logic") or item.get("second_value")),
                "first_source": clean(item.get("first_source")),
                "second_source": clean(item.get("second_source")),
                "status": "unresolved",
            }
        )

    field_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for field in fields:
        field_groups[(clean(field.get("target")), clean(field.get("target_field")))].append(field)
    for (target, field_name), items in field_groups.items():
        if not target or not field_name:
            continue
        types = unique(item.get("type", "") for item in items)
        if len(types) > 1:
            conflicts.append(
                {
                    "code": "FIELD_TYPE_CONFLICT",
                    "kind": "field_type_conflict",
                    "target": target,
                    "field": field_name,
                    "values": types,
                    "status": "unresolved",
                }
            )

    rule_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        rule_groups[(clean(rule.get("name")), clean(rule.get("evaluation_grain")).lower())].append(rule)
    for (name, grain), items in rule_groups.items():
        signatures = unique(
            "|".join(f"{p.get('subject')}:{p.get('operator')}:{p.get('value')}" for p in item.get("predicates", []))
            for item in items
            if item.get("predicates")
        )
        if name and len(signatures) > 1:
            conflicts.append(
                {
                    "code": "RULE_OPERATOR_CONFLICT",
                    "kind": "rule_operator_conflict",
                    "target": name,
                    "field": grain,
                    "values": signatures,
                    "status": "unresolved",
                }
            )
    return conflicts


def issue(code: str, severity: str, path: str, message: str) -> dict[str, str]:
    if severity not in SEVERITIES:
        raise ValueError(f"unsupported severity: {severity}")
    return {"code": code, "severity": severity, "path": path, "message": message}


def stable_question_id(prefix: str, *semantic_parts: Any) -> str:
    semantic_key = ":".join(clean(part).lower() for part in semantic_parts).encode("utf-8")
    digest = hashlib.sha1(semantic_key).hexdigest()[:6].upper()
    return f"TC-{prefix}-X{digest}"


def add_contract_question(
    questions: list[dict[str, Any]],
    question_id: str,
    category: str,
    text: str,
    **metadata: Any,
) -> None:
    if any(clean(item.get("id")) == question_id for item in questions):
        return
    question: dict[str, Any] = {
        "id": question_id,
        "category": category,
        "text": text,
        "status": "open",
    }
    question.update({key: value for key, value in metadata.items() if value not in (None, "")})
    questions.append(question)


def validate_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    version = contract.get("contract_version", 1)
    errors: list[dict[str, str]] = []
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if version == 1:
        warnings.append(issue("LEGACY_CONTRACT_V1", "WARNING", "contract_version", "Legacy v1 remains readable for code generation review."))
        blockers.append(issue("LEGACY_CONTRACT_V1_DEPLOYMENT", "DEPLOYMENT_BLOCKER", "contract_version", "Strict deployment requires contract v2."))
        return validation_result(errors, blockers, warnings)
    if version != CONTRACT_VERSION:
        errors.append(issue("UNSUPPORTED_CONTRACT_VERSION", "ERROR", "contract_version", f"Expected 1 or {CONTRACT_VERSION}, got {version!r}."))
        return validation_result(errors, blockers, warnings)

    if clean(contract.get("project_type")) not in {"report", "data-sync"}:
        errors.append(issue("PROJECT_TYPE_UNRESOLVED", "ERROR", "project_type", "Project type must be report or data-sync."))
    seen_question_ids: set[str] = set()
    for index, question in enumerate(contract.get("open_questions", []) or []):
        path = f"open_questions[{index}]"
        if not isinstance(question, Mapping):
            errors.append(issue("INVALID_OPEN_QUESTION", "ERROR", path, "Open question must be an object."))
            continue
        question_id = clean(question.get("id"))
        if not QUESTION_ID_PATTERN.fullmatch(question_id):
            errors.append(issue("INVALID_QUESTION_ID", "ERROR", f"{path}.id", "Question ID must use TC-CG/TC-DP/TC-NB plus a stable numeric or deterministic fallback suffix."))
        elif question_id in seen_question_ids:
            errors.append(issue("DUPLICATE_QUESTION_ID", "ERROR", f"{path}.id", f"Question ID {question_id} is duplicated."))
        seen_question_ids.add(question_id)
        if clean(question.get("category")) not in QUESTION_CATEGORIES:
            errors.append(issue("INVALID_QUESTION_CATEGORY", "ERROR", f"{path}.category", "Question category is unsupported."))
        if not clean(question.get("text")):
            errors.append(issue("EMPTY_QUESTION_TEXT", "ERROR", f"{path}.text", "Open question text must not be empty."))
    for index, conflict in enumerate(contract.get("conflicts", []) or []):
        if clean(conflict.get("status")).lower() != "resolved":
            errors.append(issue(clean(conflict.get("code")) or "EVIDENCE_CONFLICT", "ERROR", f"conflicts[{index}]", "Conflicting requirement evidence must be resolved explicitly."))

    for index, source in enumerate(contract.get("source_contracts", []) or []):
        if clean(source.get("location_status")) != "confirmed":
            blockers.append(issue("SOURCE_LOCATION_UNCONFIRMED", "DEPLOYMENT_BLOCKER", f"source_contracts[{index}].exact_location", "Exact physical source location is not confirmed."))
        range_contract = source.get("range_contract") if isinstance(source.get("range_contract"), Mapping) else {}
        if not clean(range_contract.get("selection")):
            blockers.append(issue("SOURCE_RANGE_UNDECLARED", "DEPLOYMENT_BLOCKER", f"source_contracts[{index}].range_contract.selection", "Source range semantics are missing."))
        if clean(source.get("storage_kind")) == "hbase" and not clean(range_contract.get("final_request_validation")):
            blockers.append(issue("HBASE_FINAL_REQUEST_UNVALIDATED", "DEPLOYMENT_BLOCKER", f"source_contracts[{index}].range_contract.final_request_validation", "Validate the final HBase request after wrapper defaults are applied."))

    parameters = contract.get("parameter_contracts", []) or []
    if not parameters:
        blockers.append(issue("PARAMETER_CONTRACT_UNDECLARED", "DEPLOYMENT_BLOCKER", "parameter_contracts", "Declare parameters explicitly, including a no-parameter contract when applicable."))
    for index, parameter in enumerate(parameters):
        semantics = parameter.get("semantics") if isinstance(parameter.get("semantics"), Mapping) else {}
        missing = [shape for shape in ["omitted", "null", "blank", "empty", "scalar", "list", "invalid"] if not clean(semantics.get(shape))]
        if missing:
            blockers.append(issue("PARAMETER_SHAPES_INCOMPLETE", "DEPLOYMENT_BLOCKER", f"parameter_contracts[{index}].semantics", f"Missing semantics for: {', '.join(missing)}."))

    runtime = contract.get("runtime_contract") if isinstance(contract.get("runtime_contract"), Mapping) else {}
    for key in ["python_min", "entrypoint", "result_protocol", "environment_connection_matrix", "safe_log_policy"]:
        if not runtime.get(key):
            blockers.append(issue("RUNTIME_CONTRACT_INCOMPLETE", "DEPLOYMENT_BLOCKER", f"runtime_contract.{key}", f"Runtime field {key} is missing."))

    writes = contract.get("write_contracts", []) or []
    if not writes and clean(contract.get("project_type")) in {"report", "data-sync"}:
        blockers.append(issue("WRITE_CONTRACT_UNDECLARED", "DEPLOYMENT_BLOCKER", "write_contracts", "At least one target write contract is required."))
    for index, write in enumerate(writes):
        path = f"write_contracts[{index}]"
        if not write.get("ordered_columns"):
            blockers.append(issue("WRITE_COLUMNS_UNDECLARED", "DEPLOYMENT_BLOCKER", f"{path}.ordered_columns", "Target column order is missing."))
        if len(write.get("column_types") or []) != len(write.get("ordered_columns") or []):
            blockers.append(issue("WRITE_TYPES_INCOMPLETE", "DEPLOYMENT_BLOCKER", f"{path}.column_types", "Each ordered target column needs a type."))
        if not clean(write.get("write_mode")):
            blockers.append(issue("WRITE_MODE_UNDECLARED", "DEPLOYMENT_BLOCKER", f"{path}.write_mode", "Write mode is missing."))
        safety = write.get("replacement_safety") if isinstance(write.get("replacement_safety"), Mapping) else {}
        strategy = clean(safety.get("strategy")).lower()
        acknowledged = safety.get("non_atomic_risk_acknowledged") is True
        if strategy in {"delete_then_insert", "non_atomic_replace"} and not acknowledged:
            blockers.append(issue("NON_ATOMIC_REPLACE_UNACKNOWLEDGED", "DEPLOYMENT_BLOCKER", f"{path}.replacement_safety", "DELETE-then-INSERT needs an atomic/recoverable strategy or explicit non-atomic risk acknowledgement."))
        if clean(write.get("storage_kind")) == "clickhouse" and not write.get("staging_wire_format"):
            blockers.append(issue("CLICKHOUSE_WIRE_FORMAT_UNDECLARED", "DEPLOYMENT_BLOCKER", f"{path}.staging_wire_format", "Declare encoding, header, null, integer, datetime, and explicit-column behavior."))
        if clean(write.get("empty_output_policy")) != "block_destructive_replace":
            warnings.append(issue("EMPTY_OUTPUT_POLICY_REVIEW", "WARNING", f"{path}.empty_output_policy", "Empty output should not trigger destructive replacement by default."))

    return validation_result(errors, blockers, warnings)


def validation_result(errors: list[dict[str, str]], blockers: list[dict[str, str]], warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "failed" if errors else "passed",
        "deployment_status": "ready" if not errors and not blockers else "review_required",
        "error_count": len(errors),
        "deployment_blocker_count": len(blockers),
        "warning_count": len(warnings),
        "errors": errors,
        "deployment_blockers": blockers,
        "warnings": warnings,
    }


def build_contract_v2(facts: Mapping[str, Any], base_contract: Mapping[str, Any]) -> dict[str, Any]:
    fields = build_field_contracts(facts)
    sources = build_source_contracts(facts)
    rules = build_rule_contracts(facts)
    parameters = build_parameter_contracts(facts)
    writes = build_write_contracts(facts)
    conflicts = detect_contract_conflicts(facts, fields, rules)
    blockers = unique(base_contract.get("blockers", []) or [])
    open_questions = [dict(item) for item in base_contract.get("open_questions", []) or []]
    for conflict in conflicts:
        question_id = stable_question_id(
            "CG",
            conflict.get("kind"),
            conflict.get("target"),
            conflict.get("field"),
        )
        conflict["question_id"] = question_id
        question_text = f"Resolve {conflict.get('kind')} for {conflict.get('target') or 'requirement'} {conflict.get('field') or ''}."
        add_contract_question(
            open_questions,
            question_id,
            "blocking_codegen",
            question_text,
            conflict_code=conflict.get("code"),
        )
        blockers.append(f"[{question_id}] {question_text}")
    blockers = unique(blockers)
    contract = dict(base_contract)
    contract.update(
        {
            "contract_version": CONTRACT_VERSION,
            "field_contracts": fields,
            "source_contracts": sources,
            "rule_contracts": rules,
            "parameter_contracts": parameters,
            "runtime_contract": build_runtime_contract(facts),
            "write_contracts": writes,
            "conflicts": conflicts,
            "open_questions": open_questions,
            "validation_contract": {
                "severity_model": {
                    "ERROR": "Always fails validation and code-generation readiness.",
                    "DEPLOYMENT_BLOCKER": "Fails only strict deployment validation.",
                    "WARNING": "Non-blocking review evidence.",
                },
                "gates": VALIDATION_GATES,
            },
            "blockers": blockers,
        }
    )
    validation = validate_contract(contract)
    for validation_issue in validation["deployment_blockers"]:
        question_id = stable_question_id("DP", validation_issue.get("code"), validation_issue.get("path"))
        add_contract_question(
            open_questions,
            question_id,
            "deployment_confirmation",
            validation_issue["message"],
            validation_code=validation_issue.get("code"),
            path=validation_issue.get("path"),
        )
    for validation_issue in validation["warnings"]:
        question_id = stable_question_id("NB", validation_issue.get("code"), validation_issue.get("path"))
        add_contract_question(
            open_questions,
            question_id,
            "non_blocking",
            validation_issue["message"],
            validation_code=validation_issue.get("code"),
            path=validation_issue.get("path"),
        )
    contract["open_questions"] = open_questions
    contract["ready_for_codegen"] = bool(base_contract.get("ready_for_codegen")) and not validation["errors"]
    contract["validation_result"] = validation
    return contract
