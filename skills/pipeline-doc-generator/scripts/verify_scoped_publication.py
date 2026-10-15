#!/usr/bin/env python3
"""Synthetic regressions for scoped presentation, task coverage and corrections."""
from __future__ import annotations

import copy
import argparse
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader

from pipeline_doc_common import blocking_questions, write_json
from render_pipeline_doc import document_stem
from verify_pipeline_doc_generator import facts, run, RENDER, VALIDATE


def sample(profile):
    data = facts(profile, "合成同步设计" if profile == "sync" else "合成报表设计")
    data["sources"][0]["filters"] = ["AUDITED_FILTER = 1"]
    field = data["sources"][0]["fields"][0]
    field.update(key="metric__goal", history="AUDITED_SOURCE_DIFFERENCE")
    field["source_refs"] = [{"document": "synthetic.xlsx", "sheet": "fields", "range": "B2"}]
    target = data["targets"][0]
    target["fields"][0].update(key="metric__goal", source_field="metric__goal", logic="同名源字段直接取值")
    target.update(rowkey="AUDITED_ROWKEY", write_mode="AUDITED_WRITE_SCOPE", logic=["AUDITED_TARGET_NOTE"])
    data["pipelines"][0].update(trigger="每日 06:00、18:00（UTC+8）", trigger_display="每日 06:00、18:00",
                                 trigger_display_for="每日 06:00、18:00（UTC+8）")
    data["render_preferences"].update(include_source_filters=False, include_field_history=False)
    data["document"]["release_mode"] = "initial_draft"
    return data


def bundle(root, profile):
    output = root / profile
    output.mkdir(parents=True, exist_ok=True)
    data = sample(profile)
    path = output / "facts.json"
    write_json(path, data)
    stem = document_stem(data["document"]["title"])

    def render():
        run(str(RENDER), "--facts", str(path), "--out-dir", str(output))
        run(str(VALIDATE), "--facts", str(path), "--profile", profile, "--markdown", str(output / f"{stem}.md"))
        return json.loads(path.read_text(encoding="utf-8"))

    def texts():
        return [(output / f"{stem}.md").read_text(encoding="utf-8"),
                (output / f"{stem}.html").read_text(encoding="utf-8"),
                "".join("".join(page.extract_text() for page in PdfReader(output / f"{stem}.pdf").pages).split())]

    saved = render()
    for text in texts():
        assert "AUDITED_FILTER" not in text and "AUDITED_SOURCE_DIFFERENCE" not in text
        assert "UTC+8" not in text and "06:00" in text and "18:00" in text
        assert "metric__goal" in text and "初始版本" in text
        if profile == "sync":
            assert "AUDITED_ROWKEY" not in text and "AUDITED_WRITE_SCOPE" not in text
    for key in ("sources", "targets", "pipelines"):
        assert saved[key] == data[key], f"Presentation changed canonical {key}"
    assert saved["render_preferences"]["include_target_notes"] is False

    # Re-running from persisted facts must preserve blank cells, not refill them.
    saved = render()
    assert len(saved["document"]["release_history"]) == 1
    assert saved["render_preferences"]["include_source_filters"] is False
    assert saved["render_preferences"]["include_field_history"] is False

    # Correct the canonical normalization input; keep stable identity/provenance.
    original_id = saved["sources"][0]["fields"][0]["id"]
    saved["sources"][0]["fields"][0]["key"] = "metric_goal"
    saved["targets"][0]["fields"][0].update(key="metric_goal", source_field="metric_goal")
    saved["field_corrections"] = [{"source_id": saved["sources"][0]["id"], "field_id": original_id,
                                  "original_key": "metric__goal", "key": "metric_goal",
                                  "source_refs": copy.deepcopy(saved["sources"][0]["fields"][0]["source_refs"])}]
    write_json(path, saved)
    saved = render()
    assert saved["sources"][0]["fields"][0]["id"] == original_id
    assert saved["field_corrections"][0]["original_key"] == "metric__goal"
    for text in texts():
        assert "metric_goal" in text and "metric__goal" not in text
    saved = render()
    assert saved["sources"][0]["fields"][0]["key"] == "metric_goal"

    # An explicit requested extension restores presentation without destroying audit.
    saved["render_preferences"].update(include_source_filters=True, include_field_history=True, include_target_notes=True)
    saved["pipelines"][0].pop("trigger_display")
    saved["pipelines"][0].pop("trigger_display_for")
    write_json(path, saved)
    render()
    for text in texts():
        assert "AUDITED_FILTER" in text and "UTC+8" in text
        if profile == "sync":
            assert "AUDITED_SOURCE_DIFFERENCE" in text and "AUDITED_ROWKEY" in text and "AUDITED_WRITE_SCOPE" in text
        else:
            assert "AUDITED_TARGET_NOTE" in text
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["document"]["release_mode"] = "versioned"
    saved["render_preferences"]["include_source_filters"] = False
    write_json(path, saved)
    saved = render()
    assert saved["document"]["release_history"][-1]["version"] == "0.0.2"
    assert render()["document"]["release_history"] == saved["document"]["release_history"]
    return {"profile": profile, "blank_preferences_persist": True, "audit_preserved": True,
            "correction_survives_regeneration": True, "extensions_restore_display": True}


