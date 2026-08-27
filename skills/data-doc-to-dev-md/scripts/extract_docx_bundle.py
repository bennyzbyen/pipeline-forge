#!/usr/bin/env python3
"""Extract DOCX requirement evidence into a Technical Design handoff.

The public imports from the historical single-file implementation remain
available here. Implementation is separated by responsibility into OOXML
extraction, structured-fact construction, delivery rendering, and contract
modules; this file owns only CLI orchestration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from docx_bundle_contract import (
    READINESS_QUESTION_IDS,
    add_open_question,
    build_codegen_contract,
    build_question_groups_v2,
    detect_component_kind,
    detect_project_type,
    format_open_question,
    readiness_question_id,
    write_questions_v2,
)
from docx_bundle_facts import (
    build_structured_facts,
    hbase_targets_from_paragraphs,
    infer_bysku_report_component_hint,
    project_text_blob,
    report_field_rows,
    report_targets_from_paragraphs,
)
from docx_bundle_tables import (
    add_provenance,
    append_unique_by_key,
    best_context_match,
    cell_value,
    cell_value_contains,
    detect_header_index,
    first_fields,
    has_header,
    has_headers,
    header_score,
    make_unique_headers,
    normalize_header,
    normalized_table_key,
    preamble_text,
    provenance_from_summary,
    read_csv_dicts,
    read_csv_rows,
    read_csv_table,
    split_cell_lines,
    split_field_names,
    split_table_names,
    table_name_from_text,
)
from docx_bundle_ooxml import (
    NS_REL,
    NS_W,
    NS_X,
    Paragraph,
    SheetSummary,
    cell_text,
    col_index,
    compact_text,
    element_text,
    embedding_rel_ids,
    extract_docx_paragraphs,
    extract_embedded_tables,
    extract_embedding_contexts,
    extract_word_tables,
    extract_xlsx_tables,
    io_bytes,
    iter_sheet_rows,
    local_name,
    qn,
    read_document_relationships,
    read_shared_strings,
    read_workbook_relationships,
    read_zip_text,
    safe_name,
    sheet_target_path,
    target_basename,
    word_cell_text,
)
from docx_bundle_render import (
    facts_summary_lines,
    flattened_report_fields,
    markdown_list,
    markdown_table,
    paragraphs_matching,
    write_dev_doc_v2,
    write_extracted_markdown,
)
from technical_contract import build_contract_v2


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
    question_groups = build_question_groups_v2(all_paragraphs, all_table_summaries, structured_facts)
    structured_facts["codegen_contract"] = build_codegen_contract(structured_facts, question_groups)
    (dev_doc_dir / "structured_facts.json").write_text(
        json.dumps(structured_facts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_dev_doc_v2(
        dev_doc_dir / "technical_design.md",
        docx_path,
        project_name,
        all_paragraphs,
        all_table_summaries,
        structured_facts,
    )
    write_questions_v2(dev_doc_dir / "questions.md", question_groups)

    if len(docx_paths) == 1:
        print(f"extracted: {extracted_dir / 'extracted_document.md'}")
    else:
        print(f"extracted: {extracted_dir}")
    print(f"technical_design: {dev_doc_dir / 'technical_design.md'}")
    legacy_dev_doc_path = dev_doc_dir / "dev_doc.md"
    if legacy_dev_doc_path.exists():
        print(f"warning: legacy handoff retained at {legacy_dev_doc_path}; use technical_design.md for this run")
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
