#!/usr/bin/env python3
"""Normalize simple source references without interpreting business expressions."""

from __future__ import annotations

import re
from typing import Any


_PART = r'(?:[A-Za-z0-9_]+|`[A-Za-z0-9_]+`|"[A-Za-z0-9_]+"|\[[A-Za-z0-9_]+\])'
_IDENTIFIER = re.compile(rf'{_PART}(?:\s*\.\s*{_PART})*')
_FILE_LOCATION = re.compile(r'^(?:[/\\]|[A-Za-z]:[/\\]|(?:fs|gateway)://(?=\S))', re.IGNORECASE)
_STORAGES = (("hbase", ("hbase",)), ("clickhouse", ("clickhouse",)),
             ("mssql", ("mssql", "sql server")), ("mysql", ("mysql",)))


def is_file_location(value: Any) -> bool:
    return bool(_FILE_LOCATION.match(str(value or "").strip()))


def source_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if is_file_location(text) else " ".join(text.split())


def simple_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(text):
        return ""
    return ".".join(part.strip().strip('`"[]') for part in text.split("."))


def column_identifier(value: Any) -> str:
    name = simple_identifier(value)
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else ""


def source_identity(value: Any) -> str:
    text = str(value or "").strip()
    if is_file_location(text):
        return text  # Remote file/path case rules are not implied by the host OS.
    return (simple_identifier(text) or " ".join(text.split())).lower()


def storage_kind(value: Any, location: Any = "") -> str:
    text = " ".join(str(value or "").split()).lower()
    for kind, markers in _STORAGES:
        if any(marker in text for marker in markers):
            return kind
    if (is_file_location(location) or "gateway" in text or "文件" in text
            or re.search(r"(?<![a-z0-9])fs(?![a-z0-9])", text)):
        return "fs"
    location_text = str(location or "").lower()
    for kind, markers in _STORAGES:
        if any(marker in location_text for marker in markers):
            return kind
    return "other"


def storage_identity(value: Any) -> str:
    kind = storage_kind(value)
    return kind if kind != "other" else " ".join(str(value or "").split()).lower()


def selected_columns(value: Any) -> list[str]:
    """Split only lists of simple columns; retain formulas as one evidence item."""
    result: list[str] = []
    seen: set[str] = set()
    for item in [value] if isinstance(value, str) else value or []:
        text = " ".join(str(item or "").split())
        if not text:
            continue
        parts = [column_identifier(part) for part in re.split(r"[,，;；\s]+", text) if part]
        names = parts if all(parts) else [text]
        for name in names:
            if name not in seen:
                result.append(name)
                seen.add(name)
    return result
