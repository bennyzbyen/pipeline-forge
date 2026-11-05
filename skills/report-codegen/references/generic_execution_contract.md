# Generic Report Execution Contract

Use this normalized contract only when no named specialized implementation matches. It is a data-only DSL: never place Python, SQL fragments, `eval`, lambdas, or import paths in it.

## Readiness Rule

A generic `standard_report` or `bysku_report_pipeline` is ready for full scaffolding only when:

- `codegen_contract.ready_for_codegen` is true;
- every logical output has one physical ClickHouse table and an exact ordered `final_columns` list;
- `execution_contract` passes `scripts/verify_report_plan_semantics.py`;
- every source, step, output, and write is represented explicitly.

Without this contract, `--allow-blocked-scaffold` may create a review-only project, but the project must retain its non-runnable placeholders and must not be presented as complete.

## Top-Level Shape

```json
{
  "version": 2,
  "parameters": [],
  "runtime": {},
  "sources": {},
  "steps": [],
  "outputs": {},
  "writes": {}
}
```

Version 1 remains readable for code-generation review. Strict deployment requires version 2.

## Parameters And Runtime

Each parameter declares semantics for `omitted`, `null`, `blank`, `empty`, `scalar`, `list`, and `invalid`, plus executable `accepted_shapes`, `default_on`, and `default` fields. Keep project-specific meanings distinct: a report date may default to T-1, while an empty COT period may mean automatic incremental mode.

Runtime v2 declares `python_min`, `entrypoint`, the exact DataEngine result protocol (`put` / `inst` / `task` / `metrics`), an environment-to-connection-mode matrix, and a safe-log policy with credential and parameter-value logging disabled. Environment names never imply a connection mode.

Output and write keys must exactly match the plan's output target names. Output columns must exactly match each plan output's `final_columns`, including order.

## Sources

Each source key becomes the DataFrame name available to transformation steps.

```json
{
  "orders": {
    "kind": "hbase",
    "location": "l0_order.orders_p",
    "columns": ["store_code", "period", "amount"],
    "range": {
      "start": "time_range.period",
      "stop": "time_range.period",
      "row_prefixs": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
    }
  }
}
```

Supported kinds:

- `hbase`: uses an injected DataFrame or the project HBase client.
- `fs`: uses an injected DataFrame or downloads CSV/TSV/Parquet files through the FS client.
- `mssql` and `mysql`: use injected data or the explicit callable runtime adapter `mssql_reader` / `mysql_reader`.
- `injected`: requires `params.source_data[source_name]`; intended for verified fixtures or host-managed adapters.

Every source declares its requested `columns`. For HBase, the reader accepts extra or empty export columns and projects the requested qualifiers that are present. On nonempty input, downstream operations and declared constraints enforce the fields they consume. Non-injected sources also require `location`.

### Declared Value And Grain Constraints

Sources and outputs may declare `column_constraints` and `unique_by`. These are optional, evidence-backed rules, not inferred business defaults. Unspecified types and nullability remain unknown; existing contracts without these properties retain their behavior.

```json
{
  "columns": ["store", "day", "amount"],
  "unique_by": ["store", "day"],
  "column_constraints": {
    "store": {"type": "String", "nullable": false},
    "day": {"type": "Date", "min_from": "params.start", "max_from": "params.stop", "max_inclusive": false},
    "amount": {"type": "Decimal(18,2)", "min": "0", "nullable": true}
  }
}
```

Supported constraint types are `String`, `Int8/16/32/64/128/256`, matching `UInt` types, `Float32/64`, `Decimal(P,S)` (1–76 precision), `Date`, and whole-second `DateTime`. Declare nullability separately with a boolean `nullable`; nullable values are not coerced into defaults. Unsupported constraint types are errors. Existing write `column_types` remain a separate target/wire declaration.

Numeric checks reject fractional integers, overflow, non-finite non-null values, and excess decimal precision/scale. Exact integer and decimal text is checked without passing through binary floats or rounding; floating input may already have lost precision upstream. Trailing fractional zeros are acceptable when the value is exactly representable at the declared scale. Values and DataFrame dtypes remain unchanged by validation. Explicit integer value constraints reject booleans; legacy integer wire formatting still maps boolean flags to 0/1 when no stricter value rule is declared.

