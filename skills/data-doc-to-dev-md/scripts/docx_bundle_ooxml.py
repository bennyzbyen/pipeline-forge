#!/usr/bin/env python3
"""Low-level OOXML and table extraction for DOCX requirement bundles."""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from document_sections import DocumentSection


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
    extraction_issues: list[dict] = field(default_factory=list)
    section_role: str = ""


def extract_docx_paragraphs(docx_path: Path) -> tuple[list[Paragraph], int, list[str]]:
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            raise ValueError(f"{docx_path} does not contain word/document.xml")
        root = ET.fromstring(document_xml)

        return _docx_paragraphs(root, docx)


def _docx_paragraphs(root: ET.Element, docx: zipfile.ZipFile) -> tuple[list[Paragraph], int, list[str]]:
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
        return _embedding_contexts(root, rels, window)


def _embedding_contexts(root: ET.Element, rels: dict[str, str], window: int = 4) -> dict[str, str]:
    contexts: dict[str, str] = {}
    if not rels:
        return contexts
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


def _table_sections(root: ET.Element, rels: dict[str, str] | None = None) -> tuple[dict[int, str], dict[str, str]]:
    word_roles, embedded_roles = {}, {}
    body = root.find(qn(NS_W, "body"))
    section = DocumentSection()
    for element in body if body is not None else []:
        if element.tag == qn(NS_W, "p"):
            style = element.find(f"./{qn(NS_W, 'pPr')}/{qn(NS_W, 'pStyle')}")
            section.feed(element_text(element), style.attrib.get(qn(NS_W, "val"), "") if style is not None else "")
        for table in element.iter(qn(NS_W, "tbl")):
            word_roles[id(table)] = section.role
        for rel_id in embedding_rel_ids(element, rels or {}):
            name = target_basename(rels[rel_id])
            previous = embedded_roles.get(name, section.role)
            embedded_roles[name] = section.role if previous == section.role else "ambiguous"
    return word_roles, embedded_roles


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


def _limit_table_rows(rows: list[list[str]], max_rows: int) -> tuple[list[list[str]], list[dict]]:
    if max_rows > 0 and len(rows) > max_rows:
        return rows[:max_rows], [{
            "code": "TABLE_EXTRACTION_TRUNCATED", "severity": "ERROR", "export_limit": max_rows,
            "message": f"Additional non-empty rows exist beyond the requested limit of {max_rows}; re-extract without a limit before using this table.",
        }]
    return rows, []


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
            read_limit = max_rows + 1 if max_rows > 0 else max_rows
            rows = list(iter_sheet_rows(sheet_root, shared_strings, max_rows=read_limit))
            rows, issues = _limit_table_rows(rows, max_rows)
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
                    extraction_issues=issues,
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
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        rels = read_document_relationships(docx)
        contexts, roles = {}, {}
        if document_xml and rels:
            root = ET.fromstring(document_xml)
            contexts = _embedding_contexts(root, rels)
            _word_roles, roles = _table_sections(root, rels)
        return _embedded_tables(docx, tables_dir, max_rows, contexts, roles)


def _embedded_tables(docx: zipfile.ZipFile, tables_dir: Path, max_rows: int, contexts: dict[str, str],
                     roles: dict[str, str] | None = None) -> list[SheetSummary]:
    summaries: list[SheetSummary] = []
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
            summary.section_role = (roles or {}).get(workbook_name, "")
            if summary.section_role == "ambiguous":
                summary.extraction_issues.append({"code": "TABLE_SECTION_AMBIGUOUS", "severity": "ERROR",
                    "message": "The same embedded workbook occurs in different section roles; resolve its ownership."})
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
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            return []
        root = ET.fromstring(document_xml)
        return _word_tables(root, tables_dir, max_rows)


def _word_tables(root: ET.Element, tables_dir: Path, max_rows: int,
                 roles: dict[int, str] | None = None) -> list[SheetSummary]:
    summaries: list[SheetSummary] = []
    if roles is None:
        roles, _embedded_roles = _table_sections(root)
    for table_index, table in enumerate(root.iter(qn(NS_W, "tbl")), start=1):
        rows: list[list[str]] = []
        for row in table.findall(qn(NS_W, "tr")):
            if max_rows and len(rows) >= max_rows + 1:
                break
            values = [word_cell_text(cell) for cell in row.findall(qn(NS_W, "tc"))]
            if any(value.strip() for value in values):
                rows.append(values)
        rows, issues = _limit_table_rows(rows, max_rows)
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
                extraction_issues=issues,
                section_role=roles.get(id(table), ""),
            )
        )
    return summaries


def extract_docx_evidence(
    docx_path: Path,
    tables_dir: Path,
    word_tables_dir: Path,
    max_rows: int,
) -> tuple[list[Paragraph], int, list[SheetSummary], list[SheetSummary]]:
    """Share one document read/parse within an extraction; retain standalone APIs."""
    with zipfile.ZipFile(docx_path) as docx:
        document_xml = read_zip_text(docx, "word/document.xml")
        if not document_xml:
            raise ValueError(f"{docx_path} does not contain word/document.xml")
        root = ET.fromstring(document_xml)
        paragraphs, table_count, _embedded = _docx_paragraphs(root, docx)
        rels = read_document_relationships(docx)
        word_roles, embedded_roles = _table_sections(root, rels)
        word_tables_dir.mkdir(parents=True, exist_ok=True)
        word_summaries = _word_tables(root, word_tables_dir, max_rows, word_roles)
        tables_dir.mkdir(parents=True, exist_ok=True)
        contexts = _embedding_contexts(root, rels)
        sheet_summaries = _embedded_tables(docx, tables_dir, max_rows, contexts, embedded_roles)
    return paragraphs, table_count, sheet_summaries, word_summaries
