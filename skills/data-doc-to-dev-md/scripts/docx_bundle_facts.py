#!/usr/bin/env python3
"""Build structured facts from normalized DOCX table evidence."""

from __future__ import annotations

import re

from docx_bundle_bysku import (
    infer_bysku_report_component_hint,
    project_text_blob,
)
from docx_bundle_ooxml import Paragraph, SheetSummary, compact_text
from source_reference import source_identity, storage_identity, selected_columns, storage_kind
from docx_bundle_tables import (
    TableColumns,
    add_provenance,
    append_unique_by_key,
    best_context_match,
    cell_value,
    first_fields,
    has_header,
    has_headers,
    normalized_table_key,
    table_identity,
    matching_tables,
    paragraph_sections,
    preamble_text,
    provenance_from_summary,
    read_csv_table,
    split_field_names,
    split_table_names,
    table_name_from_text,
)


def report_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    records = paragraph_sections(paragraphs or [])
    targets: list[dict] = []
    seen: set[str] = set()
    for index, (paragraph, role) in enumerate(records[:-1]):
        text = compact_text(paragraph.text)
        if role not in {"", "target"} or "clickhouse" not in text.lower():
            continue
        next_paragraph, next_role = records[index + 1]
        if next_role not in {"", "target"} or (paragraph.source_doc_index, paragraph.source_doc_name) != (next_paragraph.source_doc_index, next_paragraph.source_doc_name):
            continue
        table = compact_text(next_paragraph.text)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", table_identity(table)):
            continue
        if table in seen:
            continue
        seen.add(table)
        description = ""
        if index + 2 < len(records):
            detail, detail_role = records[index + 2]
            if detail_role in {"", "target"} and (detail.source_doc_index, detail.source_doc_name) == (paragraph.source_doc_index, paragraph.source_doc_name):
                description = compact_text(detail.text)
        targets.append({"storage": text, "table": table, "database": table.split(".", 1)[0],
                        "table_name": table.split(".", 1)[1], "description": description,
                        "source_doc_index": paragraph.source_doc_index, "source_doc_name": paragraph.source_doc_name})
    return targets


