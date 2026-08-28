#!/usr/bin/env python3
"""Validate and collect mixed requirement-document inputs."""

from __future__ import annotations

from pathlib import Path

from docx_bundle_ooxml import (
    Paragraph,
    SheetSummary,
    extract_docx_paragraphs,
    extract_embedded_tables,
    extract_word_tables,
    safe_name,
)
from docx_bundle_render import write_extracted_markdown
from requirement_bundle_markdown import MARKDOWN_SUFFIXES, extract_markdown_to_dirs


SUPPORTED_INPUT_SUFFIXES = {".docx", *MARKDOWN_SUFFIXES}


def _flatten_path_args(raw_values: list[list[str]] | list[str] | None) -> list[str]:
    values: list[str] = []
    for item in raw_values or []:
        if isinstance(item, list):
            values.extend(item)
        else:
            values.append(item)
    return values


def docx_paths_from_args(raw_docx: list[list[str]] | list[str]) -> list[Path]:
    paths = [Path(value).expanduser().resolve() for value in _flatten_path_args(raw_docx)]
    if not paths:
        raise ValueError("at least one --docx input is required")
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() != ".docx":
            raise ValueError(f"expected .docx input, got: {path}")
    return paths


def requirement_paths_from_args(
    raw_input: list[list[str]] | list[str] | None,
    raw_docx: list[list[str]] | list[str] | None,
) -> list[Path]:
    if raw_docx:
        return docx_paths_from_args(raw_docx)
    paths = [Path(value).expanduser().resolve() for value in _flatten_path_args(raw_input)]
    if not paths:
        raise ValueError("at least one --input or --docx input is required")
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_INPUT_SUFFIXES))
            raise ValueError(f"expected one of {supported}, got: {path}")
    return paths


def annotate_document_context(
    paragraphs: list[Paragraph],
    summaries: list[SheetSummary],
    source_path: Path,
    doc_index: int,
) -> None:
    for paragraph in paragraphs:
        paragraph.source_doc_index = doc_index
        paragraph.source_doc_name = source_path.name
    for summary in summaries:
        summary.source_doc_index = doc_index
        summary.source_doc_name = source_path.name


def extract_document_to_dirs(
    docx_path: Path,
    extracted_dir: Path,
    tables_dir: Path,
    word_tables_dir: Path,
    max_table_rows: int,
    doc_index: int,
) -> tuple[list[Paragraph], int, list[SheetSummary], list[SheetSummary]]:
    paragraphs, table_count, _embedded = extract_docx_paragraphs(docx_path)
    word_summaries = extract_word_tables(docx_path, word_tables_dir, max_rows=max_table_rows)
    sheet_summaries = extract_embedded_tables(docx_path, tables_dir, max_rows=max_table_rows)
    annotate_document_context(paragraphs, sheet_summaries + word_summaries, docx_path, doc_index)
    write_extracted_markdown(
        extracted_dir / "extracted_document.md",
        docx_path,
        paragraphs,
        table_count,
        sheet_summaries + word_summaries,
    )
    return paragraphs, table_count, sheet_summaries, word_summaries


def extract_requirement_to_dirs(
    source_path: Path,
    extracted_dir: Path,
    max_table_rows: int,
    doc_index: int,
) -> tuple[list[Paragraph], int, list[SheetSummary], list[SheetSummary], list[SheetSummary]]:
    if source_path.suffix.lower() == ".docx":
        paragraphs, table_count, sheet_summaries, word_summaries = extract_document_to_dirs(
            source_path,
            extracted_dir,
            extracted_dir / "extracted_tables",
            extracted_dir / "word_tables",
            max_table_rows,
            doc_index,
        )
        return paragraphs, table_count, sheet_summaries, word_summaries, []
    paragraphs, markdown_summaries = extract_markdown_to_dirs(
        source_path,
        extracted_dir,
        extracted_dir / "markdown_tables",
        max_table_rows,
        doc_index,
    )
    return paragraphs, 0, [], [], markdown_summaries


def document_meta(
    source_path: Path,
    doc_index: int,
    paragraphs: list[Paragraph],
    table_count: int,
    embedded_count: int,
    word_count: int,
    markdown_count: int,
) -> dict:
    title = next(
        (paragraph.text for paragraph in paragraphs if paragraph.style == "Title" or paragraph.style.startswith("Heading")),
        paragraphs[0].text if paragraphs else source_path.stem,
    )
    return {
        "index": doc_index,
        "name": source_path.name,
        "path": str(source_path),
        "format": "docx" if source_path.suffix.lower() == ".docx" else "markdown",
        "title": title,
        "paragraphs": len(paragraphs),
        "word_tables": table_count,
        "embedded_sheets": embedded_count,
        "word_table_csvs": word_count,
        "markdown_tables": markdown_count,
    }


def collect_requirement_evidence(
    input_paths: list[Path],
    extracted_dir: Path,
    max_table_rows: int,
) -> tuple[list[Paragraph], list[SheetSummary], list[dict], dict[str, int]]:
    all_paragraphs: list[Paragraph] = []
    all_summaries: list[SheetSummary] = []
    documents: list[dict] = []
    totals = {"embedded_sheets": 0, "word_tables": 0, "markdown_tables": 0}
    for doc_index, source_path in enumerate(input_paths, start=1):
        doc_dir = extracted_dir
        if len(input_paths) > 1:
            doc_dir = extracted_dir / f"doc_{doc_index:03d}_{safe_name(source_path.stem)}"
            doc_dir.mkdir(parents=True, exist_ok=True)
        paragraphs, table_count, embedded, word_tables, markdown_tables = extract_requirement_to_dirs(
            source_path,
            doc_dir,
            max_table_rows,
            doc_index,
        )
        all_paragraphs.extend(paragraphs)
        all_summaries.extend(embedded + word_tables + markdown_tables)
        totals["embedded_sheets"] += len(embedded)
        totals["word_tables"] += len(word_tables)
        totals["markdown_tables"] += len(markdown_tables)
        documents.append(
            document_meta(
                source_path,
                doc_index,
                paragraphs,
                table_count,
                len(embedded),
                len(word_tables),
                len(markdown_tables),
            )
        )
    return all_paragraphs, all_summaries, documents, totals
