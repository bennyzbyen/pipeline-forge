# Supervisor Portal Report Patterns

This reference is self-contained and should be used before any external sample. The remote repository `https://github.com/bennyzbyen/datahub_supervisor_portal.git` is optional style guidance only when it is accessible.

Use this as the first-choice pattern for report development unless the user explicitly selects another pattern.

## Project Shape

```text
<project>/
  plugin_main.py
  main_execute.py
  common_utils/
  data_utils/
    data_source.py
    data_process.py
    data_storage.py
  params_configs/
    db_config.py
    col_config.py
    rowkey_config.py
  gateway/   # fixed platform package; preserve or install, do not generate business logic
  hbase/     # fixed platform package; preserve or install, do not generate business logic
  fs/        # fixed platform package; preserve or install, do not generate business logic
  params.example.json
```

## Bundled Scaffold

When a target directory is empty or no local/remote sample is available, use `assets/minimal_report_project/` as the scaffold source. The scaffold is intentionally minimal and must be adapted to the dev document:

- replace placeholder source and target table config
- implement only confirmed KPI logic
- keep newly generated credential-like values as placeholders
- preserve existing `gateway/`, `hbase/`, and `fs/` package files; if absent, only create minimal placeholders needed for import compatibility
- add confirmation comments only for unresolved business rules
- keep scaffold `NotImplementedError` guards until real source reads, transformations, and writes are implemented

## Structured Doc Handoff

When `structured_facts.json` exists, use it as the first source of codegen facts:

- `report_sources`: source storage, HBase/FS/MSSQL table or path, read range, source fields, and join/filter notes.
- `report_clickhouse_targets`: physical `database.table` targets extracted from Data Target text.
- `report_targets`: logical DataEngine target-management rows.
- `report_field_mappings`: target dictionaries with field order, source description, source field, calculation logic, and EO/DMS-specific rules.
- `report_schedules`: pipeline and task names.

Do not collapse several report outputs into one generic DataFrame. Generate one named output per target dictionary or physical target, and keep final column lists explicit.

Supervisor Portal docs may omit DataEngine Target Management rows and only provide a physical ClickHouse target matrix with `Description`, `Data Storage`, `Database`, and `Table Name`. In that case, map field-logic sheets to physical targets by embedded-sheet order, record the inference, and leave any extra target without a field dictionary as an explicit gap.

For the standard supervisor portal bottom-table project, the main output path covers:

- `supervisor_portal_store`
- `supervisor_portal_store_sales`
- `supervisor_portal_salesman`
- `supervisor_portal_salesman_sales`
- `supervisor_portal_mars_geo`
- `supervisor_portal_mars_geo_sales`
- `user_information`

Treat `sv_store_display_rack` as a separate project path. It uses its own mapping CSV/API flow and should not be mixed into the main store/salesman pipeline unless the user explicitly asks for that operator.

## Architecture

- `plugin_main.py`: DataEngine/platform entry point and param parsing.
- `main_execute.py`: orchestration, timing metrics, error handling, email notification.
- `DataSource`: reads HBase, MSSQL, FS, existing T+0/T-1 outputs, calendar, and supporting data.
- `DataProcess`: cleans, joins, calculates KPI fields, aggregates detail and summary outputs.
- `DataStorage`: deletes/replaces target period/date and inserts ClickHouse or stores evidence files.
- `params_configs/rowkey_config.py`: manual confirmation surface for HBase rowkey rules when the report writes HBase or triggers downstream HBase writes.

## Platform Package Usage

Read `platform_client_usage.md` before generating or modifying code that uses `gateway/`, `fs/`, or `hbase`.

- Use the project Gateway facade (`Client` or `GateWayClient`) to obtain `getHbaseClient(fs_root_dir=...)` and `getFsClient()`.
- Do not call Gateway token/header/API helpers or raw `requests` from report business modules.
- Default FS operations are `exists`, `listdir`, `copy_to_local`, and `copy_from_local(..., overwrite=True)`.
- Default HBase operations are `query_df`, `insert_df(..., mode="import")`, `insert_file(..., sep="\x1D")`, `delete_df`, and table-level `truncate` when explicitly configured.
- Do not generate `mode="insert"`, `HbaseClient.delete(...)`, direct `fs.operate_common` calls, `open`, `append`, `rename`, `mkdirs`, direct chunk upload, or manual `info:` column-family prefixes unless the existing project already uses that exact pattern.

