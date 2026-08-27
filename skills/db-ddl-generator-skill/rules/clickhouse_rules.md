# ClickHouse Rules

## Deployment Profiles

- Require an explicit engine and `ORDER BY` in QA and PROD.
- Add `ON CLUSTER` only when the confirmed profile names a cluster.
- Require an explicit replication path for replicated engines.
- Require an explicit version column when replacement semantics depend on one; never pick a datetime column merely because it exists.

- Environment names do not imply engine, cluster, or replication settings.
- Source production DDL may be preserved as an explicit profile, but exported metadata gaps remain blockers.
- `ORDER BY` is not a uniqueness constraint. Document the intended replacement grain separately.

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
- The convention is a requested COT profile, not a universal ClickHouse default.

## Type Notes

- String: use `String`; use `LowCardinality(String)` only when cardinality is known to be low or source already uses it.
- Decimal: preserve precision/scale as `Decimal(p, s)`.
- Date/time: use `Date`, `DateTime`, or `DateTime64` according to source precision.
- Int/Float: map to explicit widths (`Int32`, `Int64`, `Float64`) when possible.
- Comments use inline `COMMENT 'text'` after the type/default clause.
