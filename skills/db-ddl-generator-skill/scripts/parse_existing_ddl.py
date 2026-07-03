#!/usr/bin/env python3
"""Parse existing CREATE TABLE DDL into the standard schema contract."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CONSTRAINT_KEYWORDS = {
    "not",
    "null",
    "default",
    "comment",
    "primary",
    "constraint",
    "references",
    "collate",
    "auto_increment",
    "identity",
    "generated",
    "unique",
    "check",
    "encode",
    "compression",
}


def read_sql(path: Path) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeError:
            continue
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def ddl_column_name(row: Dict[str, str]) -> Optional[str]:
    candidates = {"create_table_query", "create_table_sql", "ddl", "sql", "statement"}
    for key in row:
        if key and key.strip().lower() in candidates:
            return key
    return None


def parse_csv_export(path: Path) -> Dict[str, Any]:
    rows = read_csv_rows(path)
    tables: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for idx, row in enumerate(rows, start=1):
        ddl_key = ddl_column_name(row)
        if not ddl_key:
            warnings.append(f"row {idx}: no DDL column such as create_table_query was found")
            continue
        sql = row.get(ddl_key) or ""
        if "CREATE TABLE" not in sql.upper():
            warnings.append(f"row {idx}: DDL column does not contain CREATE TABLE")
            continue
        try:
            schema = parse_sql(sql, source=f"{path}#row{idx}")
        except Exception as exc:
            warnings.append(f"row {idx}: failed to parse DDL: {exc}")
            continue
        if row.get("database"):
            schema["database"] = row["database"]
        if row.get("table_name"):
            schema["table_name"] = row["table_name"]
        tables.append(schema)
    return {"source": str(path), "tables": tables, "warnings": warnings}


def clean_ident(identifier: str) -> str:
    text = identifier.strip().rstrip(",")
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    if text.startswith(("`", '"')) and text.endswith(("`", '"')):
        return text[1:-1]
    return text


def split_qualified_name(name: str) -> Tuple[Optional[str], Optional[str], str]:
    parts = [clean_ident(part) for part in re.split(r"\.", name.strip()) if part.strip()]
    if len(parts) == 1:
        return None, None, parts[0]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return parts[-3], parts[-2], parts[-1]


def find_matching_paren(sql: str, start_idx: int) -> int:
    depth = 0
    quote: Optional[str] = None
    idx = start_idx
    while idx < len(sql):
        char = sql[idx]
        if quote:
            if char == quote:
                if idx + 1 < len(sql) and sql[idx + 1] == quote:
                    idx += 2
                    continue
                quote = None
            idx += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
        idx += 1
    raise ValueError("unclosed CREATE TABLE column list")


def split_top_level(block: str) -> List[str]:
    items: List[str] = []
    start = 0
    depth = 0
    quote: Optional[str] = None
    idx = 0
    while idx < len(block):
        char = block[idx]
        if quote:
            if char == quote:
                if idx + 1 < len(block) and block[idx + 1] == quote:
                    idx += 2
                    continue
                quote = None
            idx += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            item = block[start:idx].strip()
            if item:
                items.append(item)
            start = idx + 1
        idx += 1
    if quote:
        return split_top_level_loose(block)
    tail = block[start:].strip()
    if tail:
        items.append(tail)
    return items


def split_top_level_loose(block: str) -> List[str]:
    items: List[str] = []
    start = 0
    depth = 0
    for idx, char in enumerate(block):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            item = block[start:idx].strip()
            if item:
                items.append(item)
            start = idx + 1
    tail = block[start:].strip()
    if tail:
        items.append(tail)
    return items


def first_token(item: str) -> Tuple[str, str]:
    text = item.strip()
    if text.startswith("["):
        end = text.find("]")
        return text[: end + 1], text[end + 1 :].strip()
    if text.startswith(("`", '"')):
        quote = text[0]
        end = text.find(quote, 1)
        return text[: end + 1], text[end + 1 :].strip()
    parts = text.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def extract_comment(item: str) -> str:
    match = re.search(r"\bCOMMENT\s+'((?:''|[^'])*)'", item, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).replace("''", "'") if match else ""


def extract_default(item: str) -> Optional[str]:
    match = re.search(
        r"\bDEFAULT\s+(.+?)(?=\s+COMMENT\b|\s+NOT\s+NULL\b|\s+NULL\b|\s+PRIMARY\b|\s+CONSTRAINT\b|$)",
        item,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip().rstrip(",")


def parse_type(rest: str) -> str:
    tokens = rest.split()
    collected: List[str] = []
    depth = 0
    for token in tokens:
        bare = token.strip().strip(",").lower()
        if depth == 0 and bare in CONSTRAINT_KEYWORDS:
            break
        collected.append(token)
        depth += token.count("(") - token.count(")")
    return " ".join(collected).strip()


def parse_column(item: str) -> Optional[Dict[str, Any]]:
    token, rest = first_token(item)
    name = clean_ident(token)
    if not name:
        return None
    lowered = name.lower()
    if lowered in {"constraint", "primary", "key", "index", "unique", "foreign", "check"}:
        return None
    source_type = parse_type(rest)
    if not source_type:
        return None
    lower_item = item.lower()
    nullable = "not null" not in lower_item
    primary = "primary key" in lower_item
    return {
        "name": name,
        "source_type": source_type,
        "type": source_type,
        "nullable": False if primary else nullable,
        "default": extract_default(item),
        "primary_key": primary,
        "index": False,
        "comment": extract_comment(item),
        "remarks": "",
    }


def parse_column_names(text: str) -> List[str]:
    match = re.search(r"\((.*?)\)", text, flags=re.DOTALL)
    if not match:
        return []
    return [clean_ident(part.strip()) for part in split_top_level(match.group(1))]


def detect_dialect(sql: str) -> str:
    lower = sql.lower()
    if "replicated" in lower or "mergetree" in lower or " order by " in lower and "`" in sql:
        return "clickhouse"
    if "engine=innodb" in lower or "auto_increment" in lower or "`" in sql:
        return "mysql"
    if "[" in sql and "]" in sql or "identity(" in lower or "sp_addextendedproperty" in lower:
        return "mssql"
    if "comment on column" in lower or "::" in lower or "jsonb" in lower:
        return "postgres"
    return "unknown"


def apply_postgres_comments(sql: str, schema: Dict[str, Any]) -> None:
    table_lookup = {column["name"].lower(): column for column in schema["columns"]}
    for match in re.finditer(
        r"COMMENT\s+ON\s+COLUMN\s+([A-Za-z0-9_\".]+)\s+IS\s+'((?:''|[^'])*)'",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        qualified, comment = match.groups()
        column_name = clean_ident(qualified.split(".")[-1])
        column = table_lookup.get(column_name.lower())
        if column:
            column["comment"] = comment.replace("''", "'")
    table_match = re.search(
        r"COMMENT\s+ON\s+TABLE\s+([A-Za-z0-9_\".]+)\s+IS\s+'((?:''|[^'])*)'",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if table_match:
        schema["table_comment"] = table_match.group(2).replace("''", "'")


def parse_tail(tail: str, schema: Dict[str, Any]) -> None:
    engine_match = re.search(r"\bENGINE\s*=\s*(.+?)(?=\s+PARTITION\s+BY|\s+ORDER\s+BY|\s+PRIMARY\s+KEY|\s+SETTINGS|;|$)", tail, re.I | re.S)
    if engine_match:
        schema["engine"] = " ".join(engine_match.group(1).split())
    partition_match = re.search(r"\bPARTITION\s+BY\s+(.+?)(?=\s+ORDER\s+BY|\s+PRIMARY\s+KEY|\s+SETTINGS|;|$)", tail, re.I | re.S)
    if partition_match:
        schema["partition_by"] = [partition_match.group(1).strip()]
    order_match = re.search(r"\bORDER\s+BY\s+(.+?)(?=\s+PRIMARY\s+KEY|\s+SETTINGS|;|$)", tail, re.I | re.S)
    if order_match:
        expr = order_match.group(1).strip()
        schema["order_by"] = parse_column_names(expr) if expr.startswith("(") else [expr]
    primary_match = re.search(r"\bPRIMARY\s+KEY\s+(.+?)(?=\s+SETTINGS|;|$)", tail, re.I | re.S)
    if primary_match:
        expr = primary_match.group(1).strip()
        schema["primary_key"] = parse_column_names(expr) if expr.startswith("(") else [expr]
    settings_match = re.search(r"\bSETTINGS\s+(.+?)(?:;|$)", tail, re.I | re.S)
    if settings_match:
        schema["settings_raw"] = " ".join(settings_match.group(1).split())


def parse_sql(sql: str, source: Optional[str] = None) -> Dict[str, Any]:
    create_match = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_`\"\[\].]+)",
        sql,
        flags=re.IGNORECASE,
    )
    if not create_match:
        raise ValueError("no CREATE TABLE statement found")
    raw_name = create_match.group(1)
    database, schema_name, table_name = split_qualified_name(raw_name)
    open_idx = sql.find("(", create_match.end())
    try:
        close_idx = find_matching_paren(sql, open_idx)
    except ValueError:
        engine_boundary = re.search(r"\)\s+ENGINE\b", sql[open_idx:], flags=re.IGNORECASE)
        if not engine_boundary:
            raise
        close_idx = open_idx + engine_boundary.start()
    block = sql[open_idx + 1 : close_idx]
    tail = sql[close_idx + 1 :]

    schema: Dict[str, Any] = {
        "database": database,
        "schema": schema_name,
        "table_name": table_name,
        "table_comment": "",
        "columns": [],
        "primary_key": [],
        "indexes": [],
        "partition_by": [],
        "order_by": [],
        "engine": "",
        "dialect": detect_dialect(sql),
        "source": source,
        "warnings": [],
    }

    for item in split_top_level(block):
        lowered = item.strip().lower()
        if lowered.startswith("primary key") or " primary key " in lowered and lowered.startswith("constraint"):
            schema["primary_key"] = parse_column_names(item)
            continue
        if lowered.startswith(("key ", "index ", "unique key", "unique index")):
            token, rest = first_token(item)
            if token.lower() in {"key", "index"}:
                index_name, index_rest = first_token(rest)
            else:
                _, after_unique = first_token(rest)
                index_name, index_rest = first_token(after_unique)
            schema["indexes"].append({"name": clean_ident(index_name), "columns": parse_column_names(index_rest)})
            continue
        column = parse_column(item)
        if column:
            schema["columns"].append(column)
            if column["primary_key"] and column["name"] not in schema["primary_key"]:
                schema["primary_key"].append(column["name"])

    for column in schema["columns"]:
        if column["name"] in schema["primary_key"]:
            column["primary_key"] = True
            column["nullable"] = False

    for match in re.finditer(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([A-Za-z0-9_`\"\[\]]+)\s+ON\s+[A-Za-z0-9_`\"\[\].]+\s+(?:USING\s+\w+\s+)?\((.*?)\)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        schema["indexes"].append({"name": clean_ident(match.group(1)), "columns": parse_column_names(f"({match.group(2)})")})

    apply_postgres_comments(sql, schema)
    parse_tail(tail, schema)
    if not schema["columns"]:
        schema["warnings"].append("no columns parsed from CREATE TABLE")
    return schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.input.suffix.lower() == ".csv":
        schema = parse_csv_export(args.input)
    else:
        sql = read_sql(args.input)
        schema = parse_sql(sql, source=str(args.input))
    output = json.dumps(schema, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
