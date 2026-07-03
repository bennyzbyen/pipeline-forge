#!/usr/bin/env python3
"""Build a report codegen plan from data-doc-to-dev-md structured_facts.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def split_table_names(value: Any) -> List[str]:
    names: List[str] = []
    for part in re.split(r"[\r\n]+", str(value or "")):
        matches = re.findall(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+|/[^\s,，;；]+", part)
        candidates = matches or [part]
        for candidate in candidates:
            normalized = clean_text(candidate)
            if normalized and normalized not in names:
                names.append(normalized)
    return names


def normalize_table_names(source: Dict[str, Any]) -> List[str]:
    values = source.get("table_names") or [source.get("table_or_path", "")]
    names: List[str] = []
    for value in values:
        for name in split_table_names(value):
            if name not in names:
                names.append(name)
    return names


def source_kind(source: Dict[str, Any]) -> str:
    storage = clean_text(source.get("storage")).lower()
    table_or_path = clean_text(source.get("table_or_path"))
    if "hbase" in storage:
        return "hbase"
    if table_or_path.startswith("/") or "gateway" in storage or "目录" in storage:
        return "fs"
    if "mssql" in storage or "sql server" in storage:
        return "mssql"
    if "mysql" in storage:
        return "mysql"
    return "other"


def match_physical_target(logical: Dict[str, Any], physical_targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    desc = clean_text(logical.get("description"))
    for target in physical_targets:
        if clean_text(target.get("description")) == desc:
            return target
    return {}


def match_mapping_physical_target(mapping: Dict[str, Any], physical_targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    inferred_table = clean_text(mapping.get("inferred_physical_table"))
    inferred_desc = clean_text(mapping.get("inferred_target_description"))
    inferred_name = clean_text(mapping.get("inferred_target_name"))
    for target in physical_targets:
        target_table = clean_text(target.get("table"))
        target_name = clean_text(target.get("table_name"))
        if inferred_table and inferred_table == target_table:
            return target
        if inferred_name and inferred_name in {target_table, target_name}:
            return target
    if inferred_table or inferred_name:
        return {}
    for target in physical_targets:
        target_desc = clean_text(target.get("description"))
        if inferred_desc and inferred_desc == target_desc:
            return target
    return {}


def infer_component_kind(
    sources: List[Dict[str, Any]],
    physical_targets: List[Dict[str, Any]],
    logical_targets: List[Dict[str, Any]],
    schedules: List[Dict[str, Any]],
    component_hints: List[Dict[str, Any]] | None = None,
) -> str:
    for hint in component_hints or []:
        kind = clean_text(hint.get("component_kind"))
        if kind:
            return kind

    target_storage = " ".join(
        clean_text(item.get("storage")).lower()
        for item in [*physical_targets, *logical_targets]
    )
    schedule_text = " ".join(
        clean_text(value).lower()
        for item in schedules
        for value in [item.get("pipeline_name"), item.get("task_name"), item.get("description")]
    )
    source_text = " ".join(clean_text(item.get("table_or_path")).lower() for item in sources)
    prepare_markers = ["init_data_source", "period_export_execute", "cal_store_yield_grade"]
    if "hbase" in target_storage and any(marker in schedule_text for marker in prepare_markers):
        return "hbase_prepare_pipeline"
    if "hbase" in target_storage and "l0_cmt.sellout" in source_text:
        return "hbase_prepare_pipeline"
    all_text = " ".join([target_storage, schedule_text, source_text])
    if (
        ("bysku" in all_text or "zo_bysku_detail" in all_text)
        and ("clickhouse" in all_text or "store_" in all_text)
        and ("b5" in all_text or "npd" in all_text or "sku" in all_text)
    ):
        return "bysku_report_pipeline"
    return "standard_report"


def build_plan(facts: Dict[str, Any]) -> Dict[str, Any]:
    sources = facts.get("report_sources", [])
    physical_targets = facts.get("report_physical_targets") or facts.get("report_clickhouse_targets", [])
    logical_targets = facts.get("report_targets", [])
    field_mappings = facts.get("report_field_mappings", [])
    schedules = facts.get("report_schedules", [])
    component_hints = facts.get("component_hints", [])

    outputs = []
    for index, mapping in enumerate(field_mappings):
        logical = logical_targets[index] if index < len(logical_targets) else {}
        physical = match_mapping_physical_target(mapping, physical_targets) or match_physical_target(logical, physical_targets)
        if not physical and len(physical_targets) == 1:
            logical_storage = clean_text(logical.get("storage")).lower()
            physical_storage = clean_text(physical_targets[0].get("storage")).lower()
            if not logical_storage or logical_storage == physical_storage:
                physical = physical_targets[0]
        fields = mapping.get("fields", [])
        outputs.append(
            {
                "target_name": mapping.get("inferred_target_name") or logical.get("target_name", ""),
                "target_description": mapping.get("inferred_target_description") or logical.get("description", ""),
                "physical_table": physical.get("table", ""),
                "storage": logical.get("storage") or physical.get("storage", ""),
                "field_count": len(fields),
                "final_columns": [field.get("target_field", "") for field in fields if field.get("target_field")],
                "field_rules": fields,
            }
        )

    grouped_sources: Dict[str, List[Dict[str, Any]]] = {"hbase": [], "fs": [], "mssql": [], "mysql": [], "other": []}
    for source in sources:
        kind = source_kind(source)
        table_names = normalize_table_names(source)
        grouped_sources[kind].append(
            {
                "table_or_path": source.get("table_or_path", ""),
                "table_names": table_names,
                "description": source.get("description", ""),
                "range": source.get("range", ""),
                "fields": source.get("fields", []),
                "join_filter": source.get("join_filter", ""),
            }
        )

    return {
        "summary": {
            "source_count": len(sources),
            "physical_target_count": len(physical_targets),
            "logical_target_count": len(logical_targets),
            "output_count": len(outputs),
            "schedule_count": len(schedules),
            "component_kind": infer_component_kind(sources, physical_targets, logical_targets, schedules, component_hints),
        },
        "sources": grouped_sources,
        "physical_targets": physical_targets,
        "logical_targets": logical_targets,
        "outputs": outputs,
        "schedules": schedules,
        "component_hints": component_hints,
        "handoff_readiness": facts.get("handoff_readiness", []),
        "inferences": facts.get("inferences", []),
    }


def markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "- None detected.\n"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            values.append(clean_text(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(plan: Dict[str, Any]) -> str:
    lines: List[str] = ["# Report Codegen Plan", ""]
    summary = plan["summary"]
    lines.extend(
        [
            "## Summary",
            "",
            f"- Sources: {summary['source_count']}",
            f"- Physical targets: {summary['physical_target_count']}",
            f"- Logical targets: {summary['logical_target_count']}",
            f"- Outputs: {summary['output_count']}",
            f"- Schedules: {summary['schedule_count']}",
            f"- Component kind: {summary.get('component_kind', 'standard_report')}",
            "",
        ]
    )
    if plan.get("component_hints"):
        lines.extend(
            [
                "## Component Hints",
                "",
                markdown_table(
                    plan["component_hints"],
                    ["component_kind", "handoff_to", "reference", "intermediate_storage"],
                ),
                "",
            ]
        )
    if plan.get("handoff_readiness"):
        readiness_rows = []
        for item in plan["handoff_readiness"]:
            readiness_rows.append(
                {
                    "component_kind": item.get("component_kind", ""),
                    "ready_for_full_codegen": item.get("ready_for_full_codegen", ""),
                    "checks": "; ".join(
                        f"{check.get('name')}={check.get('status')}"
                        for check in item.get("checks", [])
                    ),
                }
            )
        lines.extend(
            [
                "## Handoff Readiness",
                "",
                markdown_table(readiness_rows, ["component_kind", "ready_for_full_codegen", "checks"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Sources",
            "",
        ]
    )
    for kind, sources in plan["sources"].items():
        lines.extend(
            [
                f"### {kind.upper()}",
                "",
                markdown_table(sources, ["table_or_path", "range", "fields", "join_filter"]),
                "",
            ]
        )

    lines.extend(["## Targets", ""])
    target_rows = []
    for target in plan["physical_targets"]:
        target_rows.append(
            {
                "table": target.get("table", ""),
                "storage": target.get("storage", ""),
                "description": target.get("description", ""),
            }
        )
    lines.append(markdown_table(target_rows, ["table", "storage", "description"]))

    lines.extend(["", "## Outputs", ""])
    output_rows = [
        {
            "target_name": output.get("target_name", ""),
            "physical_table": output.get("physical_table", ""),
            "target_description": output.get("target_description", ""),
            "field_count": output.get("field_count", 0),
        }
        for output in plan["outputs"]
    ]
    lines.append(markdown_table(output_rows, ["target_name", "physical_table", "target_description", "field_count"]))

    lines.extend(["", "## Final Columns", ""])
    for output in plan["outputs"]:
        lines.extend(
            [
                f"### {output.get('target_name') or output.get('physical_table')}",
                "",
                "```text",
                "\n".join(output.get("final_columns", [])),
                "```",
                "",
            ]
        )

    lines.extend(["## Field Rules Checklist", ""])
    for output in plan["outputs"]:
        rule_rows = []
        for field in output.get("field_rules", []):
            rule_rows.append(
                {
                    "target_field": field.get("target_field", ""),
                    "source_desc": field.get("source_desc", ""),
                    "source_field": field.get("source_field", ""),
                    "calculation_logic": field.get("calculation_logic", ""),
                    "eo_order_logic": field.get("eo_order_logic", ""),
                    "dms_order_logic": field.get("dms_order_logic", ""),
                }
            )
        lines.extend(
            [
                f"### {output.get('target_name') or output.get('physical_table')}",
                "",
                markdown_table(
                    rule_rows,
                    ["target_field", "source_desc", "source_field", "calculation_logic", "eo_order_logic", "dms_order_logic"],
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report codegen plan from structured_facts.json.")
    parser.add_argument("--facts", required=True, help="Path to structured_facts.json.")
    parser.add_argument("--out", required=True, help="Output directory for report_codegen_plan.md/json.")
    args = parser.parse_args()

    facts_path = Path(args.facts).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(load_json(facts_path))
    (out_dir / "report_codegen_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report_codegen_plan.md").write_text(render_markdown(plan), encoding="utf-8")
    print(f"plan_json: {out_dir / 'report_codegen_plan.json'}")
    print(f"plan_md: {out_dir / 'report_codegen_plan.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
