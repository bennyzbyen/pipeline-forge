#!/usr/bin/env python3
"""Extract DataEngine PRD/DOCX content and embedded Excel tables.

This script intentionally uses only the Python standard library so it can run
in restricted Windows environments without installing python-docx or openpyxl.
It reads .docx/.xlsx files as ZIP packages and extracts enough structure for
implementation-ready data development documentation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def qn(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def safe_name(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", value).strip(" ._")
    value = re.sub(r"\s+", "_", value)
    return value[:80] or fallback


def read_zip_text(zip_file: zipfile.ZipFile, name: str) -> str | None:
    try:
        with zip_file.open(name) as handle:
            return handle.read().decode("utf-8")
    except KeyError:
        return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def target_basename(target: str) -> str:
    return target.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass
class Paragraph:
    style: str
    text: str
    source_doc_index: int = 1
    source_doc_name: str = ""


@dataclass
class SheetSummary:
    workbook_name: str
    sheet_name: str
    dimension: str
    csv_path: Path
    row_count: int
    headers: list[str]
    source: str = "embedded"
    source_doc_index: int = 1
    source_doc_name: str = ""
    context_text: str = ""


def extract_docx_paragraphs(docx_path: Path) -> tuple[list[Paragraph], int, list[str]]:
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            raise ValueError(f"{docx_path} does not contain word/document.xml")
        root = ET.fromstring(document_xml)

        paragraphs: list[Paragraph] = []
        for paragraph in root.iter(qn(NS_W, "p")):
            texts = [node.text or "" for node in paragraph.iter(qn(NS_W, "t"))]
            text = compact_text("".join(texts))
            if not text:
                continue
            style = ""
            p_style = paragraph.find(f"./{qn(NS_W, 'pPr')}/{qn(NS_W, 'pStyle')}")
            if p_style is not None:
                style = p_style.attrib.get(qn(NS_W, "val"), "")
            paragraphs.append(Paragraph(style=style, text=text))

        table_count = sum(1 for _ in root.iter(qn(NS_W, "tbl")))
        embedded = [
            entry.filename
            for entry in docx.infolist()
            if entry.filename.startswith("word/embeddings/")
            and entry.filename.lower().endswith(".xlsx")
        ]
        return paragraphs, table_count, embedded


def read_document_relationships(docx: zipfile.ZipFile) -> dict[str, str]:
    text = read_zip_text(docx, "word/_rels/document.xml.rels")
    if not text:
        return {}
    root = ET.fromstring(text)
    rels: dict[str, str] = {}
    for rel in root:
        if local_name(rel.tag) == "Relationship":
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rel_id and target:
                rels[rel_id] = target
    return rels


def element_text(element: ET.Element) -> str:
    return compact_text("".join(node.text or "" for node in element.iter(qn(NS_W, "t"))))


def embedding_rel_ids(element: ET.Element, rels: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for node in element.iter():
        for key, value in node.attrib.items():
            if not (key == "r:id" or key.endswith("}id")):
                continue
            target = rels.get(value, "")
            if "embeddings/" in target.replace("\\", "/") and target.lower().endswith(".xlsx"):
                ids.append(value)
    return ids


def extract_embedding_contexts(docx_path: Path, window: int = 4) -> dict[str, str]:
    contexts: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            return contexts
        rels = read_document_relationships(docx)
        if not rels:
            return contexts
        root = ET.fromstring(document_xml)
        body = root.find(qn(NS_W, "body"))
        if body is None:
            return contexts
        recent_texts: list[str] = []
        for element in list(body):
            current_text = element_text(element)
            ids = embedding_rel_ids(element, rels)
            for rel_id in ids:
                workbook_name = target_basename(rels[rel_id])
                context_parts = recent_texts[-window:]
                if current_text:
                    context_parts = context_parts + [current_text]
                contexts[workbook_name] = "\n".join(context_parts)
            if current_text:
                recent_texts.append(current_text)
    return contexts


def col_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref.upper())
    if not letters:
        return 0
    value = 0
    for char in letters.group(1):
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def read_shared_strings(xlsx: zipfile.ZipFile) -> list[str]:
    text = read_zip_text(xlsx, "xl/sharedStrings.xml")
    if not text:
        return []
    root = ET.fromstring(text)
    values: list[str] = []
    for si in root.iter(qn(NS_X, "si")):
        parts = [node.text or "" for node in si.iter(qn(NS_X, "t"))]
        values.append("".join(parts))
    return values


def read_workbook_relationships(xlsx: zipfile.ZipFile) -> dict[str, str]:
    text = read_zip_text(xlsx, "xl/_rels/workbook.xml.rels")
    if not text:
        return {}
    root = ET.fromstring(text)
    rels: dict[str, str] = {}
    for rel in root:
        if local_name(rel.tag) == "Relationship":
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rel_id and target:
                rels[rel_id] = target
    return rels


def sheet_target_path(target: str) -> str:
    target = target.replace("\\", "/")
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(qn(NS_X, "t")))

    value_node = cell.find(qn(NS_X, "v"))
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def iter_sheet_rows(
    sheet_root: ET.Element,
    shared_strings: list[str],
    max_rows: int,
) -> Iterable[list[str]]:
    emitted = 0
    for row in sheet_root.iter(qn(NS_X, "row")):
        if max_rows and emitted >= max_rows:
            break
        values_by_col: dict[int, str] = {}
        max_col = -1
        for cell in row.findall(qn(NS_X, "c")):
            ref = cell.attrib.get("r", "")
            idx = col_index(ref)
            max_col = max(max_col, idx)
            values_by_col[idx] = cell_text(cell, shared_strings)
        if max_col < 0:
            continue
        values = [values_by_col.get(i, "") for i in range(max_col + 1)]
        if any(str(value).strip() for value in values):
            emitted += 1
            yield values


def extract_xlsx_tables(
    workbook_name: str,
    workbook_bytes: bytes,
    tables_dir: Path,
    workbook_index: int,
    max_rows: int,
) -> list[SheetSummary]:
    summaries: list[SheetSummary] = []
    with zipfile.ZipFile(io_bytes(workbook_bytes)) as xlsx:
        workbook_xml = read_zip_text(xlsx, "xl/workbook.xml")
        if not workbook_xml:
            return summaries
        shared_strings = read_shared_strings(xlsx)
        rels = read_workbook_relationships(xlsx)
        workbook_root = ET.fromstring(workbook_xml)

        sheet_index = 0
        for sheet in workbook_root.iter(qn(NS_X, "sheet")):
            sheet_index += 1
            sheet_name = sheet.attrib.get("name", f"sheet{sheet_index}")
            rel_id = sheet.attrib.get(qn(NS_REL, "id"), "")
            target = rels.get(rel_id)
            if not target:
                continue

            sheet_xml = read_zip_text(xlsx, sheet_target_path(target))
            if not sheet_xml:
                continue
            sheet_root = ET.fromstring(sheet_xml)
            dimension_node = sheet_root.find(qn(NS_X, "dimension"))
            dimension = dimension_node.attrib.get("ref", "") if dimension_node is not None else ""
            rows = list(iter_sheet_rows(sheet_root, shared_strings, max_rows=max_rows))
            if not rows:
                continue

            csv_name = (
                f"embedding_{workbook_index:03d}_sheet_{sheet_index:03d}_"
                f"{safe_name(sheet_name, 'sheet')}.csv"
            )
            csv_path = tables_dir / csv_name
            with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerows(rows)

            headers = [compact_text(str(value)) for value in rows[0]][:12]
            summaries.append(
                SheetSummary(
                    workbook_name=workbook_name,
                    sheet_name=sheet_name,
                    dimension=dimension,
                    csv_path=csv_path,
                    row_count=len(rows),
                    headers=headers,
                )
            )
    return summaries


class io_bytes:
    """Small file-like adapter around bytes for zipfile.ZipFile."""

    def __init__(self, data: bytes):
        import io

        self._buffer = io.BytesIO(data)

    def read(self, *args):
        return self._buffer.read(*args)

    def seek(self, *args):
        return self._buffer.seek(*args)

    def tell(self):
        return self._buffer.tell()

    def seekable(self):
        return True

    def close(self):
        self._buffer.close()


def extract_embedded_tables(docx_path: Path, tables_dir: Path, max_rows: int) -> list[SheetSummary]:
    tables_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[SheetSummary] = []
    contexts = extract_embedding_contexts(docx_path)
    with zipfile.ZipFile(docx_path) as docx:
        entries = [
            entry
            for entry in docx.infolist()
            if entry.filename.startswith("word/embeddings/")
            and entry.filename.lower().endswith(".xlsx")
        ]
        for index, entry in enumerate(entries, start=1):
            workbook_bytes = docx.read(entry.filename)
            workbook_name = Path(entry.filename).name
            extracted = extract_xlsx_tables(
                workbook_name=workbook_name,
                workbook_bytes=workbook_bytes,
                tables_dir=tables_dir,
                workbook_index=index,
                max_rows=max_rows,
            )
            for summary in extracted:
                summary.context_text = contexts.get(workbook_name, "")
            summaries.extend(extracted)
    return summaries


def word_cell_text(cell: ET.Element) -> str:
    parts: list[str] = []
    for paragraph in cell.findall(f".//{qn(NS_W, 'p')}"):
        text = compact_text("".join(node.text or "" for node in paragraph.iter(qn(NS_W, "t"))))
        if text:
            parts.append(text)
    return "\n".join(parts)


def extract_word_tables(docx_path: Path, tables_dir: Path, max_rows: int) -> list[SheetSummary]:
    tables_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[SheetSummary] = []
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            return summaries
        root = ET.fromstring(document_xml)
        for table_index, table in enumerate(root.iter(qn(NS_W, "tbl")), start=1):
            rows: list[list[str]] = []
            for row in table.findall(qn(NS_W, "tr")):
                if max_rows and len(rows) >= max_rows:
                    break
                values = [word_cell_text(cell) for cell in row.findall(qn(NS_W, "tc"))]
                if any(value.strip() for value in values):
                    rows.append(values)
            if not rows:
                continue

            header_index = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if any("字段key" in cell or "字段名" in cell for cell in row)
                ),
                0,
            )
            if header_index > 0:
                rows = rows[header_index:]

            max_width = max(len(row) for row in rows)
            rows = [row + [""] * (max_width - len(row)) for row in rows]
            csv_name = f"word_table_{table_index:03d}.csv"
            csv_path = tables_dir / csv_name
            with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerows(rows)
            summaries.append(
                SheetSummary(
                    workbook_name="word/document.xml",
                    sheet_name=f"word_table_{table_index:03d}",
                    dimension=f"{len(rows)}x{max_width}",
                    csv_path=csv_path,
                    row_count=len(rows),
                    headers=[compact_text(str(value)) for value in rows[0]][:12],
                    source="word",
                )
            )
    return summaries


def paragraphs_matching(paragraphs: list[Paragraph], keywords: list[str], limit: int = 12) -> list[str]:
    matches: list[str] = []
    lowered = [(p.text.lower(), p.text) for p in paragraphs]
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for lower_text, text in lowered:
            if keyword_lower in lower_text and text not in matches:
                matches.append(text)
                if len(matches) >= limit:
                    return matches
    return matches


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- 待从原始文档或人工补充材料确认\n"
    return "".join(f"- {item}\n" for item in items)


def write_extracted_markdown(
    path: Path,
    docx_path: Path,
    paragraphs: list[Paragraph],
    table_count: int,
    sheet_summaries: list[SheetSummary],
) -> None:
    title = paragraphs[0].text if paragraphs else docx_path.stem
    lines = [
        f"# {title}",
        "",
        f"- Source DOCX: `{docx_path}`",
        f"- Paragraphs: {len(paragraphs)}",
        f"- Word tables: {table_count}",
        f"- Embedded extracted sheets: {len(sheet_summaries)}",
        "",
        "## Extracted Tables",
        "",
    ]
    if not sheet_summaries:
        lines.append("- No embedded Excel or Word tables extracted.")
    else:
        for summary in sheet_summaries:
            rel_path = summary.csv_path.as_posix()
            headers = " | ".join(summary.headers)
            lines.append(
                f"- `{rel_path}`: source `{summary.source}`, workbook `{summary.workbook_name}`, "
                f"sheet `{summary.sheet_name}`, dimension `{summary.dimension}`, "
                f"rows `{summary.row_count}`, headers `{headers}`"
            )

    lines.extend(["", "## Paragraphs", ""])
    for idx, paragraph in enumerate(paragraphs, start=1):
        prefix = f"{idx:04d}"
        style = f" [{paragraph.style}]" if paragraph.style else ""
        lines.append(f"- {prefix}{style} {paragraph.text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def report_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    if not paragraphs:
        return []
    targets: list[dict] = []
    seen: set[str] = set()
    texts = [compact_text(paragraph.text) for paragraph in paragraphs if compact_text(paragraph.text)]
    for index, text in enumerate(texts):
        if "clickhouse" not in text.lower():
            continue
        if index + 1 >= len(texts):
            continue
        table = texts[index + 1]
        if "." not in table or " " in table:
            continue
        description = texts[index + 2] if index + 2 < len(texts) else ""
        if table in seen:
            continue
        seen.add(table)
        targets.append(
            {
                "storage": text,
                "table": table,
                "database": table.split(".", 1)[0],
                "table_name": table.split(".", 1)[1],
                "description": description,
            }
        )
    return targets


def hbase_targets_from_paragraphs(paragraphs: list[Paragraph] | None) -> list[dict]:
    if not paragraphs:
        return []
    targets: list[dict] = []
    seen: set[str] = set()
    texts = [compact_text(paragraph.text) for paragraph in paragraphs if compact_text(paragraph.text)]
    in_target_section = False
    for index, text in enumerate(texts):
        lower_text = text.lower()
        if "data target" in lower_text or "target management" in lower_text:
            in_target_section = True
        if in_target_section and ("datahub pipeline" in lower_text or "data pipeline management" in lower_text):
            in_target_section = False
        if not in_target_section and "hbase:" not in lower_text:
            continue
        if "hbase" not in lower_text:
            continue

        window = " ".join(texts[index : index + 4])
        matches = re.findall(r"(?:[A-Za-z0-9_]+\.)+[A-Za-z0-9_]+", window)
        for table in matches:
            if not re.search(r"[A-Za-z_]", table):
                continue
            if table.startswith("l0_") or table in seen:
                continue
            seen.add(table)
            description = ""
            for candidate in texts[index : index + 5]:
                if candidate != table and table not in candidate and "hbase" not in candidate.lower():
                    description = candidate
                    break
            targets.append(
                {
                    "storage": "hbase",
                    "database": table.split(".", 1)[0],
                    "table_name": table.split(".", 1)[1],
                    "table": table,
                    "description": description,
                }
            )
    return targets


def report_field_rows(rows: list[dict[str, str]]) -> list[dict]:
    fields: list[dict] = []
    for row in rows:
        key = cell_value(row, "Key", "字段 key", "字段key", "字段", "Column", "Field")
        field_name = cell_value(row, "字段名称", "字段名")
        if not key and not field_name:
            continue
        formula = (
            cell_value(row, "计算逻辑", "报表字段逻辑", "字段逻辑", "字段公式", "数据源+字段公式", "数据源 + 字段公式")
            or cell_value_contains(row, "字段公式")
            or cell_value_contains(row, "数据源", "公式")
            or cell_value_contains(row, "报表字段", "逻辑")
        )
        fields.append(
            {
                "target_field": key,
                "field_name": field_name,
                "source_category": cell_value(row, "数据源分类"),
                "source_desc": cell_value(row, "数据源描述", "来源库表", "数据源"),
                "source_storage": cell_value(row, "数据源位置", "存放地"),
                "source_table": cell_value(row, "数据表", "数据源表", "源数据表"),
                "source_field": cell_value(row, "数据源对应的字段", "数据源字段key", "数据源字段 key", "来源字段"),
                "calculation_logic": formula,
                "eo_order_logic": cell_value_contains(row, "EO+ERP"),
                "dms_order_logic": cell_value_contains(row, "DMS"),
                "sample": cell_value(row, "字段样例", "示例", "数据样例"),
                "field_type": cell_value(row, "字段类型", "Type"),
                "field_order": cell_value(row, "字段顺序"),
                "display": cell_value(row, "字段是否显示"),
                "remark": cell_value(row, "备注", "变更记录", "更新记录"),
            }
        )
    return fields


def build_structured_facts(sheet_summaries: list[SheetSummary], paragraphs: list[Paragraph] | None = None) -> dict:
    clickhouse_targets = report_targets_from_paragraphs(paragraphs)
    hbase_targets = hbase_targets_from_paragraphs(paragraphs)
    facts = {
        "documents": [],
        "merge_policy": "",
        "conflicts": [],
        "cot_report_tables": [],
        "data_utilizations": [],
        "target_mappings": [],
        "schedules": [],
        "field_dictionaries": [],
        "report_sources": [],
        "report_targets": [],
        "report_physical_targets": clickhouse_targets + hbase_targets,
        "report_clickhouse_targets": clickhouse_targets,
        "report_schedules": [],
        "report_field_mappings": [],
        "report_business_rules": [],
        "report_kpi_rules": [],
        "component_hints": [],
        "handoff_readiness": [],
        "inferences": [],
    }
    field_dicts: list[dict] = []
    report_field_dicts: list[dict] = []

    for summary in sheet_summaries:
        headers, rows, preamble = read_csv_table(summary.csv_path)
        if not headers or not rows:
            continue
        declared_table = table_name_from_text(preamble_text(preamble))

        if has_headers(headers, ["序号", "业务描述", "hbase 表", "Hbase数据范围", "clickhouse表"]):
            for row in rows:
                source_table = cell_value(row, "hbase 表")
                clickhouse_table = cell_value(row, "clickhouse表")
                if not source_table and not clickhouse_table:
                    continue
                facts["cot_report_tables"].append(
                    add_provenance(
                        {
                        "seq": cell_value(row, "序号"),
                        "category": cell_value(row, "所属类别"),
                        "report_type": cell_value(row, "报表类型"),
                        "business_desc": cell_value(row, "业务描述"),
                        "source_hbase_table": source_table,
                        "source_range": cell_value(row, "Hbase数据范围"),
                        "clickhouse_table": clickhouse_table,
                        },
                        summary,
                    )
                )
            continue

        if has_headers(headers, ["Description", "Data Storage", "Database", "Table Name"]):
            for row in rows:
                table_name = cell_value(row, "Table Name")
                database = cell_value(row, "Database")
                if not table_name:
                    continue
                table = f"{database}.{table_name}" if database else table_name
                if any(target.get("table") == table for target in facts["report_clickhouse_targets"]):
                    continue
                target = add_provenance(
                    {
                        "storage": cell_value(row, "Data Storage"),
                        "database": database,
                        "table_name": table_name,
                        "table": table,
                        "description": cell_value(row, "Description"),
                    },
                    summary,
                )
                facts["report_clickhouse_targets"].append(target)
                append_unique_by_key(facts["report_physical_targets"], dict(target), "table")
            continue

        if has_headers(headers, ["位置", "数据库", "数据表名", "数据表"]):
            current_storage = ""
            current_database = ""
            for row in rows:
                storage = cell_value(row, "位置") or current_storage
                database = cell_value(row, "数据库") or current_database
                description = cell_value(row, "数据表名")
                table_name = cell_value(row, "数据表")
                if cell_value(row, "位置"):
                    current_storage = storage
                if cell_value(row, "数据库"):
                    current_database = database
                if not table_name:
                    continue
                table = table_name if "." in table_name or not database else f"{database}.{table_name}"
                target = add_provenance(
                    {
                        "storage": storage,
                        "database": database,
                        "table_name": table_name.rsplit(".", 1)[-1],
                        "table": table,
                        "description": description,
                    },
                    summary,
                )
                append_unique_by_key(facts["report_physical_targets"], target, "table")
                if "clickhouse" in storage.lower():
                    append_unique_by_key(facts["report_clickhouse_targets"], dict(target), "table")
            continue

        if (
            has_headers(headers, ["位置", "数据表名", "数据表"])
            and has_header(headers, "取数范围", "数据范围")
        ):
            for row in rows:
                source_name = cell_value(row, "数据表名")
                physical_table = cell_value(row, "数据表")
                if not source_name and not physical_table:
                    continue
                facts["report_sources"].append(
                    add_provenance(
                        {
                            "storage": cell_value(row, "位置"),
                            "table_or_path": physical_table or source_name,
                            "table_names": split_table_names(physical_table or source_name),
                            "description": source_name,
                            "range": cell_value(row, "取数范围", "数据范围"),
                            "fields": split_cell_lines(cell_value(row, "字段")),
                            "join_filter": cell_value(row, "关联、过滤信息"),
                        },
                        summary,
                    )
                )
            continue

        if (
            has_headers(headers, ["分类", "位置", "数据表", "数据表名"])
            and has_header(headers, "使用字段")
        ):
            for row in rows:
                source_name = cell_value(row, "数据表名")
                physical_table = cell_value(row, "数据表")
                if not source_name and not physical_table:
                    continue
                fields = split_field_names(cell_value(row, "使用字段"))
                facts["report_sources"].append(
                    add_provenance(
                        {
                            "storage": cell_value(row, "位置"),
                            "table_or_path": physical_table or source_name,
                            "table_names": split_table_names(physical_table or source_name),
                            "description": source_name,
                            "range": cell_value(row, "备注"),
                            "fields": fields,
                            "join_filter": cell_value(row, "备注"),
                            "category": cell_value(row, "分类"),
                        },
                        summary,
                    )
                )
            continue

        if has_headers(headers, ["异常类型", "判断规则", "产出数据表"]):
            for row in rows:
                abnormal_type = cell_value(row, "异常类型")
                if not abnormal_type:
                    continue
                facts["report_business_rules"].append(
                    add_provenance(
                        {
                            "abnormal_type": abnormal_type,
                            "rule": cell_value(row, "判断规则", "判断规则（EO补差GSV异常阈值）"),
                            "grain": cell_value(row, "数据粒度"),
                            "source": cell_value(row, "数据源", "数据来源"),
                            "output_table": cell_value(row, "产出数据表"),
                            "scenario": cell_value(row, "场景"),
                        },
                        summary,
                    )
                )
            continue

        if (
            has_header(headers, "KPI 名称", "KPI名称", "汇总列")
            and has_header(headers, "数据来源底表")
            and has_header(headers, "汇总逻辑")
        ):
            for row in rows:
                name = cell_value(row, "KPI 名称", "KPI名称", "汇总列")
                if not name:
                    continue
                facts["report_kpi_rules"].append(
                    add_provenance(
                        {
                            "kpi": name,
                            "unit": cell_value(row, "单位"),
                            "source_table": cell_value(row, "数据来源底表"),
                            "source_field": cell_value(row, "取值字段"),
                            "aggregation_logic": cell_value(row, "汇总逻辑"),
                        },
                        summary,
                    )
                )
            continue

        if has_headers(headers, ["Name", "Description"]):
            for row in rows:
                name = cell_value(row, "Name")
                if name:
                    facts["data_utilizations"].append(
                        add_provenance({"name": name, "description": cell_value(row, "Description")}, summary)
                    )
            continue

        if has_headers(headers, ["Data Utilization Name", "catalog"]):
            for row in rows:
                name = cell_value(row, "Data Utilization Name")
                catalog = cell_value(row, "catalog")
                if not name and not catalog:
                    continue
                hbase_prefix = cell_value(row, "hbase_target前缀")
                clickhouse_prefix = cell_value(row, "clickhouse_target前缀")
                explicit_hbase = cell_value(row, "Hbase Target Name")
                explicit_clickhouse = cell_value(row, "Clickhouse Target Name")
                facts["target_mappings"].append(
                    add_provenance(
                        {
                            "data_utilization": name,
                            "catalog": catalog,
                            "hbase_target": explicit_hbase or f"{hbase_prefix}{catalog}",
                            "clickhouse_target": explicit_clickhouse or f"{clickhouse_prefix}{catalog}",
                            "hbase_target_prefix": hbase_prefix,
                            "clickhouse_target_prefix": clickhouse_prefix,
                        },
                        summary,
                    )
                )
            continue

        if has_headers(headers, ["Data Utilization Name", "Target Name", "Target Description", "Data Storage"]):
            for row in rows:
                name = cell_value(row, "Data Utilization Name")
                target_name = cell_value(row, "Target Name")
                if not name and not target_name:
                    continue
                facts["report_targets"].append(
                    add_provenance(
                        {
                            "data_utilization": name,
                            "target_name": target_name,
                            "description": cell_value(row, "Target Description"),
                            "storage": cell_value(row, "Data Storage"),
                        },
                        summary,
                    )
                )
            continue

        if has_headers(headers, ["Data Utilization Name", "task1 name", "Description"]):
            for row in rows:
                name = cell_value(row, "Data Utilization Name")
                if name:
                    facts["report_schedules"].append(
                        add_provenance(
                            {
                                "data_utilization": name,
                                "pipeline_name": cell_value(row, "Pipline_Name", "Pipeline Name", "Pipeline_Name"),
                                "task_name": cell_value(row, "task1 name"),
                                "description": cell_value(row, "Description"),
                                "schedule": cell_value(row, "trigger time", "定时任务"),
                            },
                            summary,
                        )
                    )
            continue

        if has_header(headers, "Pipeline Name") and has_header(headers, "定时任务"):
            for row in rows:
                pipeline_name = cell_value(row, "Pipeline Name")
                if pipeline_name:
                    facts["report_schedules"].append(
                        add_provenance(
                            {
                                "data_utilization": "",
                                "pipeline_name": pipeline_name,
                                "task_name": "",
                                "description": cell_value(row, "Description", "Desription"),
                                "schedule": cell_value(row, "定时任务"),
                            },
                            summary,
                        )
                    )
            continue

        if (has_header(headers, "Key", "字段 key", "字段key") and has_header(headers, "字段名称", "字段名")):
            report_field_dicts.append(
                add_provenance(
                    {
                    "csv": summary.csv_path.name,
                    "sheet": summary.sheet_name,
                    "row_count": len(rows),
                    "headers": headers[:12],
                    "first_fields": first_fields(rows),
                    "fields": report_field_rows(rows),
                    "declared_table": declared_table,
                    },
                    summary,
                )
            )
            continue

        if has_headers(headers, ["Data Utilization Name", "task1 name", "定时同步时间"]):
            for row in rows:
                name = cell_value(row, "Data Utilization Name")
                if name:
                    facts["schedules"].append(
                        add_provenance(
                            {
                                "data_utilization": name,
                                "pipeline_name": cell_value(row, "Pipeline Name"),
                                "task_name": cell_value(row, "task1 name"),
                                "schedule": cell_value(row, "定时同步时间"),
                                "pipeline_prefix": cell_value(row, "pipeline前缀"),
                            },
                            summary,
                        )
                    )
            continue

        if (
            "字段" in headers
            or "字段名称" in headers
            or "Key" in headers
            or "Column" in headers
            or "Field" in headers
        ):
            field_dicts.append(
                add_provenance(
                    {
                    "csv": summary.csv_path.name,
                    "sheet": summary.sheet_name,
                    "row_count": len(rows),
                    "headers": headers[:8],
                    "first_fields": first_fields(rows),
                    "declared_table": declared_table,
                    },
                    summary,
                )
            )

    util_names = [item["name"] for item in facts["data_utilizations"]]
    for index, item in enumerate(field_dicts):
        context_match = best_context_match(str(item.get("source_context", "")), util_names)
        if context_match:
            item["inferred_data_utilization"] = context_match
            item["inference_method"] = "embedding_context"
            facts["inferences"].append(
                f"{item['csv']} is mapped to {context_match} by embedding context."
            )
        elif index < len(util_names):
            item["inferred_data_utilization"] = util_names[index]
            item["inference_method"] = "embedded_sheet_order"
            facts["inferences"].append(
                f"{item['csv']} is mapped to {util_names[index]} by embedded-sheet order."
            )
        facts["field_dictionaries"].append(item)

    report_targets = facts.get("report_targets", [])
    report_physical_targets = facts.get("report_physical_targets", []) or facts.get("report_clickhouse_targets", [])
    for target in report_targets:
        target_key = normalized_table_key(target.get("target_name", ""))
        if not target_key:
            continue
        for physical_target in report_physical_targets:
            physical_key = normalized_table_key(
                physical_target.get("table", "") or physical_target.get("table_name", "")
            )
            if target_key and target_key == physical_key:
                target["physical_table"] = physical_target.get("table", "")
                target["database"] = physical_target.get("database", "")
                target["physical_description"] = physical_target.get("description", "")
                break

    for index, item in enumerate(report_field_dicts):
        declared_key = normalized_table_key(item.get("declared_table", ""))
        matched_target = None
        matched_physical_target = None
        if declared_key:
            matched_target = next(
                (
                    target
                    for target in report_targets
                    if normalized_table_key(target.get("target_name", "")) == declared_key
                    or normalized_table_key(target.get("physical_table", "")) == declared_key
                ),
                None,
            )
            matched_physical_target = next(
                (
                    target
                    for target in report_physical_targets
                    if normalized_table_key(target.get("table", "") or target.get("table_name", "")) == declared_key
                ),
                None,
            )

        if matched_target:
            item["inferred_target_name"] = matched_target.get("target_name", "")
            item["inferred_target_description"] = matched_target.get("description", "")
            item["inferred_physical_table"] = matched_target.get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by declared table {item.get('declared_table', '')}."
            )
        elif matched_physical_target:
            item["inferred_target_name"] = matched_physical_target.get("table_name", "") or matched_physical_target.get("table", "")
            item["inferred_target_description"] = matched_physical_target.get("description", "")
            item["inferred_physical_table"] = matched_physical_target.get("table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_physical_table']} by declared table {item.get('declared_table', '')}."
            )
        elif index < len(report_targets):
            item["inferred_target_name"] = report_targets[index].get("target_name", "")
            item["inferred_target_description"] = report_targets[index].get("description", "")
            item["inferred_physical_table"] = report_targets[index].get("physical_table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_target_name']} by report target order."
            )
        elif index < len(report_physical_targets):
            physical_target = report_physical_targets[index]
            item["inferred_target_name"] = physical_target.get("table_name", "") or physical_target.get("table", "")
            item["inferred_target_description"] = physical_target.get("description", "")
            item["inferred_physical_table"] = physical_target.get("table", "")
            facts["inferences"].append(
                f"{item['csv']} is mapped to {item['inferred_physical_table']} by embedded physical-target order."
            )
        facts["report_field_mappings"].append(item)

    existing_sources = {
        (item.get("storage", ""), item.get("table_or_path", ""))
        for item in facts.get("report_sources", [])
    }
    for mapping in facts.get("report_field_mappings", []):
        for field in mapping.get("fields", []):
            source_table = field.get("source_table", "")
            source_storage = field.get("source_storage", "")
            if not source_table or (source_storage, source_table) in existing_sources:
                continue
            facts["report_sources"].append(
                {
                    "storage": source_storage,
                    "table_or_path": source_table,
                    "table_names": split_table_names(source_table),
                    "description": field.get("source_desc", ""),
                    "range": "",
                    "fields": [field.get("source_field", "")] if field.get("source_field") else [],
                    "join_filter": field.get("calculation_logic", ""),
                    "category": field.get("source_category", ""),
                    "source_doc_index": mapping.get("source_doc_index", 1),
                    "source_doc_name": mapping.get("source_doc_name", ""),
                    "source_csv": mapping.get("source_csv", ""),
                    "source_sheet": mapping.get("source_sheet", ""),
                    "source_kind": "inferred_from_field_mapping",
                }
            )
            existing_sources.add((source_storage, source_table))

    conflicts_by_field: dict[tuple[str, str], dict] = {}
    for mapping in facts.get("report_field_mappings", []):
        target_key = normalized_table_key(
            mapping.get("inferred_physical_table", "")
            or mapping.get("inferred_target_name", "")
            or mapping.get("declared_table", "")
        )
        for field in mapping.get("fields", []):
            field_key = field.get("target_field", "") or field.get("field_name", "")
            logic = compact_text(field.get("calculation_logic", ""))
            if not target_key or not field_key or not logic:
                continue
            key = (target_key, field_key)
            existing = conflicts_by_field.get(key)
            if existing and existing.get("logic") != logic:
                facts["conflicts"].append(
                    {
                        "kind": "field_rule_conflict",
                        "target": target_key,
                        "field": field_key,
                        "first_logic": existing.get("logic", ""),
                        "first_source": existing.get("source", ""),
                        "second_logic": logic,
                        "second_source": mapping.get("source_doc_name", ""),
                    }
                )
            else:
                conflicts_by_field[key] = {
                    "logic": logic,
                    "source": mapping.get("source_doc_name", ""),
                }

    infer_bysku_report_component_hint(facts, paragraphs)
    return facts


def markdown_table(rows: list[dict], columns: list[tuple[str, str]], limit: int = 80) -> str:
    if not rows:
        return ""
    selected_rows = rows[:limit]
    header = "| " + " | ".join(title for title, _key in columns) + " |"
    sep = "| " + " | ".join("---" for _title, _key in columns) + " |"
    lines = [header, sep]
    for row in selected_rows:
        values = []
        for _title, key in columns:
            raw_value = row.get(key, "")
            if isinstance(raw_value, list):
                raw_value = ", ".join(str(item) for item in raw_value)
            value = compact_text(str(raw_value)).replace("|", "\\|")
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    if len(rows) > limit:
        lines.append(f"\n- Truncated: showing {limit} of {len(rows)} rows.")
    return "\n".join(lines) + "\n"


def facts_summary_lines(facts: dict) -> list[str]:
    lines: list[str] = []
    if facts.get("documents"):
        lines.append(f"Documents merged: {len(facts['documents'])}.")
    if facts.get("cot_report_tables"):
        lines.append(f"Detected COT-style sync matrix: {len(facts['cot_report_tables'])} source/target rows.")
    if facts.get("report_sources"):
        lines.append(f"Detected report source matrix: {len(facts['report_sources'])} source rows.")
    if facts.get("report_physical_targets"):
        lines.append(f"Detected physical targets: {len(facts['report_physical_targets'])} tables.")
    if facts.get("report_targets"):
        lines.append(f"Detected report target-management rows: {len(facts['report_targets'])} targets.")
    if facts.get("report_field_mappings"):
        lines.append(f"Detected report field-logic sheets: {len(facts['report_field_mappings'])} target dictionaries.")
    if facts.get("report_business_rules"):
        lines.append(f"Detected PRD abnormal/business rules: {len(facts['report_business_rules'])}.")
    if facts.get("report_kpi_rules"):
        lines.append(f"Detected PRD KPI/aggregation rules: {len(facts['report_kpi_rules'])}.")
    if facts.get("component_hints"):
        kinds = ", ".join(item.get("component_kind", "") for item in facts["component_hints"] if item.get("component_kind"))
        lines.append(f"Detected component hints: {kinds}.")
    if facts.get("handoff_readiness"):
        blocked = [
            item.get("component_kind", "")
            for item in facts["handoff_readiness"]
            if not item.get("ready_for_full_codegen", False)
        ]
        if blocked:
            lines.append(f"Handoff readiness blocked for: {', '.join(blocked)}.")
        else:
            lines.append("Handoff readiness: ready for full codegen.")
    if facts.get("field_dictionaries"):
        lines.append(f"Detected {len(facts['field_dictionaries'])} field dictionary sheets.")
    if facts.get("schedules"):
        lines.append(f"Detected {len(facts['schedules'])} pipeline schedules.")
    if facts.get("report_schedules"):
        lines.append(f"Detected report pipeline schedules: {len(facts['report_schedules'])}.")
    return lines


def flattened_report_fields(facts: dict) -> list[dict]:
    rows: list[dict] = []
    for mapping in facts.get("report_field_mappings", []):
        for field in mapping.get("fields", []):
            rows.append(
                {
                    "target": mapping.get("inferred_target_name", ""),
                    "target_desc": mapping.get("inferred_target_description", ""),
                    "physical_table": mapping.get("inferred_physical_table", ""),
                    **field,
                }
            )
    return rows


def project_text_blob(facts: dict, paragraphs: list[Paragraph] | None = None) -> str:
    parts: list[str] = []
    if paragraphs:
        parts.extend(paragraph.text for paragraph in paragraphs)
    for key in [
        "report_sources",
        "report_targets",
        "report_physical_targets",
        "report_clickhouse_targets",
        "report_field_mappings",
        "report_schedules",
    ]:
        parts.append(json.dumps(facts.get(key, []), ensure_ascii=False))
    return "\n".join(parts)


def infer_bysku_report_component_hint(facts: dict, paragraphs: list[Paragraph] | None = None) -> None:
    blob = project_text_blob(facts, paragraphs)
    lower_blob = blob.lower()
    has_sample_alias = "执行为王" in blob or "execute_king" in lower_blob
    has_bysku = "bysku" in lower_blob or "zo_bysku_detail" in lower_blob
    has_sku_family = any(marker in lower_blob for marker in ["npd", "b5", "sku"]) or "新品" in blob
    has_pipeline_storage = "clickhouse" in lower_blob and (
        "hbase" in lower_blob or "fs" in lower_blob or "数据源" in blob
    )
    if not (has_bysku and has_sku_family and has_pipeline_storage):
        return

    known_target_tables = [
        "store_np_sku_details",
        "store_np_sku_summary",
        "store_np_sku_ttl",
        "store_b5_sku_details",
        "store_b5_sku_summary",
        "store_b5_sku_ttl",
    ]
    target_tables = [table for table in known_target_tables if table in lower_blob]
    if (
        not target_tables
        and has_sample_alias
        and any(marker in lower_blob for marker in ["clickhouse_execute_king_npd", "clickhouse_execute_king_b5"])
    ):
        target_tables = known_target_tables

    database = "supervisor_dashboard" if "supervisor_dashboard" in lower_blob else ""
    physical_by_table: dict[str, dict] = {}
    for table_name in target_tables:
        table = f"{database}.{table_name}" if database else table_name
        target = {
            "storage": "ClickHouse",
            "database": database,
            "table_name": table_name,
            "table": table,
            "description": "bySKU ClickHouse output",
            "source_kind": "inferred_bysku_report_pipeline",
            "confidence": "medium",
            "requires_confirmation": True,
        }
        physical_by_table[table_name] = target
        append_unique_by_key(facts["report_physical_targets"], dict(target), "table")
        append_unique_by_key(facts["report_clickhouse_targets"], dict(target), "table")

    for mapping in facts.get("report_field_mappings", []):
        mapping_text = " ".join(
            [
                str(mapping.get("declared_table", "")),
                str(mapping.get("source_context", "")),
                str(mapping.get("inferred_target_name", "")),
                str(mapping.get("inferred_target_description", "")),
            ]
        ).lower()
        for table_name, target in physical_by_table.items():
            if table_name not in mapping_text:
                continue
            mapping["inferred_target_name"] = table_name
            mapping["inferred_physical_table"] = target["table"]
            mapping["inferred_target_description"] = target["description"]
            mapping["target_requires_confirmation"] = True
            facts.setdefault("inferences", []).append(
                f"{mapping.get('csv', '')} is mapped to {target['table']} by bySKU output-table evidence."
            )
            break

    npd_tables = [table for table in target_tables if "_np_" in table or "_npd_" in table]
    b5_tables = [table for table in target_tables if "_b5_" in table]
    other_tables = [table for table in target_tables if table not in set(npd_tables + b5_tables)]
    output_groups: list[dict] = []
    if npd_tables:
        output_groups.append(
            {
                "name": "npd",
                "physical_tables": npd_tables,
                "delete_condition": "mars_week = <current week>",
            }
        )
    if b5_tables:
        output_groups.append(
            {
                "name": "b5",
                "physical_tables": b5_tables,
                "delete_condition": "mars_week = <current week>",
            }
        )
    if other_tables:
        output_groups.append(
            {
                "name": "sku",
                "physical_tables": other_tables,
                "delete_condition": "<documented period predicate>",
            }
        )

    components = [
        {
            "name": "prepare_data",
            "role": "Export period-scoped HBase bySKU rows to compressed FS CSV files.",
            "expected_file_pattern": "zo_bysku_detail_<period>.csv.gz",
        }
    ]
    if output_groups:
        for group in output_groups:
            components.append(
                {
                    "name": f"cal_{group['name']}",
                    "role": "Read FS bySKU files and calculate ClickHouse outputs for one SKU family.",
                    "target_tables": group["physical_tables"],
                }
            )
    else:
        components.append(
            {
                "name": "cal_sku",
                "role": "Read FS bySKU files and calculate documented SKU-family ClickHouse outputs.",
                "target_tables": [],
            }
        )

    hint = {
        "component_kind": "bysku_report_pipeline",
        "handoff_to": "report-codegen",
        "reference": "references/bysku_report_pipeline_patterns.md",
        "sample_aliases": ["executing_king"] if has_sample_alias else [],
        "source_tables": sorted(set(re.findall(r"l2_cot_perfect_store\.zo_[A-Za-z0-9_]+", lower_blob))),
        "intermediate_storage": "FS bySKU gzip files",
        "components": components,
        "output_groups": output_groups,
        "write_strategy": [
            "Delete ClickHouse current-period rows by the documented period key before insert.",
            "Roll-delete periods older than the documented retention threshold after successful inserts.",
            "Keep inferred physical target tables as confirmation-required unless production code or deployment config proves them.",
        ],
        "required_confirmations": [
            "Confirm FS bySKU directory and file type.",
            "Confirm SKU XML/params source for sku_map, sku_cal_range, sku_ttl_filter, and active SKU flags.",
            "Confirm ClickHouse physical tables and delete predicates.",
        ],
    }
    facts.setdefault("component_hints", []).append(hint)
    facts.setdefault("inferences", []).append(
        "Detected bysku_report_pipeline from bySKU + SKU-family + ClickHouse evidence."
    )

    mapped_tables = {
        str(mapping.get("inferred_physical_table", "")).rsplit(".", 1)[-1]
        for mapping in facts.get("report_field_mappings", [])
        if mapping.get("inferred_physical_table")
    }
    missing_mappings = [table for table in target_tables if table not in mapped_tables]
    readiness_checks = [
        {
            "name": "component_kind",
            "status": "ok",
            "detail": "Detected bysku_report_pipeline.",
        },
        {
            "name": "physical_targets",
            "status": "needs_confirmation" if target_tables else "blocked",
            "detail": (
                "ClickHouse physical tables were inferred from document text and must be confirmed."
                if target_tables
                else "ClickHouse physical tables were not explicit enough to infer safely."
            ),
        },
        {
            "name": "field_mapping_to_outputs",
            "status": "blocked" if missing_mappings else "ok",
            "detail": "Missing field dictionaries for: " + ", ".join(missing_mappings) if missing_mappings else "All inferred outputs have field mappings.",
        },
        {
            "name": "fs_and_sku_params",
            "status": "needs_confirmation",
            "detail": "FS directory, file extension, and SKU XML/params source must be confirmed before codegen.",
        },
        {
            "name": "write_strategy",
            "status": "needs_confirmation",
            "detail": "Confirm mars_week delete predicates and R13P retention cleanup before deployment.",
        },
    ]
    facts.setdefault("handoff_readiness", []).append(
        {
            "component_kind": "bysku_report_pipeline",
            "ready_for_full_codegen": bool(target_tables) and not missing_mappings,
            "checks": readiness_checks,
        }
    )


def write_dev_doc(
    path: Path,
    docx_path: Path,
    project_name: str,
    paragraphs: list[Paragraph],
    sheet_summaries: list[SheetSummary],
) -> None:
    title = paragraphs[0].text if paragraphs else project_name
    source_hits = paragraphs_matching(paragraphs, ["数据源", "Source", "链接信息", "数据列表", "HBase", "MSSQL", "MySQL", "Blob"])
    target_hits = paragraphs_matching(paragraphs, ["Data Target", "目标表", "目标表字典", "ClickHouse", "Data Storage"])
    flow_hits = paragraphs_matching(paragraphs, ["数据流程", "写入流程", "同步逻辑", "Data Transformation", "Pipeline"])
    schedule_hits = paragraphs_matching(paragraphs, ["调度", "定时", "运行时间", "频率", "重跑", "rerun", "Pipeline Planning"])
    calc_hits = paragraphs_matching(paragraphs, ["计算逻辑", "KPI", "汇总逻辑", "字段逻辑", "过滤", "关联"])

    table_lines = []
    for summary in sheet_summaries[:40]:
        headers = " | ".join(summary.headers)
        table_lines.append(f"`{summary.csv_path.name}`: `{summary.sheet_name}`; headers: {headers}")

    content = f"""# {project_name} Development Document

