#!/usr/bin/env python3
"""Build structured facts from normalized DOCX table evidence."""

from __future__ import annotations

import re

from docx_bundle_bysku import (
    infer_bysku_report_component_hint,
    project_text_blob,
)
from docx_bundle_ooxml import Paragraph, SheetSummary, compact_text
from docx_bundle_tables import (
    add_provenance,
    append_unique_by_key,
    best_context_match,
    cell_value,
    cell_value_contains,
    first_fields,
    has_header,
    has_headers,
    normalized_table_key,
    preamble_text,
    read_csv_table,
    split_cell_lines,
    split_field_names,
    split_table_names,
    table_name_from_text,
)


def report_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    if not paragraphs:
        return []
    targets: list[dict] = []
    seen: set[str] = set()
    texts = [compact_text(paragraph.text) for paragraph in paragraphs if compact_text(paragraph.text)]
    for index, text in enumerate(texts):
        if "clickhouse" not in text.lower():
            continue
        if index + 1 >= len(texts):
            continue
        table = texts[index + 1]
        if "." not in table or " " in table:
            continue
        description = texts[index + 2] if index + 2 < len(texts) else ""
        if table in seen:
            continue
        seen.add(table)
        targets.append(
            {
                "storage": text,
                "table": table,
                "database": table.split(".", 1)[0],
                "table_name": table.split(".", 1)[1],
                "description": description,
            }
        )
    return targets