`Date` uses strict ISO dates or native dates/midnight timestamps. `DateTime` accepts ISO datetime text or native timestamps at whole-second precision; it does not discard fractional seconds or assume a timezone. Aware values are compared as UTC instants, including explicit fold/offset information, while the original values remain unchanged. Bounds use either literal `min` / `max` or `min_from` / `max_from` from `params.<key>` or `time_range.<key>`. Bounds are inclusive unless their boolean `min_inclusive` / `max_inclusive` is false. Numeric bounds are finite comparison thresholds, so they may lie outside the column range or use finer decimal scale; only row values must fit the declared storage type. Missing, inverted, invalid or timezone-incompatible bounds fail even on an empty frame; an equal-bound half-open range permits only an empty/non-valued population. Empty frames do not create missing rows or values.

`unique_by` is an ordered list of distinct declared columns. Repeated key tuples, including repeated null-key tuples, fail. A single null key remains permitted unless `nullable: false` is also declared. Use this for confirmed source uniqueness and output/aggregate grain. It does not infer a primary key from field names.

The shared `declared_constraints.py` helper is copied into generated `data_utils/`. Source checks run before transformations; output checks run on projected results. Put a date-window bound on the output when filtering is responsible for selecting that window; source bounds assert that all input rows already satisfy it. Storage preflights all outputs with these declarations before the first client/write call, so a bad declared output cannot follow a successful write from the same call. This is validation preflight, not an atomic multi-target transaction.

## Steps

Steps run in list order. Each `id` must be unique and may refer only to sources or earlier steps.

Supported operations:

- `select` / `project`: `input` or `source`, plus ordered `columns`.
- `filter`: `input` plus `conditions` using `eq`, `ne`, `in`, `not_in`, `gt`, `ge`, `lt`, `le`, `isnull`, `notnull`, or literal `contains`.
- `rename`: `input` plus `columns` as old-to-new mapping.
- `derive`: `input` plus named expressions.
- `join`: `left`, `right`, `how`, and either `on` or equal-length `left_on` / `right_on`; optional `validate` declares `one_to_one`, `one_to_many`, `many_to_one`, or `many_to_many`.
- `aggregate`: `input`, optional `group_by`, and named aggregations.
- `union`: two or more prior `inputs`.
- `deduplicate`: `input`, `subset`, and optional `keep` (`first`, `last`, or boolean `false`). False removes every row belonging to a duplicated key; omitted `keep` retains the first row.

Supported derive expressions:

- `copy`: `{ "op": "copy", "column": "amount" }`
- `literal`: `{ "op": "literal", "value": "valid" }`
- `literal` from runtime: `{ "op": "literal", "value_from": "time_range.period" }`
- `coalesce`: `{ "op": "coalesce", "columns": ["new_code", "old_code"] }`
- `add`, `subtract`, `multiply`, `divide`: operands use `{ "column": "x" }`, `{ "value": 1 }`, or `{ "value_from": "params.rate" }`
- `concat`: operands plus optional `separator`

Division propagates null operands and replaces a zero denominator with null, for both data columns and scalar literals/runtime parameters. An explicit `fill_value` replaces a missing division result; omitting it preserves null. Use a fill only when the requirement confirms that default. Operation order comes from the declared steps and operand order; the interpreter does not parse prose formulas or infer rounding, caps, or classification rules.

Supported aggregations are `sum`, `count`, `nunique`, `min`, `max`, `mean`, `first`, and `last`.