def hbase_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    records = paragraph_sections(paragraphs or [])
    targets: list[dict] = []
    seen: set[str] = set()
    for index, (paragraph, role) in enumerate(records):
        text = compact_text(paragraph.text)
        if role not in {"", "target"} or "hbase" not in text.lower():
            continue
        if role != "target" and "hbase:" not in text.lower():
            continue
        texts = [compact_text(item.text) for item, item_role in records[index:index + 5]
                 if item_role in {"", "target"} and (item.source_doc_index, item.source_doc_name) == (paragraph.source_doc_index, paragraph.source_doc_name)]
        for table in re.findall(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+", " ".join(texts[:4])):
            if not re.search(r"[A-Za-z_]", table) or table.startswith("l0_") or table in seen:
                continue
            seen.add(table)
            description = next((item for item in texts if item != table and table not in item and "hbase" not in item.lower()), "")
            targets.append({"storage": "hbase", "database": table.split(".", 1)[0],
                            "table_name": table.split(".", 1)[1], "table": table, "description": description,
                            "source_doc_index": paragraph.source_doc_index, "source_doc_name": paragraph.source_doc_name})
    return targets


def report_field_rows(rows: list[dict[str, str]]) -> list[dict]:
    fields: list[dict] = []
    layouts = {}
    for row in rows:
        headers = tuple(row)
        if headers not in layouts:
            layouts[headers] = TableColumns(headers)
        value = layouts[headers].value
        contains = layouts[headers].contains
        key = value(row, "Key", "字段 key", "字段key", "字段", "Column", "Field")
        field_name = value(row, "字段名称", "字段名")
        if not key and not field_name:
            continue
        formula = (
            value(row, "计算逻辑", "报表字段逻辑", "字段逻辑", "字段公式", "数据源+字段公式", "数据源 + 字段公式")
            or contains(row, "字段公式")
            or contains(row, "数据源", "公式")
            or contains(row, "报表字段", "逻辑")
        )
        fields.append(
            {
                "target_field": key,
                "field_name": field_name,
                "source_category": value(row, "数据源分类"),
                "source_desc": value(row, "数据源描述", "来源库表", "数据源"),
                "source_storage": value(row, "数据源位置", "存放地"),
                "source_table": value(row, "数据表", "数据源表", "源数据表"),
                "source_field": value(row, "数据源对应的字段", "数据源字段key", "数据源字段 key", "来源字段"),
                "calculation_logic": formula,
                "eo_order_logic": contains(row, "EO+ERP"),
                "dms_order_logic": contains(row, "DMS"),
                "sample": value(row, "字段样例", "示例", "数据样例"),
                "field_type": value(row, "字段类型", "Type"),
                "field_order": value(row, "字段顺序"),
                "display": value(row, "字段是否显示"),
                "remark": value(row, "备注", "变更记录", "更新记录"),
            }
        )
    return fields


def _extract_physical_and_source_table(headers: list[str], rows: list[dict[str, str]], summary: SheetSummary, facts: dict) -> bool:
    if has_headers(headers, ["序号", "业务描述", "hbase 表", "Hbase数据范围", "clickhouse表"]):
        for row in rows:
            source_table = cell_value(row, "hbase 表")
            clickhouse_table = cell_value(row, "clickhouse表")
            if not source_table and not clickhouse_table:
                continue
            facts["cot_report_tables"].append(
                add_provenance(
                    {
                    "seq": cell_value(row, "序号"),
                    "category": cell_value(row, "所属类别"),
                    "report_type": cell_value(row, "报表类型"),
                    "business_desc": cell_value(row, "业务描述"),
                    "source_hbase_table": source_table,
                    "source_range": cell_value(row, "Hbase数据范围"),
                    "clickhouse_table": clickhouse_table,
                    },
                    summary,
                )
            )
        return True

    english = has_headers(headers, ["Description", "Data Storage", "Database", "Table Name"])
    physical_chinese = has_headers(headers, ["位置", "数据库", "数据表名", "数据表"])
    range_layout = has_headers(headers, ["位置", "数据表名", "数据表"]) and has_header(headers, "取数范围", "数据范围")
    usage_layout = has_headers(headers, ["分类", "位置", "数据表", "数据表名"]) and has_header(headers, "使用字段")
    if not (english or physical_chinese or range_layout or usage_layout):
        return False

    is_source = summary.section_role == "source" or (
        summary.section_role != "target" and not english and not physical_chinese)
    columns = TableColumns(headers)
    value = columns.value
    current_storage = current_database = ""
    for row in rows:
        storage = value(row, "Data Storage" if english else "位置")
        database = value(row, "Database" if english else "数据库")
        if physical_chinese:
            storage, database = storage or current_storage, database or current_database
            current_storage, current_database = storage, database
        description = value(row, "Description" if english else "数据表名")
        table_name = value(row, "Table Name" if english else "数据表")
        table = f"{database}.{table_name}" if table_name and database else table_name
        if not english and "." in table_name:
            table = table_name
        if is_source:
            location = table or description
            if not location:
                continue
            source = {
                "storage": storage, "table_or_path": location, "table_names": split_table_names(location),
                "description": description,
                "range": value(row, "备注") if usage_layout else value(row, "取数范围", "数据范围", "Range", "Selection"),
                "fields": split_field_names(value(row, "使用字段") if usage_layout else value(row, "字段", "Columns", "Fields")),
                "join_filter": value(row, "备注") if usage_layout else value(row, "关联、过滤信息", "Join Filter"),
            }
            if usage_layout:
                source["category"] = value(row, "分类")
            facts["report_sources"].append(add_provenance(source, summary))
        elif table_name:
            target = add_provenance({"storage": storage, "database": database,
                "table_name": table_name if english else table_name.rsplit(".", 1)[-1],
                "table": table, "description": description}, summary)
            if not any(item.get("table") == table and storage_identity(item.get("storage")) == storage_identity(storage)
                       for item in facts["report_physical_targets"]):
                facts["report_physical_targets"].append(target)
            if storage_kind(storage) == "clickhouse":
                append_unique_by_key(facts["report_clickhouse_targets"], dict(target), "table")
    return True


def _extract_business_and_catalog_table(headers: list[str], rows: list[dict[str, str]], summary: SheetSummary, facts: dict) -> bool:
    if has_headers(headers, ["异常类型", "判断规则", "产出数据表"]):
        for row in rows:
            abnormal_type = cell_value(row, "异常类型")
            if not abnormal_type:
                continue
            facts["report_business_rules"].append(
                add_provenance(
                    {
                        "abnormal_type": abnormal_type,
                        "rule": cell_value(row, "判断规则", "判断规则（EO补差GSV异常阈值）"),
                        "grain": cell_value(row, "数据粒度"),
                        "source": cell_value(row, "数据源", "数据来源"),
                        "output_table": cell_value(row, "产出数据表"),
                        "scenario": cell_value(row, "场景"),
                    },
                    summary,
                )
            )
        return True

    if (
        has_header(headers, "KPI 名称", "KPI名称", "汇总列")
        and has_header(headers, "数据来源底表")
        and has_header(headers, "汇总逻辑")
    ):
        for row in rows:
            name = cell_value(row, "KPI 名称", "KPI名称", "汇总列")
            if not name:
                continue
            facts["report_kpi_rules"].append(
                add_provenance(
                    {
                        "kpi": name,
                        "unit": cell_value(row, "单位"),
                        "source_table": cell_value(row, "数据来源底表"),
                        "source_field": cell_value(row, "取值字段"),
                        "aggregation_logic": cell_value(row, "汇总逻辑"),
                    },
                    summary,
                )
            )
        return True

    if has_headers(headers, ["Name", "Description"]):
        for row in rows:
            name = cell_value(row, "Name")
            if name:
                facts["data_utilizations"].append(
                    add_provenance({"name": name, "description": cell_value(row, "Description")}, summary)
                )
        return True

    if (
        has_headers(headers, ["数据项", "Title"])
        and has_header(headers, "IT Owner&Email", "IT Owner & Email")
        and has_header(headers, "Biz Owner&Email", "Biz Owner & Email")
    ):
        for row in rows:
            data_item = cell_value(row, "数据项")
            if not data_item:
                continue
            facts["report_catalog_basic_info"].append(
                add_provenance(
                    {
                        "data_item": data_item,
                        "title": cell_value(row, "Title"),
                        "it_owner": cell_value(row, "IT Owner&Email", "IT Owner & Email"),
                        "business_owner": cell_value(row, "Biz Owner&Email", "Biz Owner & Email"),
                        "fe": cell_value(row, "FE&Email", "FE & Email"),
                        "it_bp": cell_value(row, "IT BP & Email", "IT BP&Email"),
                        "data_engineer": cell_value(row, "Data Engineer & Email", "Data Engineer&Email"),
                    },
                    summary,
                )
            )
        return True

    if has_headers(headers, ["Data Utilization Name", "catalog"]):
        for row in rows:
            name = cell_value(row, "Data Utilization Name")
            catalog = cell_value(row, "catalog")
            if not name and not catalog:
                continue
            hbase_prefix = cell_value(row, "hbase_target前缀")
            clickhouse_prefix = cell_value(row, "clickhouse_target前缀")
            explicit_hbase = cell_value(row, "Hbase Target Name")
            explicit_clickhouse = cell_value(row, "Clickhouse Target Name")
            facts["target_mappings"].append(
                add_provenance(
                    {
                        "data_utilization": name,
                        "catalog": catalog,
                        "hbase_target": explicit_hbase or f"{hbase_prefix}{catalog}",
                        "clickhouse_target": explicit_clickhouse or f"{clickhouse_prefix}{catalog}",
                        "hbase_target_prefix": hbase_prefix,
                        "clickhouse_target_prefix": clickhouse_prefix,
                    },
                    summary,
                )
            )
        return True

    if has_headers(headers, ["Data Utilization Name", "Target Name", "Target Description", "Data Storage"]):
        for row in rows:
            name = cell_value(row, "Data Utilization Name")
            target_name = cell_value(row, "Target Name")
            if not name and not target_name:
                continue
            facts["report_targets"].append(
                add_provenance(
                    {
                        "data_utilization": name,
                        "target_name": target_name,
                        "description": cell_value(row, "Target Description"),
                        "storage": cell_value(row, "Data Storage"),
                    },
                    summary,
                )
            )
        return True
    return False


def _extract_schedule_or_field_table(headers: list[str], rows: list[dict[str, str]], summary: SheetSummary, facts: dict, declared_table: str, field_dicts: list[dict], report_field_dicts: list[dict]) -> bool:
    if has_headers(headers, ["Data Utilization Name", "task1 name", "Description"]):
        for row in rows:
            name = cell_value(row, "Data Utilization Name")
            if name:
                facts["report_schedules"].append(
                    add_provenance(
                        {
                            "data_utilization": name,
                            "pipeline_name": cell_value(row, "Pipline_Name", "Pipeline Name", "Pipeline_Name"),
                            "task_name": cell_value(row, "task1 name"),
                            "description": cell_value(row, "Description"),
                            "schedule": cell_value(row, "trigger time", "定时任务"),
                        },
                        summary,
                    )
                )
        return True

    if has_header(headers, "Pipeline Name") and has_header(headers, "定时任务"):
        for row in rows:
            pipeline_name = cell_value(row, "Pipeline Name")
            if pipeline_name:
                facts["report_schedules"].append(
                    add_provenance(
                        {
                            "data_utilization": "",
                            "pipeline_name": pipeline_name,
                            "task_name": "",
                            "description": cell_value(row, "Description", "Desription"),
                            "schedule": cell_value(row, "定时任务"),
                        },
                        summary,
                    )
                )
        return True

    if (has_header(headers, "Key", "字段 key", "字段key") and has_header(headers, "字段名称", "字段名")):
        report_field_dicts.append(
            add_provenance(
                {
                "csv": summary.csv_path.name,
                "sheet": summary.sheet_name,
                "row_count": len(rows),
                "headers": headers[:12],
                "first_fields": first_fields(rows),
                "fields": report_field_rows(rows),
                "declared_table": declared_table,
                },
                summary,
            )
        )
        return True

    if has_headers(headers, ["Data Utilization Name", "task1 name", "定时同步时间"]):
        for row in rows:
            name = cell_value(row, "Data Utilization Name")
            if name:
                facts["schedules"].append(
                    add_provenance(
                        {
                            "data_utilization": name,
                            "pipeline_name": cell_value(row, "Pipeline Name"),
                            "task_name": cell_value(row, "task1 name"),
                            "schedule": cell_value(row, "定时同步时间"),
                            "pipeline_prefix": cell_value(row, "pipeline前缀"),
                        },
                        summary,
                    )
                )
        return True

    if (
        "字段" in headers
        or "字段名" in headers
        or "字段名称" in headers
        or "Key" in headers
        or "Column" in headers
        or "Field" in headers
    ):
        field_dicts.append(
            add_provenance(
                {
                "csv": summary.csv_path.name,
                "sheet": summary.sheet_name,
                "row_count": len(rows),
                "headers": headers[:8],
                "first_fields": first_fields(rows),
                "declared_table": declared_table,
                },
                summary,
            )
        )
    return False


def _map_cot_field_dictionaries(facts: dict, field_dicts: list[dict]) -> None:
    util_names = [item["name"] for item in facts["data_utilizations"]]
    for index, item in enumerate(field_dicts):
        item['requires_confirmation'] = True
        context_match = best_context_match(str(item.get("source_context", "")), util_names)
        if context_match:
            item["inferred_data_utilization"] = context_match
            item["inference_method"] = "embedding_context"
            facts["inferences"].append(
                f"{item['csv']} is mapped to {context_match} by embedding context."
            )
        elif index < len(util_names):
            item["inferred_data_utilization"] = util_names[index]
            item["inference_method"] = "embedded_sheet_order"
            facts["inferences"].append(
                f"{item['csv']} is mapped to {util_names[index]} by embedded-sheet order."
            )
        facts["field_dictionaries"].append(item)


def _match_report_targets_to_physical_tables(facts: dict) -> None:
    report_physical_targets = facts.get("report_physical_targets", []) or facts.get("report_clickhouse_targets", [])
    for target in facts.get("report_targets", []):
        value = target.get("physical_table") or target.get("target_name", "")
        matches = matching_tables(value, report_physical_targets, "table", "table_name")
        if len(matches) == 1:
            physical_target = matches[0]
            target["physical_table"] = physical_target.get("table", "")
            target["database"] = physical_target.get("database", "")
            target["physical_description"] = physical_target.get("description", "")
        elif len(matches) > 1:
            target["requires_confirmation"] = True
            target["physical_table_candidates"] = [item.get("table", "") for item in matches]


def _map_report_field_dictionaries(facts: dict, report_field_dicts: list[dict]) -> None:
    report_targets = facts.get("report_targets", [])
    report_physical_targets = facts.get("report_physical_targets", []) or facts.get("report_clickhouse_targets", [])
    for index, item in enumerate(report_field_dicts):
        previously_unconfirmed = bool(item.get('requires_confirmation') or item.get('target_requires_confirmation'))
        item['requires_confirmation'] = True
        declared = item.get("declared_table", "")
        logical_matches = matching_tables(declared, report_targets, "target_name", "physical_table")
        physical_matches = matching_tables(declared, report_physical_targets, "table", "table_name")
        matched_target = logical_matches[0] if len(logical_matches) == 1 else None
        matched_physical_target = physical_matches[0] if len(physical_matches) == 1 else None
        if len(logical_matches) > 1 or (not matched_target and len(physical_matches) > 1):
            item["physical_table_candidates"] = [target.get("physical_table") or target.get("table", "")
                                                 for target in logical_matches + physical_matches]
            facts["report_field_mappings"].append(item)
            continue

        if matched_target:
            item['requires_confirmation'] = previously_unconfirmed or bool(matched_target.get('requires_confirmation'))
            item["inferred_target_name"] = matched_target.get("target_name", "")
            item["inferred_target_description"] = matched_target.get("description", "")
            item["inferred_physical_table"] = matched_target.get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by declared table {item.get('declared_table', '')}."
            )
        elif matched_physical_target:
            item['requires_confirmation'] = previously_unconfirmed or bool(matched_physical_target.get('requires_confirmation'))
            item["inferred_target_name"] = matched_physical_target.get("table_name", "") or matched_physical_target.get("table", "")
            item["inferred_target_description"] = matched_physical_target.get("description", "")
            item["inferred_physical_table"] = matched_physical_target.get("table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_physical_table']} by declared table {item.get('declared_table', '')}."
            )
        elif not declared and index < len(report_targets):
            item["inferred_target_name"] = report_targets[index].get("target_name", "")
            item["inferred_target_description"] = report_targets[index].get("description", "")
            item["inferred_physical_table"] = report_targets[index].get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by report target order."
            )
        elif not declared and index < len(report_physical_targets):
            physical_target = report_physical_targets[index]
            item["inferred_target_name"] = physical_target.get("table_name", "") or physical_target.get("table", "")
            item["inferred_target_description"] = physical_target.get("description", "")
            item["inferred_physical_table"] = physical_target.get("table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_physical_table']} by embedded physical-target order."
            )
        facts["report_field_mappings"].append(item)


