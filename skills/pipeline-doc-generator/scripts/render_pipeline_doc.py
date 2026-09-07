#!/usr/bin/env python3
"""Render one canonical waterline into Markdown, standalone HTML, and PDF."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from pipeline_doc_common import OUTPUT_FORMATS, apply_fixed_defaults, blocking_questions, bullet_lines, configure_utf8_stdio, load_json, markdown_table, write_json, write_questions
from pipeline_doc_authoring import checkpoint_revision, prepare_revision
from pipeline_doc_presentation import connection_note, is_blob_connection, sas_url, same_prose, unique_paragraphs
from pipeline_diagram_contract import validate_svg_safety

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def document_stem(value: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*]+', "_", str(value or "水线文档")).strip().rstrip(".")
    return stem or "水线文档"


def release_history(facts: dict) -> str:
    rows = facts["document"].get("release_history") or []
    return markdown_table(["文档修订版本", "变更摘要", "作者", "发布日期"], [[row.get("version", ""), row.get("summary", ""), row.get("author", ""), row.get("date", "")] for row in rows])


def source_fields(source: dict) -> str:
    values: list[str] = []
    for field in source.get("fields") or []:
        values.append(str(field.get("key") or field.get("name") or "") if isinstance(field, dict) else str(field))
    return "\n".join(value for value in values if value)


def source_table_report(facts: dict) -> str:
    rows = []
    for source in facts.get("sources") or []:
        rows.append([source.get("location", ""), source.get("name", ""), source.get("description", ""), source.get("range", ""), source_fields(source), "\n".join(source.get("filters") or [])])
    return markdown_table(["位置", "数据表名", "数据表", "取数范围", "字段", "关联、过滤信息"], rows)


def source_table_sync(facts: dict) -> str:
    rows = []
    for index, source in enumerate(facts.get("sources") or [], start=1):
        rows.append([index, source.get("location", ""), source.get("category", ""), source.get("report_type", ""), source.get("description", ""), source.get("name", ""), source.get("range", ""), "\n".join(source.get("filters") or [])])
    return markdown_table(["序号", "数据位置", "所属类别", "报表类型", "业务描述", "表（source）", "数据范围", "字段差异/过滤信息"], rows)


def source_connections(facts: dict) -> str:
    connections = facts.get("source_connections") or []
    by_environment: dict[str, list[dict]] = {}
    for connection in connections:
        by_environment.setdefault(str(connection.get("environment") or "连接信息"), []).append(connection)
    sections: list[str] = []
    for environment, items in by_environment.items():
        sections.extend([f"### {environment}", ""])
        # Mixed connections keep separate schemas instead of empty generic columns.
        for blob in (True, False):
            selected = [item for item in items if is_blob_connection(facts, item) == blob]
            if not selected:
                continue
            if blob:
                sections.append(markdown_table(["SAS URL", "Database / 路径", "备注"], [[sas_url(item), item.get("database", ""), connection_note(item)] for item in selected]))
            else:
                sections.append(markdown_table(["Host / 地址", "Database / 路径", "说明"], [[item.get("host", ""), item.get("database", ""), item.get("note", "")] for item in selected]))
    return "\n\n".join(sections)


def source_dictionaries(facts: dict) -> str:
    sections: list[str] = []
    for index, source in enumerate(facts.get("sources") or [], start=1):
        fields = source.get("fields") or []
        rows = []
        for field in fields:
            if isinstance(field, dict):
                rows.append([field.get("key", ""), field.get("name", ""), field.get("source_type", ""), field.get("type", ""), field.get("history", "")])
            else:
                rows.append([field, "", "", "", ""])
        sections.extend([f"### 3.3.{index} {source.get('name', source.get('id', ''))}", "", markdown_table(["字段", "字段描述", "源字段类型", "目标字段类型", "变更历史"], rows)])
    return "\n\n".join(sections)


def target_storage_label(location: str) -> str:
    lowered = str(location or "").strip().lower()
    known = (
        ("clickhouse", "ClickHouse"),
        ("hbase", "HBase"),
        ("mysql", "MySQL"),
        ("mssql", "MSSQL"),
        ("sql server", "MSSQL"),
        ("postgresql", "PostgreSQL"),
        ("postgres", "PostgreSQL"),
        ("blob", "Blob"),
    )
    return next((label for token, label in known if token in lowered), str(location or "目标").strip())


def physical_target_name(target: dict) -> str:
    database = str(target.get("database") or "").strip()
    table = str(target.get("table") or "").strip()
    return table if not database or table.startswith(f"{database}.") else f"{database}.{table}"


def targets_for_source(facts: dict, source_id: str) -> list[dict]:
    mapped_ids: set[str] = set()
    for pipeline in facts.get("pipelines") or []:
        if source_id in (pipeline.get("sources") or []):
            mapped_ids.update(str(target_id) for target_id in pipeline.get("targets") or [])
    result = []
    for target in facts.get("targets") or []:
        explicit_sources = set(target.get("sources") or target.get("source_ids") or [])
        field_sources = {str(field.get("source") or "") for field in target.get("fields") or []}
        if str(target.get("id") or "") in mapped_ids or source_id in explicit_sources or source_id in field_sources:
            result.append(target)
    return result


def target_table_sync(facts: dict) -> str:
    preferences = facts.get("render_preferences") or {}
    include_target_category = preferences.get("include_target_category") is True
    include_target_report_type = preferences.get("include_target_report_type") is True
    include_target_range = preferences.get("include_target_range") is True
    storage_labels: list[str] = []
    for target in facts.get("targets") or []:
        label = target_storage_label(str(target.get("location") or ""))
        if label not in storage_labels:
            storage_labels.append(label)
    headers = ["序号", "原表位置", "原表名", "业务描述"]
    if include_target_category:
        headers.append("所属类别")
    if include_target_report_type:
        headers.append("报表类型")
    for label in storage_labels:
        headers.append(f"{label}表名")
    if include_target_range:
        headers.append("数据范围")
    rows = []
    for index, source in enumerate(facts.get("sources") or [], start=1):
        related_targets = targets_for_source(facts, str(source.get("id") or ""))
        row = [index, source.get("location", ""), source.get("name", ""), source.get("description", "")]
        if include_target_category:
            row.append(source.get("category", ""))
        if include_target_report_type:
            row.append(source.get("report_type", ""))
        for label in storage_labels:
            targets = [target for target in related_targets if target_storage_label(str(target.get("location") or "")) == label]
            row.append("\n".join(physical_target_name(target) for target in targets))
        if include_target_range:
            range_values = []
            for target in related_targets:
                value = str(target.get("range") or "")
                if not value:
                    continue
                if len(storage_labels) == 1 and len(related_targets) == 1:
                    range_values.append(value)
                else:
                    range_values.append(f"{target_storage_label(str(target.get('location') or ''))}：{value}")
            row.append("\n".join(range_values))
        rows.append(row)
    return markdown_table(headers, rows)


def target_table_report(facts: dict) -> str:
    return markdown_table(["位置", "数据库", "数据表名", "数据表"], [[target.get("location", ""), target.get("database", ""), target.get("description", ""), target.get("table", "")] for target in facts.get("targets") or []])


def target_sync_notes(facts: dict) -> str:
    """One compact home for write/rowkey facts, never another flow narrative."""
    return "\n\n".join(
        f"{physical_target_name(target)}：" + "；".join(
            value for value in (f"写入方式：{target.get('write_mode', '')}",
                                f"RowKey：{target['rowkey']}" if target.get("rowkey") else "") if value
        ) for target in facts.get("targets") or []
    )


def target_logic_sections(facts: dict) -> str:
    targets = facts.get("targets") or []
    category_order: list[str] = []
    for target in targets:
        category = str(target.get("category") or "数据底表")
        if category not in category_order:
            category_order.append(category)
    sections: list[str] = []
    target_counter = 0
    for category_index, category in enumerate(category_order, start=1):
        grouped = [target for target in targets if str(target.get("category") or "数据底表") == category]
        sections.extend([f"### 3.1.{category_index} {category}", ""])
        for item_index, target in enumerate(grouped, start=1):
            target_counter += 1
            sections.extend([f"#### 3.1.{category_index}.{item_index} {target.get('description') or target.get('table')}", ""])
            metadata = [
                f"数据粒度：{target.get('grain', '')}",
                f"写入方式：{target.get('write_mode', '')}" if target.get("write_mode") else "",
            ]
            sections.append("\n\n".join(line for line in metadata if line))
            field_logic = [field.get("logic", "") for field in target.get("fields") or []]
            logic = [value for value in unique_paragraphs(target.get("logic") or []) if not any(same_prose(value, item) for item in field_logic)]
            if logic:
                sections.extend(["", bullet_lines(logic)])
            rows = [[field.get("key", ""), field.get("name", ""), field.get("type", ""), field.get("source", ""), field.get("source_field", ""), field.get("logic", ""), field.get("sample", "")] for field in target.get("fields") or []]
            sections.extend(["", markdown_table(["字段key", "字段名称", "字段类型", "数据源", "数据源字段", "计算逻辑", "数据样例"], rows), ""])
    return "\n".join(sections).strip()


def data_utilization_rows(facts: dict) -> list[list[str]]:
    seen: set[str] = set()
    rows: list[list[str]] = []
    for pipeline in facts.get("pipelines") or []:
        name = str(pipeline.get("data_utilization") or "")
        if name and name not in seen:
            seen.add(name)
            rows.append([name, overview_reference(facts, pipeline.get("description", ""))])
    return rows


def data_utilization_for_target(facts: dict, target_id: str) -> str:
    return next((str(pipeline.get("data_utilization") or "") for pipeline in facts.get("pipelines") or [] if target_id in (pipeline.get("targets") or [])), "")


def catalog_basic_info_table(catalog: dict) -> str:
    basic = catalog.get("basic_info") or []
    headers = ["数据项", "Title", "IT Owner&Email", "Biz Owner&Email", "FE&Email", "IT BP & Email", "Data Engineer & Email"]
    rows = [[row.get("data_item", ""), row.get("title", ""), row.get("it_owner", ""), row.get("biz_owner", ""), row.get("fe", ""), row.get("it_bp", ""), row.get("data_engineer", "")] for row in basic]
    return markdown_table(headers, rows)


def overview_reference(facts: dict, value: str) -> str:
    return "见第 1 章需求概述。" if any(same_prose(value, paragraph) for paragraph in facts.get("requirements", {}).get("summary", [])) else value


def project_pipeline_sections(facts: dict, profile: str, catalog_svg_rel: str = "") -> str:
    document = facts["document"]
    team = document["team"]
    chapter = "5" if profile == "sync" else "4"
    sections = [
        f"## {chapter}.1 创建Project",
        "",
        f"### {chapter}.1.1 Basic Info",
        "",
        f"Name: {document.get('project_name', '')}",
        "",
        f"Description: {overview_reference(facts, document.get('description', ''))}",
        "",
        f"### {chapter}.1.2 Project Team",
        "",
        f"Owner: {team.get('owner', '')}",
        "",
        f"Developer: {team.get('developer', '')}",
        "",
        f"Operator: {team.get('operator', '')}",
        "",
        f"### {chapter}.1.3 Project Documentation",
        "",
        document.get("documentation") or "本文档",
        "",
        f"## {chapter}.2 Data Pipeline Management",
        "",
        f"### {chapter}.2.1 Data Utilization Management",
        "",
        markdown_table(["Name", "Description"], data_utilization_rows(facts)),
        "",
        f"### {chapter}.2.2 Target Management",
        "",
    ]
    if profile == "sync":
        target_rows = []
        for target in facts.get("targets") or []:
            target_name = target.get("target_name") or target.get("hbase_target_name") or target.get("clickhouse_target_name") or target.get("table", "")
            target_rows.append([
                data_utilization_for_target(facts, target.get("id", "")),
                target_name,
                target.get("location", ""),
            ])
        sections.append(markdown_table(["Data Utilization Name", "Target Name", "Target Storage"], target_rows))
    else:
        target_rows = [[data_utilization_for_target(facts, target.get("id", "")), target.get("target_name", target.get("table", "")), target.get("description", ""), f"{target.get('location', '')} {target.get('database', '')}.{target.get('table', '')}".strip()] for target in facts.get("targets") or []]
        sections.append(markdown_table(["Data Utilization Name", "Target Name", "Target Description", "Data Storage"], target_rows))
    sections.extend(["", f"### {chapter}.2.3 Pipeline Management", ""])
    pipeline_rows = []
    for pipeline in facts.get("pipelines") or []:
        description = [*(pipeline.get("steps") or []), *(pipeline.get("write_order") or [])]
        if pipeline.get("rerun"):
            description.append(f"重跑：{pipeline['rerun']}")
        if profile == "sync":
            pipeline_rows.append([pipeline.get("data_utilization", ""), pipeline.get("name", ""), pipeline.get("task_name", ""), pipeline.get("trigger", "")])
        else:
            described_logic = [item for target in facts.get("targets", []) if target.get("id") in pipeline.get("targets", []) for item in target.get("logic", [])]
            description = [item for item in unique_paragraphs(description) if not any(same_prose(item, logic) for logic in described_logic)]
            pipeline_rows.append([pipeline.get("data_utilization", ""), pipeline.get("name", ""), pipeline.get("task_name", ""), "\n".join(description), pipeline.get("trigger", "")])
    headers = ["Data Utilization Name", "Pipeline Name", "task1 name", "定时同步时间"] if profile == "sync" else ["Data Utilization Name", "Pipeline Name", "task1 name", "Description", "trigger time"]
    sections.append(markdown_table(headers, pipeline_rows))
    catalog = facts.get("catalog") or {}
    if profile == "sync":
        sections.extend(["", "### 5.2.4 Catalog Basic Info", ""])
        sections.append(catalog_basic_info_table(catalog) if catalog.get("enabled") else "不适用（已确认）")
    else:
        sections.extend(["", "### 4.2.4 登记 Data Catalog", ""])
        if catalog.get("enabled"):
            if catalog_svg_rel:
                sections.append(f"![Data Catalog 登记流程]({catalog_svg_rel})")
            sections.extend(["", "### 4.2.5 检查 Catalog Basic Info", ""])
            sections.append(catalog_basic_info_table(catalog))
            sections.extend(["", "### 4.2.6 登记 Data Dictionary", ""])
            sections.append(markdown_table(["数据项", "Column", "Type"], [[row.get("data_item", ""), row.get("column", ""), row.get("type", "")] for row in catalog.get("dictionary") or []]))
            sections.extend(["", "### 4.2.7 登记 Data Storage", ""])
            sections.append(markdown_table(["数据项", "存放地", "Field&Type", "Limit（Sample Data）"], [[row.get("data_item", ""), row.get("location", ""), row.get("field_type", ""), row.get("limit", "")] for row in catalog.get("storage") or []]))
        else:
            sections.extend(["不适用（已确认）", "", "### 4.2.5 检查 Catalog Basic Info", "", "不适用（已确认）"])
    return "\n".join(str(item) for item in sections)


def resources_section(facts: dict) -> str:
    resources = facts["resources"]
    return f"- 估计峰值：{resources.get('peak_memory', '')}\n\n- 资源环境：{resources.get('environment', '')}"


def render_markdown(facts: dict, data_svg_rel: str, catalog_svg_rel: str = "") -> str:
    profile = facts["profile"]
    document = facts["document"]
    common_start = [f"# {document['title']}", "", "# 发布历史", "", release_history(facts), ""]
    if profile == "sync":
        parts = [
            *common_start,
            "# 1. 需求概述", "", "\n\n".join(unique_paragraphs(facts["requirements"].get("summary") or [])), "",
            "# 2. 数据流图", "", f"![数据流图]({data_svg_rel})", "",
            "# 3. Source 数据源", "",
            "## 3.1 链接信息", "", source_connections(facts), "",
            "## 3.2 数据列表", "", source_table_sync(facts), "",
            "## 3.3 数据字典", "", source_dictionaries(facts), "",
            "# 4. Target", "", target_table_sync(facts), "", target_sync_notes(facts), "",
            "# 5. Pipeline", "", project_pipeline_sections(facts, profile), "",
            "# 6. 资源评估", "", resources_section(facts), "",
            "# 7. 上线时间", "", document.get("go_live", ""), "",
        ]
    else:
        parts = [
            *common_start,
            "# 1. 需求概述", "", "\n\n".join(unique_paragraphs(facts["requirements"].get("summary") or [])), "", "## 1.1 数据流图", "", f"![数据流程图]({data_svg_rel})", "",
            "# 2. 数据源详情", "", "## 2.1 链接信息", "", source_connections(facts), "",
            "## 2.2 数据列表", "", source_table_report(facts), "",
            "# 3. Data Target", "", target_table_report(facts), "",
            "## 3.1 数据底表 & 逻辑说明", "", target_logic_sections(facts), "",
            "# 4. DataHub Pipeline", "", project_pipeline_sections(facts, profile, catalog_svg_rel), "",
            "# 5. 资源评估", "", resources_section(facts), "",
        ]
    return "\n".join(str(item) for item in parts).rstrip() + "\n"


def split_pipe_row(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def inline_markup(value: str) -> str:
    placeholders: list[str] = []

    def protect_code(match: re.Match[str]) -> str:
        placeholders.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(placeholders) - 1}\x00"

    value = re.sub(r"`([^`]+)`", protect_code, value)
    escaped = html.escape(value, quote=False).replace("&lt;br&gt;", "<br>")
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", lambda match: '<a href="' + html.escape(html.unescape(match.group(2)), quote=True) + '">' + match.group(1) + '</a>', escaped)
    for index, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", replacement)
    return escaped


def toc_markup(value: str) -> str:
    """Render a compact, text-only TOC label without treating path markers as HTML."""
    value = re.sub(r"(?i)<br\s*/?>", " ", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    return html.escape(" ".join(value.split()))


def safe_inline_svg(path: Path) -> str:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    validate_svg_safety(root)
    root.set("class", "waterline-flow")
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ET.tostring(root, encoding="unicode")


def embedded_image(markdown_path: Path, target: str, alt: str) -> str:
    candidate = (markdown_path.parent / target).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if candidate.suffix.lower() == ".svg":
        caption = html.escape(alt, quote=True)
        return f'<figure><button type="button" class="waterline-diagram-open" data-caption="{caption}" aria-label="聚焦查看：{caption}" aria-haspopup="dialog">{safe_inline_svg(candidate)}<span class="waterline-diagram-hint" aria-hidden="true">点击聚焦 · 可缩放和拖动</span></button><figcaption>{caption}</figcaption></figure>'
    mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    data = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return f'<figure><img src="data:{mime};base64,{data}" alt="{html.escape(alt, quote=True)}"><figcaption>{html.escape(alt)}</figcaption></figure>'


def markdown_to_html(markdown: str, markdown_path: Path, title: str) -> str:
    lines = markdown.splitlines()
    headings: list[tuple[int, str, str]] = []
    used_ids: set[str] = set()
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match:
            continue
        base = f"section-{len(headings) + 1}"
        anchor = base
        suffix = 1
        while anchor in used_ids:
            suffix += 1
            anchor = f"{base}-{suffix}"
        used_ids.add(anchor)
        headings.append((len(match.group(1)), match.group(2), anchor))

    body: list[str] = []
    heading_cursor = 0
    index = 0
    in_code = False
    code_lines: list[str] = []
    list_kind = ""

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            body.append(f"</{list_kind}>")
            list_kind = ""

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            close_list()
            if in_code:
                body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            close_list()
            level, text, anchor = headings[heading_cursor]
            heading_cursor += 1
            body.append(f'<h{level} id="{anchor}">{inline_markup(text)}</h{level}>')
            index += 1
            continue
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
        if image_match:
            close_list()
            body.append(embedded_image(markdown_path, image_match.group(2), image_match.group(1)))
            index += 1
            continue
        if line.lstrip().startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            close_list()
            headers = split_pipe_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append(split_pipe_row(lines[index]))
                index += 1
            body.append('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{inline_markup(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            for row in rows:
                row.extend([""] * (len(headers) - len(row)))
                body.append("<tr>" + "".join(f"<td>{inline_markup(cell)}</td>" for cell in row[: len(headers)]) + "</tr>")
            body.append("</tbody></table></div>")
            continue
        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            kind = "ul" if unordered else "ol"
            if list_kind != kind:
                close_list()
                body.append(f"<{kind}>")
                list_kind = kind
            body.append(f"<li>{inline_markup((unordered or ordered).group(1))}</li>")
            index += 1
            continue
        if not line.strip():
            close_list()
            index += 1
            continue
        close_list()
        paragraph = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#{1,6})\s+|^\s*[-*+]\s+|^\s*\d+[.)]\s+|^\s*\||^!\[|^```", lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        body.append(f"<p>{inline_markup(' '.join(paragraph))}</p>")
    close_list()
    if in_code:
        body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")

    # The document title is a separate home link, not a chapter in the outline.
    document_heading = headings[0] if headings and headings[0][0] == 1 and toc_markup(headings[0][1]) == toc_markup(title) else None
    chapter_headings = headings[1:] if document_heading else headings
    title_label = toc_markup(title)
    document_link = f'<a class="toc-document-title" href="#{document_heading[2]}">{title_label}</a>' if document_heading else f'<p class="toc-document-title">{title_label}</p>'
    toc_items = [f'<li class="level-{level}"><a href="#{anchor}">{toc_markup(text)}</a></li>' for level, text, anchor in chapter_headings if level <= 3]
    css = """
    :root{color-scheme:light;--ink:#0f172a;--muted:#475569;--line:#cbd5e1;--accent:#2563eb;--paper:#fff;--wash:#f8fafc;--toc-width:320px;--layout-width:1720px}
    *{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;line-height:1.65}
    .toc-toggle{position:fixed;top:24px;left:24px;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
    .toc-toggle-label{position:fixed;top:16px;left:max(16px,calc((100% - var(--layout-width))/2 + 16px));z-index:40;display:flex;align-items:center;gap:10px;min-height:42px;padding:8px 14px;border:1px solid #475569;border-radius:9px;background:#1e293b;color:#f8fafc;font-size:13px;font-weight:600;cursor:pointer;user-select:none;box-shadow:0 2px 6px #0f172a18}
    .toc-toggle-label:hover{background:#334155}.toc-toggle:focus-visible + .toc-toggle-label{outline:3px solid #60a5fa;outline-offset:3px}
    .toc-toggle-icon{display:block;width:17px;height:14px;border:1.5px solid currentColor;border-radius:2px;position:relative}.toc-toggle-icon:before{content:"";position:absolute;left:4px;top:0;bottom:0;border-left:1.5px solid currentColor}
    .toc-toggle-open{display:none}.toc-toggle:not(:checked) + .toc-toggle-label .toc-toggle-close{display:none}.toc-toggle:not(:checked) + .toc-toggle-label .toc-toggle-open{display:inline}
    .layout{display:grid;grid-template-columns:var(--toc-width) minmax(0,1fr);width:100%;max-width:var(--layout-width);margin:auto}
    .toc{position:sticky;top:0;min-width:0;height:100vh;height:100dvh;display:flex;flex-direction:column;padding:82px 20px 18px;background:#0f172a;color:#e2e8f0}
    .toc-header{flex-shrink:0;padding:0 12px 22px;border-bottom:1px solid #334155}.toc-eyebrow{margin:0 0 9px;color:#94a3b8;font-size:11px;letter-spacing:.16em}
    .toc a,.toc-document-title{display:block;max-width:100%;text-decoration:none;white-space:normal;overflow-wrap:anywhere;word-break:break-word;line-height:1.6}
    .toc-document-title{margin:0;color:#f8fafc;font-size:17px;font-weight:600}.toc-document-title:hover{color:#bfdbfe}
    .toc-chapters{min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#475569 #0f172a;padding:18px 4px 8px}
    .toc h2{margin:0 8px 12px;color:#94a3b8;font-size:12px;font-weight:500;letter-spacing:.15em}.toc ul{min-width:0;list-style:none;margin:0;padding:0}
    .toc li{min-width:0;margin:2px 0;break-inside:avoid}.toc-list a{padding:5px 8px;border-radius:6px;color:#cbd5e1;font-size:13px}
    .toc-list .level-1{margin-top:12px}.toc-list .level-1:first-child{margin-top:0}.toc-list .level-1 a{color:#f1f5f9;font-size:14px;font-weight:600}
    .toc-list .level-2{padding-left:12px}.toc-list .level-3{padding-left:24px}.toc-list .level-3 a{font-size:12px;color:#b8c7db}
    .toc-list a:hover{color:#fff;background:#1e293b}.toc a:focus-visible{outline:2px solid #60a5fa;outline-offset:1px}
    .toc-toggle:not(:checked) ~ .layout{grid-template-columns:minmax(0,1fr)}.toc-toggle:not(:checked) ~ .layout .toc{display:none}.toc-toggle:not(:checked) ~ .layout main{margin-top:80px}.toc-backdrop{display:none}
    main{min-width:0;margin:28px;background:var(--paper);padding:42px 48px;border-radius:16px;box-shadow:0 12px 32px rgba(15,23,42,.08);overflow-wrap:anywhere}h1,h2,h3{overflow-wrap:anywhere;word-break:break-word}h1{margin-top:2.3rem;border-bottom:2px solid #dbeafe;padding-bottom:.45rem}h1:first-child{margin-top:0;font-size:2.2rem;border:0;text-align:center}h2{margin-top:2rem;color:#1d4ed8}h3{margin-top:1.5rem;color:#334155}
    main [id]{scroll-margin-top:80px}
    .table-wrap{overflow:auto;margin:1rem 0 1.5rem;border:1px solid var(--line);border-radius:10px}table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:14px}th,td{padding:9px 12px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);vertical-align:top;text-align:left;white-space:normal;overflow-wrap:anywhere;word-break:break-word}th{position:sticky;top:0;background:#eaf2ff;color:#1e3a8a;z-index:1}tr:last-child td{border-bottom:0}th:last-child,td:last-child{border-right:0}code{background:#eff6ff;padding:.12rem .35rem;border-radius:4px}pre{overflow:auto;background:#0f172a;color:#e2e8f0;padding:16px;border-radius:10px}
    figure{margin:1.5rem 0;text-align:center;overflow:auto}.waterline-flow{display:block;max-width:100%;height:auto;margin:auto}figcaption{color:var(--muted);font-size:13px;margin-top:.5rem}
    @media(max-width:980px){.layout{display:block}.toc{position:fixed;left:0;top:0;width:min(var(--toc-width),calc(100% - 48px));z-index:30;box-shadow:8px 0 32px #0f172a26}.toc-toggle:checked ~ .toc-backdrop{display:block;position:fixed;inset:0;z-index:20;background:#0f172a55;cursor:pointer}main,.toc-toggle:not(:checked) ~ .layout main{margin:0;border-radius:0;padding:84px 20px 28px}h1:first-child{font-size:1.7rem}}
    @media print{body{background:#fff}.layout,.toc-toggle:not(:checked) ~ .layout{display:block}.toc,.toc-toggle,.toc-toggle-label,.toc-toggle:checked ~ .toc-backdrop{display:none}main,.toc-toggle:not(:checked) ~ .layout main{margin:0;padding:0;box-shadow:none}.table-wrap{overflow:visible}table{font-size:10px}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}}
    """
    navigation = (
        '<input type="checkbox" id="toc-toggle" class="toc-toggle" checked aria-label="显示目录" aria-controls="document-toc">'
        '<label for="toc-toggle" class="toc-toggle-label"><span class="toc-toggle-icon" aria-hidden="true"></span>'
        '<span class="toc-toggle-close">收起目录</span><span class="toc-toggle-open">展开目录</span></label>'
        '<label for="toc-toggle" class="toc-backdrop" aria-hidden="true"></label>'
        '<div class="layout"><aside id="document-toc" class="toc" aria-label="文档导航">'
        '<header class="toc-header"><p class="toc-eyebrow">水线文档</p>' + document_link + '</header>'
        '<nav class="toc-chapters" aria-label="章节目录"><h2>目录</h2><ul class="toc-list">' + "".join(toc_items) + '</ul></nav></aside>'
    )
    viewer = ""
    script_policy = "'none'"
    if any('class="waterline-diagram-open"' in part for part in body):
        css += (ASSETS / "diagram-viewer.css").read_text(encoding="utf-8")
        script = (ASSETS / "diagram-viewer.js").read_text(encoding="utf-8")
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        script_policy = f"'sha256-{digest}'"
        viewer = (ASSETS / "diagram-viewer.html").read_text(encoding="utf-8") + '<script data-waterline-viewer="1">' + script + '</script>'
    csp = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src {script_policy}; base-uri 'none'; object-src 'none'"
    return "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta http-equiv=\"Content-Security-Policy\" content=\"" + csp + "\"><title>" + html.escape(title) + "</title><style>" + css + "</style></head><body>" + navigation + '<main id="document-main">' + "\n".join(body) + "</main></div>" + viewer + "</body></html>\n"


def catalog_spec() -> dict:
    groups = [
        {"id": "catalog_basic_group", "title": "Catalog Basic Info", "column": 0, "order": 0},
        {"id": "catalog_dictionary_group", "title": "Data Dictionary", "column": 1, "order": 1},
        {"id": "catalog_source_group", "title": "Source", "column": 2, "order": 2},
        {"id": "catalog_storage_group", "title": "Data Storage", "column": 3, "order": 3},
    ]
    nodes = [
        {"id": "catalog_basic_info", "label": "3.1 登记 Catalog Basic Info", "kind": "process", "column": 0, "order": 0, "group": "catalog_basic_group"},
        {"id": "catalog_dictionary", "label": "3.2 登记 Data Dictionary", "kind": "process", "column": 1, "order": 0, "group": "catalog_dictionary_group"},
        {"id": "catalog_source", "label": "3.3 登记 Source", "kind": "process", "column": 2, "order": 0, "group": "catalog_source_group"},
        {"id": "catalog_storage", "label": "3.4 登记 Data Storage", "kind": "process", "column": 3, "order": 0, "group": "catalog_storage_group"},
    ]
    edges = [{"id": f"catalog_edge_{index}", "from": nodes[index - 1]["id"], "to": nodes[index]["id"], "kind": "control"} for index in range(1, len(nodes))]
    return {"title": "Data Catalog 登记流程", "description": "依次登记 Catalog Basic Info、Data Dictionary、Source 和 Data Storage。", "groups": groups, "nodes": nodes, "edges": edges}


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--format", choices=tuple(OUTPUT_FORMATS), default="all", help="All three formats are always generated; legacy choices are accepted as aliases for all.")
    args = parser.parse_args()
    facts_path = args.facts.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = apply_fixed_defaults(load_json(facts_path))
    from diagram_design_bridge import read_bound_asset, local_asset, require_bindings
    if not blocking_questions(facts):
        require_bindings(facts)
    for slot, config in facts.get("render_preferences", {}).get("diagrams", {}).items():
        if slot not in {"data_flow", "catalog"} or config.get("engine") != "diagram-design":
            raise ValueError("Invalid bound diagram slot or engine")
        spec = facts["flow"] if slot == "data_flow" else catalog_spec()
        payload = read_bound_asset(spec, config, facts_path.parent)
        if out_dir != facts_path.parent:
            destination = local_asset(out_dir, config["svg"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    if args.format != "all":
        print("Output policy: legacy --format is accepted; generating Markdown, HTML, and PDF together.")
    write_json(facts_path, facts)
    canonical_facts = out_dir / "facts.json"
    if canonical_facts != facts_path:
        write_json(canonical_facts, facts)
    questions_path = out_dir / "questions.md"
    write_questions(questions_path, facts)
    blockers = blocking_questions(facts)
    if blockers:
        print(f"BLOCKED: {len(blockers)} open blocking questions; see {questions_path}", file=sys.stderr)
        return 2

    prepare_revision(facts)
    write_json(facts_path, facts)
    if canonical_facts != facts_path:
        write_json(canonical_facts, facts)

    stem = document_stem(facts["document"]["title"])
    asset_dir = out_dir / f"{stem}_files"
    asset_dir.mkdir(parents=True, exist_ok=True)
    data_spec_path = asset_dir / "data_flow.spec.json"
    data_svg_path = asset_dir / "data_flow.svg"
    write_json(data_spec_path, facts["flow"])
    from diagram_design_bridge import render_diagram
    render_diagram(facts["flow"], data_svg_path, facts, facts_path.parent, "data_flow")
    data_svg_rel = f"{asset_dir.name}/{data_svg_path.name}"

    catalog_svg_rel = ""
    if facts["profile"] == "report" and (facts.get("catalog") or {}).get("enabled"):
        cat_spec = catalog_spec()
        cat_spec_path = asset_dir / "catalog_registration_flow.spec.json"
        cat_svg_path = asset_dir / "catalog_registration_flow.svg"
        write_json(cat_spec_path, cat_spec)
        render_diagram(cat_spec, cat_svg_path, facts, facts_path.parent, "catalog")
        catalog_svg_rel = f"{asset_dir.name}/{cat_svg_path.name}"

    markdown = render_markdown(facts, data_svg_rel, catalog_svg_rel)
    markdown_path = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"
    selected_formats = OUTPUT_FORMATS["all"]
    if "pdf" in selected_formats:
        from render_pipeline_pdf import render_pdf
        pdf_path = out_dir / f"{stem}.pdf"
        render_pdf(markdown, markdown_path, pdf_path, facts)
        print(f"pdf: {pdf_path}")
    if "markdown" in selected_formats:
        markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
        print(f"markdown: {markdown_path}")
    if "html" in selected_formats:
        standalone = markdown_to_html(markdown, markdown_path, facts["document"]["title"])
        html_path.write_text(standalone, encoding="utf-8", newline="\n")
        print(f"html: {html_path}")
    checkpoint_revision(facts)
    write_json(facts_path, facts)
    if canonical_facts != facts_path:
        write_json(canonical_facts, facts)
    print(f"facts: {canonical_facts}")
    print(f"questions: {questions_path}")
    print(f"svg: {data_svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