Join cardinality uses the [pandas merge validation semantics](https://pandas.pydata.org/docs/reference/api/pandas.merge.html): uniqueness on both sides, left only, or right only respectively. `many_to_many` explicitly permits multiplication; an omitted declaration keeps the existing merge behavior. Null-key matching is unchanged; declare source null constraints when null keys are forbidden. Deduplication follows [pandas keep semantics](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html). Grouping retains null-key groups and existing count/sum behavior; only confirmed output grain is enforced.

### Static Column Lineage

Validation propagates the declared source columns through each step before scaffolding. Every filter, projection, rename key, derive operand, join key, grouping key, explicit aggregation column, deduplication key, and output column must exist in its input schema. Errors identify the exact contract property with `unknown_input_column`; invalid or duplicate column names and ambiguous join suffixes are also rejected. Field names retain their exact case and spaces. Only `select` / `project` accept `source` as an alias for `input`.

- `select` / `project` keep their ordered subset; `filter` and `deduplicate` preserve columns.
- `rename` removes old names and keeps column positions. Swaps are valid; name collisions are errors.
- `derive` follows mapping insertion order, so an expression may use an earlier derived column. Overwrites keep the original position. Literals and `value_from` paths are values, not field references.
- `join` follows the runtime's key handling and `_x` / `_y` default suffixes, or an explicit pair of string/null suffixes. Output names must remain unique.
- `aggregate` keeps only grouping keys and named aggregate outputs. `count` without an explicit column retains the runtime fallback.
- `union` keeps the first-seen union of input columns, including heterogeneous schemas.

These checks use column metadata only; they do not execute data or establish formula correctness. An invalid upstream schema remains an error without speculative downstream field diagnostics. Valid contracts keep the existing validation result shape and runtime behavior.

Example:

```json
{
  "id": "region_summary",
  "op": "aggregate",
  "input": "joined_orders",
  "group_by": ["region", "period"],
  "aggregations": {
    "revenue": {"column": "revenue", "agg": "sum"},
    "store_count": {"column": "store_code", "agg": "nunique"}
  }
}
```

## Outputs And Writes

```json
{
  "outputs": {
    "region_sales": {
      "input": "final_output",
      "columns": ["region", "period", "revenue"]
    }
  },
  "writes": {
    "region_sales": {
      "kind": "clickhouse",
      "table": "report.region_sales",
      "mode": "replace_where",
      "columns": ["region", "period", "revenue"],
      "column_types": ["String", "String", "Decimal(18,2)"],
      "transport": "insert_file",
      "empty_output_policy": "block_destructive_replace",
      "replacement_safety": {
        "strategy": "delete_then_insert",
        "non_atomic_risk_acknowledged": true
      },
      "staging_wire_format": {
        "encoding": "utf-8",
        "bom": false,
        "header": false,
        "null": "\\N",
        "datetime_precision": "seconds",
        "integer_format": "integer",
        "explicit_columns": true
      },
      "predicate": {
        "column": "period",
        "value_from": "time_range.period"
      }
    }
  }
}
```

Supported write modes are `append` and `replace_where`. Predicates use one equality or a non-empty `all` list with confirmed identifiers and `time_range.<key>` or `params.<key>` values. Empty output defaults to preserving rows (`block_destructive_replace`/`skip`); `reject` raises; `clear_slice` requires `empty_snapshot_confirmed=true` and bounded replacement predicates. Missing outputs are errors. See `lifecycle_contracts.md` for completion and recovery semantics.

For legacy v1 contracts that omit write `columns`, the writer uses that output's ordered columns. Omitted v1 types preserve values without type coercion. Prepared file writes use those same projected columns. V2 still requires explicit write columns and types for deployment; a non-empty output must never be written with zero columns.

Integer wire formatting validates the declared signed/unsigned range and formats each value exactly. Canonical integer ranges and legacy `INT`/`INTEGER`/`INT1` signed/unsigned aliases follow the [ClickHouse integer definitions](https://clickhouse.com/docs/reference/data-types/int-uint). Native integer columns use exact extrema checks; numeric text uses exact scalar parsing. Large integers mixed with nulls must not pass through a floating intermediate; this applies to both `insert_df` and `insert_file`. Unknown decimal rounding or business-default rules remain unresolved rather than being invented by validation.

`DELETE` followed by `INSERT` is non-atomic. Strict deployment blocks it unless the contract supplies an atomic/recoverable strategy or explicitly acknowledges the non-atomic risk. For `insert_file`, staging must use explicit ordered columns, UTF-8 without BOM or header, `\\N` nulls, integer-safe formatting, and second-precision datetimes.

## Verification

Run:

```text
python scripts/verify_report_plan_semantics.py --project-dir <generated-project>
python scripts/verify_generic_report_runtime_semantics.py
python scripts/verify_qas_synthetic_acceptance.py
```

For HBase prepare projects, also run:

```text
python scripts/verify_report_runtime_semantics.py --project-dir <generated-project> --project-type hbase_prepare
```
