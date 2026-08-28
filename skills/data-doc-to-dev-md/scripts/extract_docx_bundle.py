#!/usr/bin/env python3
"""Extract DOCX or Markdown requirement evidence into a Technical Design handoff.

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
from code_unit_contract import (
    CONFIRMATION_QUESTION_ID,
    apply_proposal,
)
from requirement_bundle_inputs import (
    annotate_document_context,
    collect_requirement_evidence,
    document_meta,
    docx_paths_from_args,
    extract_document_to_dirs,
    extract_requirement_to_dirs,
    requirement_paths_from_args,
)


def run(args: argparse.Namespace) -> int:
    input_paths = requirement_paths_from_args(getattr(args, "input", None), getattr(args, "docx", None))
    primary_path = input_paths[0]

    project_name = args.project_name or safe_name(primary_path.stem)
    out_root = Path(args.out).expanduser().resolve()
    extracted_dir = out_root / "extracted"
    dev_doc_dir = out_root / "dev_doc"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    dev_doc_dir.mkdir(parents=True, exist_ok=True)

    all_paragraphs, all_table_summaries, documents, totals = collect_requirement_evidence(
        input_paths,
        extracted_dir,
        args.max_table_rows,
    )

    structured_facts = build_structured_facts(all_table_summaries, all_paragraphs)
    structured_facts["documents"] = documents
    if len(input_paths) > 1:
        structured_facts["merge_policy"] = (
            "DataEngine/waterline technical facts take precedence for tables, fields, storage, and schedules; "
            "PRD facts supplement business goals, abnormal rules, KPI logic, and UI aggregation logic. "
            "Conflicts are recorded in conflicts/questions instead of silently overwriting evidence."
        )
    question_groups = build_question_groups_v2(all_paragraphs, all_table_summaries, structured_facts)
    structured_facts["codegen_contract"] = build_codegen_contract(structured_facts, question_groups)
    apply_proposal(structured_facts)
    add_open_question(
        question_groups["blocking_codegen"],
        CONFIRMATION_QUESTION_ID,
        "blocking_codegen",
        "请确认建议的代码单元数量、每个单元覆盖的水线、参数化方案和依赖边界；确认前不得进入完整代码生成。",
    )
    (dev_doc_dir / "structured_facts.json").write_text(
        json.dumps(structured_facts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_dev_doc_v2(
        dev_doc_dir / "technical_design.md",
        primary_path,
        project_name,
        all_paragraphs,
        all_table_summaries,
        structured_facts,
    )
    write_questions_v2(dev_doc_dir / "questions.md", question_groups)

    if len(input_paths) == 1:
        print(f"extracted: {extracted_dir / 'extracted_document.md'}")
    else:
        print(f"extracted: {extracted_dir}")
    print(f"technical_design: {dev_doc_dir / 'technical_design.md'}")
    legacy_dev_doc_path = dev_doc_dir / "dev_doc.md"
    if legacy_dev_doc_path.exists():
        print(f"warning: legacy handoff retained at {legacy_dev_doc_path}; use technical_design.md for this run")
    print(f"questions: {dev_doc_dir / 'questions.md'}")
    print(f"structured_facts: {dev_doc_dir / 'structured_facts.json'}")
    print(f"documents: {len(input_paths)}")
    print(f"embedded_sheets: {totals['embedded_sheets']}")
    print(f"word_tables: {totals['word_tables']}")
    print(f"markdown_tables: {totals['markdown_tables']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract DOCX or Markdown requirements into a Technical Design handoff.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        action="append",
        nargs="+",
        help="Input .docx, .md, or .markdown paths. Repeat or mix formats for multi-document projects.",
    )
    input_group.add_argument(
        "--docx",
        action="append",
        nargs="+",
        help="Legacy DOCX-only input. Prefer --input for new workflows.",
    )
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
