#!/usr/bin/env python3
"""Infer bySKU multi-component report routing from structured facts."""

from __future__ import annotations

import json
import re

from docx_bundle_ooxml import Paragraph
from docx_bundle_tables import append_unique_by_key


def project_text_blob(facts: dict, paragraphs: list[Paragraph] | None = None) -> str:
    parts: list[str] = []
    if paragraphs:
        parts.extend(paragraph.text for paragraph in paragraphs)
    for key in [
        "report_sources",
        "report_targets",
        "report_physical_targets",
        "report_clickhouse_targets",
        "report_field_mappings",
        "report_schedules",
    ]:
        parts.append(json.dumps(facts.get(key, []), ensure_ascii=False))
    return "\n".join(parts)


def _bysku_signals(blob: str) -> tuple[str, bool, bool]:
    lower_blob = blob.lower()
    has_sample_alias = "执行为王" in blob or "execute_king" in lower_blob
    has_bysku = "bysku" in lower_blob or "zo_bysku_detail" in lower_blob
    # A normal COT table-sync matrix may contain zo_bysku_detail_p. Because "bysku"
    # itself contains "sku", a generic "sku" marker would misroute the entire COT
    # document to report-codegen. Require evidence of an actual SKU-family calculation
    # pipeline beyond the source table name.
    sku_family_markers = [
        "npd",
        "b5",
        "新品",
        "sku_map",
        "sku_combo_map",
        "sku_cal_range",
        "sku_ttl_filter",
        "sku_is_active",
        "store_np_sku",
        "store_b5_sku",
        "r13p",
        "prepare_data",
        "cal_sku",
    ]
    has_sku_family = has_sample_alias or any(marker in lower_blob for marker in sku_family_markers)
    has_pipeline_storage = "clickhouse" in lower_blob and (
        "hbase" in lower_blob or "fs" in lower_blob or "数据源" in blob
    )
    detected = has_bysku and has_sku_family and has_pipeline_storage
    return lower_blob, has_sample_alias, detected


def _infer_bysku_physical_targets(
    facts: dict,
    lower_blob: str,
    has_sample_alias: bool,
) -> tuple[list[str], dict[str, dict]]:
    known_target_tables = [
        "store_np_sku_details",
        "store_np_sku_summary",
        "store_np_sku_ttl",
        "store_b5_sku_details",
        "store_b5_sku_summary",
        "store_b5_sku_ttl",
    ]
    target_tables = [table for table in known_target_tables if table in lower_blob]
    if (
        not target_tables
        and has_sample_alias
        and any(marker in lower_blob for marker in ["clickhouse_execute_king_npd", "clickhouse_execute_king_b5"])
    ):
        target_tables = known_target_tables

    database = "supervisor_dashboard" if "supervisor_dashboard" in lower_blob else ""
    physical_by_table: dict[str, dict] = {}
    for table_name in target_tables:
        table = f"{database}.{table_name}" if database else table_name
        target = {
            "storage": "ClickHouse",
            "database": database,
            "table_name": table_name,
            "table": table,
            "description": "bySKU ClickHouse output",
            "source_kind": "inferred_bysku_report_pipeline",
            "confidence": "medium",
            "requires_confirmation": True,
        }
        physical_by_table[table_name] = target
        append_unique_by_key(facts["report_physical_targets"], dict(target), "table")
        append_unique_by_key(facts["report_clickhouse_targets"], dict(target), "table")

    return target_tables, physical_by_table


def _map_bysku_output_fields(facts: dict, physical_by_table: dict[str, dict]) -> None:
    for mapping in facts.get("report_field_mappings", []):
        mapping_text = " ".join(
            [
                str(mapping.get("declared_table", "")),
                str(mapping.get("source_context", "")),
                str(mapping.get("inferred_target_name", "")),
                str(mapping.get("inferred_target_description", "")),
            ]
        ).lower()
        for table_name, target in physical_by_table.items():
            if table_name not in mapping_text:
                continue
            mapping["inferred_target_name"] = table_name
            mapping["inferred_physical_table"] = target["table"]
            mapping["inferred_target_description"] = target["description"]
            mapping["target_requires_confirmation"] = True
            facts.setdefault("inferences", []).append(
                f"{mapping.get('csv', '')} is mapped to {target['table']} by bySKU output-table evidence."
            )
            break


def _build_bysku_output_groups(target_tables: list[str]) -> list[dict]:
    npd_tables = [table for table in target_tables if "_np_" in table or "_npd_" in table]
    b5_tables = [table for table in target_tables if "_b5_" in table]
    other_tables = [table for table in target_tables if table not in set(npd_tables + b5_tables)]
    output_groups: list[dict] = []
    if npd_tables:
        output_groups.append(
            {
                "name": "npd",
                "physical_tables": npd_tables,
                "delete_condition": "mars_week = <current week>",
            }
        )
    if b5_tables:
        output_groups.append(
            {
                "name": "b5",
                "physical_tables": b5_tables,
                "delete_condition": "mars_week = <current week>",
            }
        )
    if other_tables:
        output_groups.append(
            {
                "name": "sku",
                "physical_tables": other_tables,
                "delete_condition": "<documented period predicate>",
            }
        )
    return output_groups


