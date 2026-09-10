#!/usr/bin/env python3
"""Offline regression for automatic revisions, proposed names, and PL questions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

from pipeline_doc_authoring import checkpoint_revision, next_version, pending_names, prepare_revision
from pipeline_doc_common import apply_fixed_defaults, effective_questions, blocking_questions, write_questions
from verify_pipeline_doc_generator import facts, run, RENDER, VALIDATE


def test_initial_and_migration(root):
    data = facts("sync", "合成自动维护")
    data["document"]["release_history"] = []
    data["questions"] = [
        {"id": "WL-BLOCK-RELEASE", "severity": "block", "question": "请提供版本、摘要、作者、日期", "status": "open"},
        {"id": "WL-CONF-KEEP", "severity": "confirmation", "question": "资料冲突", "status": "resolved", "answer": "保留 WL- 原始证据文字", "source_refs": [{"document": "synthetic.md"}]},
        {"id": "WL-OPTION-NOTE", "severity": "optional", "question": "补充说明", "status": "open"},
    ]
    data["conflicts"] = [{"id": "WL-CONF-SCHEDULE", "description": "调度时间不一致", "status": "open"}]
    apply_fixed_defaults(data)
    row = data["document"]["release_history"][0]
    assert row["version"] == "0.0.1" and row["summary"] == "初始版本" and row["date"]
    questions = effective_questions(data)
    assert all(q["id"].startswith("PL-") for q in questions)
    assert not any(q["id"] == "PL-BLOCK-RELEASE-AUTHOR" for q in questions)
    assert row["author"] == "张本彦"
    assert data["document"]["release_mode"] == "initial_draft"
    assert not any(q["id"] == "PL-BLOCK-RELEASE" for q in questions)
    assert data["questions"][1]["answer"] == "保留 WL- 原始证据文字"
    assert data["questions"][1]["status"] == "resolved" and data["questions"][1]["source_refs"]
    assert data["conflicts"][0]["id"] == "PL-CONF-SCHEDULE"
    data["document"]["author"] = "Tester"
    apply_fixed_defaults(data)
    assert not any(q["id"] == "PL-BLOCK-RELEASE-AUTHOR" for q in effective_questions(data))
    write_questions(root / "questions.md", data)
    assert "[WL-" not in (root / "questions.md").read_text(encoding="utf-8")
    return {"initial_metadata_automatic": True, "standing_author_default": True, "legacy_ids_migrated": True, "answers_preserved": True}


def test_names(root):
    data = facts("sync", "合成命名确认")
    for key in ("data_utilization", "name", "task_name"):
        data["pipelines"][0][key] = ""
    second = copy.deepcopy(data["pipelines"][0])
    second["id"] = "pipeline_second"
    data["pipelines"].append(second)
    original_sources = copy.deepcopy(data["sources"])
    apply_fixed_defaults(data)
    for pipeline in data["pipelines"]:
        assert len(pending_names(pipeline)) == 3
    assert data["pipelines"][0]["name"] != data["pipelines"][1]["name"]
    first_names = [(p["data_utilization"], p["name"], p["task_name"]) for p in data["pipelines"]]
    apply_fixed_defaults(data)
    assert first_names == [(p["data_utilization"], p["name"], p["task_name"]) for p in data["pipelines"]]
    assert data["sources"] == original_sources
    path = root / "facts.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run(str(RENDER), "--facts", str(path), "--out-dir", str(root), "--format", "both", expected=2)
    assert not list(root.glob("*.html"))
    prompts = (root / "questions.md").read_text(encoding="utf-8")
    assert all(name in prompts for name in first_names[0])
    for pipeline in data["pipelines"]:
        pipeline["name_confirmation"]["confirmed_values"] = {key: pipeline[key] for key in pending_names(pipeline)}
    assert not blocking_questions(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run(str(RENDER), "--facts", str(path), "--out-dir", str(root), "--format", "both")
    data = json.loads(path.read_text(encoding="utf-8"))
    title = data["document"]["title"]
    run(str(VALIDATE), "--facts", str(path), "--profile", "sync", "--markdown", str(root/f"{title}.md"), "--html", str(root/f"{title}.html"))
    accepted_version = data["document"]["release_history"][-1]["version"]
    run(str(RENDER), "--facts", str(path), "--out-dir", str(root), "--format", "html")
    assert json.loads(path.read_text(encoding="utf-8"))["document"]["release_history"][-1]["version"] == accepted_version
    data["pipelines"][0]["name"] += "_revised"
    assert pending_names(data["pipelines"][0]) == ["name"]
    assert any("PIPELINE-NAMES" in q["id"] for q in blocking_questions(data))
    return {"candidates_generated": True, "unique_pipeline_names": True, "acceptance_required": True, "accepted_names_stable": True, "changed_proposal_reconfirmed": True}


def test_versions():
    data = apply_fixed_defaults(facts("report", "合成自动版本"))
    prepare_revision(data)  # Legacy history is preserved, then checkpointed.
    assert len(data["document"]["release_history"]) == 1
    checkpoint_revision(data)
    original = copy.deepcopy(data["document"]["release_history"])
    data["render_preferences"].update(last_format="html-pdf", pdf_orientation="landscape")
    data["sources"][0]["source_refs"].append({"document": "another.md"})
    prepare_revision(data)
    assert data["document"]["release_history"] == original
    data["pipelines"][0]["trigger"] = "每天 09:00"
    data["change_log"].append({"summary": "将同步任务触发时间调整为每天 09:00", "source": "user_confirmation"})
    prepare_revision(data)
    assert data["document"]["release_history"][-1]["version"] == "0.0.2"
    assert data["document"]["release_history"][-1]["summary"] == data["change_log"][-1]["summary"]
    prepare_revision(data)  # Retry before success must not duplicate this row.
    assert len(data["document"]["release_history"]) == 2
    checkpoint_revision(data)
    prepare_revision(data)
    assert len(data["document"]["release_history"]) == 2
    data["targets"][0]["fields"][0]["logic"] = "调整后的字段规则"
    prepare_revision(data)
    assert data["document"]["release_history"][-1]["version"] == "0.0.3"
    assert "目标表" in data["document"]["release_history"][-1]["summary"]
    assert "09:00" not in data["document"]["release_history"][-1]["summary"]
    checkpoint_revision(data)
    data["targets"][0]["table"] = "user_selected_target"
    data["document"]["release_history"].append({"version": "1.0.0", "summary": "用户调整后的摘要", "author": "Tester", "date": "2026/09/02"})
    prepare_revision(data)
    assert len(data["document"]["release_history"]) == 4
    assert data["document"]["release_history"][-1]["summary"] == "用户调整后的摘要"
    assert next_version("v1.2.9") == "v1.2.10" and next_version("R09") == "R10"
    pending = apply_fixed_defaults(facts("sync", "合成已确认待定作者"))
    pending["document"]["release_history"][0]["author"] = "待定"
    pending["confirmed_pending_paths"] = ["/document/release_history/0/author"]
    checkpoint_revision(pending)
    pending["document"]["description"] = "更新说明"
    prepare_revision(pending)
    assert not blocking_questions(pending), blocking_questions(pending)
    return {"content_edits_versioned": True, "format_rerender_no_bump": True, "retry_idempotent": True, "new_summary_only": True, "manual_override_preserved": True}


def run_authoring_regressions(root):
    root.mkdir(parents=True, exist_ok=True)
    naming_root = root / "naming"
    naming_root.mkdir(exist_ok=True)
    return {"initial_and_migration": test_initial_and_migration(root), "naming": test_names(naming_root), "revisions": test_versions()}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="pipeline_authoring_") as temporary:
        print(json.dumps({"status": "ok", **run_authoring_regressions(Path(temporary))}, ensure_ascii=False, indent=2))
