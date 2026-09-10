#!/usr/bin/env python3
"""Offline regressions for report edits learned from the document workflow."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

from pipeline_doc_authoring import checkpoint_revision, prepare_revision
from pipeline_doc_common import apply_fixed_defaults, blocking_questions
from pipeline_doc_report import target_reference
from render_pipeline_doc import render_markdown
from validate_pipeline_doc import validate_facts
from verify_pipeline_doc_generator import facts, run, RENDER, VALIDATE


def run_report_policy(root):
    data = facts("report", "合成报表固定格式")
    data["document"]["release_history"] = []
    data["document"]["documentation"] = "引用模型 LLD [本地设计](../model.md)"
    data["source_connections"] = []
    first = data["targets"][0]
    first["storage_tables"] = {"HBase": "demo_hbase.measure", "ClickHouse": "demo_ck.measure"}
    first["fields"][0]["source_field"] = "unique_source_key"
    second = copy.deepcopy(first)
    second.update(id="second_target", table="second_table", storage_tables={"ClickHouse": "demo_ck.second_table"})
    data["targets"].append(second)
    data["pipelines"][0]["targets"].append(second["id"])
    data["catalog"]["dictionary"].append({"data_item": "second entry", "target_id": "second_target"})
    apply_fixed_defaults(data)
    checkpoint_revision(data)
    data["requirements"]["summary"] = ["从 HBase 读取源数据，加工后写入结果存储。"]
    data["change_log"].append({"summary": "修改初稿概述"})
    prepare_revision(data)
    assert len(data["document"]["release_history"]) == 1
    assert data["document"]["release_history"][0]["author"] == "张本彦"
    assert data["document"]["release_history"][0]["version"] == "0.0.1"
    markdown = render_markdown(data, "flow.svg")
    assert "链接信息" not in markdown and "../model.md" not in markdown
    assert "源字段/计算规则" not in markdown and "数据样例" not in markdown
    assert "unique_source_key" in markdown and "直接取值" in markdown
    assert "demo_hbase.measure" in markdown and "demo_ck.measure" in markdown
    assert "demo_ck.second_table" in markdown and "不适用" in markdown
    assert f"### 3.1.1 {first['table']}" in markdown
    row = data["catalog"]["dictionary"][0]
    assert target_reference(data, row) == "参见 3.1.1"
    data["targets"].reverse()
    assert target_reference(data, row) == "参见 3.1.2"
    original = copy.deepcopy(data)
    data["targets"].pop()
    errors = []
    validate_facts(data, "report", errors, [])
    assert any("Catalog" in error for error in errors), errors
    data = original
    # Hidden connection details do not block a report or leak into its body.
    blob = copy.deepcopy(data)
    blob["sources"][0]["location"] = "Azure Blob Storage"
    assert not any("CONNECTION" in q["id"] for q in blocking_questions(blob))
    # Same name in different schemas cannot accidentally select a dictionary.
    ambiguous = copy.deepcopy(data)
    ambiguous["targets"][0]["table"] = ambiguous["targets"][1]["table"] = "ambiguous_table"
    try:
        target_reference(ambiguous, {"data_item": ambiguous["targets"][0]["table"]})
    except ValueError:
        pass
    else:
        raise AssertionError("Ambiguous dictionary identity accepted")
    root.mkdir(parents=True, exist_ok=True)
    path = root / "facts.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run(str(RENDER), "--facts", str(path), "--out-dir", str(root), "--format", "all")
    title = data["document"]["title"]
    run(str(VALIDATE), "--facts", str(path), "--profile", "report", "--markdown", str(root/f"{title}.md"),
        "--html", str(root/f"{title}.html"), "--pdf", str(root/f"{title}.pdf"))
    rendered = json.loads(path.read_text(encoding="utf-8"))
    assert len(rendered["document"]["release_history"]) == 1
    assert rendered["document"]["documentation"] == data["document"]["documentation"], "Audit evidence was erased"
    # Entering version management creates exactly one subsequent release.
    rendered["document"]["release_mode"] = "versioned"
    prepare_revision(rendered)
    assert rendered["document"]["release_history"][-1]["version"] == "0.0.2"
    prepare_revision(rendered)
    assert len(rendered["document"]["release_history"]) == 2
    return {"draft_pin": True, "storage_identities": True, "unique_field_logic_preserved": True,
            "catalog_reorder_and_missing_target": True, "three_format_bundle": True}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="report_document_policy_") as temporary:
        print(json.dumps(run_report_policy(Path(temporary)), ensure_ascii=False, indent=2))
