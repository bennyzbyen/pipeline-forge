#!/usr/bin/env python3
"""Shared facts, question, and Markdown helpers for pipeline-doc-generator."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from pipeline_doc_authoring import NAME_LABELS, normalize_authoring, pending_names


PENDING_VALUES = {"待定", "待确认", "tbd", "todo", "unknown", "未确认"}
FIXED_ENGINEER_ROLE = "数砚工程师"
OUTPUT_FORMATS = {
    "markdown": ("markdown",), "html": ("html",), "pdf": ("pdf",),
    "both": ("markdown", "html"),
    "markdown-pdf": ("markdown", "pdf"), "html-pdf": ("html", "pdf"),
    "all": ("markdown", "html", "pdf"),
}


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def apply_fixed_defaults(facts: dict[str, Any]) -> dict[str, Any]:
    document = facts.setdefault("document", {})
    team = document.setdefault("team", {})
    team["developer"] = FIXED_ENGINEER_ROLE
    team["operator"] = FIXED_ENGINEER_ROLE
    return normalize_authoring(facts)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or fallback


def md_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = "\n".join(str(item) for item in value)
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    rendered = ["| " + " | ".join(md_cell(item) for item in headers) + " |"]
    rendered.append("| " + " | ".join("---" for _ in headers) + " |")
    for raw_row in rows:
        row = list(raw_row)
        if len(row) < len(headers):
            row.extend([""] * (len(headers) - len(row)))
        rendered.append("| " + " | ".join(md_cell(item) for item in row[: len(headers)]) + " |")
    return "\n".join(rendered)


def bullet_lines(values: Iterable[Any], empty: str = "不适用（已确认）") -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    return "\n\n".join(f"- {item}" for item in items) if items else empty


def pointer_value(data: Any, pointer: str) -> Any:
    current = data
    for token in pointer.strip("/").split("/") if pointer.strip("/") else []:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current.get(token)
        else:
            return None
    return current


def is_ready(data: dict[str, Any], pointer: str) -> bool:
    value = pointer_value(data, pointer)
    if value is None or value == "" or value == [] or value == {}:
        return False
    if isinstance(value, str) and value.strip().lower() in PENDING_VALUES:
        return pointer in set(data.get("confirmed_pending_paths") or [])
    return True


def question(question_id: str, severity: str, prompt: str, *, path: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": question_id,
        "severity": severity,
        "question": prompt,
        "status": "open",
    }
    if path:
        row["path"] = path
    return row


def structural_questions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    required = [
        ("/profile", "PL-BLOCK-PROFILE", "请确认使用 sync（同步型）还是 report（报表加工型）模板。"),
        ("/document/title", "PL-BLOCK-TITLE", "请提供正式水线文档标题。"),
        ("/document/project_name", "PL-BLOCK-PROJECT", "请提供 DataEngine/DataHub Project Name。"),
        ("/document/description", "PL-BLOCK-DESCRIPTION", "请提供项目描述。"),
        ("/document/team/owner", "PL-BLOCK-OWNER", "请确认 Project Owner。"),
        ("/requirements/summary", "PL-BLOCK-OVERVIEW", "请补充可写入需求概述的项目目标和范围。"),
        ("/sources", "PL-BLOCK-SOURCES", "请补充数据源物理表/路径、范围、字段及过滤关联。"),
        ("/targets", "PL-BLOCK-TARGETS", "请补充目标存储、数据库、物理表、粒度和字段逻辑。"),
        ("/pipelines", "PL-BLOCK-PIPELINES", "请确认任务拆分、调度及输入输出映射；Data Utilization、Pipeline、Task 名称由技能拟定供确认。"),
        ("/resources/peak_memory", "PL-BLOCK-MEMORY", "请提供峰值内存评估，或明确确认写为待定。"),
        ("/resources/environment", "PL-BLOCK-ENVIRONMENT", "请提供资源环境，或明确确认写为待定。"),
        ("/flow/nodes", "PL-BLOCK-FLOW-NODES", "请补充数据流程图节点。"),
        ("/flow/edges", "PL-BLOCK-FLOW-EDGES", "请补充数据流程图连线。"),
    ]
    for path, question_id, prompt in required:
        if not is_ready(facts, path):
            result.append(question(question_id, "block", prompt, path=path))

    history = facts.get("document", {}).get("release_history") or []
    if history and not is_ready(facts, f"/document/release_history/{len(history)-1}/author"):
        result.append(question("PL-BLOCK-RELEASE-AUTHOR", "block", "请确认文档作者；版本和变更摘要由技能自动维护，无需填写。", path=f"/document/release_history/{len(history)-1}/author"))

    profile = facts.get("profile")
    if profile not in {"sync", "report"}:
        if not any(item["id"] == "PL-BLOCK-PROFILE" for item in result):
            result.append(question("PL-BLOCK-PROFILE", "block", "Profile 必须是 sync 或 report。", path="/profile"))
    if profile == "sync":
        for path, question_id, prompt in (
            ("/source_connections", "PL-BLOCK-CONNECTIONS", "请补充 Source 链接信息，或确认本项目不适用。"),
            ("/document/write_flow", "PL-BLOCK-WRITE-FLOW", "请补充目标写入顺序与落地方式。"),
            ("/document/sync_logic", "PL-BLOCK-SYNC-LOGIC", "请补充增量/全量、范围、覆盖、去重和重跑逻辑。"),
            ("/document/go_live", "PL-BLOCK-GO-LIVE", "请确认上线时间，或明确确认写为待定。"),
        ):
            if not is_ready(facts, path):
                result.append(question(question_id, "block", prompt, path=path))
        preferences = facts.get("render_preferences") or {}
        target_column_keys = ("include_target_category", "include_target_report_type", "include_target_range")
        if any(not isinstance(preferences.get(key), bool) for key in target_column_keys):
            result.append(question(
                "PL-BLOCK-TARGET-OPTIONAL-COLUMNS",
                "block",
                "请分别确认 Target 章节是否需要增加“所属类别”“报表类型”“数据范围”列；每项回答需要或不需要。",
                path="/render_preferences",
            ))
    if profile in {"sync", "report"} and pointer_value(facts, "/catalog/enabled") is None:
        result.append(question("PL-BLOCK-CATALOG", "block", "请确认是否登记 Data Catalog。", path="/catalog/enabled"))
    if profile in {"sync", "report"} and pointer_value(facts, "/catalog/enabled") is True and not is_ready(facts, "/catalog/basic_info"):
        result.append(question("PL-BLOCK-CATALOG-BASIC-INFO", "block", "请补充 Catalog Basic Info，至少提供数据项和 Title。", path="/catalog/basic_info"))

    result.extend(_item_questions(facts))
    result.extend(_reference_questions(facts))
    return _dedupe_questions(result)


def _item_questions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, source in enumerate(facts.get("sources") or []):
        prefix = f"/sources/{index}"
        for key, label in (("id", "稳定 ID"), ("location", "数据位置（例如 Blob、HBase、MySQL）"), ("name", "物理表或路径"), ("range", "取数范围")):
            if not is_ready(facts, f"{prefix}/{key}"):
                result.append(question(f"PL-BLOCK-SOURCE-{index + 1}-{key.upper()}", "block", f"数据源 {index + 1} 缺少{label}。", path=f"{prefix}/{key}"))
    for index, target in enumerate(facts.get("targets") or []):
        prefix = f"/targets/{index}"
        for key, label in (("id", "稳定 ID"), ("location", "目标存储"), ("table", "物理表名"), ("grain", "数据粒度"), ("schedule", "更新频率"), ("fields", "字段字典")):
            if not is_ready(facts, f"{prefix}/{key}"):
                result.append(question(f"PL-BLOCK-TARGET-{index + 1}-{key.upper()}", "block", f"目标表 {index + 1} 缺少{label}。", path=f"{prefix}/{key}"))
    for index, pipeline in enumerate(facts.get("pipelines") or []):
        prefix = f"/pipelines/{index}"
        proposed = pending_names(pipeline)
        if proposed:
            identity = re.sub(r"[^A-Z0-9]+", "-", str(pipeline.get("id") or index+1).upper()).strip("-")
            names = "；".join(f"{NAME_LABELS[key]}：{pipeline[key]}" for key in proposed)
            result.append(question(f"PL-BLOCK-PIPELINE-NAMES-{identity}", "block", f"建议采用以下名称：{names}。是否采用？不合适时再调整。", path=f"{prefix}/name_confirmation"))
        for key, label in (("id", "稳定 ID"), ("data_utilization", "Data Utilization"), ("name", "Pipeline Name"), ("task_name", "Task Name"), ("trigger", "触发时间"), ("sources", "输入 source IDs"), ("targets", "输出 target IDs")):
            if not is_ready(facts, f"{prefix}/{key}"):
                result.append(question(f"PL-BLOCK-PIPELINE-{index + 1}-{key.upper().replace('_', '-')}", "block", f"Pipeline {index + 1} 缺少{label}。", path=f"{prefix}/{key}"))
    return result


def _reference_questions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    source_ids = [str(item.get("id") or "") for item in facts.get("sources") or []]
    target_ids = [str(item.get("id") or "") for item in facts.get("targets") or []]
    pipeline_ids = [str(item.get("id") or "") for item in facts.get("pipelines") or []]
    for domain, ids in (("SOURCE", source_ids), ("TARGET", target_ids), ("PIPELINE", pipeline_ids)):
        duplicates = sorted({item for item in ids if item and ids.count(item) > 1})
        if duplicates:
            result.append(question(f"PL-BLOCK-DUPLICATE-{domain}-IDS", "block", f"{domain.lower()} IDs 重复：{', '.join(duplicates)}。"))
    known_sources, known_targets = set(source_ids), set(target_ids)
    for index, pipeline in enumerate(facts.get("pipelines") or []):
        unknown_sources = sorted(set(pipeline.get("sources") or []) - known_sources)
        unknown_targets = sorted(set(pipeline.get("targets") or []) - known_targets)
        if unknown_sources or unknown_targets:
            result.append(question("PL-BLOCK-PIPELINE-REFERENCES", "block", f"Pipeline {index + 1} 引用了未知 ID：sources={unknown_sources}, targets={unknown_targets}。"))
    node_ids = [str(item.get("id") or "") for item in (facts.get("flow") or {}).get("nodes") or []]
    known_nodes = set(node_ids)
    if len(node_ids) != len(known_nodes):
        result.append(question("PL-BLOCK-DUPLICATE-FLOW-IDS", "block", "流程图节点 ID 重复。"))
    for edge in (facts.get("flow") or {}).get("edges") or []:
        if edge.get("from") not in known_nodes or edge.get("to") not in known_nodes:
            result.append(question("PL-BLOCK-FLOW-REFERENCES", "block", f"流程图连线 {edge.get('id', '')} 引用了未知节点。"))
    return result


def effective_questions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    apply_fixed_defaults(facts)
    explicit = [copy.deepcopy(item) for item in facts.get("questions") or [] if item.get("status", "open") != "resolved"]
    for index, conflict in enumerate(facts.get("conflicts") or [], start=1):
        if conflict.get("status", "open") != "resolved":
            explicit.append(
                question(
                    conflict.get("id") or f"PL-CONF-CONFLICT-{index:03d}",
                    "confirmation",
                    conflict.get("question") or conflict.get("description") or "请确认冲突事实。",
                )
            )
    return _dedupe_questions(structural_questions(facts) + explicit)


def blocking_questions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in effective_questions(facts) if item.get("severity") == "block" and item.get("status", "open") != "resolved"]


def _dedupe_questions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        by_id.setdefault(str(item.get("id") or "PL-OPTION-UNKNOWN"), item)
    return list(by_id.values())


def write_questions(path: Path, facts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = effective_questions(facts)
    lines = ["# 水线文档待确认问题", ""]
    if not rows:
        lines.append("当前无未解决问题。")
    else:
        order = ("block", "confirmation", "optional")
        labels = {"block": "阻塞正式生成", "confirmation": "需要确认", "optional": "可选补充"}
        for severity in order:
            selected = [item for item in rows if item.get("severity") == severity]
            if not selected:
                continue
            lines.extend([f"## {labels[severity]}", ""])
            for item in selected:
                suffix = f"（路径：`{item['path']}`）" if item.get("path") else ""
                lines.append(f"- [{item['id']}] {item['question']}{suffix}")
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return rows


def new_facts(title: str = "") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "profile": "",
        "profile_suggestion": {"value": "", "confidence": "", "reason": ""},
        "document": {
            "title": title,
            "project_name": "",
            "description": "",
            "release_history": [],
            "team": {"owner": "", "developer": FIXED_ENGINEER_ROLE, "operator": FIXED_ENGINEER_ROLE},
            "documentation": "本文档",
            "write_flow": [],
            "sync_logic": [],
            "go_live": "",
        },
        "requirements": {"summary": [], "scope": []},
        "source_connections": [],
        "sources": [],
        "targets": [],
        "pipelines": [],
        "catalog": {"enabled": None, "basic_info": [], "dictionary": [], "storage": []},
        "resources": {"peak_memory": "", "environment": ""},
        "flow": {"title": "数据流程图", "description": "", "groups": [], "nodes": [], "edges": []},
        "documents": [],
        "questions": [],
        "conflicts": [],
        "confirmed_pending_paths": [],
        "render_preferences": {
            "last_format": "",
            "include_target_category": None,
            "include_target_report_type": None,
            "include_target_range": None,
        },
        "change_log": [],
    }


SYNC_HEADINGS = [
    "发布历史",
    "1. 数据写入流程与同步调整",
    "2. Source 数据源",
    "3. Target",
    "4. Pipeline",
    "5. 资源评估",
    "6. 上线时间",
]

REPORT_HEADINGS = [
    "发布历史",
    "1. 需求概述",
    "2. 数据源详情",
    "3. Data Target",
    "4. DataHub Pipeline",
    "5. 资源评估",
]


def expected_headings(profile: str) -> list[str]:
    if profile == "sync":
        return SYNC_HEADINGS
    if profile == "report":
        return REPORT_HEADINGS
    raise ValueError(f"unknown profile: {profile}")
