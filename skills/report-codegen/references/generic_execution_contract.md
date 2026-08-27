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

Every source requires an exact `columns` list. Non-injected sources also require `location`.

## Steps

Steps run in list order. Each `id` must be unique and may refer only to sources or earlier steps.

Supported operations:

- `select` / `project`: `input` or `source`, plus ordered `columns`.
- `filter`: `input` plus `conditions` using `eq`, `ne`, `in`, `not_in`, `gt`, `ge`, `lt`, `le`, `isnull`, `notnull`, or literal `contains`.
- `rename`: `input` plus `columns` as old-to-new mapping.
- `derive`: `input` plus named expressions.
- `join`: `left`, `right`, `how`, and either `on` or equal-length `left_on` / `right_on`.
- `aggregate`: `input`, optional `group_by`, and named aggregations.
- `union`: two or more prior `inputs`.
- `deduplicate`: `input`, `subset`, and optional `keep`.

Supported derive expressions:

- `copy`: `{ "op": "copy", "column": "amount" }`
- `literal`: `{ "op": "literal", "value": "valid" }`
- `literal` from runtime: `{ "op": "literal", "value_from": "time_range.period" }`
- `coalesce`: `{ "op": "coalesce", "columns": ["new_code", "old_code"] }`
- `add`, `subtract`, `multiply`, `divide`: operands use `{ "column": "x" }`, `{ "value": 1 }`, or `{ "value_from": "params.rate" }`
- `concat`: operands plus optional `separator`

Supported aggregations are `sum`, `count`, `nunique`, `min`, `max`, `mean`, `first`, and `last`.

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

Supported write modes are `append` and `replace_where`. A replace predicate must use one confirmed identifier and a runtime value from `time_range.<key>` or `params.<key>`. Generated storage validates identifiers, escapes values, and never deletes existing rows when the output DataFrame is empty.

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
