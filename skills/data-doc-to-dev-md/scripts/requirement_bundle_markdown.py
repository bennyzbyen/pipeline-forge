#!/usr/bin/env python3
"""Normalize Markdown requirement documents into paragraph and table evidence."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from docx_bundle_ooxml import Paragraph, SheetSummary, compact_text, safe_name


MARKDOWN_SUFFIXES = {".md", ".markdown"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+(.+)$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def split_markdown_row(line: str) -> list[str]:
    """Split a GFM pipe row while preserving escaped pipes and inline code."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith(r"\|"):
        text = text[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    in_code = False
    for index, char in enumerate(text):
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and index + 1 < len(text) and text[index + 1] == "|":
            escaped = True
            continue
        if char == "`":
            in_code = not in_code
            current.append(char)
            continue
        if char == "|" and not in_code:
            cells.append(compact_text("".join(current)))
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    cells.append(compact_text("".join(current)))
    return cells


def is_table_separator(line: str, expected_width: int) -> bool:
    cells = [cell.replace(" ", "") for cell in split_markdown_row(line)]
    return len(cells) == expected_width and all(SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


def _frontmatter_paragraphs(lines: list[str], source_name: str, doc_index: int) -> tuple[list[Paragraph], int]:
    if not lines or lines[0].strip() != "---":
        return [], 0
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return [], 0
    paragraphs = [
        Paragraph(style="Metadata", text=compact_text(line), source_doc_index=doc_index, source_doc_name=source_name)
        for line in lines[1:end]
        if compact_text(line) and not line.lstrip().startswith("#")
    ]
    return paragraphs, end + 1


def _write_markdown_table(
    rows: list[list[str]],
    tables_dir: Path,
    table_index: int,
    source_path: Path,
    doc_index: int,
    context: str,
) -> SheetSummary:
    width = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    context_name = safe_name(context, "table")
    csv_path = tables_dir / f"markdown_table_{table_index:03d}_{context_name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(normalized_rows)
    return SheetSummary(
        workbook_name=source_path.name,
        sheet_name=f"markdown_table_{table_index:03d}_{context_name}",
        dimension=f"{len(normalized_rows)}x{width}",
        csv_path=csv_path,
        row_count=len(normalized_rows),
        headers=[compact_text(value) for value in normalized_rows[0]][:12],
        source="markdown",
        source_doc_index=doc_index,
        source_doc_name=source_path.name,
        context_text=context,
    )


def parse_markdown_evidence(
    source_path: Path,
    tables_dir: Path,
    max_rows: int,
    doc_index: int,
) -> tuple[list[Paragraph], list[SheetSummary], str]:
    text = read_markdown(source_path)
    lines = text.splitlines()
    paragraphs, index = _frontmatter_paragraphs(lines, source_path.name, doc_index)
    tables_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[SheetSummary] = []
    paragraph_buffer: list[str] = []
    code_buffer: list[str] = []
    in_fence = False
    fence_marker = ""
    current_heading = source_path.stem
    recent_text = ""

    def add_paragraph(style: str, value: str) -> None:
        nonlocal recent_text
        normalized = compact_text(value)
        if not normalized:
            return
        paragraphs.append(
            Paragraph(
                style=style,
                text=normalized,
                source_doc_index=doc_index,
                source_doc_name=source_path.name,
            )
        )
        if style not in {"Metadata", "CodeBlock"} and not style.startswith("Heading"):
            recent_text = normalized

    def flush_paragraph() -> None:
        if paragraph_buffer:
            add_paragraph("BodyText", " ".join(paragraph_buffer))
            paragraph_buffer.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if in_fence:
            if stripped.startswith(fence_marker):
                add_paragraph("CodeBlock", "\n".join(code_buffer))
                code_buffer.clear()
                in_fence = False
                fence_marker = ""
            else:
                code_buffer.append(line)
            index += 1
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_paragraph()
            in_fence = True
            fence_marker = stripped[:3]
            index += 1
            continue

        heading = HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            current_heading = compact_text(heading.group(2))
            recent_text = ""
            add_paragraph(f"Heading{len(heading.group(1))}", current_heading)
            index += 1
            continue

        if "|" in line and index + 1 < len(lines):
            header = split_markdown_row(line)
            if len(header) >= 2 and is_table_separator(lines[index + 1], len(header)):
                flush_paragraph()
                rows = [header]
                index += 2
                while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                    row = split_markdown_row(lines[index])
                    if len(row) != len(header):
                        break
                    rows.append(row)
                    index += 1
                if max_rows:
                    rows = rows[:max_rows]
                context = " / ".join(part for part in (current_heading, recent_text) if part)
                summaries.append(
                    _write_markdown_table(rows, tables_dir, len(summaries) + 1, source_path, doc_index, context)
                )
                continue

        list_item = LIST_RE.match(line)
        if list_item:
            flush_paragraph()
            add_paragraph("List", list_item.group(1))
        elif stripped.startswith(">"):
            flush_paragraph()
            add_paragraph("Quote", stripped.lstrip("> "))
        elif not stripped:
            flush_paragraph()
        else:
            paragraph_buffer.append(stripped)
        index += 1

    flush_paragraph()
    if code_buffer:
        add_paragraph("CodeBlock", "\n".join(code_buffer))
    return paragraphs, summaries, text


def write_markdown_evidence(
    path: Path,
    source_path: Path,
    paragraphs: list[Paragraph],
    summaries: list[SheetSummary],
    source_text: str,
) -> None:
    title = next((item.text for item in paragraphs if item.style.startswith("Heading")), source_path.stem)
    lines = [
        f"# {title}",
        "",
        f"- Source Markdown: `{source_path}`",
        f"- Normalized paragraphs: {len(paragraphs)}",
        f"- Extracted Markdown tables: {len(summaries)}",
        "",
        "## Extracted Tables",
        "",
    ]
    if summaries:
        lines.extend(
            f"- `{summary.csv_path.name}`: {summary.row_count} rows; context: {summary.context_text or 'n/a'}"
            for summary in summaries
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Source Content", "", source_text.rstrip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def extract_markdown_to_dirs(
    source_path: Path,
    extracted_dir: Path,
    tables_dir: Path,
    max_rows: int,
    doc_index: int,
) -> tuple[list[Paragraph], list[SheetSummary]]:
    paragraphs, summaries, source_text = parse_markdown_evidence(
        source_path,
        tables_dir,
        max_rows=max_rows,
        doc_index=doc_index,
    )
    write_markdown_evidence(
        extracted_dir / "extracted_document.md",
        source_path,
        paragraphs,
        summaries,
        source_text,
    )
    return paragraphs, summaries
