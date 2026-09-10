#!/usr/bin/env python3
"""Offline regressions for concise prose, Blob connections, and three-format edits."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader

from pipeline_doc_common import blocking_questions, write_json
from pipeline_doc_presentation import connection_note, concise_trigger, sas_expiry, sas_url
from render_pipeline_doc import project_pipeline_sections, source_connections, target_table_sync
from pipeline_diagram_contract import validate_svg
from verify_pipeline_doc_generator import facts, run, RENDER, VALIDATE


def blob_facts(profile):
    data = facts(profile, f"合成{profile}三格式简洁水线")
    overview = "将测试产量数据从 Azure Blob Storage 同步至目标存储。"
    data["requirements"]["summary"] = [overview, overview]
    data["document"]["description"] = overview
    data["document"]["write_flow"] = []
    data["document"]["sync_logic"] = []
    source = data["sources"][0]
    source.update(location="Azure Blob Storage", name="DEMO/FULL/yyyy/mm/dd/part-*", system="合成来源")
    # Deliberately invalid credentials on a reserved domain; never use real SAS.
    url = "https://storage.example.invalid/container?sp=rl&se=2030-01-01T00%3A00%3A00Z&sig=" + "TEST%2BONLY%2FNOT%3DVALID"
    data["source_connections"] = [{"environment": "QA", "source_id": source["id"], "sas_url": url, "database": "DEMO/FULL/yyyy/mm/dd", "note": "合成只读连接"}]
    data["targets"][0].update(rowkey="已确认的业务组合键", catalog="legacy_catalog_not_for_display")
    pipeline = data["pipelines"][0]
    pipeline.update(description=overview, trigger="每日 06:00 执行", schedule_notes="上游需在 05:30 前就绪，失败时按运维方案重试。")
    data["flow"]["nodes"][0].update(kind="blob", label="测试产量", identifiers=[source["name"]])
    for node in data["flow"]["nodes"]:
        node["details"] = ["RowKey：自增序号", "字段类型：str", "truncate + insert", "每日 06:00 执行"]
    data["questions"] = [{"id": "WL-BLOCK-WRITE-FLOW", "severity": "block", "question": "旧写入叙述", "status": "open"}]
    data["render_preferences"]["last_format"] = "html"
    return data


def test_connections_and_gates():
    data = blob_facts("sync")
    original = copy.deepcopy(data)
    assert not blocking_questions(data), blocking_questions(data)
    assert data["render_preferences"]["last_format"] == "all"
    assert data["source_connections"] == original["source_connections"]
    assert data["targets"][0]["rowkey"] == original["targets"][0]["rowkey"]
    connection = data["source_connections"][0]
    assert sas_url(connection) == original["source_connections"][0]["sas_url"]
    assert sas_expiry(connection) == "2030-01-01 00:00:00+00:00"
    assert connection_note(connection).count("过期时间") == 1
    blob_table = source_connections(data)
    assert "| SAS URL | Database / 路径 | 备注 |" in blob_table
    assert "Host / 地址" not in blob_table and sas_url(connection) in blob_table

    mysql = copy.deepcopy(data["sources"][0])
    mysql.update(id="source_mysql", location="MySQL", name="demo.product")
    data["sources"].append(mysql)
    data["source_connections"].append({"environment": "QA", "source_id": "source_mysql", "host": "mysql.example.invalid", "database": "demo", "note": "只读"})
    mixed = source_connections(data)
    assert mixed.count("| SAS URL |") == 1 and mixed.count("| Host / 地址 |") == 1
    assert not blocking_questions(data), blocking_questions(data)
    missing_blob = copy.deepcopy(data)
    missing_blob["source_connections"] = [missing_blob["source_connections"][1]]
    assert any(q["id"] == "PL-BLOCK-BLOB-CONNECTIONS" for q in blocking_questions(missing_blob))
    ambiguous = copy.deepcopy(data)
    ambiguous["source_connections"][0].pop("source_id")
    assert any(q["id"].endswith("-SOURCE") for q in blocking_questions(ambiguous))
    for field, suffix in (("sas_url", "-SAS"), ("database", "-PATH")):
        missing = blob_facts("sync")
        missing["source_connections"][0][field] = ""
        assert any(q["id"].endswith(suffix) for q in blocking_questions(missing))
    missing = blob_facts("sync")
    missing["source_connections"][0]["sas_url"] = "https://storage.example.invalid/container?sig=FAKE_POLICY_TOKEN"
    assert any(q["id"].endswith("-EXPIRY") for q in blocking_questions(missing))
    missing["source_connections"][0]["expires_at"] = "由存储访问策略控制（已确认）"
    assert not blocking_questions(missing)
    bad_trigger = blob_facts("sync")
    bad_trigger["pipelines"][0]["trigger"] = "上游 06:00 就绪；水线 08:00 执行并校验写入"
    diagnostics = blocking_questions(bad_trigger)
    assert any(q["id"].endswith("-TRIGGER-DISPLAY") for q in diagnostics)
    assert bad_trigger["pipelines"][0]["trigger"].startswith("上游")  # Never guess a run time.
    for value in ("每日 06:00 执行", "每日 06:00、18:00", "0 6 * * * (Asia/Shanghai)", "手动触发", "_SUCCESS 事件触发"):
        assert concise_trigger(value), value
    bad_flow = blob_facts("sync")
    bad_flow["flow"]["nodes"][2]["label"] = "HBase\nRowKey：自增序号"
    assert any("FLOW" in q["id"] for q in blocking_questions(bad_flow))
    range_data = blob_facts("sync")
    range_data["render_preferences"]["include_target_range"] = True
    assert "每日 07:00" not in target_table_sync(range_data), "Range must not fall back to schedule"
    for profile in ("sync", "report"):
        disabled = blob_facts(profile)
        disabled["catalog"] = {"enabled": False}
        assert "Catalog Basic Info" in project_pipeline_sections(disabled, profile)
    return {"blob_and_mixed_connections": True, "expiry_gate": True, "no_time_guessing": True, "legacy_migration": True}


def test_bundle(root, profile):
    output = root / profile
    output.mkdir(parents=True, exist_ok=True)
    data = blob_facts(profile)
    path = output / "facts.json"
    write_json(path, data)
    # No --format: the default must produce three files even for legacy facts.
    run(str(RENDER), "--facts", str(path), "--out-dir", str(output))
    title = data["document"]["title"]
    md, html, pdf = [output / f"{title}{suffix}" for suffix in (".md", ".html", ".pdf")]
    assert all(item.is_file() for item in (md, html, pdf))
    run(str(VALIDATE), "--facts", str(path), "--profile", profile, "--markdown", str(md))
    text = md.read_text(encoding="utf-8")
    assert text.index("# 1. 需求概述") < text.index("数据流图")
    assert text.count(data["requirements"]["summary"][0]) == 1
    assert "写入流程" not in text and "同步逻辑说明" not in text
    assert "| catalog |" not in text and "legacy_catalog_not_for_display" not in text
    assert "Catalog Basic Info" in text
    assert ("SAS URL" in text) == (profile == "sync")
    assert text.count("06:00") == 1 and "05:30" not in text and "每日 07:00" not in text
    svg_path = output / f"{title}_files/data_flow.svg"
    tree = ET.parse(svg_path).getroot()
    visible = "".join(item.text or "" for item in tree.iter() if item.tag.endswith("}text"))
    for value in ("RowKey", "自增序号", "字段类型", "truncate", "06:00", "05:30"):
        assert value not in visible, value
    assert data["sources"][0]["name"] in visible
    saved = json.loads(path.read_text(encoding="utf-8"))
    validate_svg(tree, saved["flow"])
    assert saved["flow"] == data["flow"]  # Hidden implementation facts remain auditable.
    assert saved["pipelines"][0]["schedule_notes"] == data["pipelines"][0]["schedule_notes"]
    pdf_text = "".join(page.extract_text() for page in PdfReader(pdf).pages)
    assert "05:30" not in pdf_text and "自增序号" not in pdf_text
    assert "06:00" in html.read_text(encoding="utf-8")

    # Identical counts and valid SVGs cannot hide a stale schedule/field cell.
    original_html = html.read_text(encoding="utf-8")
    html.write_text(original_html.replace("06:00", "22:00"), encoding="utf-8")
    try:
        run(str(VALIDATE), "--facts", str(path), "--profile", profile, "--html", str(html), expected=1)
    finally:
        html.write_text(original_html, encoding="utf-8")

    # A missing sibling format must fail even when only --markdown was supplied.
    held_pdf = output / "held.pdf"
    pdf.rename(held_pdf)
    try:
        run(str(VALIDATE), "--facts", str(path), "--profile", profile, "--markdown", str(md), expected=1)
    finally:
        held_pdf.rename(pdf)
    saved["pipelines"][0]["trigger"] = "每日 08:30 执行"
    write_json(path, saved)
    run(str(RENDER), "--facts", str(path), "--out-dir", str(output), "--format", "html")
    run(str(VALIDATE), "--facts", str(path), "--profile", profile, "--html", str(html))
    for item in (md, html):
        changed = item.read_text(encoding="utf-8")
        assert "08:30" in changed and "06:00" not in changed
    assert "08:30" in "".join(page.extract_text() for page in PdfReader(pdf).pages)
    return {"profile": profile, "all_formats": True, "single_schedule": True, "overview_only_diagram": True, "edits_refresh_all": True}


def run_presentation_regressions(root):
    return {"gates": test_connections_and_gates(), "bundles": [test_bundle(root, profile) for profile in ("sync", "report")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pipeline_presentation_") as temporary:
        print(json.dumps(run_presentation_regressions(args.work_dir or Path(temporary)), ensure_ascii=False, indent=2))