## DataSource Pattern

- Use threaded reads when multiple independent HBase/MSSQL tables are required.
- Keep source column lists in `params_configs/col_config.py`.
- Keep connection placeholders and FS roots in `params_configs/db_config.py`.
- Use calendar data to derive:
  - current date
  - yesterday
  - current period
  - period start/end
  - T+0/T-1 fallback windows when needed
- Do not connect locally during generation.

Supervisor Portal source rules:

- HBase `l0_eo.order_detail_sync` in the document maps to the production-style `l0_eo.order_details_sync`; verify the final table name in deployment logs.
- HBase `l2_cot_exe_report.rpt_exe_visit_planning_execute_rate_2025` maps to the production-style base table `l2_cot_exe_report.rpt_exe_visit_planning_execute_rate`; verify yearly table naming before deployment.
- Read order history by `p_start` to `p_end`, visit planning execution by `period`, store planning by `currentday`, and product/user reference tables full-scan.
- Read MSSQL `store_details` full-scan with the sugar-cover filters and active/closed-date condition.
- Read MSSQL `eo_order_detail_pool` by `current_date`; read `fts_store_visit_log` from `p_start_time` through `current_date`.
- Keep injected `hbase_data`, `mssql_data`, `hbase_client`, `mssql_client`, `gateway_client`, and `clickhouse_client` paths available for local fake-data verification.

## DataProcess Pattern

- Store raw source DataFrames as instance attributes.
- Split large logic into private methods that return `self` when using a pipeline chain.
- Use explicit final column lists for each output table.
- Before aggregation, log or preserve row-count checkpoints when possible.
- For KPI formulas, only implement formulas present in the dev document.
- Unknown filters or grouping keys must become confirmation items, not guesses.

Supervisor Portal calculation rules:

- Build store output from filtered store master data.
- `today_sales`: valid same-day MSSQL `eo_order_detail_pool` rows where order state is not cancelled/refused, grouped by store.
- `pty_sales`: HBase EO order history from period start through yesterday, valid order statuses only, grouped by store.
- `ptd_sales = today_sales + pty_sales`.
- Today's visit and plan flags come from same-day visit logs and store planning.
- PTY/PTD visit-plan counts come from visit-planning execution rows filtered to `visit_emp_segment = MW`.
- Production-style PTY/PTD activation denominators are sums of `pty_total_visits` / `ptd_total_visits` for active digital stores, not distinct visited-store counts.
- `is_store_activated` is true for `FT-TT`, `WS`, `FT-Non KA` + `MT`, or `O2O前置仓` with non-`PlatformOwned` store channel.
- Store-sales output cross-joins stores with product `segment/subsegment` dimensions and aggregates today/PTY sales by store and product dimension.
- In store-sales output, previous store-sales snapshot is only used to rename previous `today_sales` into current `yesterday_sales`; current `pty_sales` must come from current-period order history, never from the previous snapshot.
- When injecting previous snapshots for local validation, strip them to the columns requested by the calculation before merging; extra snapshot columns can collide with current-period metrics.
- Salesman and MARS geo outputs aggregate from store-level outputs; sales-dimension outputs aggregate from store-sales outputs.
- `user_information` is a direct HBase-to-ClickHouse shape with final column ordering.

## DataStorage Pattern

- Use one upload task per output table.
- Delete by period/date/batch before insert only when replacement semantics are clear.
- Use `insert_file` or the local project's established ClickHouse client pattern.
- Clean temporary CSV files in `finally`.
- Do not silently continue on failed target writes unless the requirement explicitly wants best-effort writes.

Supervisor Portal storage uses a batch status lifecycle instead of period delete:

