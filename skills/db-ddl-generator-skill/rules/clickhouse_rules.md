# ClickHouse Rules

## QA Template

- Usually omit `ON CLUSTER`.
- Prefer `ReplacingMergeTree(version_column)` when a version/update timestamp column exists; otherwise use `MergeTree`.
- Keep partition/order expressions simple and explicit.

## PROD Template

- Include `ON CLUSTER cl_1shards_2replicas` when the user says production creation used it, even if exported DDL omits it.
- Prefer `ReplicatedReplacingMergeTree(path, '{replica}', version_column)` when a version/update timestamp column exists.
- Use ZooKeeper path format:
  `/clickhouse/databases/{database}/tables/{shard_name}/{table_name}`
- Include `PARTITION BY`, `ORDER BY`, optional `PRIMARY KEY`, and `SETTINGS index_granularity = 8192`.

## Key Constraints

- Do not put `Nullable(...)` columns into `ORDER BY`, `PRIMARY KEY`, or partition keys unless the source cluster explicitly allows nullable keys and the user accepts the risk.
- Partition field types should not be changed casually. Preserve `String`, `Date`, `DateTime`, or numeric partition semantics from source DDL.
- If a key column was nullable in the source, report the conflict and either:
  - keep it nullable and warn that ClickHouse key settings may fail, or
  - convert it to non-nullable only when the source/default semantics justify it.

## COT Report Convention

- For COT/DataEngine report tables, when both `period` and `code` columns exist, generate:
  `PARTITION BY period`
  `ORDER BY (period, code)`
- In that case, make `period` and `code` non-nullable in the generated ClickHouse DDL.
- Do not apply this convention when either column is missing or the user explicitly provides other partition/order fields.

## Type Notes

- String: use `String`; use `LowCardinality(String)` only when cardinality is known to be low or source already uses it.
- Decimal: preserve precision/scale as `Decimal(p, s)`.
- Date/time: use `Date`, `DateTime`, or `DateTime64` according to source precision.
- Int/Float: map to explicit widths (`Int32`, `Int64`, `Float64`) when possible.
- Comments use inline `COMMENT 'text'` after the type/default clause.