def mapping(root):
    output = root / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    data = facts("sync", "合成同步概览")
    source, target, pipeline = [copy.deepcopy(data[key][0]) for key in ("sources", "targets", "pipelines")]
    data["sources"], data["targets"], data["pipelines"] = [], [], []
    for index in range(3):
        sid, tid, pid = f"source_{index}", f"target_{index}", f"sync_{index}"
        data["sources"].append(dict(copy.deepcopy(source), id=sid, location="MySQL", name=f"demo.source_{index}"))
        data["targets"].append(dict(copy.deepcopy(target), id=tid, table=f"demo_target_{index}"))
        data["targets"][-1]["fields"][0]["source"] = sid
        data["pipelines"].append(dict(copy.deepcopy(pipeline), id=pid, name=pid, task_name=f"load_{index}", sources=[sid], targets=[tid]))
    node = data["flow"]["nodes"][1]
    node.update(label="DataEngine Pipeline", pipeline_ids=[p["id"] for p in data["pipelines"]])
    data["flow"]["nodes"][0].update(label="MySQL", kind="database", identifiers=[s["name"] for s in data["sources"]])
    data["flow"]["nodes"][2].update(label="HBase", identifiers=[t["table"] for t in data["targets"]])
    data["flow"]["platforms"] = [{"id": "engine", "title": "DataEngine", "node_ids": [node["id"], data["flow"]["nodes"][2]["id"]]}]
    original = copy.deepcopy(data)
    assert not blocking_questions(data), blocking_questions(data)
    for ids, code in [(["sync_0"], "COVERAGE"), (["unknown", "sync_1", "sync_2"], "MAPPING"),
                      (["sync_0", "sync_0", "sync_1", "sync_2"], "MAPPING"), ([], "MAPPING"), ("sync_0", "MAPPING")]:
        broken = copy.deepcopy(data)
        broken["flow"]["nodes"][1]["pipeline_ids"] = ids
        assert any(q["id"].endswith(code) for q in blocking_questions(broken)), ids
    path = output / "facts.json"
    write_json(path, data)
    run(str(RENDER), "--facts", str(path), "--out-dir", str(output))
    stem = document_stem(data["document"]["title"])
    run(str(VALIDATE), "--facts", str(path), "--profile", "sync", "--markdown", str(output / f"{stem}.md"))
    saved = json.loads(path.read_text(encoding="utf-8"))
    for key in ("sources", "targets", "pipelines"):
        assert saved[key] == original[key], f"Graphical aggregation changed actual {key}"
    assert len([n for n in saved["flow"]["nodes"] if n["kind"] == "pipeline"]) == 1
    md = (output / f"{stem}.md").read_text(encoding="utf-8")
    for task in saved["pipelines"]:
        assert task["name"] in md and task["task_name"] in md
    return {"one_overview_node_three_actual_tasks": True, "full_mapping_retained": True, "invalid_mapping_rejected": True}


def run_scoped_publication(root):
    data = sample("sync")
    for bad_value in ("", "上游 05:00 就绪；每日 06:00 执行并重试"):
        broken = copy.deepcopy(data)
        broken["pipelines"][0]["trigger_display"] = bad_value
        assert any(q["id"].endswith("TRIGGER-LABEL") for q in blocking_questions(broken))
    data["pipelines"][0]["trigger"] = "每日 08:00（UTC+8）"
    assert any(q["id"].endswith("TRIGGER-LABEL-STALE") for q in blocking_questions(data))
    data = sample("sync")
    data["targets"][0]["write_mode"] = ""
    assert any(q["id"].endswith("WRITE_MODE") for q in blocking_questions(data))
    data = sample("sync")
    data["render_preferences"]["include_source_filters"] = "false"
    assert any("PRESENTATION" in q["id"] for q in blocking_questions(data))
    return {"bundles": [bundle(root, profile) for profile in ("sync", "report")],
            "overview": mapping(root), "stale_schedule_label_rejected": True, "hidden_contract_still_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pipeline_publication_") as temporary:
        print(json.dumps(run_scoped_publication(args.work_dir or Path(temporary)), ensure_ascii=False, indent=2))
