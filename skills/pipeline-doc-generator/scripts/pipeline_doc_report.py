"""Report table identities and internal dictionary references; no I/O."""
from __future__ import annotations


def storage_tables(target):
    """Prefer explicit per-storage identities; support legacy dual-write facts."""
    if target.get("storage_tables"):
        return target["storage_tables"]
    location = str(target.get("location") or "")
    labels = [label for label in ("HBase", "ClickHouse", "MySQL", "MSSQL", "PostgreSQL", "Blob")
              if label.lower() in location.lower()]
    database, table = str(target.get("database") or ""), str(target.get("table") or "")
    physical = table if not database or table.startswith(database + ".") else database + "." + table
    return {label: physical for label in labels or [location or "目标"]}


def target_reference(facts, row):
    """Resolve stable IDs first; legacy names must identify exactly one target."""
    key = row.get("target_id") or row.get("data_item")
    targets = facts.get("targets") or []
    matches = [i for i, target in enumerate(targets, 1) if key == target.get("id")]
    if not matches and not row.get("target_id"):
        matches = [i for i, target in enumerate(targets, 1)
                   if key and key in [target.get("table"), target.get("target_name"), *storage_tables(target).values()]]
    if len(matches) != 1:
        raise ValueError("Catalog row needs a target_id identifying exactly one target")
    return f"参见 3.1.{matches[0]}"


def field_logic(field):
    """Keep unique legacy source-field information in the single logic column."""
    source_field = str(field.get("source_field") or "").strip()
    logic = str(field.get("logic") or "").strip()
    if source_field and source_field not in logic:
        return f"源字段：{source_field}" + (f"；{logic}" if logic else "")
    return logic or source_field