## 1. Project Overview

- Source document: `{docx_path.name}`
- Original title: {title}
- Project type: 待确认是 `data-sync` 还是 `report`

## 2. Source Tables

{markdown_list(source_hits)}
## 3. Target Tables

{markdown_list(target_hits)}
## 4. Field Dictionary

The extracted embedded tables below are the primary field-dictionary evidence:

{markdown_list(table_lines)}
## 5. Field Mapping

- 待从字段字典、字段逻辑表、数据源字段 key、目标表字段 key 中整理。

## 6. Data Processing Flow

{markdown_list(flow_hits)}
## 7. KPI / Calculation Logic

{markdown_list(calc_hits)}
## 8. Write Strategy

- 待确认写入目标是 HBase、ClickHouse、FS 留痕，还是组合写入。
- 待确认删除旧数据策略、全量/增量策略、分区或 period 清理策略。

## 9. Scheduling And Rerun

{markdown_list(schedule_hits)}
## 10. Parameter Design

- Credentials must use placeholders in generated code.
- 待确认运行参数：period/current_date/sync_dates/receiver_emails/source table/target table/rowkey fields.

## 11. Log Verification Plan

- 部署后检查 DataSource 阶段：输入表、时间范围、导出行数。
- 部署后检查 DataProcess 阶段：过滤前后行数、关键 join 行数、KPI 输出行数。
- 部署后检查 DataStorage 阶段：目标表、删除条件、插入行数、耗时。

