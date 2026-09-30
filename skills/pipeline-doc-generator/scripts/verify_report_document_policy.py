#!/usr/bin/env python3
"""Offline regressions for report edits learned from the document workflow."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

from pipeline_doc_authoring import checkpoint_revision, prepare_revision
from pipeline_doc_common import apply_fixed_defaults, blocking_questions
from pipeline_doc_report import target_reference, target_layer
from render_pipeline_doc import render_markdown, target_logic_sections, split_pipe_row
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
    first["category"] = "L2/I3"
    first["table"] = "warehouse_i3_daily_metric"
    first["logic"] = ["AUDIT_ONLY_TABLE_NARRATIVE"]
    first["processing_notes"] = ["AUDIT_ONLY_PROCESSING_NOTE"]
    extra_field = copy.deepcopy(first["fields"][0])
    extra_field.update(id="optional_metric", key="optional_metric", name="可空指标")
    first["fields"].append(extra_field)
    first["fields"][0]["nullable"] = False
    first["fields"][1]["nullable"] = True
    second = copy.deepcopy(first)
    second.update(id="second_target", table="second_table", category="silver",
                  storage_tables={"ClickHouse": "demo_ck.second_table"})
    second["fields"][1].pop("nullable")
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
    markdown = render_markdown(data, "flow.svg", "obsolete_catalog.svg")
    assert data["render_preferences"]["include_target_notes"] is False
    assert "AUDIT_ONLY" not in markdown
    assert "L2/I3" not in markdown and "| 层级 | L2 |" in markdown
    assert "warehouse_i3_daily_metric" in markdown and first["category"] == "L2/I3"
    assert target_layer({"category": "L4 / I7"}) == "L4"
    assert target_layer({"category": "silver"}) == "silver"
    assert target_layer({"category": "L2/I3", "layer": "bronze"}) == "bronze"
    assert target_layer({"table": "unconfirmed_l2_i3_table"}) == ""
    # Explicit nullability preserves false, true and unknown independently of type text.
    table_rows = [split_pipe_row(line) for line in target_logic_sections(data).splitlines()
                  if line.startswith("| ")]
    header = next(row for row in table_rows if row[0] == "字段名")
    nullable_index = header.index("允许空")
    field_rows = [row for row in table_rows if row[0] in {field["key"] for field in first["fields"]}]
    assert [row[nullable_index] for row in field_rows] == ["否", "是", "否", ""]
    # A requested narrative extension survives defaulting and remains audit-preserving.
    extended = copy.deepcopy(data)
    extended["render_preferences"]["include_target_notes"] = True
    apply_fixed_defaults(extended)
    assert "AUDIT_ONLY_TABLE_NARRATIVE" in target_logic_sections(extended)
    assert "AUDIT_ONLY_PROCESSING_NOTE" in target_logic_sections(extended)
    # Hidden target prose must not suppress an actual Pipeline step.
    mapped = copy.deepcopy(data)
    mapped["pipelines"][0]["steps"] = ["AUDIT_ONLY_TABLE_NARRATIVE"]
    assert "AUDIT_ONLY_TABLE_NARRATIVE" in render_markdown(mapped, "flow.svg")
    assert "obsolete_catalog.svg" not in markdown and "登记 Data Catalog" not in markdown
    assert "4.2.4 检查 Catalog Basic Info" in markdown
    assert "4.2.5 登记 Data Dictionary" in markdown and "4.2.6 登记 Data Storage" in markdown
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
    assert rendered["render_preferences"]["include_target_notes"] is False
    stored = next(target for target in rendered["targets"] if target["id"] == first["id"])
    assert stored["logic"] == first["logic"] and stored["processing_notes"] == first["processing_notes"]
    for suffix in ("md", "html"):
        text = (root / f"{title}.{suffix}").read_text(encoding="utf-8")
        assert "AUDIT_ONLY" not in text and "warehouse_i3_daily_metric" in text
    assert rendered["document"]["documentation"] == data["document"]["documentation"], "Audit evidence was erased"
    # Entering version management creates exactly one subsequent release.
    rendered["document"]["release_mode"] = "versioned"
    prepare_revision(rendered)
    assert rendered["document"]["release_history"][-1]["version"] == "0.0.2"
    prepare_revision(rendered)
    assert len(rendered["document"]["release_history"]) == 2
    return {"draft_pin": True, "storage_identities": True, "unique_field_logic_preserved": True,
            "catalog_reorder_and_missing_target": True, "three_format_bundle": True,
            "audit_notes_hidden_and_retained": True, "requested_notes_preserved": True,
            "layer_stage_separation": True, "nullable_true_false_unknown": True,
            "pipeline_steps_not_lost": True}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="report_document_policy_") as temporary:
        print(json.dumps(run_report_policy(Path(temporary)), ensure_ascii=False, indent=2))
