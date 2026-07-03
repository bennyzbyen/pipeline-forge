#!/usr/bin/env python3
"""Regression checks for multi-DOCX extraction and delayed table headers."""

from __future__ import annotations

import html
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def col_name(index: int) -> str:
    value = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(ord("A") + remainder) + value
    return value


def sheet_xml(rows: list[list[str]]) -> str:
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row):
            ref = f"{col_name(col_index)}{row_index}"
            text = html.escape(str(value or ""))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    width = max((len(row) for row in rows), default=1)
    dimension = f"A1:{col_name(width - 1)}{len(rows) or 1}"
    return (
        f'<worksheet xmlns="{NS_X}">'
        f'<dimension ref="{dimension}"/>'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )


def make_xlsx(path: Path, rows: list[list[str]]) -> bytes:
    with zipfile.ZipFile(path, "w") as xlsx:
        xlsx.writestr(
            "xl/workbook.xml",
            (
                f'<workbook xmlns="{NS_X}" xmlns:r="{NS_REL_OFFICE}">'
                '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
        )
        xlsx.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                f'<Relationships xmlns="{NS_REL_PKG}">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        xlsx.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows))
    return path.read_bytes()


def paragraph_xml(text: str) -> str:
    return f'<w:p><w:r><w:t>{html.escape(text)}</w:t></w:r></w:p>'


def table_xml(rows: list[list[str]]) -> str:
    row_xml: list[str] = []
    for row in rows:
        cells = [
            f'<w:tc><w:p><w:r><w:t>{html.escape(str(value or ""))}</w:t></w:r></w:p></w:tc>'
            for value in row
        ]
        row_xml.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return f"<w:tbl>{''.join(row_xml)}</w:tbl>"


def make_docx(path: Path, title: str, embeddings: list[bytes], word_tables: list[list[list[str]]]) -> None:
    body = [paragraph_xml(title)]
    body.extend(table_xml(rows) for rows in word_tables)
    document = f'<w:document xmlns:w="{NS_W}"><w:body>{"".join(body)}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as docx:
        docx.writestr("word/document.xml", document)
        for index, payload in enumerate(embeddings, start=1):
            docx.writestr(f"word/embeddings/Microsoft_Excel_Worksheet{index}.xlsx", payload)


def make_docx_with_embedding_context(path: Path, blocks: list[tuple[str, bytes]]) -> None:
    rels: list[str] = []
    body: list[str] = [paragraph_xml("Synthetic COT Context Mapping")]
    with zipfile.ZipFile(path, "w") as docx:
        for index, (heading, payload) in enumerate(blocks, start=1):
            rel_id = f"rId{index}"
            workbook_name = f"Microsoft_Excel_Worksheet{index}.xlsx"
            body.append(paragraph_xml(heading))
            body.append(
                '<w:p><w:r><w:object>'
                f'<o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" '
                f'xmlns:r="{NS_REL_OFFICE}" r:id="{rel_id}"/>'
                '</w:object></w:r></w:p>'
            )
            rels.append(
                f'<Relationship Id="{rel_id}" '
                f'Type="{NS_REL_OFFICE}/package" '
                f'Target="embeddings/{workbook_name}"/>'
            )
            docx.writestr(f"word/embeddings/{workbook_name}", payload)
        document = f'<w:document xmlns:w="{NS_W}"><w:body>{"".join(body)}</w:body></w:document>'
        docx.writestr("word/document.xml", document)
        docx.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{NS_REL_PKG}">{"".join(rels)}</Relationships>')


def run_command(args: list[str]) -> None:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command failed: {' '.join(args)}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_fixture(tmp: Path) -> tuple[Path, Path]:
    prd_rule_xlsx = make_xlsx(
        tmp / "prd_rules.xlsx",
        [
            ["异常类型", "判断规则", "数据粒度", "数据源", "产出数据表"],
            ["在店时间异常", "在店时间<3分钟门店占比>=80%", "by day by业务员", "拜访频率By店报表", "qas_mw_visit_abnormal_store_daily"],
        ],
    )
    waterline_field_xlsx = make_xlsx(
        tmp / "waterline_field.xlsx",
        [
            ["报表路由：统计完美门店Project有拜访的所有明细拜访记录，取访店异常人员当天拜访的所有门店数据。", "", "", "", ""],
            ["数据源表：拜访频率by店", "", "", "", ""],
            ["数据表：qas_mw_visit_abnormal_store_daily", "", "", "", ""],
            ["计算频率：每天凌晨执行一次，执行昨日数据", "", "", "", ""],
            ["数据粒度：by day by业务员 by店", "", "", "", ""],
            ["字段key", "字段名称", "字段类型", "数据源+字段公式", "字段样例"],
            ["period", "P", "STRING", "取数据源的字段period", "2026P01"],
            ["visit_abnormal_id", "在店时间异常ID", "STRING", "同业务员+同KPI+同day共享ID", "A001"],
        ],
    )
    feedback_field_xlsx = make_xlsx(
        tmp / "feedback_field.xlsx",
        [
            ["数据表：qas_feedback_detail", "", "", "", "", ""],
            ["字段key", "字段名称", "字段类型", "数据源+字段公式", "数据样例", "报表前端是否显示"],
            ["feedback_id", "反馈ID", "STRING", "取反馈记录", "", "不显示"],
            ["kpi_type", "反馈KPI", "STRING", "取异常数据底表", "在店时间异常", "显示"],
        ],
    )
    target_mgmt_xlsx = make_xlsx(
        tmp / "target_mgmt.xlsx",
        [
            ["Data Utilization Name", "Target Name", "Target Description", "Data Storage"],
            ["qas_abnormal_data", "clickhouse_qas_mw_visit_abnormal_store_daily", "MW访店异常门店清单 by day", "clickhouse"],
            ["qas_abnormal_data", "clickhouse_qas_feedback_detail", "主管Portal反馈记录明细报表", "clickhouse"],
        ],
    )
    schedule_xlsx = make_xlsx(
        tmp / "schedule.xlsx",
        [
            ["Data Utilization Name", "Pipline_Name", "task1 name", "Description", "trigger time"],
            ["qas_abnormal_data", "cal_abnormal_data_daily", "cal_exception_data_daily", "六真异常数据by day", "0 2 * * *"],
        ],
    )

    prd_docx = tmp / "synthetic_prd.docx"
    waterline_docx = tmp / "synthetic_waterline.docx"
    make_docx(
        prd_docx,
        "Synthetic QAS PRD",
        [prd_rule_xlsx],
        [
            [
                ["KPI 名称", "单位", "数据来源底表", "取值字段", "汇总逻辑"],
                ["在店时间异常业务员数", "人", "qas_mw_visit_abnormal_store_daily", "visit_abnormal_id", "visit_abnormal_id非空去重业务员"],
            ]
        ],
    )
    make_docx(
        waterline_docx,
        "Synthetic QAS Data Engine水线文档",
        [waterline_field_xlsx, feedback_field_xlsx, target_mgmt_xlsx, schedule_xlsx],
        [
            [
                ["位置", "数据库", "数据表名", "数据表"],
                ["Superview Clickhouse", "abnormal_monitor", "MW访店异常门店清单 by day", "qas_mw_visit_abnormal_store_daily"],
                ["", "", "主管Portal反馈记录明细报表", "qas_feedback_detail"],
            ]
        ],
    )
    return prd_docx, waterline_docx


def build_cot_context_fixture(tmp: Path) -> Path:
    sixzhen_fields = make_xlsx(
        tmp / "sixzhen_fields.xlsx",
        [
            ["字段", "字段描述", "字段类型", "字段类型(mysql)"],
            ["inksaa_id", "主键", "", "bigint(20) unsigned"],
            ["period", "P", "", "varchar(10)"],
            ["store_code", "门店编码", "", "varchar(50)"],
            ["distance_rank", "距离范围区间", "", "varchar(30)"],
        ],
    )
    table_a_fields = make_xlsx(
        tmp / "table_a_fields.xlsx",
        [
            ["字段", "字段描述", "字段类型", "字段类型(mysql)"],
            ["id", "主键", "", "int"],
            ["period", "P", "", "varchar(10)"],
            ["code", "编码", "", "varchar(50)"],
        ],
    )
    data_utilizations = make_xlsx(
        tmp / "data_utilizations.xlsx",
        [
            ["Name", "Description"],
            ["table_a", "普通报表"],
            ["sixzhen_gps_distance", "进店与拍照距离收集报表"],
        ],
    )
    docx_path = tmp / "synthetic_cot_context.docx"
    make_docx_with_embedding_context(
        docx_path,
        [
            ("sixzhen_gps_distance 进店与拍照距离收集报表", sixzhen_fields),
            ("table_a 普通报表", table_a_fields),
            ("Data Utilization Management", data_utilizations),
        ],
    )
    return docx_path


def main() -> int:
    script = Path(__file__).with_name("extract_docx_bundle.py").resolve()
    with tempfile.TemporaryDirectory(prefix="docx-bundle-multidoc-") as tmp_name:
        tmp = Path(tmp_name)
        prd_docx, waterline_docx = build_fixture(tmp)

        single_out = tmp / "single"
        run_command(
            [
                sys.executable,
                str(script),
                "--docx",
                str(waterline_docx),
                "--out",
                str(single_out),
                "--project-name",
                "Synthetic Single",
            ]
        )
        assert_true((single_out / "extracted" / "extracted_document.md").exists(), "single-doc extracted document missing")
        assert_true((single_out / "dev_doc" / "dev_doc.md").exists(), "single-doc dev_doc missing")

        multi_out = tmp / "multi"
        run_command(
            [
                sys.executable,
                str(script),
                "--docx",
                str(prd_docx),
                "--docx",
                str(waterline_docx),
                "--out",
                str(multi_out),
                "--project-name",
                "Synthetic QAS",
            ]
        )

        doc_dirs = sorted((multi_out / "extracted").glob("doc_*"))
        assert_true(len(doc_dirs) == 2, f"expected two per-document extracted directories, got {len(doc_dirs)}")

        facts_path = multi_out / "dev_doc" / "structured_facts.json"
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        assert_true(len(facts.get("documents", [])) == 2, "structured facts should list both documents")
        assert_true(len(facts.get("report_targets", [])) == 2, "target-management rows were not extracted")
        assert_true(len(facts.get("report_schedules", [])) == 1, "pipeline schedule was not extracted")
        assert_true(len(facts.get("report_field_mappings", [])) >= 2, "delayed-header field dictionaries were not extracted")
        assert_true(len(facts.get("report_business_rules", [])) >= 1, "PRD abnormal rules were not extracted")
        assert_true(len(facts.get("report_kpi_rules", [])) >= 1, "PRD KPI rules were not extracted")

        physical_tables = {item.get("table") for item in facts.get("report_physical_targets", [])}
        assert_true(
            "abnormal_monitor.qas_mw_visit_abnormal_store_daily" in physical_tables,
            "physical ClickHouse target qas_mw_visit_abnormal_store_daily missing",
        )
        assert_true(
            "abnormal_monitor.qas_feedback_detail" in physical_tables,
            "physical ClickHouse target qas_feedback_detail missing",
        )

        dev_doc = (multi_out / "dev_doc" / "dev_doc.md").read_text(encoding="utf-8")
        assert_true("abnormal_monitor.qas_mw_visit_abnormal_store_daily" in dev_doc, "dev_doc missing physical target")
        assert_true("qas_feedback_detail" in dev_doc, "dev_doc missing delayed-header feedback dictionary")
        assert_true("在店时间异常" in dev_doc, "dev_doc missing PRD abnormal/KPI rule")

        questions = (multi_out / "dev_doc" / "questions.md").read_text(encoding="utf-8")
        assert_true("报表物理目标表未识别" not in questions, "questions should not report missing physical targets")

        cot_docx = build_cot_context_fixture(tmp)
        cot_out = tmp / "cot_context"
        run_command(
            [
                sys.executable,
                str(script),
                "--docx",
                str(cot_docx),
                "--out",
                str(cot_out),
                "--project-name",
                "Synthetic COT Context",
            ]
        )
        cot_facts = json.loads((cot_out / "dev_doc" / "structured_facts.json").read_text(encoding="utf-8"))
        sixzhen_mapping = next(
            (
                item
                for item in cot_facts.get("field_dictionaries", [])
                if item.get("inferred_data_utilization") == "sixzhen_gps_distance"
            ),
            {},
        )
        assert_true(sixzhen_mapping, "sixzhen_gps_distance field dictionary was not mapped")
        assert_true(
            "distance_rank" in sixzhen_mapping.get("first_fields", []),
            f"sixzhen_gps_distance mapped to wrong dictionary: {sixzhen_mapping.get('first_fields')}",
        )
        assert_true(
            sixzhen_mapping.get("inference_method") == "embedding_context",
            "sixzhen_gps_distance should be matched by embedding context, not order fallback",
        )

    print("multi-DOCX extraction regression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