def _infer_sources_from_field_mappings(facts: dict) -> None:
    existing_sources = {
        (storage_identity(item.get("storage")), source_identity(item.get("table_or_path"))): item
        for item in facts.get("report_sources", [])
    }
    inferred_columns = {key: set(selected_columns(source.get("fields")))
                        for key, source in existing_sources.items()
                        if source.get("source_kind") == "inferred_from_field_mapping"}
    for mapping in facts.get("report_field_mappings", []):
        for field in mapping.get("fields", []):
            source_table = field.get("source_table", "")
            source_storage = field.get("source_storage", "")
            if not source_table:
                continue
            key = (storage_identity(source_storage), source_identity(source_table))
            if key in existing_sources:
                source = existing_sources[key]
                # Aggregate mapped columns only for inferred sources; explicit matrices stay authoritative.
                if source.get("source_kind") == "inferred_from_field_mapping":
                    columns = source.setdefault("fields", [])
                    seen = inferred_columns[key]
                    for column in selected_columns(field.get("source_field")):
                        if column not in seen:
                            columns.append(column)
                            seen.add(column)
                continue
            facts["report_sources"].append(
                {
                    "storage": source_storage,
                    "table_or_path": source_table,
                    "table_names": split_table_names(source_table),
                    "description": field.get("source_desc", ""),
                    "range": "",
                    "fields": selected_columns(field.get("source_field")),
                    "join_filter": field.get("calculation_logic", ""),
                    "category": field.get("source_category", ""),
                    "source_doc_index": mapping.get("source_doc_index", 1),
                    "source_doc_name": mapping.get("source_doc_name", ""),
                    "source_csv": mapping.get("source_csv", ""),
                    "source_sheet": mapping.get("source_sheet", ""),
                    "source_kind": "inferred_from_field_mapping",
                }
            )
            existing_sources[key] = facts["report_sources"][-1]
            inferred_columns[key] = set(facts["report_sources"][-1]["fields"])


