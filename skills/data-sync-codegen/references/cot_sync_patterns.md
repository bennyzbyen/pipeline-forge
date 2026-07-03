# COT Sync Patterns

This reference is self-contained. If `prod_code_sample/cot_202604101607` is present in the workspace, inspect it as an optional style reference, but do not depend on it.

## When To Use

Use this pattern for yearly COT/DataEngine synchronization jobs where the sync algorithm is stable and changes are mostly:

- source MySQL tables
- HBase target tables
- ClickHouse target tables
- exported fields
- rowkey rule columns
- period/full/delta sync range
- receiver emails and runtime params

## Project Shape

Expected generated structure:

```text
<project>/
  plugin_main.py
  plugin_common.py
  sync_with_period.py
  sync_without_period.py
  cot_config/plugin_config.py
  cot_config/rowkey_config.py
  cot_sync_with_period/
    etl_source.py
    hbase_operation.py
    ck_operation.py
  cot_sync_without_period/
    etl_source.py
    hbase_operation.py
    ck_operation.py
  gateway/  # fixed platform package; preserve or install, do not generate business logic
  hbase/    # fixed platform package; preserve or install, do not generate business logic
  fs/       # fixed platform package; preserve or install, do not generate business logic
  params.example.json
```

Only generate modules that are needed by the current requirement.

## Platform Package Usage

Read `platform_client_usage.md` before generating or modifying code that uses `gateway/`, `fs/`, or `hbase`.

- Use the project Gateway facade (`Client` or `GateWayClient`) to obtain `getHbaseClient(fs_root_dir=...)` and `getFsClient()`.
- Do not call Gateway token/header/API helpers or raw `requests` from business sync modules.
- Default FS operations are `exists`, `listdir`, `copy_to_local`, and `copy_from_local(..., overwrite=True)`.
- Default HBase operations are `query_df`, `insert_df(..., mode="import")`, `insert_file(..., sep="\x1D")`, `delete_df`, and table-level `truncate` when explicitly configured.
- Do not generate `mode="insert"`, `HbaseClient.delete(...)`, direct `fs.operate_common` calls, `open`, `append`, `rename`, `mkdirs`, direct chunk upload, or manual `info:` column-family prefixes unless the existing project already uses that exact pattern.

## Bundled Scaffold

When a target directory is empty or no local production sample exists, use `assets/minimal_sync_project/` as the scaffold source. The scaffold is self-contained for normal code generation and includes entry points, timestamp handling, MySQL export, with-period/without-period HBase writers, and ClickHouse writers. It must still be adapted to the dev document:

- replace placeholder table lists and field lists
- decide whether with-period, without-period, or both modules are needed
- keep newly generated credential-like values as placeholders
- preserve existing `gateway/`, `hbase/`, and `fs/` package files; if absent, only create minimal placeholders needed for import compatibility
- add TODO comments only for genuinely unconfirmed business facts

For COT yearly sync work, prefer running `scripts/scaffold_cot_sync_project.py` instead of hand-copying templates. The script consumes `structured_facts.json`, optionally enriches fields from an extracted embedded-CSV directory, and writes a generated project plus `cot_sync_manifest.json`, `params.example.json`, `questions.md`, `verification.md`, and `cot_config/rowkey_config.py`.

After scaffolding, run `scripts/verify_cot_runtime_semantics.py --project-dir <generated-project>`. This verifier uses fake modules and must not connect to MySQL, HBase, ClickHouse, FS, or Gateway. It checks:

- `plugin_main.py` dispatches with-period and without-period tables and fills table defaults.
- manual period reruns use full sync and do not fetch or update timestamps.
- automatic with-period incremental runs fetch timestamp, detect full/delta periods, write ClickHouse then HBase, then update timestamp.
- no-change with-period runs do not write targets and do not update timestamp.
- without-period changed runs fetch, write ClickHouse then HBase, then update timestamp.
- without-period no-change runs do not write targets and do not update timestamp.

## Entry Point Contract

- `plugin_main.py` reads DataEngine params.
- It supports `algorithm_io_mode == "SINGLE"` and plain local params.
- It dispatches by source table:
  - with-period tables use `COT_REPORT_WITH_P`
  - without-period tables use `COT_REPORT_WITHOUT_P`
- It writes JSON result to the platform result path or `./result.txt`.

## COT Parameter Contract

Prefer the production-compatible grouped params shape:

```json
{
  "source_informations": {
    "mysql_table": "zo_hswmt_detail_p",
    "last_update_time_column": "inksaa_last_modified_timestamp",
    "period_column": "period",
    "period": ["2026P03"],
    "code_column": "code",
    "key_column": "id",
    "batch_size": 100000,
    "receiver_emails": []
  },
  "hbase_informations": {
    "hbase_table": "l2_cot_perfect_store.zo_hswmt_detail_2026_p",
    "rowkey_rule_columns": ["period", "code"]
  },
  "clickhouse_information": {
    "clickhouse_table": "zo_hswmt_detail_p"
  }
}
```

Keep compatibility with flatter params only when the existing target project already uses them.

## Structured Doc Handoff

When `structured_facts.json` exists, use it to create or review config:

- `cot_report_tables`: source HBase-like table, range, business description, and ClickHouse table.
- `data_utilizations`: logical DataEngine item names.
- `target_mappings`: catalog names and `hbase_` / `clickhouse_` target prefixes. Preserve exceptions such as renamed catalogs instead of deriving names blindly.
- `schedules`: DataEngine pipeline/task names and run times.
- `field_dictionaries`: output fields per Data Utilization. The document extractor may infer dictionary-to-utilization mapping by embedded-sheet order; verify exceptions.

Generation must remain portable. The script may be developed and regression-tested against workspace samples, but generated projects must only depend on their local code and runtime parameters, not on `skill_lab/prod_code_sample`.

## Blind Generation Defaults

Use these defaults before inspecting production samples:

- Source MySQL table: ClickHouse table basename from the COT matrix.
- HBase target: `source_hbase_table` from the COT matrix.
- ClickHouse target: full ClickHouse table from the COT matrix, including database prefix when present.
- With-period classification: table name ending in `_p`, HBase table ending in `_p`, or business/report text containing COT period wording such as `截P` or project collection.
- Without-period classification: execution-report tables without `_p` period naming.
- Do not classify a table as with-period only because a field dictionary contains `period`; execution reports may keep a period field while still using timestamp-only incremental sync.
- Update timestamp: prefer `inksaa_last_modified_timestamp`, then `last_update_timestamp`, then common update-time columns.
- With-period rowkey: default to `period` plus the best available business code column (`code`, `store_code`, `main_store_code`, etc.).
- Without-period rowkey: default to `id` or `inksaa_id`.
- Source database group: with-period tables default to `report_ps_p`; execution-style without-period tables default to `store_report_generator`.
- Any rowkey, source database, or timestamp inferred without direct document evidence must be listed in generated `questions.md`.

## COT 2026 Production-Calibrated Exceptions

Keep these as config-generation rules, not control-flow branches:

- `supervisor_assist_visit` is generated as `v_supervisor_assist_visit_2026`.
- `rpt_exe_sales_assess_channel` is generated as `rpt_exe_sales_assess_channel_2022`.
- `rpt_exe_visit_planning_execute_rate` remains without-period even though its field dictionary contains `period`.
- `supervisor_remake_remark`, `v_supervisor_assist_visit_2026`, `rpt_exe_sales_assess_channel_2022`, and `freshness_report` are with-period execution-family exceptions.
- `cot_gps_tracking_report`, `cot_gps_tracking_report_by_week`, `supervisor_remake_remark`, and `v_supervisor_assist_visit_2026` use the `store_report` source group.
- `rpt_exe_store_past_will` and `wechat_authorization_info` use the legacy `cot_report` ClickHouse database.
- `wechat_authorization_info` truncates ClickHouse and HBase before insert.
- Runtime `clickhouse_table` params should use bare table names; database prefixes are handled by config exceptions.

## With-Period Sync

Use when the source table has a period column and data can be refreshed by period.

Default flow:

1. Resolve MySQL connection and source table params.
2. Determine sync list from manual `period` input, last timestamp, or configured range.
3. Export source rows into local CSV chunks.
4. Insert ClickHouse if configured.
5. Insert HBase if configured.
6. Update timestamp only for incremental non-manual reruns.
7. Clean temporary local files.

Production-compatible sync-list logic:

- Manual period rerun: `[(period, "full")]` for each requested period and do not update timestamp.
- Automatic run: fetch last timestamp from FS, query updated periods where `last_update_time_column > last_timestamp`, then compare updated row count with total row count per period.
- If updated row count equals total period count, mark that period `full`; otherwise mark `delta`.
- Export full period with `where period_column = period`.
- Export delta period with `where period_column = period and last_update_time_column > last_timestamp`.