## 12. Open Questions

See `questions.md`.
"""
    path.write_text(content, encoding="utf-8")


def write_questions(path: Path, paragraphs: list[Paragraph], sheet_summaries: list[SheetSummary]) -> None:
    all_text = "\n".join(p.text for p in paragraphs).lower()
    questions = [
        "项目类型最终确认：数据同步还是报表开发？",
        "生成代码时目标项目目录是哪一个？",
        "配置文件中的 app_key/app_secret/token/IP 是否全部使用占位符？",
    ]
    if (has_hbase_target or facts.get("cot_report_tables")) and "rowkey" not in all_text:
        questions.append("HBase rowkey 规则未明确：需要确认 rowkey 拼接字段、时间字段格式、是否需要首位散列前缀。")
    if "重跑" not in all_text and "rerun" not in all_text:
        questions.append("重跑机制未明确：需要确认按 period、日期、时间戳还是全量重跑。")
    if "delete" not in all_text and "删除" not in all_text:
        questions.append("写入前删除策略未明确：需要确认 ClickHouse/HBase 是否先删旧数据。")
    if "调度" not in all_text and "定时" not in all_text and "频率" not in all_text:
        questions.append("调度频率未明确：需要确认每日、每 P、15 分钟或手动触发。")
    if not sheet_summaries:
        questions.append("未提取到嵌入 Excel 表：需要确认字段字典是否在截图、外部 Excel 或其他文档中。")

    content = "# Open Questions\n\n" + "".join(f"- {question}\n" for question in questions)
    path.write_text(content, encoding="utf-8")


def write_dev_doc_v2(
    path: Path,
    docx_path: Path,
    project_name: str,
    paragraphs: list[Paragraph],
    sheet_summaries: list[SheetSummary],
    facts: dict,
) -> None:
    title = paragraphs[0].text if paragraphs else project_name
    source_documents = facts.get("documents") or [{"name": docx_path.name}]
    source_document_names = [item.get("name", "") for item in source_documents if item.get("name")]
    source_hits = paragraphs_matching(paragraphs, ["数据源", "Source", "HBase", "MSSQL", "MySQL", "Blob"])
    target_hits = paragraphs_matching(paragraphs, ["Data Target", "目标表", "ClickHouse", "Data Storage"])
    flow_hits = paragraphs_matching(paragraphs, ["数据流程", "写入流程", "同步逻辑", "Data Transformation", "Pipeline"])
    calc_hits = paragraphs_matching(paragraphs, ["计算逻辑", "KPI", "汇总逻辑", "字段逻辑", "过滤", "关联"])

    table_lines = []
    for summary in sheet_summaries[:40]:
        headers = " | ".join(summary.headers)
        table_lines.append(f"`{summary.csv_path.name}`: `{summary.sheet_name}`; headers: {headers}")

    cot_sources = markdown_table(
        facts.get("cot_report_tables", []),
        [
            ("Seq", "seq"),
            ("Business", "business_desc"),
            ("Type", "report_type"),
            ("Source HBase", "source_hbase_table"),
            ("Range", "source_range"),
            ("ClickHouse Table", "clickhouse_table"),
        ],
    )
    cot_targets = markdown_table(
        facts.get("target_mappings", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Catalog", "catalog"),
            ("HBase Target", "hbase_target"),
            ("ClickHouse Target", "clickhouse_target"),
        ],
    )
    cot_fields = markdown_table(
        facts.get("field_dictionaries", []),
        [
            ("Data Utilization", "inferred_data_utilization"),
            ("CSV", "csv"),
            ("Rows", "row_count"),
            ("First Fields", "first_fields"),
        ],
    )
    cot_schedules = markdown_table(
        facts.get("schedules", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Task", "task_name"),
            ("Schedule", "schedule"),
            ("Pipeline Prefix", "pipeline_prefix"),
        ],
    )
    report_sources = markdown_table(
        facts.get("report_sources", []),
        [
            ("Storage", "storage"),
            ("Table / Path", "table_or_path"),
            ("Range", "range"),
            ("Fields", "fields"),
            ("Join / Filter", "join_filter"),
        ],
    )
    report_physical_targets = markdown_table(
        facts.get("report_physical_targets", []),
        [
            ("Storage", "storage"),
            ("Database", "database"),
            ("Physical Table", "table"),
            ("Description", "description"),
        ],
    )
    report_targets = markdown_table(
        facts.get("report_targets", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Target Name", "target_name"),
            ("Description", "description"),
            ("Storage", "storage"),
            ("Physical Table", "physical_table"),
        ],
    )
    report_field_summaries = markdown_table(
        facts.get("report_field_mappings", []),
        [
            ("Target", "inferred_target_name"),
            ("Physical Table", "inferred_physical_table"),
            ("Declared Table", "declared_table"),
            ("Description", "inferred_target_description"),
            ("CSV", "csv"),
            ("Rows", "row_count"),
            ("First Fields", "first_fields"),
        ],
    )
    report_field_rules = markdown_table(
        flattened_report_fields(facts),
        [
            ("Target", "target"),
            ("Physical Table", "physical_table"),
            ("Field", "target_field"),
            ("Name", "field_name"),
            ("Source", "source_desc"),
            ("Source Field", "source_field"),
            ("Rule", "calculation_logic"),
            ("EO Rule", "eo_order_logic"),
            ("DMS Rule", "dms_order_logic"),
        ],
        limit=140,
    )
    report_schedules = markdown_table(
        facts.get("report_schedules", []),
        [
            ("Data Utilization", "data_utilization"),
            ("Pipeline", "pipeline_name"),
            ("Task", "task_name"),
            ("Description", "description"),
        ],
    )
    component_hints = markdown_table(
        facts.get("component_hints", []),
        [
            ("Component Kind", "component_kind"),
            ("Handoff To", "handoff_to"),
            ("Reference", "reference"),
            ("Intermediate Storage", "intermediate_storage"),
        ],
    )
    business_rules = markdown_table(
        facts.get("report_business_rules", []),
        [
            ("Abnormal Type", "abnormal_type"),
            ("Rule", "rule"),
            ("Grain", "grain"),
            ("Source", "source"),
            ("Output Table", "output_table"),
        ],
        limit=120,
    )
    kpi_rules = markdown_table(
        facts.get("report_kpi_rules", []),
        [
            ("KPI", "kpi"),
            ("Unit", "unit"),
            ("Source Table", "source_table"),
            ("Source Field", "source_field"),
            ("Aggregation Logic", "aggregation_logic"),
        ],
        limit=120,
    )

    is_cot_sync = bool(facts.get("cot_report_tables"))
    is_report = bool(
        facts.get("report_sources")
        or facts.get("report_targets")
        or facts.get("report_clickhouse_targets")
        or facts.get("report_field_mappings")
    )
    project_type = "data-sync" if is_cot_sync else ("report" if is_report else "待确认是 `data-sync` 还是 `report`")
    source_section = cot_sources or report_sources or markdown_list(source_hits)
    if report_physical_targets or report_targets:
        target_section = ""
        if report_physical_targets:
            target_section += "Physical report targets detected from Data Target text:\n\n" + report_physical_targets + "\n"
        if report_targets:
            target_section += "Target Management rows detected from embedded Excel:\n\n" + report_targets
    else:
        target_section = cot_targets or markdown_list(target_hits)
    if is_cot_sync:
        field_section = cot_fields or markdown_list(table_lines)
    elif is_report:
        field_section = report_field_summaries or markdown_list(table_lines)
    else:
        field_section = markdown_list(table_lines)
    schedule_section = cot_schedules or report_schedules or "- 待从原始文档或人工补充材料确认。\n"
    overview_facts = markdown_list(facts_summary_lines(facts))

    if is_cot_sync:
        mapping_note = (
            "- Generate sync config from the structured matrix: source table, range, ClickHouse table, Data Utilization name, target prefixes, schedule, and field dictionary.\n"
            "- Field dictionary sheets are mapped to Data Utilization rows by embedded-sheet order; verify renamed or exception tables.\n"
        )
        write_strategy = (
            "- Write both HBase and ClickHouse targets when both are configured.\n"
            "- Perfect-store / project-collection reports: prefer ClickHouse write before HBase when the document says to release memory quickly.\n"
            "- Execution reports: prefer HBase write before ClickHouse when the document says downstream HBase service should be available first.\n"
            "- Keep table-level full/delta, truncate, delete-by-key, delete-by-period, and legacy database-prefix exceptions in config.\n"
        )
        parameter_design = (
            "- COT params should keep `source_informations`, `hbase_informations`, and `clickhouse_information` groups.\n"
            "- Required fields normally include `mysql_table`, `last_update_time_column`, optional `period_column`, optional `period`, `batch_size`, `receiver_emails`, `hbase_table`, `rowkey_rule_columns`, and `clickhouse_table`.\n"
            "- Credentials must use placeholders in generated code.\n"
        )
    elif is_report:
        mapping_note = (
            "- Generate report code from `structured_facts.json`: `report_sources`, `report_physical_targets`, `report_targets`, `report_field_mappings`, and `report_schedules`.\n"
            "- Field-logic sheets are mapped to target rows by embedded-sheet order; verify exceptions before deployment.\n"
            "- Full field-level rules extracted from the target dictionaries:\n\n"
            f"{report_field_rules or '- 未识别到字段级规则。'}"
        )
        write_strategy = (
            "- Use the detected physical target storage: HBase, ClickHouse, FS, or mixed targets.\n"
            "- For ClickHouse targets, delete/replace old target rows by `period` only when the target dictionary contains `period` and the report is period-grain; otherwise ask for confirmation.\n"
            "- For HBase prepare/pipeline projects, confirm whether the generated code should export source files to FS, trigger downstream pipeline, or calculate/write the final HBase table directly.\n"
            "- Preserve FS evidence outputs when source sections or release notes mention Gateway project retention / 留痕.\n"
        )
        parameter_design = (
            "- Default report params: `period`, `current_date`, `receiver_emails`, and `running_env`.\n"
            "- Credentials must use placeholders in generated code.\n"
            "- If period is omitted, generated code must derive the target period from the calendar only when the document states that behavior.\n"
        )
    else:
        mapping_note = "- 待从字段字典、字段逻辑表、数据源字段 key、目标表字段 key 中整理。\n"
        write_strategy = (
            "- 待确认写入目标是 HBase、ClickHouse、FS 留痕，还是组合写入。\n"
            "- 待确认删除旧数据策略、全量/增量策略、分区或 period 清理策略。\n"
        )
        parameter_design = (
            "- Credentials must use placeholders in generated code.\n"
            "- 待确认运行参数：period/current_date/sync_dates/receiver_emails/source table/target table/rowkey fields.\n"
        )

    source_documents_text = ", ".join(f"`{name}`" for name in source_document_names) or f"`{docx_path.name}`"
    kpi_logic_section = ""
    if business_rules:
        kpi_logic_section += "PRD abnormal/business rules:\n\n" + business_rules + "\n"
    if kpi_rules:
        kpi_logic_section += "PRD KPI / aggregation rules:\n\n" + kpi_rules + "\n"
    kpi_logic_section += markdown_list(calc_hits)

    content = f"""# {project_name} Development Document