- Insert a new row into `supervisor_portal.supervisor_portal_batch` with status `1`.
- Add `batch_id`, `last_update_time`, and `date` to the target DataFrame when those columns exist.
- Insert the target table data.
- Update the new batch to status `2`.
- Mark the previous finished batch as status `3`.
- Delete rows for the previous cancelled batch when present.

## Parameter Rules

Generate `params.example.json` with safe placeholders:

```json
{
  "current_date": "",
  "period": "",
  "receiver_emails": [],
  "running_env": "uat"
}
```

## Verification

For generated code, verify:

- syntax compiles
- params JSON parses
- all referenced config names exist
- all final output columns are defined
- generated examples/templates do not introduce real credentials unexpectedly
- `DataProcess.run()` does not return empty placeholder outputs
- `DataStorage.run()` does not only log planned writes
- `scripts/verify_report_runtime_semantics.py --project-dir <generated-project> --project-type supervisor_portal` passes for the main supervisor portal path

The fake runtime verifier should cover:

- injected `hbase_data` and `mssql_data` are consumed without external clients
- time range derives `currentday`, `yesterday`, `p_start_time`, `p_end_time`, and `r2p`
- the seven main outputs are produced with exact final column order
- sugar-cover store filtering removes non-target stores
- cancelled/refused same-day and PTY orders are excluded
- `today_sales`, `pty_sales`, and `ptd_sales` match the source rows
- today visit/planning flags and PTD planned-visit counts are calculated
- store-sales cross-joins product dimensions plus the empty `空/空` bucket
- salesman and MARS geo summaries aggregate only activated stores where required
- ClickHouse storage inserts batch status `1`, writes data, updates current batch to `2`, marks old finished batch `3`, and deletes old cancelled-batch rows

For deployed logs, confirm:

- DataSource time range
- source row counts
- join/filter row counts
- output row counts per table
- ClickHouse delete and insert target table names
- final metrics

## HBase Prepare / Pipeline Pattern

Use this pattern when a DataEngine report document has HBase physical targets, source export tasks such as `init_data_source` or `period_export_execute`, and downstream calculation tasks such as `cal_store_yield_grade`.

This is a report-development component, but it is not a normal ClickHouse writer:

- `DataSource` derives the target period or R13P period list from the calendar HBase table.
- `DataSource` reads the configured HBase source table by period range.
- `DataSource` filters source rows using documented filters such as `SubSegmentID in (1,2,3,6,7)`.
- `DataSource` aggregates source rows before export when the production pattern does so, for example `SelloutAmount` by `StoreID`.
- `DataSource` writes compressed CSV files to FS, for example `cmt_sellout_<period>.csv.gz`.
- `DataProcess` optionally activates downstream DataHub pipeline process UIDs when params request it.
- `DataStorage` may intentionally be no-op because the downstream DataHub pipeline owns final HBase calculation and write.

Keep these values configurable:

- `export_mode`: `init` for R13P export, `daily` for previous-period export.
- `specific_range`: manual period list for reruns.
- `hbase_export_cols`: runtime source columns.
- `is_run_pipeline`: whether to activate downstream pipeline after export.
- FS root and pipeline process UIDs as placeholders in config.

Existing project files may already contain real app keys, app secrets, API keys, process UIDs, or URLs. Preserve them when editing the same in-scope file unless the user asks to change them. Do not copy real values from production samples into new scaffold files, examples, generated params, or documentation unless the user explicitly asks.

Generate or preserve `params_configs/rowkey_config.py` for HBase prepare projects. It should include fill-in comments for:

- exact rowkey columns and order
- separator
- prefix/hash/salt behavior
- date or period formatting
- one expected rowkey example
- `confirmed = False` until docs/code/logs prove the rule

For local verification, generated code should support injected `hbase_data`, `hbase_client`, `fs_client`, `gateway_client`, and `pipeline_client` so period derivation and export semantics can be tested without production services.

For deployed logs, confirm:

- resolved current date and period list
- source HBase table and row range
- source rows before and after filters
- generated FS file name and destination path
- optional pipeline process UID activation result