## Without-Period Sync

Use when sync is timestamp-only or execution-report style.

Default flow:

1. Fetch last timestamp.
2. Export rows where update time is greater than last timestamp.
3. Create rowkey from stable unique fields.
4. Insert HBase/ClickHouse based on downstream need.
5. Update last timestamp after successful writes.

Production-compatible behavior:

- If no rows changed after the last timestamp, return a warning/error metric and do not write targets.
- For ClickHouse, delete by `key_column` before inserting changed rows unless the table is configured for truncate.
- For HBase, insert changed rowkeys; truncate only for configured table-level exceptions.

## HBase Rules

- Use `rowkey` as the insert rowkey column unless existing code uses another constant.
- Prefix rowkey with the last character of the concatenated business key when following COT style.
- Do not invent rowkey fields. If missing, add to questions or comments.
- Always generate or preserve `cot_config/rowkey_config.py` as the manual rowkey review file.
- `rowkey_config.py` must contain fill-in comments for `columns`, `separator`, `prefix`, `date_format`, `example`, and `confirmed`.
- Runtime code may still read `rowkey_rule_columns` from `plugin_config.py` or DataEngine params; after confirming rowkey rules, copy confirmed columns/prefix changes back to the runtime config path.
- For full period refresh, compare or delete old rowkeys before inserting when the requirement needs historical correction.
- For with-period full refresh, production style queries old HBase rowkeys by period range, compares with newly generated rowkeys, deletes stale rowkeys, then inserts the new gzipped files.
- Write HBase files with `\x1D` separator and `rowkey` as the first column when matching COT style.
- For DataFrame HBase writes, use `HBASE_ROW_KEY` when the local wrapper requires it. Exported HBase data normally returns `rowkey`; file insert wrappers can map `rowkey` to `HBASE_ROW_KEY`.
- Do not use `mode="insert"` for generated HBase writes; sample wrappers leave sync insert paths incomplete or unsupported.

## ClickHouse Rules

- Use `insert_file` for file-based bulk insert when matching the COT sample.
- Delete by period or configured partition before inserting when refresh semantics require replacement.
- Keep `cluster` configurable; empty in UAT and `ON CLUSTER ...` in PROD.
- With-period full mode: drop the target period partition before insert.
- With-period delta mode: delete rows by `code_column` and `period_column` for only the exported store/code set, then insert.
- Without-period mode: delete by `key_column` for exported rows, unless the table is configured in `ck_truncate_list`.
- Some legacy COT execution tables may live under older ClickHouse database prefixes; keep such exceptions in config.

## COT Table Classification Rules

- Prefer explicit config lists when provided: `with_period_tables`, `without_period_tables`, `store_report_generator_table_list`, `store_report_table_list`, truncate lists, and legacy table lists.
- If lists are not provided, infer cautiously:
  - field dictionary contains `period` and the document range is P-based -> candidate with-period
  - execution report without reliable period refresh semantics -> candidate without-period
  - any inference must be noted in generated config comments or `questions.md`
- Do not assume Data Utilization name, ClickHouse table name, and source table suffix are always identical; use the target mapping table for exceptions.

## Config Rules

- Put table lists, field lists, environment placeholders, and path constants in config modules.
- Keep source database routing in config, for example report_ps_p, store_report_generator, and store_report table groups.
- Keep table-level exceptions in config, not in sync control flow.
- Existing project files may already contain real app keys, secrets, passwords, tokens, hosts, or ports. Preserve them when editing the same in-scope file unless the user asks to change them.
- New scaffold files, examples, generated params, and copied sample-derived code must use placeholders unless the user explicitly asks to insert real values:
  - `<APP_KEY>`
  - `<APP_SECRET>`
  - `<CLICKHOUSE_HOST>`
  - `<CLICKHOUSE_PASSWORD>`
  - `<MSSQL_TOKEN>`
  - `<BLOB_SAS_URL>`

## Verification

Local verification is limited to:

- `python -m py_compile` for generated `.py` files
- `scripts/verify_cot_runtime_semantics.py --project-dir <generated-project>` for generated COT scaffold runtime semantics
- JSON parse check for `params.example.json`
- Manual scan that generated examples/templates did not introduce real credentials unexpectedly

Deployment verification should inspect logs for:

- resolved table names
- period/time range
- exported row count
- HBase inserted/deleted row count
- ClickHouse deleted/inserted row count
- final DataEngine metrics
