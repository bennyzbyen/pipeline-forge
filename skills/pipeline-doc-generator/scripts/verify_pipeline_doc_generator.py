#!/usr/bin/env python3
"""Run deterministic extraction, rendering, validation, and edit regressions."""

from __future__ import annotations

import argparse
import copy
from contextlib import nullcontext
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from openpyxl import Workbook
from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from render_waterline_svg import graph_model, render_spec, validate_svg, validate_spec, PALETTES
from render_pipeline_doc import markdown_to_html, safe_inline_svg, inline_markup
from validate_pipeline_doc import validate_html
from pipeline_doc_common import OUTPUT_FORMATS


HERE = Path(__file__).resolve().parent
EXTRACT = HERE / "extract_requirement_evidence.py"
RENDER = HERE / "render_pipeline_doc.py"
VALIDATE = HERE / "validate_pipeline_doc.py"


def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run([sys.executable, *args], text=True, capture_output=True, encoding="utf-8", env=environment)
    if completed.returncode != expected:
        raise AssertionError(f"command failed ({completed.returncode}): {args}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
    return completed


class NavigationProbe(HTMLParser):
    """Inspect rendered navigation and its targets without a browser dependency."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict] = []
        self.stack: list[dict] = []
        self.feed(markup)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag, "attrs": dict(attrs), "ancestors": list(self.stack), "text": ""}
        self.nodes.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        for node in self.stack:
            node["text"] += data


def assert_html_navigation(markup: str) -> NavigationProbe:
    probe = NavigationProbe(markup)
    # Diagram-internal marker IDs are not document navigation targets.
    html_nodes = [node for node in probe.nodes if node["tag"].split(":")[-1] != "svg" and not any(parent["tag"].split(":")[-1] == "svg" for parent in node["ancestors"])]
    ids = [node["attrs"]["id"] for node in html_nodes if "id" in node["attrs"]]
    assert len(ids) == len(set(ids)), "Duplicate HTML IDs break navigation"
    by_id = {node["attrs"]["id"]: node for node in html_nodes if "id" in node["attrs"]}
    toggle = by_id["toc-toggle"]
    assert toggle["tag"] == "input" and toggle["attrs"]["type"] == "checkbox"
    assert "checked" in toggle["attrs"] and toggle["attrs"].get("aria-label")
    assert toggle["attrs"]["aria-controls"] == "document-toc"
    assert by_id["document-toc"]["tag"] == "aside"
    assert any(node["tag"] == "label" and node["attrs"].get("for") == "toc-toggle" and node["text"] for node in probe.nodes)
    links = [node for node in probe.nodes if node["tag"] == "a" and any(parent["attrs"].get("class") == "toc-list" for parent in node["ancestors"])]
    main_headings = [node for node in probe.nodes if node["tag"] in {"h1", "h2", "h3"} and any(parent["tag"] == "main" for parent in node["ancestors"])]
    home_links = [node for node in probe.nodes if node["tag"] == "a" and node["attrs"].get("class") == "toc-document-title"]
    if home_links:
        assert len(home_links) == 1
        assert home_links[0]["attrs"]["href"] == "#" + main_headings[0]["attrs"]["id"]
        assert not any(parent["tag"] == "li" for parent in home_links[0]["ancestors"])
        main_headings = main_headings[1:]
    assert [node["attrs"]["href"] for node in links] == ["#" + node["attrs"]["id"] for node in main_headings], "Chapters must remain ordered and independently navigable"
    for link in links + home_links:
        assert link["attrs"]["href"][1:] in by_id
    assert not any(node["tag"] in {"link", "details", "summary"} for node in probe.nodes)
    scripts = [node for node in probe.nodes if node["tag"] == "script"]
    for script in scripts:
        assert script["attrs"] == {"data-waterline-viewer": "1"}
        assert script["text"] == (HERE.parent / "assets/diagram-viewer.js").read_text(encoding="utf-8")
    assert len(scripts) <= 1
    return probe


def test_html_navigation(root: Path) -> dict:
    title = '合成超长标题：Blob 同步 <P>/<W> 与 "引用" & <script>alert(1)</script>'
    path = "PLANT_PRODUCTION/FULL/<P>/<W>/" + "long_source_name_" * 8 + "part-*"
    markdown = f"# {title}\n\n# 发布历史\n\n# 1. 数据源\n\n## 1.1 数据字典\n\n### 1.1.1 `{path}`<br>字段清单\n\n# 2. Target\n"
    markup = markdown_to_html(markdown, root / "navigation.md", title)
    probe = assert_html_navigation(markup)
    chapter_labels = [node["text"] for node in probe.nodes if node["tag"] == "a" and any(parent["attrs"].get("class") == "toc-list" for parent in node["ancestors"])]
    assert title not in chapter_labels
    assert f"1.1.1 {path} 字段清单" in chapter_labels
    assert any(node["attrs"].get("class") == "toc-document-title" and node["text"] == title for node in probe.nodes)
    assert not any(node["tag"] in {"script", "w"} for node in probe.nodes)
    # A partial document without a matching H1 title must not lose its first chapter.
    assert_html_navigation(markdown_to_html("# 1. 数据源\n\n# 2. Target\n", root / "partial.md", "项目标题"))
    (root / "navigation_long_title.html").write_text(markup, encoding="utf-8")
    return {"title_separated": True, "chapter_links": len(chapter_labels), "unsafe_title_escaped": True, "native_toggle": True}


def xlsx_bytes_with_stale_dimension() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "字段字典"
    sheet.append(["字段key", "字段名称", "字段类型"])
    sheet.append(["store_code", "门店编码", "String"])
    sheet.append(["amount", "金额", "Decimal(18,2)"])
    raw = BytesIO()
    workbook.save(raw)
    source = zipfile.ZipFile(BytesIO(raw.getvalue()))
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for member in source.namelist():
            data = source.read(member)
            if member == "xl/worksheets/sheet1.xml":
                data = data.replace(b'ref="A1:C3"', b'ref="A1:A1"')
            target.writestr(member, data)
    source.close()
    return output.getvalue()


def make_embedded_docx(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:o="urn:schemas-microsoft-com:office:office">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>合成 HLD</w:t></w:r></w:p>
    <w:p><w:r><w:t>Source 数据字典</w:t></w:r><w:r><w:object><o:OLE r:id="rId1"/></w:object></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Description</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>daily_report</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>日报</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:sectPr/>
  </w:body>
</w:document>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/package" Target="embeddings/Microsoft_Excel_Worksheet1.xlsx"/>
</Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/embeddings/Microsoft_Excel_Worksheet1.xlsx" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", relationships)
        archive.writestr("word/embeddings/Microsoft_Excel_Worksheet1.xlsx", xlsx_bytes_with_stale_dimension())


def make_markdown(path: Path) -> None:
    path.write_text("""# 合成 PRD

## 数据源

| 位置 | 数据表名 | 取数范围 |
| --- | --- | --- |
| HBase | l0_demo.source_daily | T-1 |

```text
| 这不是 | 表格 |
| --- | --- |
```
""", encoding="utf-8")


def make_searchable_pdf(path: Path) -> None:
    document = SimpleDocTemplate(str(path), pagesize=A4)
    table = Table([["Source", "Range"], ["l0_demo.source_daily", "T-1"]])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue)]))
    document.build([table])


def make_scanned_pdf(path: Path) -> None:
    image = Image.new("RGB", (1000, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "SCANNED REQUIREMENT PAGE", fill="black")
    image.save(path, "PDF", resolution=144.0)


def facts(profile: str, title: str) -> dict:
    sync_profile = profile == "sync"
    target_location = "HBase" if sync_profile else "Superview ClickHouse"
    target_database = "" if sync_profile else "demo"
    target_table = "l0_demo_target_daily" if sync_profile else "target_daily"
    target_kind = "hbase" if sync_profile else "clickhouse"
    target_label = target_table if sync_profile else f"{target_database}.{target_table}"
    write_storage = "HBase" if sync_profile else "ClickHouse"
    result = {
        "schema_version": "1.0",
        "profile": profile,
        "document": {
            "title": title,
            "project_name": "synthetic_pipeline",
            "description": "合成水线回归项目",
            "release_history": [{"version": "0.0.1", "summary": "初始版本", "author": "Tester", "date": "2026/09/01"}],
            "team": {"owner": "Owner", "developer": "Developer", "operator": "Operator"},
            "documentation": "本文档",
            "write_flow": [f"校验完成后写入 {write_storage}。"],
            "sync_logic": ["每日读取 T-1 数据并按业务主键覆盖。"],
            "go_live": "2026/09/30",
        },
        "requirements": {"summary": ["整合源数据并生成可审计的目标底表。"], "scope": []},
        "source_connections": [{"environment": "QA", "host": "qa.example", "database": "demo", "note": "占位连接信息"}],
        "sources": [{"id": "source_daily", "location": "Data Hub HBase", "system": "HBase", "name": "PLANT_PRODUCTION/FULL/<P>/<W>/part-*", "description": "合成源表", "range": "T-1", "category": "测试", "report_type": "日报", "fields": [{"id": "source_store_code", "key": "store_code", "name": "门店编码", "source_type": "String", "type": "String", "history": ""}], "filters": ["state = 1"], "source_refs": [{"document": "synthetic.docx", "heading": "数据源"}]}],
        "targets": [{"id": "target_daily", "location": target_location, "database": target_database, "table": target_table, "target_prefix": "legacy_target_prefix", "description": "合成目标表", "category": "测试底表", "report_type": "日报", "grain": "By门店 By日", "schedule": "每日 07:00", "write_mode": "按日覆盖", "logic": ["过滤有效门店并汇总。"], "fields": [{"id": "target_store_code", "key": "store_code", "name": "门店编码", "type": "String", "source": "source_daily", "source_field": "store_code", "logic": "直接取值", "sample": "S001"}]}],
        "pipelines": [{"id": "pipeline_daily", "data_utilization": "daily_report", "name": "daily_pipeline", "task_name": "build_daily", "description": "生成合成日报", "trigger": "每日 07:00", "prefix": "legacy_pipeline_prefix", "sources": ["source_daily"], "targets": ["target_daily"], "steps": ["读取源表", "过滤并写入目标表"], "write_order": [write_storage], "rerun": "按日期参数重跑"}],
        "catalog": {
            "enabled": True,
            "basic_info": [{"data_item": "target_daily", "title": "合成目标表", "it_owner": "IT", "biz_owner": "Biz", "fe": "FE", "it_bp": "BP", "data_engineer": "DE"}],
            "dictionary": [{"data_item": "target_daily", "column": "store_code", "type": "String"}],
            "storage": [{"data_item": "target_daily", "location": "demo.target_daily", "field_type": "store_code String", "limit": "S001"}],
        },
        "resources": {"peak_memory": "10G内", "environment": "共享"},
        "flow": {
            "title": "合成数据流程图",
            "description": f"源数据经 Pipeline 写入 {write_storage}。",
            "nodes": [
                {"id": "flow_source", "label": "PLANT_PRODUCTION/FULL/<P>/<W>", "kind": "hbase", "column": 0, "order": 0, "details": ["T-1"]},
                {"id": "flow_pipeline", "label": "daily_pipeline", "kind": "pipeline", "column": 1, "order": 0, "details": ["每日 07:00"]},
                {"id": "flow_target", "label": target_label, "kind": target_kind, "column": 2, "order": 0, "details": ["按日覆盖"]},
            ],
            "edges": [
                {"id": "edge_source_pipeline", "from": "flow_source", "to": "flow_pipeline", "label": "读取", "kind": "source"},
                {"id": "edge_pipeline_target", "from": "flow_pipeline", "to": "flow_target", "label": "写入", "kind": "output"},
            ],
        },
        "questions": [],
        "conflicts": [],
        "confirmed_pending_paths": [],
        "render_preferences": {
            "last_format": "",
            "include_target_category": False,
            "include_target_report_type": False,
            "include_target_range": False,
        },
        "change_log": [],
    }
    return result


def generated_path(out: Path, title: str, suffix: str) -> Path:
    return out / f"{title}{suffix}"


def test_extraction(root: Path) -> dict:
    docx = root / "synthetic.docx"
    markdown = root / "synthetic.md"
    searchable = root / "searchable.pdf"
    scanned = root / "scanned.pdf"
    make_embedded_docx(docx)
    make_markdown(markdown)
    make_searchable_pdf(searchable)
    make_scanned_pdf(scanned)
    output = root / "extract_output"
    run(str(EXTRACT), "--input", str(docx), str(markdown), str(searchable), str(scanned), "--out", str(output))
    index = json.loads((output / "extracted" / "evidence_index.json").read_text(encoding="utf-8"))
    assert len(index["documents"]) == 4
    all_tables = [table for document in index["documents"] for table in document.get("tables") or []]
    assert any(table["kind"] == "embedded_excel" and table["rows"] == 3 and table["columns"] == 3 for table in all_tables), all_tables
    assert sum(table["kind"] == "markdown_table" for table in all_tables) == 1, all_tables
    assert any(table["kind"] == "pdf_table" for table in all_tables), all_tables
    assert index["documents"][3]["requires_visual_review"] is True
    return {"documents": 4, "tables": len(all_tables), "visual_review_pages": len(index["documents"][3]["images"])}


def render_and_validate(root: Path, profile: str, output_format: str) -> dict:
    title = f"合成{profile}水线文档"
    output = root / f"render_{profile}_{output_format}"
    output.mkdir(parents=True)
    facts_path = output / "facts.json"
    facts_path.write_text(json.dumps(facts(profile, title), ensure_ascii=False, indent=2), encoding="utf-8")
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", output_format)
    markdown = generated_path(output, title, ".md")
    html = generated_path(output, title, ".html")
    pdf = generated_path(output, title, ".pdf")
    normalized_facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert normalized_facts["document"]["team"]["owner"] == "Owner"
    assert normalized_facts["document"]["team"]["developer"] == "数砚工程师"
    assert normalized_facts["document"]["team"]["operator"] == "数砚工程师"
    questions_text = (output / "questions.md").read_text(encoding="utf-8")
    assert "PL-BLOCK-DEVELOPER" not in questions_text
    assert "PL-BLOCK-OPERATOR" not in questions_text
    assert markdown.exists() is ("markdown" in OUTPUT_FORMATS[output_format])
    assert html.exists() is ("html" in OUTPUT_FORMATS[output_format])
    assert pdf.exists() is ("pdf" in OUTPUT_FORMATS[output_format])
    args = [str(VALIDATE), "--facts", str(facts_path), "--profile", profile]
    if markdown.exists():
        args.extend(["--markdown", str(markdown)])
        markdown_text = markdown.read_text(encoding="utf-8")
        assert "Owner: Owner" in markdown_text
        assert "Developer: 数砚工程师" in markdown_text
        assert "Operator: 数砚工程师" in markdown_text
        if profile == "sync":
            target_section = markdown_text.split("# 3. Target", 1)[1].split("# 4. Pipeline", 1)[0]
            assert "| 序号 | 数据位置 |" in markdown_text
            assert "| 1 | Data Hub HBase |" in markdown_text
            assert "# 3. Target" in markdown_text
            assert "| 序号 | 原表位置 | 原表名 | 业务描述 | HBase表名 |" in target_section
            assert "| 1 | Data Hub HBase | PLANT_PRODUCTION/FULL/<P>/<W>/part-* | 合成源表 | l0_demo_target_daily |" in target_section
            assert "所属类别" not in target_section
            assert "报表类型" not in target_section
            assert "数据范围" not in target_section
            assert "| Data Utilization Name | Target Name | Target Storage | catalog |" in markdown_text
            assert "| Data Utilization Name | Pipeline Name | task1 name | 定时同步时间 |" in markdown_text
            assert "target前缀" not in markdown_text
            assert "pipeline前缀" not in markdown_text
            assert "legacy_target_prefix" not in markdown_text
            assert "legacy_pipeline_prefix" not in markdown_text
            assert "### 4.2.4 Catalog Basic Info" in markdown_text
            assert "| 数据项 | Title | IT Owner&Email | Biz Owner&Email | FE&Email | IT BP & Email | Data Engineer & Email |" in markdown_text
            assert "ClickHouse" not in markdown_text
    if html.exists():
        args.extend(["--html", str(html)])
    if pdf.exists():
        args.extend(["--pdf", str(pdf)])
    run(*args)
    if html.exists():
        html_text = html.read_text(encoding="utf-8")
        assert_html_navigation(html_text)
        assert "Developer: 数砚工程师" in html_text
        assert "Operator: 数砚工程师" in html_text
        assert "target前缀" not in html_text
        assert "pipeline前缀" not in html_text
        assert "legacy_target_prefix" not in html_text
        assert "legacy_pipeline_prefix" not in html_text
        if profile == "sync":
            assert "4.2.4 Catalog Basic Info" in html_text
        assert "<svg" in html_text and "<style>" in html_text
        assert "<link" not in html_text and html_text.count('<script data-waterline-viewer="1">') == 1
        assert 'Content-Security-Policy' in html_text
        assert 'data-engine="graphviz"' in html_text
        assert "overflow-y:auto;overflow-x:hidden" in html_text
        assert "overflow-wrap:anywhere" in html_text
        if profile == "sync":
            assert "PLANT_PRODUCTION/FULL/&lt;P&gt;/&lt;W&gt;/part-*" in html_text
            assert "ClickHouse" not in html_text
    return {"profile": profile, "format": output_format, "output": output, "facts": facts_path, "markdown": markdown, "html": html, "pdf": pdf}


def test_multi_target_mapping(root: Path) -> dict:
    title = "合成多目标水线文档"
    output = root / "render_sync_multi_target"
    output.mkdir(parents=True)
    data = facts("sync", title)
    clickhouse_target = copy.deepcopy(data["targets"][0])
    clickhouse_target.update({
        "id": "target_daily_clickhouse",
        "location": "Superview ClickHouse",
        "database": "demo",
        "table": "target_daily_clickhouse",
        "description": "合成 ClickHouse 查询表",
    })
    clickhouse_target["fields"][0]["id"] = "target_clickhouse_store_code"
    data["targets"].append(clickhouse_target)
    data["pipelines"][0]["targets"].append("target_daily_clickhouse")
    data["pipelines"][0]["write_order"].append("ClickHouse")
    data["flow"]["nodes"].append({"id": "flow_target_clickhouse", "label": "demo.target_daily_clickhouse", "kind": "clickhouse", "column": 2, "order": 1, "details": ["按日覆盖"]})
    data["flow"]["edges"].append({"id": "edge_pipeline_target_clickhouse", "from": "flow_pipeline", "to": "flow_target_clickhouse", "label": "写入", "kind": "output"})
    facts_path = output / "facts.json"
    facts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", "both")
    markdown = generated_path(output, title, ".md")
    html = generated_path(output, title, ".html")
    run(str(VALIDATE), "--facts", str(facts_path), "--profile", "sync", "--markdown", str(markdown), "--html", str(html))
    target_section = markdown.read_text(encoding="utf-8").split("# 3. Target", 1)[1].split("# 4. Pipeline", 1)[0]
    assert "| HBase表名 | ClickHouse表名 |" in target_section
    assert "所属类别" not in target_section
    assert "报表类型" not in target_section
    assert "数据范围" not in target_section
    source_rows = [line for line in target_section.splitlines() if line.startswith("| 1 |")]
    assert len(source_rows) == 1, source_rows
    assert "PLANT_PRODUCTION/FULL/<P>/<W>/part-*" in source_rows[0]
    assert "l0_demo_target_daily" in source_rows[0]
    assert "demo.target_daily_clickhouse" in source_rows[0]
    data["render_preferences"]["include_target_category"] = True
    data["render_preferences"]["include_target_report_type"] = True
    data["render_preferences"]["include_target_range"] = True
    facts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", "both")
    target_section_with_range = markdown.read_text(encoding="utf-8").split("# 3. Target", 1)[1].split("# 4. Pipeline", 1)[0]
    assert "| 所属类别 | 报表类型 | HBase表名 | ClickHouse表名 | 数据范围 |" in target_section_with_range
    assert "HBase数据范围" not in target_section_with_range
    assert "ClickHouse数据范围" not in target_section_with_range
    assert "HBase：每日 07:00<br>ClickHouse：每日 07:00" in target_section_with_range
    run(str(VALIDATE), "--facts", str(facts_path), "--profile", "sync", "--markdown", str(markdown), "--html", str(html))
    return {"source_rows": len(source_rows), "target_storages": ["HBase", "ClickHouse"], "optional_columns_toggle": True}


def test_target_optional_column_gate(root: Path) -> dict:
    title = "合成待确认Target列水线文档"
    output = root / "render_sync_target_columns_unconfirmed"
    output.mkdir(parents=True)
    data = facts("sync", title)
    for key in ("include_target_category", "include_target_report_type", "include_target_range"):
        data["render_preferences"].pop(key)
    facts_path = output / "facts.json"
    facts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", "both", expected=2)
    questions = (output / "questions.md").read_text(encoding="utf-8")
    assert "PL-BLOCK-TARGET-OPTIONAL-COLUMNS" in questions
    assert not generated_path(output, title, ".md").exists()
    assert not generated_path(output, title, ".html").exists()
    return {"question": "PL-BLOCK-TARGET-OPTIONAL-COLUMNS", "formal_output_blocked": True}


def test_sync_catalog_basic_info_gate(root: Path) -> dict:
    title = "合成待补充Catalog水线文档"
    output = root / "render_sync_catalog_unconfirmed"
    output.mkdir(parents=True)
    data = facts("sync", title)
    data["catalog"]["basic_info"] = []
    facts_path = output / "facts.json"
    facts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", "both", expected=2)
    questions = (output / "questions.md").read_text(encoding="utf-8")
    assert "PL-BLOCK-CATALOG-BASIC-INFO" in questions
    assert not generated_path(output, title, ".md").exists()
    assert not generated_path(output, title, ".html").exists()
    return {"question": "PL-BLOCK-CATALOG-BASIC-INFO", "formal_output_blocked": True}


def test_conversational_edit(result: dict) -> dict:
    facts_path: Path = result["facts"]
    data = json.loads(facts_path.read_text(encoding="utf-8"))
    data["targets"][0]["table"] = "target_daily_v2"
    data["targets"][0]["fields"][0]["key"] = "store_id"
    data["pipelines"][0]["trigger"] = "每日 08:00"
    data["flow"]["nodes"][2]["label"] = "demo.target_daily_v2"
    data["change_log"].append({"timestamp": "2026-09-01T00:00:00+08:00", "summary": "修改目标表、字段和调度", "source": "user_confirmation"})
    facts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    output: Path = result["output"]
    run(str(RENDER), "--facts", str(facts_path), "--out-dir", str(output), "--format", "both")
    markdown = result["markdown"]
    html = result["html"]
    svg = next(output.glob("*_files/data_flow.svg"))
    for path in (markdown, html, svg):
        text = path.read_text(encoding="utf-8")
        assert "target_daily_v2" in text, path
    assert "store_id" in markdown.read_text(encoding="utf-8")
    assert "每日 08:00" in html.read_text(encoding="utf-8")
    run(str(VALIDATE), "--facts", str(facts_path), "--profile", result["profile"], "--markdown", str(markdown), "--html", str(html))
    return {"changed_target": "target_daily_v2", "changed_field": "store_id", "changed_trigger": "每日 08:00"}


def test_complex_flow_layout(root: Path) -> dict:
    spec = {
        "title": "执行为王复杂流程回归",
        "description": "验证分组标题、跨列连线和连线标签。",
        "groups": [
            {"id": "sources", "title": "数据源", "column": 0, "order": 0},
            {"id": "prepare", "title": "调度 / 准备", "column": 1, "order": 1},
            {"id": "calculate", "title": "业务计算", "column": 2, "order": 2},
            {"id": "targets", "title": "Superview ClickHouse", "column": 3, "order": 3},
        ],
        "nodes": [
            {"id": "source", "label": "HBase Source", "kind": "hbase", "column": 0, "order": 0, "group": "sources"},
            {"id": "manual", "label": "prepare_history_or_manual", "kind": "pipeline", "column": 1, "order": 0, "group": "prepare"},
            {"id": "daily", "label": "daily_export_sku", "kind": "pipeline", "column": 1, "order": 1, "group": "prepare"},
            {"id": "npd", "label": "cal_npd_daily", "kind": "pipeline", "column": 2, "order": 0, "group": "calculate"},
            {"id": "b5", "label": "cal_b5_daily", "kind": "pipeline", "column": 2, "order": 1, "group": "calculate"},
            {"id": "target_npd", "label": "store_np_sku_details", "kind": "clickhouse", "column": 3, "order": 0, "group": "targets"},
            {"id": "target_b5", "label": "store_b5_sku_details", "kind": "clickhouse", "column": 3, "order": 1, "group": "targets"},
            {"id": "target_config", "label": "store_assess_channnel", "kind": "clickhouse", "column": 3, "order": 2, "group": "targets"},
        ],
        "edges": [
            {"id": "source_daily", "from": "source", "to": "daily", "label": "当P增量", "kind": "source"},
            {"id": "manual_npd", "from": "manual", "to": "npd", "label": "手动重跑", "kind": "control"},
            {"id": "manual_b5", "from": "manual", "to": "b5", "label": "手动重跑", "kind": "control"},
            {"id": "daily_npd", "from": "daily", "to": "npd", "label": "触发新品", "kind": "pipeline"},
            {"id": "daily_b5", "from": "daily", "to": "b5", "label": "触发B5", "kind": "pipeline"},
            {"id": "npd_target", "from": "npd", "to": "target_npd", "kind": "output"},
            {"id": "b5_target", "from": "b5", "to": "target_b5", "kind": "output"},
            {"id": "daily_config", "from": "daily", "to": "target_config", "label": "每日同步配置", "kind": "output"},
        ],
    }
    output = root / "complex_flow.svg"
    render_spec(spec, output)
    svg_text = output.read_text(encoding="utf-8")
    assert "Superview ClickHouse" in svg_text and "阶段 4" not in svg_text
    document = ET.parse(output).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    validate_svg(document, spec)
    assert output.with_suffix(".dot").is_file() and output.with_suffix(".layout.json").is_file()
    first_bytes = output.read_bytes()
    render_spec(spec, output)
    assert output.read_bytes() == first_bytes, "Repeated rendering must be stable"
    # An explicit parallel-entry card keeps the daily configuration edge at its row port.
    spec["presentation"] = {"cards": [{"id": "entry_pair", "title": "两个独立入口", "node_ids": ["manual", "daily"]}]}
    cards, edges, _, _ = graph_model(spec)
    config_edge = next(edge for edge in edges if any(e["id"] == "daily_config" for e in edge["originals"]))
    assert config_edge["tailport"] == "p1"
    render_spec(spec, root / "parallel_flow.svg")
    validate_svg(ET.parse(root / "parallel_flow.svg").getroot(), spec)
    return {"edges": len(spec["edges"]), "engine": "graphviz", "stable_rerender": True, "parallel_entry_port": True}


def test_graphviz_contract(root: Path) -> dict:
    spec = {
        "title": "合成分类配色与完整文本", "description": "验证布局、长标识符与同类聚合。",
        "nodes": [{"id": "s", "label": "Blob 文件", "kind": "blob", "column": 0,
                   "details": ["input/" + "long_segment_" * 14 + "/*.csv", "第一行\n第二行\n第三行\n第四行"]},
                  {"id": "p", "label": "同步任务", "kind": "pipeline", "column": 1}],
        "edges": [{"id": "read", "from": "s", "to": "p", "label": "读取", "kind": "source"}],
    }
    for i in range(3):
        spec["nodes"].append({"id": f"t{i}", "label": f"demo.target_{i}", "kind": "clickhouse", "column": 2, "details": [f"目标 {i}"]})
        spec["edges"].append({"id": f"write{i}", "from": "p", "to": f"t{i}", "kind": "output", "label": "写入"})
    output = root / "categories.svg"
    render_spec(spec, output)
    tree = ET.parse(output).getroot()
    validate_svg(tree, spec)
    assert len([n for n in tree.iter() if n.get("data-members")]) == 3
    assert len([n for n in tree.iter() if n.get("data-edge-ids")]) == 2
    visible = ''.join(n.text or '' for n in tree.iter() if n.tag.endswith('}text'))
    assert "第四行" in visible and spec["nodes"][0]["details"][0] in visible
    for card in [n for n in tree.iter() if n.get("data-category")]:
        band = next(n for n in card if n.get("class") == "node-band")
        assert band.get("fill") == PALETTES[card.get("data-category")][1]
    invalid = copy.deepcopy(spec)
    invalid["presentation"] = {"cards": [{"id": "bad", "node_ids": ["s", "p"]}]}
    try:
        validate_spec(invalid)
        raise AssertionError("Mixed-kind card accepted")
    except ValueError:
        pass
    edited = copy.deepcopy(spec)
    edited["edges"][0]["label"] = "已修改"
    try:
        validate_svg(tree, edited)
        raise AssertionError("Stale SVG accepted")
    except ValueError:
        pass
    return {"all_text_preserved": True, "auto_group_coverage": True, "category_colors": True, "stale_svg_rejected": True}


def test_viewer_security(root: Path) -> dict:
    data = facts("sync", "合成安全检查")
    svg = root / "security.svg"
    render_spec(data["flow"], svg)
    markup = markdown_to_html("![流程图](security.svg)", root / "security.md", "安全检查")
    expected = {"flow": data["flow"], "targets": []}
    candidate = root / "security.html"
    candidate.write_text(markup, encoding="utf-8")
    errors = []
    validate_html(candidate, expected, errors, {})
    assert not errors, errors
    for addition in ('<script>alert(1)</script>', '<img src="https://example.invalid/p.png">', '<style>body{background:url(other.png)}</style>', '<svg onload="alert(1)"></svg>'):
        candidate.write_text(markup.replace('</body>', addition+'</body>'), encoding="utf-8")
        errors = []
        validate_html(candidate, expected, errors, {})
        assert errors, addition
    malicious = root / "untrusted.svg"
    for child in ('<script>alert(1)</script>', '<g onload="alert(1)"/>', '<rect fill="url(https://example.invalid/x)"/>', '<foreignObject/>'):
        malicious.write_text('<svg xmlns="http://www.w3.org/2000/svg">'+child+'</svg>', encoding="utf-8")
        try:
            safe_inline_svg(malicious)
            raise AssertionError("Unsafe SVG accepted")
        except ValueError:
            pass
    link = inline_markup('[链接](https://example.invalid/" onmouseover="alert)')
    probe = NavigationProbe(link)
    assert all(not key.startswith('on') for node in probe.nodes for key in node['attrs'])
    candidate.write_text(markup, encoding="utf-8")
    return {"trusted_viewer_only": True, "external_resources_rejected": True, "unsafe_svg_rejected": True, "attribute_injection_escaped": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="Optional directory for retaining regression artifacts.")
    args = parser.parse_args()
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8", errors="replace")
    context = nullcontext(str(args.work_dir.resolve())) if args.work_dir else tempfile.TemporaryDirectory(prefix="pipeline_doc_generator_")
    with context as temporary:
        root = Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        metrics = {"extraction": test_extraction(root), "flow_layout": test_complex_flow_layout(root), "graphviz_contract": test_graphviz_contract(root), "viewer_security": test_viewer_security(root), "html_navigation": test_html_navigation(root), "renders": []}
        edit_candidate = None
        for profile in ("sync", "report"):
            for output_format in OUTPUT_FORMATS:
                result = render_and_validate(root, profile, output_format)
                metrics["renders"].append({"profile": profile, "format": output_format})
                if profile == "report" and output_format == "both":
                    edit_candidate = result
        metrics["target_optional_column_gate"] = test_target_optional_column_gate(root)
        metrics["sync_catalog_basic_info_gate"] = test_sync_catalog_basic_info_gate(root)
        metrics["multi_target_mapping"] = test_multi_target_mapping(root)
        assert edit_candidate is not None
        metrics["conversational_edit"] = test_conversational_edit(edit_candidate)
        from verify_authoring_policy import run_authoring_regressions
        metrics["authoring_policy"] = run_authoring_regressions(root / "authoring")
        from verify_pipeline_pdf import run_pdf_regressions
        metrics["pdf"] = run_pdf_regressions(root / "pdf_special", check_formats=False)
        print(json.dumps({"status": "ok", **metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
