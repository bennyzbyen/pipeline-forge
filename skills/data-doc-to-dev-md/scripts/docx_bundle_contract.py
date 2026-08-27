#!/usr/bin/env python3
"""Build codegen questions and the machine-readable technical contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx_bundle_ooxml import Paragraph, SheetSummary
from technical_contract import build_contract_v2


def detect_project_type(facts: dict) -> str:
    if any(
        item.get("component_kind") == "bysku_report_pipeline" or item.get("handoff_to") == "report-codegen"
        for item in facts.get("component_hints", [])
    ):
        return "report"
    if facts.get("cot_report_tables"):
        return "data-sync"
    if (
        facts.get("report_sources")
        or facts.get("report_targets")
        or facts.get("report_clickhouse_targets")
        or facts.get("report_field_mappings")
    ):
        return "report"
    return "unknown"


def detect_component_kind(facts: dict, project_type: str) -> str:
    for hint in facts.get("component_hints", []):
        component_kind = str(hint.get("component_kind", "")).strip()
        if component_kind:
            return component_kind
    if project_type == "data-sync":
        return "cot_table_sync"
    if project_type == "report":
        return "standard_report"
    return "unclassified"


READINESS_QUESTION_IDS = {
    ("bysku_report_pipeline", "physical_targets"): "TC-CG-003",
    ("bysku_report_pipeline", "field_mapping_to_outputs"): "TC-CG-022",
    ("bysku_report_pipeline", "fs_and_sku_params"): "TC-CG-001",
    ("bysku_report_pipeline", "write_strategy"): "TC-CG-003",
}


def add_open_question(
    questions: list[dict[str, str]],
    question_id: str,
    category: str,
    text: str,
) -> None:
    """Add one semantic question while keeping its stable identifier unique."""
    if any(item.get("id") == question_id for item in questions):
        return
    questions.append(
        {
            "id": question_id,
            "category": category,
            "text": text,
            "status": "open",
        }
    )


def readiness_question_id(component_kind: str, check_name: str) -> str:
    """Return a stable ID for known and future readiness checks."""
    known = READINESS_QUESTION_IDS.get((component_kind, check_name))
    if known:
        return known
    semantic_key = f"{component_kind}:{check_name}".encode("utf-8")
    digest = hashlib.sha1(semantic_key).hexdigest()[:6].upper()
    return f"TC-CG-X{digest}"


def format_open_question(question: dict[str, str]) -> str:
    return f"[{question['id']}] {question['text']}"


def build_question_groups_v2(
    paragraphs: list[Paragraph],
    sheet_summaries: list[SheetSummary],
    facts: dict,
) -> dict[str, list[dict[str, str]]]:
    all_text = "\n".join(p.text for p in paragraphs).lower()
    physical_targets = facts.get("report_physical_targets") or facts.get("report_clickhouse_targets") or []
    target_storage = " ".join(str(item.get("storage", "")).lower() for item in physical_targets + facts.get("report_targets", []))
    has_clickhouse_target = bool(facts.get("report_clickhouse_targets")) or "clickhouse" in target_storage
    has_hbase_target = "hbase" in target_storage
    report_source_text = json.dumps(facts.get("report_sources", []), ensure_ascii=False).lower()
    has_fs_evidence = any(marker in all_text or marker in report_source_text for marker in ["gateway", "fs", "留痕", "文件目录"])
    component_kinds = {item.get("component_kind") for item in facts.get("component_hints", [])}
    blocking: list[dict[str, str]] = []
    deployment: list[dict[str, str]] = []
    non_blocking: list[dict[str, str]] = []
    add_open_question(deployment, "TC-DP-001", "deployment_confirmation", "生成代码时目标项目目录是哪一个？")
    add_open_question(
        deployment,
        "TC-DP-002",
        "deployment_confirmation",
        "配置文件中的 app_key/app_secret/token/IP 是否全部使用占位符？",
    )
    if "bysku_report_pipeline" in component_kinds:
        add_open_question(
            blocking,
            "TC-CG-001",
            "blocking_codegen",
            "bySKU 中间 FS 目录、文件压缩格式、文件覆盖策略需要确认。",
        )
        add_open_question(
            blocking,
            "TC-CG-002",
            "blocking_codegen",
            "SKU 参数来源需要确认：sku_map、sku_cal_range、sku_ttl_filter、sku_is_active 是来自 XML、params JSON 还是外部配置。",
        )
        add_open_question(
            blocking,
            "TC-CG-003",
            "blocking_codegen",
            "ClickHouse 物理表名与删除条件需要确认：明细/汇总/TTL 是否按 period/week 删除，历史保留是否按文档阈值滚动删除。",
        )
    if "bysku_report_pipeline" in component_kinds:
        pass
    elif facts.get("cot_report_tables"):
        add_open_question(
            blocking,
            "TC-CG-004",
            "blocking_codegen",
            "COT 每张表的 rowkey_rule_columns 是否有单独清单？如果没有，需要按字段字典确认。",
        )
        add_open_question(
            blocking,
            "TC-CG-005",
            "blocking_codegen",
            "COT with_period_tables / without_period_tables 是否按当前生产分类沿用，还是需要按新文档调整？",
        )
        add_open_question(
            blocking,
            "TC-CG-006",
            "blocking_codegen",
            "是否存在 ClickHouse 历史库名前缀、HBase truncate、ClickHouse truncate 等表级例外？",
        )
    elif facts.get("report_sources") or facts.get("report_targets") or facts.get("report_field_mappings"):
        if not physical_targets:
            add_open_question(blocking, "TC-CG-007", "blocking_codegen", "报表物理目标表未识别：需要确认 database.table / hbase table 与逻辑 Target Name 的对应关系。")
        elif not has_clickhouse_target and has_hbase_target:
            add_open_question(blocking, "TC-CG-008", "blocking_codegen", "HBase 目标表已识别：需要确认本项目是直接计算写入 HBase，还是先导出 FS 后触发下游 pipeline。")
        elif not has_clickhouse_target:
            add_open_question(blocking, "TC-CG-009", "blocking_codegen", "报表物理 ClickHouse 表名未识别：需要确认 database.table 与逻辑 Target Name 的对应关系。")
        if not facts.get("report_sources"):
            add_open_question(blocking, "TC-CG-010", "blocking_codegen", "报表数据源矩阵未识别：需要确认 HBase/FS/MSSQL 源表、取数范围和字段清单。")
        if not facts.get("report_field_mappings"):
            add_open_question(blocking, "TC-CG-011", "blocking_codegen", "报表字段逻辑表未识别：需要确认输出字段顺序、计算逻辑和汇总口径。")
        if has_clickhouse_target and "delete" not in all_text and "删除" not in all_text:
            add_open_question(blocking, "TC-CG-012", "blocking_codegen", "ClickHouse 写入前删除条件需要确认：按 period 删除、按 date 删除、还是 batch/status 模式。")
        if has_hbase_target:
            add_open_question(blocking, "TC-CG-013", "blocking_codegen", "HBase rowkey、写入模式、是否先删旧数据需要结合部署项目或下游 pipeline 确认。")
        if has_fs_evidence:
            add_open_question(blocking, "TC-CG-014", "blocking_codegen", "文档包含 Gateway/FS 留痕或数据准备：需要确认 FS 目录、文件名和失败时是否阻断主流程。")
    else:
        add_open_question(blocking, "TC-CG-015", "blocking_codegen", "项目类型最终确认：数据同步还是报表开发？")
    if (
        has_hbase_target
        or (facts.get("cot_report_tables") and "bysku_report_pipeline" not in component_kinds)
    ) and "rowkey" not in all_text:
        add_open_question(blocking, "TC-CG-016", "blocking_codegen", "HBase rowkey 规则未明确：需要确认 rowkey 拼接字段、时间字段格式、是否需要首位散列前缀。")
    if "rerun" not in all_text and "重跑" not in all_text:
        add_open_question(blocking, "TC-CG-017", "blocking_codegen", "重跑机制未明确：需要确认按 period、日期、时间戳还是全量重跑。")
    if "delete" not in all_text and "删除" not in all_text and not has_clickhouse_target:
        if has_hbase_target and not has_clickhouse_target:
            add_open_question(blocking, "TC-CG-018", "blocking_codegen", "HBase/FS prepare 项目的重跑覆盖策略未明确：需要确认 FS 文件是否覆盖、下游 HBase 是否先删旧数据。")
        else:
            add_open_question(blocking, "TC-CG-019", "blocking_codegen", "写入前删除策略未明确：需要确认 ClickHouse/HBase 是否先删旧数据。")
    if "调度" not in all_text and "定时" not in all_text and "频率" not in all_text:
        add_open_question(blocking, "TC-CG-020", "blocking_codegen", "调度频率未明确：需要确认每日、每 P、15 分钟或手动触发。")
    if not sheet_summaries:
        add_open_question(blocking, "TC-CG-021", "blocking_codegen", "未提取到嵌入 Excel 表：需要确认字段字典是否在截图、外部 Excel 或其他文档中。")

    for readiness in facts.get("handoff_readiness", []):
        if readiness.get("ready_for_full_codegen", False):
            continue
        component_kind = str(readiness.get("component_kind", "unclassified"))
        for check in readiness.get("checks", []):
            if check.get("status") not in {"blocked", "needs_confirmation"}:
                continue
            detail = str(check.get("detail", "")).strip()
            if not detail:
                continue
            add_open_question(
                blocking,
                readiness_question_id(component_kind, str(check.get("name", "unnamed"))),
                "blocking_codegen",
                detail,
            )

    return {
        "blocking_codegen": blocking,
        "deployment_confirmation": deployment,
        "non_blocking": non_blocking,
    }


def build_codegen_contract(facts: dict, question_groups: dict[str, list[dict[str, str]]]) -> dict:
    project_type = detect_project_type(facts)
    component_kind = detect_component_kind(facts, project_type)
    open_questions = [
        question
        for category in ("blocking_codegen", "deployment_confirmation", "non_blocking")
        for question in question_groups.get(category, [])
    ]
    blockers = [format_open_question(question) for question in question_groups.get("blocking_codegen", [])]

    components: list[dict] = []
    for hint in facts.get("component_hints", []):
        for component in hint.get("components", []):
            components.append(
                {
                    "name": component.get("name", ""),
                    "kind": component.get("kind") or component.get("name", ""),
                    "role": component.get("role", ""),
                    "status": "blocked" if blockers else "confirmed",
                }
            )
    if not components:
        default_name = "cot_sync" if project_type == "data-sync" else ("report_pipeline" if project_type == "report" else "unclassified")
        components.append(
            {
                "name": default_name,
                "kind": component_kind,
                "role": "Primary code generation unit derived from the confirmed design package.",
                "status": "blocked" if blockers else "confirmed",
            }
        )

    blockers = list(dict.fromkeys(blockers))
    ready_for_codegen = project_type != "unknown" and not blockers
    base_contract = {
        "contract_version": 1,
        "design_document": "technical_design.md",
        "facts_document": "structured_facts.json",
        "questions_document": "questions.md",
        "project_type": project_type,
        "component_kind": component_kind,
        "components": components,
        "open_questions": open_questions,
        "ready_for_codegen": ready_for_codegen,
        "blockers": blockers,
    }
    contract = build_contract_v2(facts, base_contract)
    for question in contract.get("open_questions", []):
        category = str(question.get("category", ""))
        if category not in question_groups:
            continue
        add_open_question(
            question_groups[category],
            str(question.get("id", "")),
            category,
            str(question.get("text", "")),
        )
    return contract


def write_questions_v2(path: Path, question_groups: dict[str, list[dict[str, str]]]) -> None:
    headings = [
        ("Blocking Code Generation", "blocking_codegen"),
        ("Deployment Confirmation", "deployment_confirmation"),
        ("Non-Blocking", "non_blocking"),
    ]
    lines = ["# Open Questions", ""]
    for heading, key in headings:
        lines.extend([f"## {heading}", ""])
        questions = question_groups.get(key, [])
        if questions:
            lines.extend(f"- {format_open_question(question)}" for question in questions)
        else:
            lines.append("- None.")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
