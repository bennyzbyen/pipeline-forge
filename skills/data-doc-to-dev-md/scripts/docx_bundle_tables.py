#!/usr/bin/env python3
"""Normalize extracted CSV tables and preserve evidence provenance."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from docx_bundle_ooxml import SheetSummary, compact_text


def cell_value(row: dict[str, str], *names: str) -> str:
    normalized_names = {normalize_header(name) for name in names}
    for name in names:
        if name in row:
            return compact_text(str(row.get(name, "")))
    for key, value in row.items():
        if normalize_header(key) in normalized_names:
            return compact_text(str(value or ""))
    return ""


def cell_value_contains(row: dict[str, str], *patterns: str) -> str:
    for key, value in row.items():
        if all(pattern in key for pattern in patterns):
            return compact_text(str(value or ""))
    return ""


def normalize_header(value: str) -> str:
    return re.sub(r"[\s_　]+", "", str(value or "")).lower()


def has_header(headers: list[str], *names: str) -> bool:
    normalized_headers = {normalize_header(header) for header in headers}
    return any(normalize_header(name) in normalized_headers for name in names)


def split_cell_lines(value: str) -> list[str]:
    parts = re.split(r"[\r\n]+", str(value or ""))
    return [compact_text(part) for part in parts if compact_text(part)]


def split_field_names(value: str) -> list[str]:
    parts = split_cell_lines(value)
    if len(parts) == 1:
        tokens = [item.strip() for item in re.split(r"\s+", parts[0]) if item.strip()]
        if len(tokens) > 1 and all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token) for token in tokens):
            return tokens
    return parts


def split_table_names(value: str) -> list[str]:
    names: list[str] = []
    for part in split_cell_lines(value):
        matches = re.findall(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+|/[^\s,，;；]+", part)
        candidates = matches or [part]
        for candidate in candidates:
            normalized = compact_text(candidate)
            if normalized and normalized not in names:
                names.append(normalized)
    return names


def read_csv_rows(path: Path) -> list[list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [list(row) for row in csv.reader(handle)]
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [list(row) for row in csv.reader(handle)]


def make_unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, header in enumerate(headers):
        value = compact_text(str(header or "")) or f"__blank_{index + 1}"
        count = seen.get(value, 0)
        seen[value] = count + 1
        result.append(value if count == 0 else f"{value}_{count + 1}")
    return result


def header_score(row: list[str]) -> int:
    normalized = {normalize_header(value) for value in row if compact_text(str(value or ""))}
    if not normalized:
        return 0
    if normalize_header("字段key") in normalized and (
        normalize_header("字段名称") in normalized or normalize_header("字段名") in normalized
    ):
        return 100
    if normalize_header("Key") in normalized and normalize_header("字段名称") in normalized:
        return 100
    if (
        normalize_header("位置") in normalized
        and normalize_header("数据库") in normalized
        and normalize_header("数据表名") in normalized
        and normalize_header("数据表") in normalized
    ):
        return 95
    if (
        normalize_header("位置") in normalized
        and normalize_header("数据表名") in normalized
        and normalize_header("数据表") in normalized
        and (normalize_header("取数范围") in normalized or normalize_header("数据范围") in normalized)
    ):
        return 92
    if (
        normalize_header("Data Utilization Name") in normalized
        and normalize_header("Target Name") in normalized
        and normalize_header("Data Storage") in normalized
    ):
        return 90
    if normalize_header("Data Utilization Name") in normalized and (
        normalize_header("task1 name") in normalized
        or normalize_header("Pipeline Name") in normalized
        or normalize_header("Pipline_Name") in normalized
    ):
        return 90
    if (
        normalize_header("异常类型") in normalized
        and normalize_header("判断规则") in normalized
        and normalize_header("产出数据表") in normalized
    ):
        return 88
    if (
        (normalize_header("KPI 名称") in normalized or normalize_header("KPI名称") in normalized)
        and normalize_header("数据来源底表") in normalized
        and normalize_header("汇总逻辑") in normalized
    ):
        return 86
    if (
        normalize_header("汇总列") in normalized
        and normalize_header("数据来源底表") in normalized
        and normalize_header("汇总逻辑") in normalized
    ):
        return 84
    if normalize_header("Name") in normalized and normalize_header("Description") in normalized:
        return 70
    if (
        normalize_header("Description") in normalized
        and normalize_header("Data Storage") in normalized
        and normalize_header("Database") in normalized
        and normalize_header("Table Name") in normalized
    ):
        return 80
    if (
        normalize_header("序号") in normalized
        and normalize_header("业务描述") in normalized
        and normalize_header("hbase 表") in normalized
    ):
        return 80
    return 0


def detect_header_index(rows: list[list[str]], scan_rows: int = 15) -> int:
    best_index = 0
    best_score = header_score(rows[0]) if rows else 0
    for index, row in enumerate(rows[:scan_rows]):
        score = header_score(row)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def read_csv_table(path: Path) -> tuple[list[str], list[dict[str, str]], list[list[str]]]:
    raw_rows = read_csv_rows(path)
    if not raw_rows:
        return [], [], []
    header_index = detect_header_index(raw_rows)
    headers = make_unique_headers(raw_rows[header_index])
    width = len(headers)
    dict_rows: list[dict[str, str]] = []
    for row in raw_rows[header_index + 1 :]:
        values = row + [""] * (width - len(row))
        values = values[:width]
        if not any(compact_text(str(value or "")) for value in values):
            continue
        dict_rows.append(dict(zip(headers, values)))
    return headers, dict_rows, raw_rows[:header_index]


def read_csv_dicts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    headers, rows, _preamble = read_csv_table(path)
    return headers, rows


def has_headers(headers: list[str], required: list[str]) -> bool:
    return all(has_header(headers, name) for name in required)


def provenance_from_summary(summary: SheetSummary) -> dict[str, str | int]:
    provenance: dict[str, str | int] = {
        "source_doc_index": summary.source_doc_index,
        "source_doc_name": summary.source_doc_name,
        "source_csv": summary.csv_path.name,
        "source_sheet": summary.sheet_name,
        "source_kind": summary.source,
    }
    if summary.context_text:
        provenance["source_context"] = summary.context_text
    return provenance


def add_provenance(row: dict, summary: SheetSummary) -> dict:
    row.update(provenance_from_summary(summary))
    return row


def preamble_text(preamble: list[list[str]]) -> str:
    parts: list[str] = []
    for row in preamble:
        for cell in row:
            value = compact_text(str(cell or ""))
            if value:
                parts.append(value)
    return "\n".join(parts)


def table_name_from_text(text: str) -> str:
    match = re.search(r"数据表[：:]\s*([A-Za-z0-9_.]+)", text)
    return match.group(1) if match else ""


def normalized_table_key(value: str) -> str:
    value = compact_text(str(value or "")).lower()
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    if value.startswith("clickhouse_"):
        value = value[len("clickhouse_") :]
    return value


def append_unique_by_key(items: list[dict], item: dict, key: str) -> None:
    value = item.get(key, "")
    if value and any(existing.get(key) == value for existing in items):
        return
    items.append(item)


def best_context_match(context: str, names: list[str]) -> str:
    if not context:
        return ""
    best_name = ""
    best_position = -1
    context_lower = context.lower()
    for name in names:
        if not name:
            continue
        position = context_lower.rfind(name.lower())
        if position > best_position:
            best_name = name
            best_position = position
    return best_name


def first_fields(rows: list[dict[str, str]], limit: int = 12) -> list[str]:
    values: list[str] = []
    for row in rows:
        field = cell_value(row, "Key", "字段 key", "字段key", "字段名称", "字段", "Column", "Field")
        if field and field not in values:
            values.append(field)
        if len(values) >= limit:
            break
    return values
