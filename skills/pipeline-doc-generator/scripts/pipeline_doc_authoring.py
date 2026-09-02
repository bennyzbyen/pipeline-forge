#!/usr/bin/env python3
"""Automatic release metadata and confirmable naming for canonical pipeline facts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date


NAME_FIELDS = ("data_utilization", "name", "task_name")
NAME_LABELS = {"data_utilization": "Data Utilization", "name": "Pipeline", "task_name": "Task"}
CHANGE_LABELS = {
    "document": "更新项目基本信息、写入说明或上线安排",
    "requirements": "更新需求目标与范围",
    "source_connections": "更新数据源连接信息",
    "sources": "更新数据源、字段及取数规则",
    "targets": "更新目标表及字段逻辑",
    "pipelines": "调整 Pipeline、Task 或调度配置",
    "catalog": "更新 Catalog 登记信息",
    "resources": "更新资源评估",
    "flow": "调整数据流程图",
    "target_columns": "调整 Target 展示列",
    "profile": "调整文档模板类型",
}


def normalize_question_ids(facts):
    """Migrate identifiers only; do not rewrite requirement prose or user answers."""
    for collection in ("questions", "conflicts"):
        for item in facts.get(collection) or []:
            identifier = item.get("id", "")
            if isinstance(identifier, str) and identifier.startswith("WL-"):
                item["id"] = "PL-" + identifier[3:]


def next_version(value):
    """Increment the last numeric component, preserving an existing version style."""
    value = str(value or "").strip()
    if not value:
        return "0.0.1"
    match = re.fullmatch(r"(.*?)(\d+)", value)
    return match[1]+str(int(match[2])+1).zfill(len(match[2])) if match else value+".1"


def normalize_name(value, fallback):
    result = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    if not result:
        result = fallback
    return ("p_"+result) if result[0].isdigit() else result


def propose_names(facts):
    """Supply deterministic candidates for missing names; never replace known ones."""
    project = normalize_name(facts.get("document", {}).get("project_name"), "pipeline")
    action = "sync" if facts.get("profile") == "sync" else "build"
    targets = {item.get("id"): item for item in facts.get("targets") or []}
    pipelines = facts.get("pipelines") or []
    used = {key: {str(p.get(key)) for p in pipelines if p.get(key)} for key in ("name", "task_name")}
    for index, pipeline in enumerate(pipelines, 1):
        target = next((targets[key] for key in pipeline.get("targets") or [] if key in targets), {})
        entity = normalize_name(target.get("table") or pipeline.get("id"), f"task_{index}")
        candidates = {"data_utilization": project, "name": f"{project}_{action}_{entity}", "task_name": f"{action}_{entity}"}
        for key, candidate in candidates.items():
            if str(pipeline.get(key) or "").strip().lower() not in {"", "待定", "待确认", "tbd", "todo", "unknown"}:
                continue
            if key in used:
                base, suffix = candidate, 2
                while candidate in used[key]:
                    candidate = f"{base}_{suffix}"; suffix += 1
                used[key].add(candidate)
            pipeline[key] = candidate
            confirmation = pipeline.setdefault("name_confirmation", {})
            proposed = confirmation.setdefault("proposed_fields", [])
            if key not in proposed:
                proposed.append(key)
            confirmation.setdefault("confirmed_values", {})


def pending_names(pipeline):
    confirmation = pipeline.get("name_confirmation") or {}
    confirmed = confirmation.get("confirmed_values") or {}
    return [key for key in confirmation.get("proposed_fields") or [] if key in NAME_FIELDS and confirmed.get(key) != pipeline.get(key)]


def normalize_authoring(facts):
    normalize_question_ids(facts)
    document = facts.setdefault("document", {})
    history = document.setdefault("release_history", [])
    if not history:
        history.append({"version": "0.0.1", "summary": "初始版本", "author": document.get("author", ""), "date": date.today().strftime("%Y/%m/%d")})
    else:
        # Fill missing metadata without overwriting existing release records.
        latest = history[-1]
        if not latest.get("version"):
            latest["version"] = next_version(history[-2].get("version") if len(history)>1 else "")
        if not latest.get("summary"):
            updates = facts.get("change_log") or []
            latest["summary"] = "初始版本" if len(history) == 1 else (updates[-1].get("summary") if updates else "") or "更新水线文档"
        if not latest.get("date"):
            latest["date"] = date.today().strftime("%Y/%m/%d")
        if not latest.get("author") and document.get("author"):
            latest["author"] = document["author"]
    propose_names(facts)
    # Supersede old blank-form prompts. Actual missing author information and
    # candidate acceptance are checked separately; no other blocker is resolved.
    for item in facts.get("questions") or []:
        identifier = item.get("id", "")
        legacy_naming = re.fullmatch(r"PL-BLOCK-PIPELINE-(\d+)-(DATA-UTILIZATION|NAME|TASK-NAME)", identifier)
        if identifier == "PL-BLOCK-RELEASE" or legacy_naming:
            item["status"] = "resolved"
            item.setdefault("answer", "由技能自动维护版本摘要并拟定名称；作者及名称采用情况单独确认。")
    return facts


def semantic_hashes(facts):
    """Store hashes only, keeping facts as the sole content source."""
    ignored = {"source_refs", "name_confirmation", "release_history", "revision_state"}
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in ignored}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    values = {key: facts.get(key) for key in CHANGE_LABELS if key != "target_columns"}
    values["target_columns"] = {key: value for key, value in (facts.get("render_preferences") or {}).items() if key.startswith("include_target_")}
    return {key: hashlib.sha256(json.dumps(clean(value), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest() for key, value in values.items()}


def prepare_revision(facts):
    """Append one revision per real edit, not per renderer attempt or format."""
    state = facts.get("revision_state") or {}
    previous = state.get("content_hashes")
    current = semantic_hashes(facts)
    if not previous or current == previous:
        return
    history = facts["document"]["release_history"]
    if history[-1].get("version") != state.get("version"):
        return  # The assistant/user already recorded this revision, or a render was retried.
    changed = [key for key in CHANGE_LABELS if current.get(key) != previous.get(key)]
    updates = (facts.get("change_log") or [])[state.get("change_log_count", 0):]
    summaries = [str(item.get("summary", "")).strip() for item in updates if item.get("summary")]
    summary = "；".join(dict.fromkeys(summaries)) if summaries else "；".join(CHANGE_LABELS[key] for key in changed)
    history.append({"version": next_version(history[-1]["version"]), "summary": summary,
                    "author": facts["document"].get("author") or history[-1].get("author", ""),
                    "date": date.today().strftime("%Y/%m/%d")})
    previous_author_path = f"/document/release_history/{len(history)-2}/author"
    if previous_author_path in (facts.get("confirmed_pending_paths") or []) and history[-1]["author"] == history[-2]["author"]:
        facts["confirmed_pending_paths"].append(f"/document/release_history/{len(history)-1}/author")


def checkpoint_revision(facts):
    """Call only after all requested outputs have been written successfully."""
    facts["revision_state"] = {"version": facts["document"]["release_history"][-1]["version"],
                               "content_hashes": semantic_hashes(facts),
                               "change_log_count": len(facts.get("change_log") or [])}