def _detect_field_rule_conflicts(facts: dict) -> None:
    conflicts_by_field: dict[tuple[str, str], dict] = {}
    for mapping in facts.get("report_field_mappings", []):
        target_key = table_identity(
            mapping.get("inferred_physical_table", "")
            or mapping.get("inferred_target_name", "")
            or mapping.get("declared_table", "")
        )
        for field in mapping.get("fields", []):
            field_key = field.get("target_field", "") or field.get("field_name", "")
            logic = compact_text(field.get("calculation_logic", ""))
            if not target_key or not field_key or not logic:
                continue
            key = (target_key, field_key)
            existing = conflicts_by_field.get(key)
            if existing and existing.get("logic") != logic:
                facts["conflicts"].append(
                    {
                        "kind": "field_rule_conflict",
                        "target": target_key,
                        "field": field_key,
                        "first_logic": existing.get("logic", ""),
                        "first_source": existing.get("source", ""),
                        "second_logic": logic,
                        "second_source": mapping.get("source_doc_name", ""),
                    }
                )
            else:
                conflicts_by_field[key] = {
                    "logic": logic,
                    "source": mapping.get("source_doc_name", ""),
                }


def build_structured_facts(
    sheet_summaries: list[SheetSummary],
    paragraphs: list[Paragraph] | None = None,
) -> dict:
    clickhouse_targets = report_targets_from_paragraphs(paragraphs)
    hbase_targets = hbase_targets_from_paragraphs(paragraphs)
    facts = {
        "documents": [],
        "merge_policy": "",
        "conflicts": [],
        "cot_report_tables": [],
        "data_utilizations": [],
        "target_mappings": [],
        "schedules": [],
        "field_dictionaries": [],
        "report_sources": [],
        "report_targets": [],
        "report_physical_targets": clickhouse_targets + hbase_targets,
        "report_clickhouse_targets": clickhouse_targets,
        "report_catalog_basic_info": [],
        "report_schedules": [],
        "report_field_mappings": [],
        "report_business_rules": [],
        "report_kpi_rules": [],
        "component_hints": [],
        "handoff_readiness": [],
        "inferences": [],
    }
    field_dicts: list[dict] = []
    report_field_dicts: list[dict] = []

    for summary in sheet_summaries:
        if summary.section_role != "example":
            for issue in summary.extraction_issues:
                facts.setdefault("extraction_issues", []).append({**issue, **provenance_from_summary(summary)})
        if summary.section_role in {"example", "ambiguous"}:
            facts.setdefault("excluded_evidence", []).append({**provenance_from_summary(summary),
                "reason": "example_only" if summary.section_role == "example" else "section_ownership_unresolved"})
            continue
        headers, rows, preamble = read_csv_table(summary.csv_path)
        if not headers or not rows:
            continue
        declared_table = table_name_from_text(preamble_text(preamble))
        if _extract_physical_and_source_table(headers, rows, summary, facts):
            continue
        if _extract_business_and_catalog_table(headers, rows, summary, facts):
            continue
        _extract_schedule_or_field_table(
            headers,
            rows,
            summary,
            facts,
            declared_table,
            field_dicts,
            report_field_dicts,
        )

    _map_cot_field_dictionaries(facts, field_dicts)
    _match_report_targets_to_physical_tables(facts)
    _map_report_field_dictionaries(facts, report_field_dicts)
    _infer_sources_from_field_mappings(facts)
    _detect_field_rule_conflicts(facts)
    infer_bysku_report_component_hint(facts, paragraphs)
    tracked = ('cot_report_tables', 'field_dictionaries', 'report_sources', 'report_physical_targets', 'report_field_mappings')
    documents = sorted({(s.source_doc_index, s.source_doc_name) for s in sheet_summaries} |
                       {(p.source_doc_index, p.source_doc_name) for p in (paragraphs or [])})
    facts['extraction_coverage'] = []
    for index, name in documents:
        counts = {key: sum(row.get('source_doc_index') == index for row in facts[key]) for key in tracked}
        recognized = {row.get('source_csv') for key in tracked for row in facts[key] if row.get('source_doc_index') == index}
        unrecognized = [s.csv_path.name for s in sheet_summaries if s.source_doc_index == index and s.csv_path.name not in recognized and s.section_role not in {"example", "ambiguous"}]
        facts['extraction_coverage'].append({'source_doc_index': index, 'source_doc_name': name,
                                             'recognized_counts': counts, 'tables_without_tracked_facts': unrecognized,
                                             'zero_means': 'not_recognized_not_business_absent'})
    facts['coverage_comparison'] = {'status': 'differences_require_review' if len({str(x['recognized_counts']) for x in facts['extraction_coverage']}) > 1 else 'counts_equal_or_single_source',
                                    'note': 'Counts compare extraction coverage only; different document roles/formats are not business conflicts by themselves.'}
    return facts
