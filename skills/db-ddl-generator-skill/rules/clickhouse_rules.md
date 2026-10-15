# ClickHouse Rules

## Deployment Profiles

- Require an explicit engine and `ORDER BY` in QA and PROD.
- Add `ON CLUSTER` only when the confirmed profile names a cluster.
- Require an explicit replication path for replicated engines.
- For replacement profiles, require an explicit version column from the user, deployment profile, or full engine expression; verify it exists, is non-nullable, and has an unsigned integer or date/time target type. Never pick a datetime column merely because it exists.

- Environment names do not imply engine, cluster, or replication settings.
- Source production DDL may be preserved as an explicit profile, but exported metadata gaps remain blockers.
- `ORDER BY` is not a uniqueness constraint. Document the intended replacement grain separately.
- Resolve explicit arguments before the exact environment/database/table profile, then the existing ClickHouse contract. Keep source fields current while inheriting only deployment configuration from an older table. Do not automatically transfer MySQL primary keys.
- Keep all explicit SETTINGS and replica expressions. Do not supply 8192 as an implicit setting. A new database with a replicated profile requires an explicitly supplied new replication path.

## Key Constraints

- Do not put `Nullable(...)` columns into `ORDER BY`, `PRIMARY KEY`, or partition keys unless the source cluster explicitly allows nullable keys and the user accepts the risk.
- Partition field types should not be changed casually. Preserve `String`, `Date`, `DateTime`, or numeric partition semantics from source DDL.
- If a key column was nullable in the source, preserve the source contract, report the conflict, and require `--allow-key-nullability-coercion` with a documented reason to generate a non-nullable target key. Before import, provide NULL-check SQL; never silently replace NULL values. This helper does not implement nullable-key settings as an alternative.

## COT Report Convention

- Only when explicitly requested, both `period` and `code` exist, and no explicit/source/profile keys exist, generate:
  `PARTITION BY period`
  `ORDER BY (period, code)`
- Do not mutate source nullability when choosing these keys; the same explicit conversion check applies.
- Do not apply this convention when either column is missing or the user explicitly provides other partition/order fields.
- The convention is a requested COT profile, not a universal ClickHouse default.

## Type Notes

- String: use `String`; use `LowCardinality(String)` only when cardinality is known to be low or source already uses it.
- Decimal: preserve precision/scale as `Decimal(p, s)`.
- MySQL integer display width is not storage width: `int(1)` and `int(50)` both map to `Int32`; unsigned integers map to the corresponding `UInt` width (`mediumint` uses 32 bits).
- Separate MySQL `DEFAULT` and `ON UPDATE`; map supported timestamp defaults and report the omitted update behavior. Do not emit AUTO_INCREMENT in ClickHouse; retain source IDs through import.
- Date/time: use `Date`, `DateTime`, or `DateTime64` according to source precision.
- Int/Float: map to explicit widths (`Int32`, `Int64`, `Float64`) when possible.
- Comments use inline `COMMENT 'text'` after the type/default clause.
