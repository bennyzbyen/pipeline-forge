#!/usr/bin/env python3
"""Render extracted evidence and the Technical Design handoff."""

from __future__ import annotations

from pathlib import Path

from code_unit_render import render_code_unit_plan_markdown

from docx_bundle_ooxml import Paragraph, SheetSummary, compact_text


def paragraphs_matching(paragraphs: list[Paragraph], keywords: list[str], limit: int = 12) -> list[str]:
    matches: list[str] = []
    lowered = [(p.text.lower(), p.text) for p in paragraphs]
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for lower_text, text in lowered:
            if keyword_lower in lower_text and text not in matches:
                matches.append(text)
                if len(matches) >= limit:
                    return matches
    return matches


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- 待从原始文档或人工补充材料确认\n"
    return "".join(f"- {item}\n" for item in items)


def write_extracted_markdown(
    path: Path,
    docx_path: Path,
    paragraphs: list[Paragraph],
    table_count: int,
    sheet_summaries: list[SheetSummary],
) -> None:
    title = paragraphs[0].text if paragraphs else docx_path.stem
    lines = [
        f"# {title}",
        "",
        f"- Source DOCX: `{docx_path}`",
        f"- Paragraphs: {len(paragraphs)}",
        f"- Word tables: {table_count}",
        f"- Embedded extracted sheets: {len(sheet_summaries)}",
        "",
        "## Extracted Tables",
        "",
    ]
    if not sheet_summaries:
        lines.append("- No embedded Excel or Word tables extracted.")
    else:
        for summary in sheet_summaries:
            rel_path = summary.csv_path.as_posix()
            headers = " | ".join(summary.headers)
            lines.append(
                f"- `{rel_path}`: source `{summary.source}`, workbook `{summary.workbook_name}`, "
                f"sheet `{summary.sheet_name}`, dimension `{summary.dimension}`, "
                f"rows `{summary.row_count}`, headers `{headers}`"
            )

    lines.extend(["", "## Paragraphs", ""])
    for idx, paragraph in enumerate(paragraphs, start=1):
        prefix = f"{idx:04d}"
        style = f" [{paragraph.style}]" if paragraph.style else ""
        lines.append(f"- {prefix}{style} {paragraph.text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_table(rows: list[dict], columns: list[tuple[str, str]], limit: int = 80) -> str:
    if not rows:
        return ""
    selected_rows = rows[:limit]
    header = "| " + " | ".join(title for title, _key in columns) + " |"
    sep = "| " + " | ".join("---" for _title, _key in columns) + " |"
    lines = [header, sep]
    for row in selected_rows:
        values = []
        for _title, key in columns:
            raw_value = row.get(key, "")
            if isinstance(raw_value, list):
                raw_value = ", ".join(str(item) for item in raw_value)
            value = compact_text(str(raw_value)).replace("|", "\\|")
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    if len(rows) > limit:
        lines.append(f"\n- Truncated: showing {limit} of {len(rows)} rows.")
    return "\n".join(lines) + "\n"


def facts_summary_lines(facts: dict) -> list[str]:
    lines: list[str] = []
    if facts.get("documents"):
        lines.append(f"Documents merged: {len(facts['documents'])}.")
    if facts.get("cot_report_tables"):
        lines.append(f"Detected COT-style sync matrix: {len(facts['cot_report_tables'])} source/target rows.")
    if facts.get("report_sources"):
        lines.append(f"Detected report source matrix: {len(facts['report_sources'])} source rows.")
    if facts.get("report_physical_targets"):
        lines.append(f"Detected physical targets: {len(facts['report_physical_targets'])} tables.")
    if facts.get("report_targets"):
        lines.append(f"Detected report target-management rows: {len(facts['report_targets'])} targets.")
    if facts.get("report_field_mappings"):
        lines.append(f"Detected report field-logic sheets: {len(facts['report_field_mappings'])} target dictionaries.")
    if facts.get("report_business_rules"):
        lines.append(f"Detected PRD abnormal/business rules: {len(facts['report_business_rules'])}.")
    if facts.get("report_kpi_rules"):
        lines.append(f"Detected PRD KPI/aggregation rules: {len(facts['report_kpi_rules'])}.")
    if facts.get("component_hints"):
        kinds = ", ".join(item.get("component_kind", "") for item in facts["component_hints"] if item.get("component_kind"))
        lines.append(f"Detected component hints: {kinds}.")
    if facts.get("handoff_readiness"):
        blocked = [
            item.get("component_kind", "")
            for item in facts["handoff_readiness"]
            if not item.get("ready_for_full_codegen", False)
        ]
        if blocked:
            lines.append(f"Handoff readiness blocked for: {', '.join(blocked)}.")
        else:
            lines.append("Handoff readiness: ready for full codegen.")
    if facts.get("field_dictionaries"):
        lines.append(f"Detected {len(facts['field_dictionaries'])} field dictionary sheets.")
    if facts.get("schedules"):
        lines.append(f"Detected {len(facts['schedules'])} pipeline schedules.")
    if facts.get("report_schedules"):
        lines.append(f"Detected report pipeline schedules: {len(facts['report_schedules'])}.")
    return lines


def flattened_report_fields(facts: dict) -> list[dict]:
    rows: list[dict] = []
    for mapping in facts.get("report_field_mappings", []):
        for field in mapping.get("fields", []):
            rows.append(
                {
                    "target": mapping.get("inferred_target_name", ""),
                    "target_desc": mapping.get("inferred_target_description", ""),
                    "physical_table": mapping.get("inferred_physical_table", ""),
                    **field,
                }
            )
    return rows


def _render_fact_tables(facts: dict) -> dict[str, str]:
    cot_sources = markdown_table(
        facts.get("cot_report_tables", []),
        [
            ("Seq", "seq"),
            ("Business", "business_desc"),
            ("Type", "report_type"),
            ("Source HBase", "source_hbase_table"),
            ("Range", "source_range"),
            ("ClickHouse Table", "clickhouse_table"),
        ],
    )
    cot_targets = markdown_table(
        facts.get("target_mappings", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Catalog", "catalog"),
            ("HBase Target", "hbase_target"),
            ("ClickHouse Target", "clickhouse_target"),
        ],
    )
    cot_fields = markdown_table(
        facts.get("field_dictionaries", []),
        [
            ("Data Utilization", "inferred_data_utilization"),
            ("CSV", "csv"),
            ("Rows", "row_count"),
            ("First Fields", "first_fields"),
        ],
    )
    cot_schedules = markdown_table(
        facts.get("schedules", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Task", "task_name"),
            ("Schedule", "schedule"),
            ("Pipeline Prefix", "pipeline_prefix"),
        ],
    )
    report_sources = markdown_table(
        facts.get("report_sources", []),
        [
            ("Storage", "storage"),
            ("Table / Path", "table_or_path"),
            ("Range", "range"),
            ("Fields", "fields"),
            ("Join / Filter", "join_filter"),
        ],
    )
    report_physical_targets = markdown_table(
        facts.get("report_physical_targets", []),
        [
            ("Storage", "storage"),
            ("Database", "database"),
            ("Physical Table", "table"),
            ("Description", "description"),
        ],
    )
    report_targets = markdown_table(
        facts.get("report_targets", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Target Name", "target_name"),
            ("Description", "description"),
            ("Storage", "storage"),
            ("Physical Table", "physical_table"),
        ],
    )
    report_field_summaries = markdown_table(
        facts.get("report_field_mappings", []),
        [
            ("Target", "inferred_target_name"),
            ("Physical Table", "inferred_physical_table"),
            ("Declared Table", "declared_table"),
            ("Description", "inferred_target_description"),
            ("CSV", "csv"),
            ("Rows", "row_count"),
            ("First Fields", "first_fields"),
        ],
    )
    report_field_rules = markdown_table(
        flattened_report_fields(facts),
        [
            ("Target", "target"),
            ("Physical Table", "physical_table"),
            ("Field", "target_field"),
            ("Name", "field_name"),
            ("Source", "source_desc"),
            ("Source Field", "source_field"),
            ("Rule", "calculation_logic"),
            ("EO Rule", "eo_order_logic"),
            ("DMS Rule", "dms_order_logic"),
        ],
        limit=140,
    )
    report_schedules = markdown_table(
        facts.get("report_schedules", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Pipeline", "pipeline_name"),
            ("Task", "task_name"),
            ("Description", "description"),
        ],
    )
    component_hints = markdown_table(
        facts.get("component_hints", []),
        [
            ("Component Kind", "component_kind"),
            ("Handoff To", "handoff_to"),
            ("Reference", "reference"),
            ("Intermediate Storage", "intermediate_storage"),
        ],
    )
    business_rules = markdown_table(
        facts.get("report_business_rules", []),
        [
            ("Abnormal Type", "abnormal_type"),
            ("Rule", "rule"),
            ("Grain", "grain"),
            ("Source", "source"),
            ("Output Table", "output_table"),
        ],
        limit=120,
    )
    kpi_rules = markdown_table(
        facts.get("report_kpi_rules", []),
        [
            ("KPI", "kpi"),
            ("Unit", "unit"),
            ("Source Table", "source_table"),
            ("Source Field", "source_field"),
            ("Aggregation Logic", "aggregation_logic"),
        ],
        limit=120,
    )
    return {
        "cot_sources": cot_sources,
        "cot_targets": cot_targets,
        "cot_fields": cot_fields,
        "cot_schedules": cot_schedules,
        "report_sources": report_sources,
        "report_physical_targets": report_physical_targets,
        "report_targets": report_targets,
        "report_field_summaries": report_field_summaries,
        "report_field_rules": report_field_rules,
        "report_schedules": report_schedules,
        "component_hints": component_hints,
        "business_rules": business_rules,
        "kpi_rules": kpi_rules,
    }


def _build_document_sections(
    facts: dict,
    rendered_tables: dict[str, str],
    source_hits: list[str],
    target_hits: list[str],
    table_lines: list[str],
) -> dict:
    cot_sources = rendered_tables["cot_sources"]
    cot_targets = rendered_tables["cot_targets"]
    cot_fields = rendered_tables["cot_fields"]
    cot_schedules = rendered_tables["cot_schedules"]
    report_sources = rendered_tables["report_sources"]
    report_physical_targets = rendered_tables["report_physical_targets"]
    report_targets = rendered_tables["report_targets"]
    report_field_summaries = rendered_tables["report_field_summaries"]
    report_field_rules = rendered_tables["report_field_rules"]
    report_schedules = rendered_tables["report_schedules"]
    is_cot_sync = bool(facts.get("cot_report_tables"))
    is_report = bool(
        facts.get("report_sources")
        or facts.get("report_targets")
        or facts.get("report_clickhouse_targets")
        or facts.get("report_field_mappings")
    )
    project_type = "data-sync" if is_cot_sync else ("report" if is_report else "待确认是 `data-sync` 还是 `report`")
    source_section = cot_sources or report_sources or markdown_list(source_hits)
    if report_physical_targets or report_targets:
        target_section = ""
        if report_physical_targets:
            target_section += "Physical report targets detected from Data Target text:\n\n" + report_physical_targets + "\n"
        if report_targets:
            target_section += "Target Management rows detected from embedded Excel:\n\n" + report_targets
    else:
        target_section = cot_targets or markdown_list(target_hits)
    if is_cot_sync:
        field_section = cot_fields or markdown_list(table_lines)
    elif is_report:
        field_section = report_field_summaries or markdown_list(table_lines)
    else:
        field_section = markdown_list(table_lines)
    schedule_section = cot_schedules or report_schedules or "- 待从原始文档或人工补充材料确认。\n"
    overview_facts = markdown_list(facts_summary_lines(facts))

    if is_cot_sync:
        mapping_note = (
            "- Generate sync config from the structured matrix: source table, range, ClickHouse table, Data Utilization name, target prefixes, schedule, and field dictionary.\n"
            "- Field dictionary sheets are mapped to Data Utilization rows by embedded-sheet order; verify renamed or exception tables.\n"
        )
        write_strategy = (
            "- Write both HBase and ClickHouse targets when both are configured.\n"
            "- Perfect-store / project-collection reports: prefer ClickHouse write before HBase when the document says to release memory quickly.\n"
            "- Execution reports: prefer HBase write before ClickHouse when the document says downstream HBase service should be available first.\n"
            "- Keep table-level full/delta, truncate, delete-by-key, delete-by-period, and legacy database-prefix exceptions in config.\n"
        )
        parameter_design = (
            "- COT params should keep `source_informations`, `hbase_informations`, and `clickhouse_information` groups.\n"
            "- Required fields normally include `mysql_table`, `last_update_time_column`, optional `period_column`, optional `period`, `batch_size`, `receiver_emails`, `hbase_table`, `rowkey_rule_columns`, and `clickhouse_table`.\n"
            "- Credentials must use placeholders in generated code.\n"
        )
    elif is_report:
        mapping_note = (
            "- Generate report code from `structured_facts.json`: `report_sources`, `report_physical_targets`, `report_targets`, `report_field_mappings`, and `report_schedules`.\n"
            "- Field-logic sheets are mapped to target rows by embedded-sheet order; verify exceptions before deployment.\n"
            "- Full field-level rules extracted from the target dictionaries:\n\n"
            f"{report_field_rules or '- 未识别到字段级规则。'}"
        )
        write_strategy = (
            "- Use the detected physical target storage: HBase, ClickHouse, FS, or mixed targets.\n"
            "- For ClickHouse targets, delete/replace old target rows by `period` only when the target dictionary contains `period` and the report is period-grain; otherwise ask for confirmation.\n"
            "- For HBase prepare/pipeline projects, confirm whether the generated code should export source files to FS, trigger downstream pipeline, or calculate/write the final HBase table directly.\n"
            "- Preserve FS evidence outputs when source sections or release notes mention Gateway project retention / 留痕.\n"
        )
        parameter_design = (
            "- Default report params: `period`, `current_date`, `receiver_emails`, and `running_env`.\n"
            "- Credentials must use placeholders in generated code.\n"
            "- If period is omitted, generated code must derive the target period from the calendar only when the document states that behavior.\n"
        )
    else:
        mapping_note = "- 待从字段字典、字段逻辑表、数据源字段 key、目标表字段 key 中整理。\n"
        write_strategy = (
            "- 待确认写入目标是 HBase、ClickHouse、FS 留痕，还是组合写入。\n"
            "- 待确认删除旧数据策略、全量/增量策略、分区或 period 清理策略。\n"
        )
        parameter_design = (
            "- Credentials must use placeholders in generated code.\n"
            "- 待确认运行参数：period/current_date/sync_dates/receiver_emails/source table/target table/rowkey fields.\n"
        )
    return {
        "project_type": project_type,
        "source_section": source_section,
        "target_section": target_section,
        "field_section": field_section,
        "schedule_section": schedule_section,
        "overview_facts": overview_facts,
        "mapping_note": mapping_note,
        "write_strategy": write_strategy,
        "parameter_design": parameter_design,
    }


def _build_contract_sections(
    facts: dict,
    project_type: str,
    source_document_names: list[str],
    docx_path: Path,
    component_hints: str,
    business_rules: str,
    kpi_rules: str,
    calc_hits: list[str],
) -> dict:
    source_documents_text = ", ".join(f"`{name}`" for name in source_document_names) or f"`{docx_path.name}`"
    codegen_contract = facts.get("codegen_contract", {})
    contract_project_type = codegen_contract.get("project_type", project_type)
    component_kind = codegen_contract.get("component_kind", "unclassified")
    ready_for_codegen = bool(codegen_contract.get("ready_for_codegen", False))
    blockers = codegen_contract.get("blockers", [])
    design_status = "review-ready" if ready_for_codegen else ("blocked" if blockers else "draft")
    contract_components = markdown_table(
        codegen_contract.get("components", []),
        [
            ("Component", "name"),
            ("Kind", "kind"),
            ("Role", "role"),
            ("Status", "status"),
        ],
    )
    blockers_section = markdown_list(blockers) if blockers else "- None.\n"
    kpi_logic_section = ""
    if business_rules:
        kpi_logic_section += "PRD abnormal/business rules:\n\n" + business_rules + "\n"
    if kpi_rules:
        kpi_logic_section += "PRD KPI / aggregation rules:\n\n" + kpi_rules + "\n"
    kpi_logic_section += markdown_list(calc_hits)
    return {
        "source_documents_text": source_documents_text,
        "codegen_contract": codegen_contract,
        "contract_project_type": contract_project_type,
        "component_kind": component_kind,
        "ready_for_codegen": ready_for_codegen,
        "design_status": design_status,
        "contract_components": contract_components,
        "blockers_section": blockers_section,
        "kpi_logic_section": kpi_logic_section,
    }


def _render_technical_design_content(
    *,
    project_name: str,
    contract_project_type: str,
    component_kind: str,
    design_status: str,
    ready_for_codegen: bool,
    source_documents_text: str,
    title: str,
    flow_hits: list[str],
    source_section: str,
    target_section: str,
    contract_components: str,
    component_hints: str,
    schedule_section: str,
    write_strategy: str,
    overview_facts: str,
    field_section: str,
    mapping_note: str,
    kpi_logic_section: str,
    parameter_design: str,
    codegen_contract: dict,
    blockers_section: str,
    code_unit_plan_section: str,
) -> str:
    content = f"""---
document_type: technical-design
design_scope: hld-with-component-lld
project_type: {contract_project_type}
component_kind: {component_kind}
design_status: {design_status}
ready_for_codegen: {str(ready_for_codegen).lower()}
structured_facts: structured_facts.json
questions: questions.md
---

# {project_name} Technical Design

## 1. Design Summary

- Source document: {source_documents_text}
- Original title: {title}
- Document type: Technical Design
- Design coverage: HLD + component LLD
- Design status: {design_status}
- Project type: {contract_project_type}
- Component kind: {component_kind}
- Ready for codegen: {str(ready_for_codegen).lower()}

## 2. HLD — High-Level Design

### 2.1 Data Architecture And Flow

{markdown_list(flow_hits)}
### 2.2 Source Systems And Tables

{source_section}
### 2.3 Target Systems And Tables

{target_section}
### 2.4 Components And Responsibilities

{contract_components or "- No component contract detected.\n"}
{("Additional component evidence:\n\n" + component_hints) if component_hints else ""}

### 2.5 Scheduling And Rerun

{schedule_section}
### 2.6 Write, Recovery And Idempotency Strategy

{write_strategy}
### 2.7 Constraints And Risks

{overview_facts}

## 3. LLD — Component Implementation Contracts

### 3.1 Data Contract And Field Dictionary

The extracted embedded tables below are the primary field-dictionary evidence:

{field_section}
### 3.2 Field Mapping And Processing Rules

{mapping_note}
### 3.3 KPI / Calculation Logic

{kpi_logic_section}
### 3.4 Parameter And Orchestration Contract

{parameter_design}

{code_unit_plan_section}

## 4. Verification And Acceptance

- DataSource: check source table, selected sync mode, period/time range, exported row count, generated file count.
- HBase: check rowkey columns, delete/truncate count, insert count, target table name.
- ClickHouse: check delete/drop/truncate condition, inserted file count, target table name, final row count.
- Final metrics: compare exported rows with HBase and ClickHouse inserted rows.

## 5. Codegen Readiness

- Contract version: {codegen_contract.get("contract_version", 1)}
- Ready for codegen: {str(ready_for_codegen).lower()}
- Machine-readable contract: `structured_facts.json#codegen_contract`

### Blocking Code Generation

{blockers_section}
### Open Questions

See `questions.md`.
"""
    return content


def write_dev_doc_v2(
    path: Path,
    docx_path: Path,
    project_name: str,
    paragraphs: list[Paragraph],
    sheet_summaries: list[SheetSummary],
    facts: dict,
) -> None:
    title = paragraphs[0].text if paragraphs else project_name
    source_documents = facts.get("documents") or [{"name": docx_path.name}]
    source_document_names = [item.get("name", "") for item in source_documents if item.get("name")]
    source_hits = paragraphs_matching(paragraphs, ["数据源", "Source", "HBase", "MSSQL", "MySQL", "Blob"])
    target_hits = paragraphs_matching(paragraphs, ["Data Target", "目标表", "ClickHouse", "Data Storage"])
    flow_hits = paragraphs_matching(paragraphs, ["数据流程", "写入流程", "同步逻辑", "Data Transformation", "Pipeline"])
    calc_hits = paragraphs_matching(paragraphs, ["计算逻辑", "KPI", "汇总逻辑", "字段逻辑", "过滤", "关联"])

    table_lines = []
    for summary in sheet_summaries[:40]:
        headers = " | ".join(summary.headers)
        table_lines.append(f"`{summary.csv_path.name}`: `{summary.sheet_name}`; headers: {headers}")
    rendered_tables = _render_fact_tables(facts)
    sections = _build_document_sections(
        facts,
        rendered_tables,
        source_hits,
        target_hits,
        table_lines,
    )
    contract = _build_contract_sections(
        facts,
        sections["project_type"],
        source_document_names,
        docx_path,
        rendered_tables["component_hints"],
        rendered_tables["business_rules"],
        rendered_tables["kpi_rules"],
        calc_hits,
    )
    content = _render_technical_design_content(
        project_name=project_name,
        contract_project_type=contract["contract_project_type"],
        component_kind=contract["component_kind"],
        design_status=contract["design_status"],
        ready_for_codegen=contract["ready_for_codegen"],
        source_documents_text=contract["source_documents_text"],
        title=title,
        flow_hits=flow_hits,
        source_section=sections["source_section"],
        target_section=sections["target_section"],
        contract_components=contract["contract_components"],
        component_hints=rendered_tables["component_hints"],
        schedule_section=sections["schedule_section"],
        write_strategy=sections["write_strategy"],
        overview_facts=sections["overview_facts"],
        field_section=sections["field_section"],
        mapping_note=sections["mapping_note"],
        kpi_logic_section=contract["kpi_logic_section"],
        parameter_design=sections["parameter_design"],
        codegen_contract=contract["codegen_contract"],
        blockers_section=contract["blockers_section"],
        code_unit_plan_section=render_code_unit_plan_markdown(facts),
    )
    path.write_text(content, encoding="utf-8")