def hbase_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    if not paragraphs:
        return []
    targets: list[dict] = []
    seen: set[str] = set()
    texts = [compact_text(paragraph.text) for paragraph in paragraphs if compact_text(paragraph.text)]
    in_target_section = False
    for index, text in enumerate(texts):
        lower_text = text.lower()
        if "data target" in lower_text or "target management" in lower_text:
            in_target_section = True
        if in_target_section and ("datahub pipeline" in lower_text or "data pipeline management" in lower_text):
            in_target_section = False
        if not in_target_section and "hbase:" not in lower_text:
            continue
        if "hbase" not in lower_text:
            continue

        window = " ".join(texts[index : index + 4])
        matches = re.findall(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+", window)
        for table in matches:
            if not re.search(r"[A-Za-z_]", table):
                continue
            if table.startswith("l0_") or table in seen:
                continue
            seen.add(table)
            description = ""
            for candidate in texts[index : index + 5]:
                if candidate != table and table not in candidate and "hbase" not in candidate.lower():
                    description = candidate
                    break
            targets.append(
                {
                    "storage": "hbase",
                    "database": table.split(".", 1)[0],
                    "table_name": table.split(".", 1)[1],
                    "table": table,
                    "description": description,
                }
            )
    return targets


def report_field_rows(rows: list[dict[str, str]]) -> list[dict]:
    fields: list[dict] = []
    for row in rows:
        key = cell_value(row, "Key", "字段 key", "字段key", "字段", "Column", "Field")
        field_name = cell_value(row, "字段名称", "字段名")
        if not key and not field_name:
            continue
        formula = (
            cell_value(row, "计算逻辑", "报表字段逻辑", "字段逻辑", "字段公式", "数据源+字段公式", "数据源 + 字段公式")
            or cell_value_contains(row, "字段公式")
            or cell_value_contains(row, "数据源", "公式")
            or cell_value_contains(row, "报表字段", "逻辑")
        )
        fields.append(
            {
                "target_field": key,
                "field_name": field_name,
                "source_category": cell_value(row, "数据源分类"),
                "source_desc": cell_value(row, "数据源描述", "来源库表", "数据源"),
                "source_storage": cell_value(row, "数据源位置", "存放地"),
                "source_table": cell_value(row, "数据表", "数据源表", "源数据表"),
                "source_field": cell_value(row, "数据源对应的字段", "数据源字段key", "数据源字段 key", "来源字段"),
                "calculation_logic": formula,
                "eo_order_logic": cell_value_contains(row, "EO+ERP"),
                "dms_order_logic": cell_value_contains(row, "DMS"),
                "sample": cell_value(row, "字段样例", "示例", "数据样例"),
                "field_type": cell_value(row, "字段类型", "Type"),
                "field_order": cell_value(row, "字段顺序"),
                "display": cell_value(row, "字段是否显示"),
                "remark": cell_value(row, "备注", "变更记录", "更新记录"),
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

    if has_headers(headers, ["Description", "Data Storage", "Database", "Table Name"]):
        for row in rows:
            table_name = cell_value(row, "Table Name")
            database = cell_value(row, "Database")
            if not table_name:
                continue
            table = f"{database}.{table_name}" if database else table_name
            if any(target.get("table") == table for target in facts["report_clickhouse_targets"]):
                continue
            target = add_provenance(
                {
                    "storage": cell_value(row, "Data Storage"),
                    "database": database,
                    "table_name": table_name,
                    "table": table,
                    "description": cell_value(row, "Description"),
                },
                summary,
            )
            facts["report_clickhouse_targets"].append(target)
            append_unique_by_key(facts["report_physical_targets"], dict(target), "table")
        return True

    if has_headers(headers, ["位置", "数据库", "数据表名", "数据表"]):
        current_storage = ""
        current_database = ""
        for row in rows:
            storage = cell_value(row, "位置") or current_storage
            database = cell_value(row, "数据库") or current_database
            description = cell_value(row, "数据表名")
            table_name = cell_value(row, "数据表")
            if cell_value(row, "位置"):
                current_storage = storage
            if cell_value(row, "数据库"):
                current_database = database
            if not table_name:
                continue
            table = table_name if "." in table_name or not database else f"{database}.{table_name}"
            target = add_provenance(
                {
                    "storage": storage,
                    "database": database,
                    "table_name": table_name.rsplit(".", 1)[-1],
                    "table": table,
                    "description": description,
                },
                summary,
            )
            append_unique_by_key(facts["report_physical_targets"], target, "table")
            if "clickhouse" in storage.lower():
                append_unique_by_key(facts["report_clickhouse_targets"], dict(target), "table")
        return True

    if (
        has_headers(headers, ["位置", "数据表名", "数据表"])
        and has_header(headers, "取数范围", "数据范围")
    ):
        for row in rows:
            source_name = cell_value(row, "数据表名")
            physical_table = cell_value(row, "数据表")
            if not source_name and not physical_table:
                continue
            facts["report_sources"].append(
                add_provenance(
                    {
                        "storage": cell_value(row, "位置"),
                        "table_or_path": physical_table or source_name,
                        "table_names": split_table_names(physical_table or source_name),
                        "description": source_name,
                        "range": cell_value(row, "取数范围", "数据范围"),
                        "fields": split_cell_lines(cell_value(row, "字段")),
                        "join_filter": cell_value(row, "关联、过滤信息"),
                    },
                    summary,
                )
            )
        return True

    if (
        has_headers(headers, ["分类", "位置", "数据表", "数据表名"])
        and has_header(headers, "使用字段")
    ):
        for row in rows:
            source_name = cell_value(row, "数据表名")
            physical_table = cell_value(row, "数据表")
            if not source_name and not physical_table:
                continue
            fields = split_field_names(cell_value(row, "使用字段"))
            facts["report_sources"].append(
                add_provenance(
                    {
                        "storage": cell_value(row, "位置"),
                        "table_or_path": physical_table or source_name,
                        "table_names": split_table_names(physical_table or source_name),
                        "description": source_name,
                        "range": cell_value(row, "备注"),
                        "fields": fields,
                        "join_filter": cell_value(row, "备注"),
                        "category": cell_value(row, "分类"),
                    },
                    summary,
                )
            )
        return True
    return False


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
    report_targets = facts.get("report_targets", [])
    report_physical_targets = facts.get("report_physical_targets", []) or facts.get("report_clickhouse_targets", [])
    for target in report_targets:
        target_key = normalized_table_key(target.get("target_name", ""))
        if not target_key:
            continue
        for physical_target in report_physical_targets:
            physical_key = normalized_table_key(
                physical_target.get("table", "") or physical_target.get("table_name", "")
            )
            if target_key and target_key == physical_key:
                target["physical_table"] = physical_target.get("table", "")
                target["database"] = physical_target.get("database", "")
                target["physical_description"] = physical_target.get("description", "")
                break


def _map_report_field_dictionaries(facts: dict, report_field_dicts: list[dict]) -> None:
    report_targets = facts.get("report_targets", [])
    report_physical_targets = facts.get("report_physical_targets", []) or facts.get("report_clickhouse_targets", [])
    for index, item in enumerate(report_field_dicts):
        declared_key = normalized_table_key(item.get("declared_table", ""))
        matched_target = None
        matched_physical_target = None
        if declared_key:
            matched_target = next(
                (
                    target
                    for target in report_targets
                    if normalized_table_key(target.get("target_name", "")) == declared_key
                    or normalized_table_key(target.get("physical_table", "")) == declared_key
                ),
                None,
            )
            matched_physical_target = next(
                (
                    target
                    for target in report_physical_targets
                    if normalized_table_key(target.get("table", "") or target.get("table_name", "")) == declared_key
                ),
                None,
            )

        if matched_target:
            item["inferred_target_name"] = matched_target.get("target_name", "")
            item["inferred_target_description"] = matched_target.get("description", "")
            item["inferred_physical_table"] = matched_target.get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by declared table {item.get('declared_table', '')}."
            )
        elif matched_physical_target:
            item["inferred_target_name"] = matched_physical_target.get("table_name", "") or matched_physical_target.get("table", "")
            item["inferred_target_description"] = matched_physical_target.get("description", "")
            item["inferred_physical_table"] = matched_physical_target.get("table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_physical_table']} by declared table {item.get('declared_table', '')}."
            )
        elif index < len(report_targets):
            item["inferred_target_name"] = report_targets[index].get("target_name", "")
            item["inferred_target_description"] = report_targets[index].get("description", "")
            item["inferred_physical_table"] = report_targets[index].get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by report target order."
            )
        elif index < len(report_physical_targets):
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
        (item.get("storage", ""), item.get("table_or_path", ""))
        for item in facts.get("report_sources", [])
    }
    for mapping in facts.get("report_field_mappings", []):
        for field in mapping.get("fields", []):
            source_table = field.get("source_table", "")
            source_storage = field.get("source_storage", "")
            if not source_table or (source_storage, source_table) in existing_sources:
                continue
            facts["report_sources"].append(
                {
                    "storage": source_storage,
                    "table_or_path": source_table,
                    "table_names": split_table_names(source_table),
                    "description": field.get("source_desc", ""),
                    "range": "",
                    "fields": [field.get("source_field", "")] if field.get("source_field") else [],
                    "join_filter": field.get("calculation_logic", ""),
                    "category": field.get("source_category", ""),
                    "source_doc_index": mapping.get("source_doc_index", 1),
                    "source_doc_name": mapping.get("source_doc_name", ""),
                    "source_csv": mapping.get("source_csv", ""),
                    "source_sheet": mapping.get("source_sheet", ""),
                    "source_kind": "inferred_from_field_mapping",
                }
            )
            existing_sources.add((source_storage, source_table))


def _detect_field_rule_conflicts(facts: dict) -> None:
    conflicts_by_field: dict[tuple[str, str], dict] = {}
    for mapping in facts.get("report_field_mappings", []):
        target_key = normalized_table_key(
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
    return facts
