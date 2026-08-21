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
  "version": 1,
  "sources": {},
  "steps": [],
  "outputs": {},
  "writes": {}
}
```

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
      "predicate": {
        "column": "period",
        "value_from": "time_range.period"
      }
    }
  }
}
```

Supported write modes are `append` and `replace_where`. A replace predicate must use one confirmed identifier and a runtime value from `time_range.<key>` or `params.<key>`. Generated storage validates identifiers, escapes values, and never deletes existing rows when the output DataFrame is empty.

## Verification

Run:

```text
python scripts/verify_report_plan_semantics.py --project-dir <generated-project>
python scripts/verify_generic_report_runtime_semantics.py
```

For HBase prepare projects, also run:

```text
python scripts/verify_report_runtime_semantics.py --project-dir <generated-project> --project-type hbase_prepare
```

