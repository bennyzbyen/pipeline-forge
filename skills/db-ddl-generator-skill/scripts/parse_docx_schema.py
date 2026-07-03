#!/usr/bin/env python3
"""Extract field definitions from DOCX embedded Excel files and Word tables."""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import parse_excel_schema


def header_key(value: Any) -> str:
    return parse_excel_schema.norm_header(value)


def target_header_map(row: List[Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(row):
        key = header_key(cell)
        if not key:
            continue
        if key in {"clickhouse表", "clickhousetable", "clickhousetargetname", "clickhousetarget"}:
            mapping["clickhouse_table"] = idx
        elif key in {"hbase表", "hbasetable", "hbasetargetname", "hbasetarget"}:
            mapping["hbase_table"] = idx
        elif key in {"业务描述", "businessdescription", "description", "desc"}:
            mapping["business_description"] = idx
        elif key in {"报表类型", "reporttype"}:
            mapping["report_type"] = idx
        elif key in {"所属类别", "category", "catalog"}:
            mapping["category"] = idx
        elif key in {"hbase数据范围", "hbasescope", "hbasedatarange"}:
            mapping["hbase_range"] = idx
    return mapping


def split_table_name(full_name: str) -> Dict[str, str]:
    text = parse_excel_schema.cell_text(full_name)
    parts = [part for part in text.split(".") if part]
    if len(parts) >= 2:
        return {"database": parts[-2], "table_name": parts[-1], "full_name": f"{parts[-2]}.{parts[-1]}"}
    return {"database": "", "table_name": text, "full_name": text}


def extract_targets_from_rows(rows: List[List[Any]], source: str) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    header_idx = None
    mapping: Dict[str, int] = {}
    for idx, row in enumerate(rows[:30]):
        candidate = target_header_map(row)
        if "clickhouse_table" in candidate:
            header_idx = idx
            mapping = candidate
            break
    if header_idx is None:
        return targets

    for row in rows[header_idx + 1 :]:
        clickhouse_idx = mapping["clickhouse_table"]
        clickhouse_value = parse_excel_schema.cell_text(row[clickhouse_idx]) if clickhouse_idx < len(row) else ""
        if not clickhouse_value:
            continue
        target = split_table_name(clickhouse_value)
        target["source"] = source
        for key, col_idx in mapping.items():
            if key == "clickhouse_table":
                continue
            target[key] = parse_excel_schema.cell_text(row[col_idx]) if col_idx < len(row) else ""
        targets.append(target)
    return targets


def is_target_name_list_schema(schema: Dict[str, Any], targets: List[Dict[str, Any]]) -> bool:
    if not targets or not schema.get("columns"):
        return False
    target_names = {target.get("table_name") for target in targets} | {target.get("full_name") for target in targets}
    target_names = {name for name in target_names if name}
    columns = schema.get("columns", [])
    match_count = sum(1 for column in columns if column.get("name") in target_names)
    all_default_string = all((column.get("source_type") or "").lower() == "string" for column in columns)
    return all_default_string and match_count >= max(3, len(columns) // 2)


def bind_targets_to_dictionaries(tables: List[Dict[str, Any]], targets: List[Dict[str, Any]], warnings: List[str]) -> List[Dict[str, Any]]:
    if not targets:
        return tables
    dictionaries = [table for table in tables if not is_target_name_list_schema(table, targets)]
    skipped = len(tables) - len(dictionaries)
    if skipped:
        warnings.append(f"skipped {skipped} target/name-list tables that are not field dictionaries")
    for schema, target in zip(dictionaries, targets):
        schema["source_table_name"] = schema.get("table_name")
        schema["database"] = target.get("database") or schema.get("database")
        schema["table_name"] = target.get("table_name") or schema.get("table_name")
        schema["table_comment"] = target.get("business_description") or schema.get("table_comment", "")
        schema["hbase_table"] = target.get("hbase_table", "")
        schema["target"] = target
    if len(dictionaries) != len(targets):
        warnings.append(f"target count {len(targets)} does not match dictionary count {len(dictionaries)}; mapped by order where possible")
    return dictionaries


def extract_embedded_excels(docx_path: Path, table_name: Optional[str] = None) -> Dict[str, Any]:
    tables: List[Dict[str, Any]] = []
    targets: List[Dict[str, Any]] = []
    warnings: List[str] = []
    with zipfile.ZipFile(docx_path) as zf, tempfile.TemporaryDirectory() as tmp_dir:
        entries = [entry for entry in zf.namelist() if entry.startswith("word/embeddings/")]
        for entry in entries:
            suffix = Path(entry).suffix.lower()
            if suffix not in {".xlsx", ".xlsm"}:
                warnings.append(f"{entry}: embedded object is not xlsx/xlsm; skipped")
                continue
            tmp_path = Path(tmp_dir) / Path(entry).name
            tmp_path.write_bytes(zf.read(entry))
            try:
                sheet_data_list = parse_excel_schema.read_xlsx_sheets(tmp_path, sheet=None)
            except Exception as exc:  # keep parsing other embeddings
                warnings.append(f"{entry}: failed to parse embedded workbook: {exc}")
                continue
            for sheet_data in sheet_data_list:
                targets.extend(extract_targets_from_rows(sheet_data["rows"], source=f"{docx_path}!/{entry}#{sheet_data['sheet_name']}"))
            schemas: List[Dict[str, Any]] = []
            for sheet_data in sheet_data_list:
                schema = parse_excel_schema.normalize_schema_from_rows(
                    sheet_data["rows"],
                    table_name=table_name or sheet_data["sheet_name"],
                    source=f"{docx_path}!/{entry}#{sheet_data['sheet_name']}",
                )
                if schema.get("columns"):
                    schemas.append(schema)
            for schema in schemas:
                schema["source"] = f"{docx_path}!/{entry}"
                if not schema.get("table_name"):
                    schema["table_name"] = Path(entry).stem
                if schema.get("warnings"):
                    warnings.append(f"{schema.get('table_name')}: {len(schema['warnings'])} field-level warnings; see tables[].warnings")
                tables.append(schema)
    tables = bind_targets_to_dictionaries(tables, targets, warnings)
    return {"tables": tables, "targets": targets, "warnings": warnings}


def extract_word_tables(docx_path: Path, table_name: Optional[str] = None) -> Dict[str, Any]:
    tables: List[Dict[str, Any]] = []
    warnings: List[str] = []
    try:
        from docx import Document
    except ImportError:
        return {"tables": [], "warnings": ["python-docx is not installed; skipped ordinary Word tables"]}

    document = Document(str(docx_path))
    for idx, table in enumerate(document.tables, start=1):
        rows: List[List[Any]] = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        schema = parse_excel_schema.normalize_schema_from_rows(
            rows,
            table_name=table_name or f"{docx_path.stem}_table_{idx}",
            source=f"{docx_path}#word_table_{idx}",
        )
        if schema.get("columns"):
            if schema.get("warnings"):
                warnings.append(f"{schema.get('table_name')}: {len(schema['warnings'])} field-level warnings; see tables[].warnings")
            tables.append(schema)
    if not tables:
        warnings.append("no ordinary Word table matched field-definition headers")
    return {"tables": tables, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--table", help="Target table name to assign when source does not provide one")
    parser.add_argument("--output", type=Path, help="Write JSON output to this path")
    parser.add_argument("--prefer", choices=["embedded", "tables", "all"], default="all")
    args = parser.parse_args()

    all_tables: List[Dict[str, Any]] = []
    warnings: List[str] = []
    targets: List[Dict[str, Any]] = []

    if args.prefer in {"embedded", "all"}:
        embedded = extract_embedded_excels(args.input, table_name=args.table)
        all_tables.extend(embedded["tables"])
        targets.extend(embedded.get("targets", []))
        warnings.extend(embedded["warnings"])

    if args.prefer in {"tables", "all"}:
        word_tables = extract_word_tables(args.input, table_name=args.table)
        all_tables.extend(word_tables["tables"])
        warnings.extend(word_tables["warnings"])

    result: Dict[str, Any] = {
        "source": str(args.input),
        "targets": targets,
        "tables": all_tables,
        "warnings": warnings,
    }
    if len(all_tables) == 1:
        result.update(all_tables[0])
    elif not all_tables:
        result["warnings"].append("no field definitions detected; ask user for column name, type, and nullable columns")

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