## 1. Project Overview

- Source document: {source_documents_text}
- Original title: {title}
- Project type: {project_type}
{overview_facts}
{("Component handoff hints:\n\n" + component_hints) if component_hints else ""}

## 2. Source Tables

{source_section}
## 3. Target Tables

{target_section}
## 4. Field Dictionary

The extracted embedded tables below are the primary field-dictionary evidence:

{field_section}
## 5. Field Mapping

{mapping_note}
## 6. Data Processing Flow

{markdown_list(flow_hits)}
## 7. KPI / Calculation Logic

{kpi_logic_section}
## 8. Write Strategy

{write_strategy}
## 9. Scheduling And Rerun

{schedule_section}
## 10. Parameter Design

{parameter_design}

## 11. Log Verification Plan

- DataSource: check source table, selected sync mode, period/time range, exported row count, generated file count.
- HBase: check rowkey columns, delete/truncate count, insert count, target table name.
- ClickHouse: check delete/drop/truncate condition, inserted file count, target table name, final row count.
- Final metrics: compare exported rows with HBase and ClickHouse inserted rows.

## 12. Open Questions

See `questions.md`.
"""
    path.write_text(content, encoding="utf-8")


def write_questions_v2(path: Path, paragraphs: list[Paragraph], sheet_summaries: list[SheetSummary], facts: dict) -> None:
    all_text = "\n".join(p.text for p in paragraphs).lower()
    physical_targets = facts.get("report_physical_targets") or facts.get("report_clickhouse_targets") or []
    target_storage = " ".join(str(item.get("storage", "")).lower() for item in physical_targets + facts.get("report_targets", []))
    has_clickhouse_target = bool(facts.get("report_clickhouse_targets")) or "clickhouse" in target_storage
    has_hbase_target = "hbase" in target_storage
    component_kinds = {item.get("component_kind") for item in facts.get("component_hints", [])}
    questions = ["生成代码时目标项目目录是哪一个？", "配置文件中的 app_key/app_secret/token/IP 是否全部使用占位符？"]
    if "bysku_report_pipeline" in component_kinds:
        questions.extend(
            [
                "bySKU 中间 FS 目录、文件压缩格式、文件覆盖策略需要确认。",
                "SKU 参数来源需要确认：sku_map、sku_cal_range、sku_ttl_filter、sku_is_active 是来自 XML、params JSON 还是外部配置。",
                "ClickHouse 物理表名与删除条件需要确认：明细/汇总/TTL 是否按 period/week 删除，历史保留是否按文档阈值滚动删除。",
            ]
        )
    if facts.get("cot_report_tables"):
        questions.extend(
            [
                "COT 每张表的 rowkey_rule_columns 是否有单独清单？如果没有，需要按字段字典确认。",
                "COT with_period_tables / without_period_tables 是否按当前生产分类沿用，还是需要按新文档调整？",
                "是否存在 ClickHouse 历史库名前缀、HBase truncate、ClickHouse truncate 等表级例外？",
            ]
        )
    elif facts.get("report_sources") or facts.get("report_targets") or facts.get("report_field_mappings"):
        if not physical_targets:
            questions.append("报表物理目标表未识别：需要确认 database.table / hbase table 与逻辑 Target Name 的对应关系。")
        elif not has_clickhouse_target and has_hbase_target:
            questions.append("HBase 目标表已识别：需要确认本项目是直接计算写入 HBase，还是先导出 FS 后触发下游 pipeline。")
        elif not has_clickhouse_target:
            questions.append("报表物理 ClickHouse 表名未识别：需要确认 database.table 与逻辑 Target Name 的对应关系。")
        if not facts.get("report_sources"):
            questions.append("报表数据源矩阵未识别：需要确认 HBase/FS/MSSQL 源表、取数范围和字段清单。")
        if not facts.get("report_field_mappings"):
            questions.append("报表字段逻辑表未识别：需要确认输出字段顺序、计算逻辑和汇总口径。")
        if has_clickhouse_target:
            questions.append("ClickHouse 写入前删除条件需要确认：按 period 删除、按 date 删除、还是 batch/status 模式。")
        if has_hbase_target:
            questions.append("HBase rowkey、写入模式、是否先删旧数据需要结合部署项目或下游 pipeline 确认。")
        questions.append("如果文档提到 Gateway/FS 留痕或数据准备，需要确认 FS 目录、文件名和失败时是否阻断主流程。")
    else:
        questions.insert(0, "项目类型最终确认：数据同步还是报表开发？")
    if (has_hbase_target or facts.get("cot_report_tables")) and "rowkey" not in all_text:
        questions.append("HBase rowkey 规则未明确：需要确认 rowkey 拼接字段、时间字段格式、是否需要首位散列前缀。")
    if "rerun" not in all_text and "重跑" not in all_text:
        questions.append("重跑机制未明确：需要确认按 period、日期、时间戳还是全量重跑。")
    if "delete" not in all_text and "删除" not in all_text:
        if has_hbase_target and not has_clickhouse_target:
            questions.append("HBase/FS prepare 项目的重跑覆盖策略未明确：需要确认 FS 文件是否覆盖、下游 HBase 是否先删旧数据。")
        else:
            questions.append("写入前删除策略未明确：需要确认 ClickHouse/HBase 是否先删旧数据。")
    if "调度" not in all_text and "定时" not in all_text and "频率" not in all_text:
        questions.append("调度频率未明确：需要确认每日、每 P、15 分钟或手动触发。")
    if not sheet_summaries:
        questions.append("未提取到嵌入 Excel 表：需要确认字段字典是否在截图、外部 Excel 或其他文档中。")

    content = "# Open Questions\n\n" + "".join(f"- {question}\n" for question in questions)
    path.write_text(content, encoding="utf-8")


def docx_paths_from_args(raw_docx: list[list[str]] | list[str]) -> list[Path]:
    values: list[str] = []
    for item in raw_docx:
        if isinstance(item, list):
            values.extend(item)
        else:
            values.append(item)
    paths = [Path(value).expanduser().resolve() for value in values]
    if not paths:
        raise ValueError("at least one --docx input is required")
    for docx_path in paths:
        if not docx_path.exists():
            raise FileNotFoundError(docx_path)
        if docx_path.suffix.lower() != ".docx":
            raise ValueError(f"expected .docx input, got: {docx_path}")
    return paths


def annotate_document_context(
    paragraphs: list[Paragraph],
    summaries: list[SheetSummary],
    docx_path: Path,
    doc_index: int,
) -> None:
    for paragraph in paragraphs:
        paragraph.source_doc_index = doc_index
        paragraph.source_doc_name = docx_path.name
    for summary in summaries:
        summary.source_doc_index = doc_index
        summary.source_doc_name = docx_path.name


def extract_document_to_dirs(
    docx_path: Path,
    extracted_dir: Path,
    tables_dir: Path,
    word_tables_dir: Path,
    max_table_rows: int,
    doc_index: int,
) -> tuple[list[Paragraph], int, list[SheetSummary], list[SheetSummary]]:
    paragraphs, table_count, _embedded = extract_docx_paragraphs(docx_path)
    word_table_summaries = extract_word_tables(docx_path, word_tables_dir, max_rows=max_table_rows)
    sheet_summaries = extract_embedded_tables(docx_path, tables_dir, max_rows=max_table_rows)
    all_table_summaries = sheet_summaries + word_table_summaries
    annotate_document_context(paragraphs, all_table_summaries, docx_path, doc_index)
    write_extracted_markdown(
        extracted_dir / "extracted_document.md",
        docx_path,
        paragraphs,
        table_count,
        all_table_summaries,
    )
    return paragraphs, table_count, sheet_summaries, word_table_summaries


def document_meta(docx_path: Path, doc_index: int, paragraphs: list[Paragraph], table_count: int, embedded_count: int, word_count: int) -> dict:
    return {
        "index": doc_index,
        "name": docx_path.name,
        "path": str(docx_path),
        "title": paragraphs[0].text if paragraphs else docx_path.stem,
        "paragraphs": len(paragraphs),
        "word_tables": table_count,
        "embedded_sheets": embedded_count,
        "word_table_csvs": word_count,
    }


def run(args: argparse.Namespace) -> int:
    docx_paths = docx_paths_from_args(args.docx)
    docx_path = docx_paths[0]
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"expected .docx input, got: {docx_path}")

    project_name = args.project_name or safe_name(docx_path.stem)
    out_root = Path(args.out).expanduser().resolve()
    extracted_dir = out_root / "extracted"
    dev_doc_dir = out_root / "dev_doc"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    dev_doc_dir.mkdir(parents=True, exist_ok=True)

    all_paragraphs: list[Paragraph] = []
    all_table_summaries: list[SheetSummary] = []
    documents: list[dict] = []
    total_embedded = 0
    total_word_csvs = 0

    if len(docx_paths) == 1:
        tables_dir = extracted_dir / "extracted_tables"
        word_tables_dir = extracted_dir / "word_tables"
        paragraphs, table_count, sheet_summaries, word_table_summaries = extract_document_to_dirs(
            docx_path,
            extracted_dir,
            tables_dir,
            word_tables_dir,
            args.max_table_rows,
            doc_index=1,
        )
        all_paragraphs.extend(paragraphs)
        all_table_summaries.extend(sheet_summaries + word_table_summaries)
        total_embedded += len(sheet_summaries)
        total_word_csvs += len(word_table_summaries)
        documents.append(document_meta(docx_path, 1, paragraphs, table_count, len(sheet_summaries), len(word_table_summaries)))
    else:
        for doc_index, current_docx in enumerate(docx_paths, start=1):
            doc_dir = extracted_dir / f"doc_{doc_index:03d}_{safe_name(current_docx.stem)}"
            tables_dir = doc_dir / "extracted_tables"
            word_tables_dir = doc_dir / "word_tables"
            doc_dir.mkdir(parents=True, exist_ok=True)
            paragraphs, table_count, sheet_summaries, word_table_summaries = extract_document_to_dirs(
                current_docx,
                doc_dir,
                tables_dir,
                word_tables_dir,
                args.max_table_rows,
                doc_index=doc_index,
            )
            all_paragraphs.extend(paragraphs)
            all_table_summaries.extend(sheet_summaries + word_table_summaries)
            total_embedded += len(sheet_summaries)
            total_word_csvs += len(word_table_summaries)
            documents.append(
                document_meta(current_docx, doc_index, paragraphs, table_count, len(sheet_summaries), len(word_table_summaries))
            )

    structured_facts = build_structured_facts(all_table_summaries, all_paragraphs)
    structured_facts["documents"] = documents
    if len(docx_paths) > 1:
        structured_facts["merge_policy"] = (
            "DataEngine/waterline technical facts take precedence for tables, fields, storage, and schedules; "
            "PRD facts supplement business goals, abnormal rules, KPI logic, and UI aggregation logic. "
            "Conflicts are recorded in conflicts/questions instead of silently overwriting evidence."
        )
    (dev_doc_dir / "structured_facts.json").write_text(
        json.dumps(structured_facts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_dev_doc_v2(dev_doc_dir / "dev_doc.md", docx_path, project_name, all_paragraphs, all_table_summaries, structured_facts)
    write_questions_v2(dev_doc_dir / "questions.md", all_paragraphs, all_table_summaries, structured_facts)

    if len(docx_paths) == 1:
        print(f"extracted: {extracted_dir / 'extracted_document.md'}")
    else:
        print(f"extracted: {extracted_dir}")
    print(f"dev_doc: {dev_doc_dir / 'dev_doc.md'}")
    print(f"questions: {dev_doc_dir / 'questions.md'}")
    print(f"structured_facts: {dev_doc_dir / 'structured_facts.json'}")
    print(f"documents: {len(docx_paths)}")
    print(f"embedded_sheets: {total_embedded}")
    print(f"word_tables: {total_word_csvs}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract DOCX text and embedded Excel tables for data development docs.")
    parser.add_argument("--docx", required=True, action="append", nargs="+", help="Input DOCX path. Repeat or pass multiple values for multi-document projects.")
    parser.add_argument("--out", required=True, help="Output directory, for example outputs/my_project.")
    parser.add_argument("--project-name", default="", help="Optional project display name.")
    parser.add_argument(
        "--max-table-rows",
        type=int,
        default=0,
        help="Maximum rows to export per embedded sheet. Use 0 for no limit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
