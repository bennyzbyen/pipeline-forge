#!/usr/bin/env python3
"""Verify Markdown-only and mixed-format requirement extraction."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent
EXTRACTOR = ROOT / "extract_docx_bundle.py"


PRD_MARKDOWN = r"""---
document_type: prd
owner: business
---
# QAS 异常监控 PRD

## 异常规则

| 异常类型 | 判断规则 | 数据粒度 | 数据来源 | 产出数据表 |
| --- | --- | --- | --- | --- |
| GSV异常 | `GSV > 10 \| tolerance at C:\data` | 门店日 | l1_sales | qas_alert_daily |

## KPI

| KPI 名称 | 单位 | 数据来源底表 | 取值字段 | 汇总逻辑 |
| --- | --- | --- | --- | --- |
| 异常门店数 | 家 | qas_alert_daily | store_code | count distinct |

```text
| 这不是 | 需求表 |
| --- | --- |
```
"""


WATERLINE_MARKDOWN = """# QAS Waterline

## 数据源

| 位置 | 数据表名 | 数据表 | 取数范围 | 字段 | 关联、过滤信息 |
| --- | --- | --- | --- | --- | --- |
| Data Hub HBase | 销售明细 | l1_sales | period = T-1 | store_code, gsv | gsv is not null |

## 物理目标

| Description | Data Storage | Database | Table Name |
| --- | --- | --- | --- |
| 异常门店日表 | Superview Clickhouse | abnormal_monitor | qas_alert_daily |

## 字段映射

| 字段 key | 字段名称 | 数据源位置 | 数据表 | 数据源对应的字段 | 计算逻辑 |
| --- | --- | --- | --- | --- | --- |
| store_code | 门店代码 | Data Hub HBase | l1_sales | store_code | 原样输出 |
| alert_flag | 异常标记 | Data Hub HBase | l1_sales | gsv | gsv > 10 |
"""


def write_minimal_docx(path: Path) -> None:
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>补充水线说明</w:t></w:r></w:p>
    <w:p><w:r><w:t>Data Target: abnormal_monitor.qas_alert_daily</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def run_extractor(inputs: list[Path], output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EXTRACTOR), "--input", *map(str, inputs), "--out", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_markdown_only(root: Path) -> dict:
    prd = root / "prd.md"
    waterline = root / "waterline.markdown"
    prd.write_text(PRD_MARKDOWN, encoding="utf-8")
    waterline.write_text(WATERLINE_MARKDOWN, encoding="utf-8")
    output = root / "markdown_output"
    completed = run_extractor([prd, waterline], output)
    assert completed.returncode == 0, completed.stderr
    facts = json.loads((output / "dev_doc" / "structured_facts.json").read_text(encoding="utf-8"))
    assert [item["format"] for item in facts["documents"]] == ["markdown", "markdown"]
    assert len(facts["report_business_rules"]) == 1
    assert facts["report_business_rules"][0]["rule"] == r"`GSV > 10 | tolerance at C:\data`"
    assert facts["report_business_rules"][0]["source_kind"] == "markdown"
    assert facts["report_sources"][0]["source_doc_name"] == "waterline.markdown"
    assert facts["report_physical_targets"][0]["table"] == "abnormal_monitor.qas_alert_daily"
    assert len(facts["report_field_mappings"]) == 1
    assert len(facts["report_field_mappings"][0]["fields"]) == 2
    csvs = list((output / "extracted").rglob("markdown_table_*.csv"))
    assert len(csvs) == 5, csvs
    design = (output / "dev_doc" / "technical_design.md").read_text(encoding="utf-8")
    assert "`prd.md`" in design and "`waterline.markdown`" in design
    return {"documents": 2, "markdown_tables": len(csvs), "mapped_fields": 2}


def assert_mixed_formats(root: Path) -> dict:
    docx = root / "waterline.docx"
    markdown = root / "supplement.md"
    write_minimal_docx(docx)
    markdown.write_text("# 补充 PRD\n\n目标表为 `abnormal_monitor.qas_alert_daily`。\n", encoding="utf-8")
    output = root / "mixed_output"
    completed = run_extractor([docx, markdown], output)
    assert completed.returncode == 0, completed.stderr
    facts = json.loads((output / "dev_doc" / "structured_facts.json").read_text(encoding="utf-8"))
    assert [item["format"] for item in facts["documents"]] == ["docx", "markdown"]
    assert facts["documents"][0]["name"] == "waterline.docx"
    assert facts["documents"][1]["name"] == "supplement.md"
    assert (output / "extracted" / "doc_001_waterline" / "extracted_document.md").exists()
    assert (output / "extracted" / "doc_002_supplement" / "extracted_document.md").exists()
    return {"documents": 2, "formats": ["docx", "markdown"]}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="requirement_markdown_regression_") as temp_dir:
        root = Path(temp_dir)
        result = {
            "status": "passed",
            "markdown_only": assert_markdown_only(root),
            "mixed_formats": assert_mixed_formats(root),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
