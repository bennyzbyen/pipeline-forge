#!/usr/bin/env python3
"""Analyze DataEngine/DataHub job logs and render a diagnosis skeleton."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


PATTERNS = [
    {
        "id": "wrapped_single_params",
        "category": "params",
        "severity": "high",
        "patterns": [
            r"KeyError:\s*['\"]source_informations['\"]",
            r"source_informations.*required",
            r"body.*params",
            r"algorithm_io_mode.*SINGLE",
        ],
        "root_cause": "DataEngine SINGLE 包装参数没有被正确拆包，或 body.params 没有被 JSON 解析成业务参数。",
        "impact": "任务在入口层失败，通常不会写 HBase/ClickHouse，也不会安全更新时间戳。",
        "fix": "检查 plugin_main.py 的参数读取逻辑，确认 algorithm_io_mode == SINGLE 时解析 params.body.params；同时核对运行参数是否包含 source_informations/hbase_informations/clickhouse_information。",
        "verify": "日志中应出现完整业务 params，并能打印 mysql_table、hbase_table、clickhouse_table。",
    },
    {
        "id": "missing_runtime_param",
        "category": "params",
        "severity": "high",
        "patterns": [
            r"KeyError:\s*['\"](period_column|rowkey_rule_columns|hbase_table|clickhouse_table|receiver_emails|mysql_table)['\"]",
            r"ValueError:.*(required|is required)",
        ],
        "root_cause": "运行参数缺失必填字段，或生成代码没有从表配置补齐默认参数。",
        "impact": "任务在参数初始化或目标写入前失败；一般不会写入目标表。",
        "fix": "补齐 params JSON，或让入口从 table_configs 按 mysql_table 补齐 period_column、rowkey_rule_columns、目标表等默认值。",
        "verify": "重跑前打印 params，确认缺失字段已存在且表名与任务一致。",
    },
    {
        "id": "no_changed_data",
        "category": "data_absence",
        "severity": "medium",
        "patterns": [
            r"无更新数据",
            r"no_changed_rows",
            r"no_changed_periods",
            r"Source table returns zero rows",
            r"未查询到数据",
            r"empty DataFrame",
        ],
        "root_cause": "本次 period/date/timestamp 范围没有检测到源数据变化，优先按上游数据缺失或时间戳条件过窄判断。",
        "impact": "通常不会写目标表；若代码把无数据当异常，会触发告警但不一定是代码缺陷。",
        "fix": "先核对运行参数里的 period/current_date/last_timestamp，再查源表在该范围内是否有记录；不要直接重刷全量，除非确认重跑策略不会重复或误删。",
        "verify": "在日志中确认 last_timestamp、period/date、源 SQL 和返回行数。",
    },
    {
        "id": "rowkey_missing_column",
        "category": "hbase",
        "severity": "high",
        "patterns": [
            r"KeyError:\s*['\"](rowkey|period|code|store_code|id|inksaa_id|salesman_code)['\"]",
            r"usecols do not match columns",
            r"rowkey.*(empty|missing|重复|duplicate)",
        ],
        "root_cause": "HBase rowkey 依赖字段不存在、字段名与源文件不一致，或 rowkey 拼接后为空/重复。",
        "impact": "HBase 写入失败；如果 ClickHouse 已先写入，可能出现 CK 成功但 HBase 失败的不一致状态。",
        "fix": "核对字段字典、导出 CSV header、rowkey_rule_columns 三者是否一致；必要时修正表级 rowkey 例外。",
        "verify": "日志或本地导出文件 header 中应包含 rowkey_rule_columns 的所有字段，插入前 rowkey 非空且数量与源行数一致。",
    },
    {
        "id": "clickhouse_table_or_cluster",
        "category": "clickhouse",
        "severity": "high",
        "patterns": [
            r"UNKNOWN_TABLE",
            r"Unknown table",
            r"Table .* doesn't exist",
            r"ON CLUSTER",
            r"DROP PARTITION",
            r"TRUNCATE TABLE",
            r"Mutation.*is still running",
        ],
        "root_cause": "ClickHouse 目标表、库名前缀、集群配置或 mutation 状态不匹配。",
        "impact": "ClickHouse 写入或删除失败；如果 HBase 已写入，需要确认是否产生部分成功。",
        "fix": "核对 clickhouse_table 是否使用裸表名、历史库是否由配置例外处理、PROD cluster 是否正确；mutation 未完成时先查 mutation 状态再决定是否重跑。",
        "verify": "日志中删除/插入 SQL 的库名、表名、cluster 和 period/key 条件应与目标一致。",
    },
    {
        "id": "gateway_client_failure",
        "category": "gateway",
        "severity": "high",
        "patterns": [
            r"Gateway(?:Client)?(?:Error|Timeout|Unavailable)",
            r"gateway\s+(?:request|invoke|authentication)\s+failed",
            r"failed\s+to\s+(?:create|get)\s+gateway\s+client",
        ],
        "root_cause": "Gateway 客户端创建、认证或请求失败，平台代理层尚未建立可用连接。",
        "impact": "任务通常停在平台客户端初始化或请求阶段；下游 HBase/FS 与 ClickHouse 写入状态需要由阶段日志确认。",
        "fix": "核对 running_env、Gateway 配置键和平台侧授权状态，先用同环境的最小健康检查确认 Gateway 可用，不要据此改写业务逻辑。",
        "verify": "日志应出现 Gateway 客户端创建成功及具体下游请求开始记录，且不再出现认证、超时或不可用错误。",
    },
    {
        "id": "hbase_operation_failure",
        "category": "hbase",
        "severity": "high",
        "patterns": [
            r"HBase(?:Client)?(?:Error|Timeout|Unavailable)",
            r"hbase\s+(?:query|scan|insert|delete|truncate)\s+failed",
            r"getHbaseClient.*(?:failed|error|timeout)",
        ],
        "root_cause": "HBase 客户端或具体读写操作失败，需要结合表名、rowkey 范围和最后成功阶段确认是访问问题还是请求契约问题。",
        "impact": "HBase 读取或写入未完成；如果 ClickHouse 写入已经发生，可能形成部分成功状态。",
        "fix": "核对 HBase 表名、rowkey/range 请求、running_env 与平台授权，并先确认是否已有目标写入后再决定重跑。",
        "verify": "日志应显示 HBase 请求范围、目标表、返回/写入行数与成功结束阶段。",
    },
    {
        "id": "fs_operation_failure",
        "category": "fs",
        "severity": "high",
        "patterns": [
            r"FS(?:Client)?(?:Error|Timeout|Unavailable)",
            r"fs\s+(?:upload|download|copy|exists|delete)\s+failed",
            r"getFsClient.*(?:failed|error|timeout)",
            r"(?:file_path|hdfs_path)\s+.+\s+not\s+exist",
        ],
        "root_cause": "FS 客户端、文件路径或文件传输操作失败，输入/中间文件没有按预期到达下一阶段。",
        "impact": "依赖该文件的 HBase/ClickHouse 导入或下游流水线不会获得完整输入。",
        "fix": "核对运行环境、文件路径、上一步文件生成结果和 FS 权限；确认文件存在及大小后再恢复后续阶段。",
        "verify": "日志应显示 FS exists/copy/upload 成功、最终路径和非零文件大小。",
    },
    {
        "id": "hbase_gateway_fs",
        "category": "gateway_hbase_fs",
        "severity": "high",
        "patterns": [
            r"Gateway",
            r"getHbaseClient",
            r"getFsClient",
            r"hbase.*(insert|truncate|delete|query).*failed",
            r"fs operate",
            r"file_path .* not exist",
            r"hdfs .* not exists",
            r"Permission denied",
            r"403|401",
        ],
        "root_cause": "Gateway/HBase/FS 访问、路径、权限或文件状态异常。",
        "impact": "通常影响 HBase/FS 写入、timestamp 读取或结果文件上传；ClickHouse 是否已写入需看前置日志。",
        "fix": "先确认 app_key/app_secret、running_env、FS 路径、HBase 表名和上传文件是否存在；不要先改业务代码。",
        "verify": "日志中应能看到 FS exists/copy、HBase insert/truncate/delete 的成功记录和目标路径。",
    },
    {
        "id": "dependency_or_import",
        "category": "environment",
        "severity": "high",
        "patterns": [
            r"ModuleNotFoundError",
            r"ImportError",
            r"No module named",
            r"cannot import name",
            r"SyntaxError",
        ],
        "root_cause": "部署环境缺少依赖、模块路径不一致，或 Python 版本与代码语法不兼容。",
        "impact": "任务在启动或模块加载阶段失败，不会进入业务处理。",
        "fix": "核对打包目录、相对 import、部署镜像依赖和 Python 版本；不要修改业务逻辑前先排除环境问题。",
        "verify": "在同版本 Python 下执行 `python -m py_compile`，部署包内应包含报错模块路径。",
    },
    {
        "id": "encoding_or_csv",
        "category": "path_encoding",
        "severity": "medium",
        "patterns": [
            r"UnicodeDecodeError",
            r"UnicodeEncodeError",
            r"ParserError",
            r"Error tokenizing data",
            r"Expected .* fields",
            r"\\x1D",
            r"compression",
        ],
        "root_cause": "CSV 编码、分隔符、压缩格式或字段数量不一致。",
        "impact": "数据读取或 HBase/ClickHouse 文件插入失败；可能只影响部分文件。",
        "fix": "核对 read_csv 编码、sep、compression、header，以及写入文件是否被上一步正确生成。",
        "verify": "抽查失败文件首行/header、分隔符和压缩格式，确认与读写代码一致。",
    },
    {
        "id": "business_logic",
        "category": "business_logic",
        "severity": "medium",
        "patterns": [
            r"MergeError",
            r"cannot convert",
            r"could not convert",
            r"division by zero",
            r"KeyError",
            r"ValueError",
            r"dropna",
            r"inner join",
        ],
        "root_cause": "可能是字段映射、类型转换、关联键或业务过滤逻辑导致的数据处理错误。",
        "impact": "可能影响报表结果完整性或任务失败；需要结合最后一个成功阶段判断写入范围。",
        "fix": "先定位失败字段、输入表和中间 DataFrame 行数，再做最小修正；不要大范围重写流程。",
        "verify": "在失败步骤前后打印字段列表、行数、空值数和 join 命中率。",
    },
]


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_lines(text: str) -> List[str]:
    return [line.rstrip("\n") for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def tail_nonempty(lines: List[str], limit: int = 30) -> List[str]:
    values = [line for line in lines if line.strip()]
    return values[-limit:]


def extract_traceback(lines: List[str]) -> Dict[str, Any]:
    tracebacks: List[List[str]] = []
    current: Optional[List[str]] = None
    for line in lines:
        if "Traceback (most recent call last)" in line:
            if current:
                tracebacks.append(current)
            current = [line]
            continue
        if current is not None:
            if line.strip() == "" and current:
                tracebacks.append(current)
                current = None
            else:
                current.append(line)
    if current:
        tracebacks.append(current)

    last = tracebacks[-1] if tracebacks else []
    exception_line = ""
    for line in reversed(last or lines):
        if re.search(r"(Error|Exception|KeyError|ValueError|RuntimeError|BaseException|FileNotFoundError|PermissionError|TimeoutError):", line):
            exception_line = line.strip()
            break
    return {"traceback_count": len(tracebacks), "last_traceback": last, "exception_line": exception_line}


def find_key_lines(lines: List[str]) -> List[str]:
    keywords = [
        "params",
        "running env",
        "获取数据同步场景",
        "同步场景",
        "无更新数据",
        "execute sql",
        "mysql",
        "clickhouse",
        "hbase",
        "rowkey",
        "truncate",
        "DROP PARTITION",
        "DELETE FROM",
        "insert",
        "ERROR",
        "Exception",
        "Traceback",
    ]
    selected: List[str] = []
    for line in lines:
        if any(keyword.lower() in line.lower() for keyword in keywords):
            stripped = line.strip()
            if stripped and stripped not in selected:
                selected.append(stripped)
    return selected[-40:]


def score_patterns(text: str) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for item in PATTERNS:
        matched = []
        for pattern in item["patterns"]:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(pattern)
        if matched:
            score = len(matched)
            hits.append({**item, "matched_patterns": matched, "score": score})
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(hits, key=lambda value: (severity_rank.get(value["severity"], 9), -value["score"]))


def analyze_log(text: str) -> Dict[str, Any]:
    lines = normalize_lines(text)
    traceback_info = extract_traceback(lines)
    hits = score_patterns(text)
    primary = hits[0] if hits else None
    competing = []
    if primary:
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        primary_rank = severity_rank.get(primary["severity"], 9)
        competing = [
            item["id"]
            for item in hits[1:]
            if severity_rank.get(item["severity"], 9) == primary_rank and item["score"] == primary["score"]
        ]
    if not text.strip():
        confidence = "low"
        confidence_reason = "日志为空，没有可用于分类的失败证据。"
    elif primary is None:
        confidence = "low"
        confidence_reason = "日志虽包含异常，但没有匹配到已知失败模式。"
    elif traceback_info["traceback_count"] == 0 or not traceback_info["exception_line"]:
        confidence = "low"
        confidence_reason = "日志没有完整 traceback/异常终行，可能已被截断。"
    elif competing:
        confidence = "low"
        confidence_reason = "存在同优先级、同分值的竞争错误模式，当前分类仅是确定性首选假设。"
    else:
        confidence = "high"
        confidence_reason = "完整 traceback 与唯一最高优先级错误模式一致。"
    return {
        "primary_classification": primary["category"] if primary else "unknown",
        "primary_pattern_id": primary["id"] if primary else "unknown",
        "confirmed_issue": primary["root_cause"] if primary else "日志中没有匹配到明确失败模式，需要补充完整 traceback、参数和失败前后 50 行日志。",
        "impact_scope": primary["impact"] if primary else "影响范围未确认。",
        "minimum_fix": primary["fix"] if primary else "先补齐完整日志，再按参数、路径/环境、数据缺失、外部服务、业务代码顺序排查。",
        "verification": primary["verify"] if primary else "确认日志包含参数、环境、源 SQL、目标写入和完整异常。",
        "diagnosis_status": "confirmed" if confidence == "high" else "hypothesis",
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "competing_pattern_ids": competing,
        "matched_patterns": [
            {
                "id": item["id"],
                "category": item["category"],
                "severity": item["severity"],
                "score": item["score"],
                "matched_patterns": item["matched_patterns"],
            }
            for item in hits[:5]
        ],
        "first_real_exception": traceback_info["exception_line"],
        "traceback_count": traceback_info["traceback_count"],
        "key_log_lines": find_key_lines(lines),
        "tail": tail_nonempty(lines),
        "uncertain_points": build_uncertainty(text, primary),
    }


def build_uncertainty(text: str, primary: Optional[Dict[str, Any]]) -> List[str]:
    missing = []
    lowered = text.lower()
    if "params" not in lowered and "source_informations" not in lowered:
        missing.append("日志中没有看到完整运行参数，无法确认表名、period/date、rowkey 和目标表是否正确。")
    if "running env" not in lowered and "env" not in lowered:
        missing.append("日志中没有明确运行环境，无法确认 UAT/PROD cluster、密钥和库名前缀。")
    if "traceback" not in lowered and primary and primary["severity"] == "high":
        missing.append("缺少完整 traceback，只能基于错误关键词做高置信假设。")
    if not re.search(r"(mysql|clickhouse|hbase|fs|gateway)", lowered):
        missing.append("日志中没有外部系统阶段信息，无法判断失败发生在数据源还是写入端。")
    return missing


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Data Job Log Diagnosis",
        "",
        "## Confirmed Issue" if result["diagnosis_status"] == "confirmed" else "## Highest-confidence Hypothesis",
        f"- {result['confirmed_issue']}",
        f"- Confidence: `{result['confidence']}` — {result['confidence_reason']}",
        "",
        "## Impact Scope",
        f"- {result['impact_scope']}",
        "",
        "## Minimum Fix",
        f"- {result['minimum_fix']}",
        "",
        "## Verification",
        f"- {result['verification']}",
        "",
        "## Evidence",
        f"- Primary classification: `{result['primary_classification']}` / `{result['primary_pattern_id']}`",
        f"- First real exception: `{result['first_real_exception'] or 'not found'}`",
        f"- Traceback count: {result['traceback_count']}",
    ]
    if result["competing_pattern_ids"]:
        lines.append("- Competing patterns: " + ", ".join(f"`{item}`" for item in result["competing_pattern_ids"]))
    if result["matched_patterns"]:
        lines.append("- Matched patterns:")
        for item in result["matched_patterns"]:
            lines.append(f"  - `{item['id']}` ({item['category']}, {item['severity']}, score={item['score']})")
    lines.extend(["", "## Key Log Lines"])
    if result["key_log_lines"]:
        lines.extend(f"- {line}" for line in result["key_log_lines"][-12:])
    else:
        lines.append("- No key log lines detected.")
    lines.extend(["", "## Uncertain Points"])
    if result["uncertain_points"]:
        lines.extend(f"- {item}" for item in result["uncertain_points"])
    else:
        lines.append("- No major missing context detected from the text log.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True, help="UTF-8 text log file.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        text = load_text(args.log)
    except OSError as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        print(f"error: log could not be read: {detail}", file=sys.stderr)
        return 2
    if not text.strip():
        print("error: log is empty; provide failure context before diagnosis", file=sys.stderr)
        return 2
    result = analyze_log(text)
    if args.format == "json":
        output = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        output = render_markdown(result)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