def _build_bysku_components(output_groups: list[dict]) -> list[dict]:
    components = [
        {
            "name": "prepare_data",
            "role": "Export period-scoped HBase bySKU rows to compressed FS CSV files.",
            "expected_file_pattern": "zo_bysku_detail_<period>.csv.gz",
        }
    ]
    if output_groups:
        for group in output_groups:
            components.append(
                {
                    "name": f"cal_{group['name']}",
                    "role": "Read FS bySKU files and calculate ClickHouse outputs for one SKU family.",
                    "target_tables": group["physical_tables"],
                }
            )
    else:
        components.append(
            {
                "name": "cal_sku",
                "role": "Read FS bySKU files and calculate documented SKU-family ClickHouse outputs.",
                "target_tables": [],
            }
        )
    return components


def _append_bysku_hint(
    facts: dict,
    lower_blob: str,
    has_sample_alias: bool,
    components: list[dict],
    output_groups: list[dict],
) -> None:
    hint = {
        "component_kind": "bysku_report_pipeline",
        "handoff_to": "report-codegen",
        "reference": "references/bysku_report_pipeline_patterns.md",
        "sample_aliases": ["executing_king"] if has_sample_alias else [],
        "source_tables": sorted(set(re.findall(r"l2_cot_perfect_store\.zo_[A-Za-z0-9_]+", lower_blob))),
        "intermediate_storage": "FS bySKU gzip files",
        "components": components,
        "output_groups": output_groups,
        "write_strategy": [
            "Delete ClickHouse current-period rows by the documented period key before insert.",
            "Roll-delete periods older than the documented retention threshold after successful inserts.",
            "Keep inferred physical target tables as confirmation-required unless production code or deployment config proves them.",
        ],
        "required_confirmations": [
            "Confirm FS bySKU directory and file type.",
            "Confirm SKU XML/params source for sku_map, sku_cal_range, sku_ttl_filter, and active SKU flags.",
            "Confirm ClickHouse physical tables and delete predicates.",
        ],
    }
    facts.setdefault("component_hints", []).append(hint)
    facts.setdefault("inferences", []).append(
        "Detected bysku_report_pipeline from bySKU + SKU-family + ClickHouse evidence."
    )


def _append_bysku_readiness(facts: dict, target_tables: list[str]) -> None:
    mapped_tables = {
        str(mapping.get("inferred_physical_table", "")).rsplit(".", 1)[-1]
        for mapping in facts.get("report_field_mappings", [])
        if mapping.get("inferred_physical_table")
    }
    missing_mappings = [table for table in target_tables if table not in mapped_tables]
    readiness_checks = [
        {
            "name": "component_kind",
            "status": "ok",
            "detail": "Detected bysku_report_pipeline.",
        },
        {
            "name": "physical_targets",
            "status": "needs_confirmation" if target_tables else "blocked",
            "detail": (
                "ClickHouse physical tables were inferred from document text and must be confirmed."
                if target_tables
                else "ClickHouse physical tables were not explicit enough to infer safely."
            ),
        },
        {
            "name": "field_mapping_to_outputs",
            "status": "blocked" if missing_mappings else "ok",
            "detail": "Missing field dictionaries for: " + ", ".join(missing_mappings) if missing_mappings else "All inferred outputs have field mappings.",
        },
        {
            "name": "fs_and_sku_params",
            "status": "needs_confirmation",
            "detail": "FS directory, file extension, and SKU XML/params source must be confirmed before codegen.",
        },
        {
            "name": "write_strategy",
            "status": "needs_confirmation",
            "detail": "Confirm mars_week delete predicates and R13P retention cleanup before deployment.",
        },
    ]
    facts.setdefault("handoff_readiness", []).append(
        {
            "component_kind": "bysku_report_pipeline",
            "ready_for_full_codegen": bool(target_tables) and not missing_mappings,
            "checks": readiness_checks,
        }
    )


def infer_bysku_report_component_hint(
    facts: dict,
    paragraphs: list[Paragraph] | None = None,
) -> None:
    blob = project_text_blob(facts, paragraphs)
    lower_blob, has_sample_alias, detected = _bysku_signals(blob)
    if not detected:
        return

    target_tables, physical_by_table = _infer_bysku_physical_targets(
        facts,
        lower_blob,
        has_sample_alias,
    )
    _map_bysku_output_fields(facts, physical_by_table)
    output_groups = _build_bysku_output_groups(target_tables)
    components = _build_bysku_components(output_groups)
    _append_bysku_hint(
        facts,
        lower_blob,
        has_sample_alias,
        components,
        output_groups,
    )
    _append_bysku_readiness(facts, target_tables)
