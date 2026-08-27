#!/usr/bin/env python3
"""Verify the legacy extractor import surface after modularization."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys

import docx_bundle_contract
import docx_bundle_facts
import docx_bundle_ooxml
import docx_bundle_render
import docx_bundle_tables
import extract_docx_bundle


MODULE_EXPORTS = {
    docx_bundle_ooxml: (
        "NS_W",
        "NS_X",
        "NS_REL",
        "qn",
        "safe_name",
        "read_zip_text",
        "local_name",
        "compact_text",
        "target_basename",
        "Paragraph",
        "SheetSummary",
        "extract_docx_paragraphs",
        "read_document_relationships",
        "element_text",
        "embedding_rel_ids",
        "extract_embedding_contexts",
        "col_index",
        "read_shared_strings",
        "read_workbook_relationships",
        "sheet_target_path",
        "cell_text",
        "iter_sheet_rows",
        "extract_xlsx_tables",
        "io_bytes",
        "extract_embedded_tables",
        "word_cell_text",
        "extract_word_tables",
    ),
    docx_bundle_tables: (
        "cell_value",
        "cell_value_contains",
        "normalize_header",
        "has_header",
        "split_cell_lines",
        "split_field_names",
        "split_table_names",
        "read_csv_rows",
        "make_unique_headers",
        "header_score",
        "detect_header_index",
        "read_csv_table",
        "read_csv_dicts",
        "has_headers",
        "provenance_from_summary",
        "add_provenance",
        "preamble_text",
        "table_name_from_text",
        "normalized_table_key",
        "append_unique_by_key",
        "best_context_match",
        "first_fields",
    ),
    docx_bundle_facts: (
        "report_targets_from_paragraphs",
        "hbase_targets_from_paragraphs",
        "report_field_rows",
        "build_structured_facts",
        "project_text_blob",
        "infer_bysku_report_component_hint",
    ),
    docx_bundle_render: (
        "paragraphs_matching",
        "markdown_list",
        "write_extracted_markdown",
        "markdown_table",
        "facts_summary_lines",
        "flattened_report_fields",
        "write_dev_doc_v2",
    ),
    docx_bundle_contract: (
        "detect_project_type",
        "detect_component_kind",
        "READINESS_QUESTION_IDS",
        "add_open_question",
        "readiness_question_id",
        "format_open_question",
        "build_question_groups_v2",
        "build_codegen_contract",
        "write_questions_v2",
    ),
}


def main() -> int:
    checked: list[str] = []
    for owner, names in MODULE_EXPORTS.items():
        for name in names:
            facade_value = getattr(extract_docx_bundle, name)
            owner_value = getattr(owner, name)
            assert facade_value is owner_value, f"legacy export {name} does not re-export its owner symbol"
            checked.append(name)

    parser = extract_docx_bundle.build_parser()
    parsed = parser.parse_args(
        [
            "--docx",
            "first.docx",
            "second.docx",
            "--out",
            "out",
            "--project-name",
            "fixture",
            "--max-table-rows",
            "25",
        ]
    )
    assert parsed.docx == [["first.docx", "second.docx"]]
    assert parsed.out == "out"
    assert parsed.project_name == "fixture"
    assert parsed.max_table_rows == 25
    assert list(inspect.signature(extract_docx_bundle.main).parameters) == ["argv"]

    entrypoint_path = Path(extract_docx_bundle.__file__)
    help_result = subprocess.run(
        [sys.executable, str(entrypoint_path), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "--docx" in help_result.stdout and "--max-table-rows" in help_result.stdout

    missing_args_result = subprocess.run(
        [sys.executable, str(entrypoint_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_args_result.returncode == 2, missing_args_result
    assert "--docx" in missing_args_result.stderr and "--out" in missing_args_result.stderr

    entrypoint_lines = len(entrypoint_path.read_text(encoding="utf-8").splitlines())
    assert entrypoint_lines <= 350, entrypoint_lines
    implementation_paths = sorted(entrypoint_path.parent.glob("docx_bundle_*.py"))
    implementation_line_counts = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in implementation_paths
    }
    implementation_function_lines = {
        f"{path.name}:{node.name}": node.end_lineno - node.lineno + 1
        for path in implementation_paths
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert implementation_line_counts
    assert max(implementation_line_counts.values()) <= 800, implementation_line_counts
    assert max(implementation_function_lines.values()) <= 200, implementation_function_lines
    print(
        json.dumps(
            {
                "status": "passed",
                "legacy_exports_checked": len(checked),
                "entrypoint_lines": entrypoint_lines,
                "max_implementation_lines": max(implementation_line_counts.values()),
                "max_function_lines": max(implementation_function_lines.values()),
                "implementation_line_counts": implementation_line_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
