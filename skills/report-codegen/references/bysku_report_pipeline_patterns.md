# bySKU Report Pipeline Patterns

Use this reference when `structured_facts.json` or `report_codegen_plan.json` has `component_kind = "bysku_report_pipeline"`, or when documents describe a bySKU HBase/FS/ClickHouse report pipeline with SKU calculation families, detail/summary/ttl outputs, and rolling period retention. 执行为王 is one concrete sample alias for this generic shape.

## Common Sample Shape

When `prod_code_sample/datahub_executing_king` is available, treat it as guidance for this pipeline shape only. Do not copy credentials, environment-specific constants, sample-specific table names, or business lists into generated projects.

The common chain is:

- `Fos_hp_bi/prepare_data`: read period-scoped HBase bySKU source rows and upload compressed CSV files to FS.
- `Fos_hp_bi/cal_npd`: read FS bySKU files, apply NPD SKU config and filters, build detail/summary/ttl ClickHouse outputs.
- `Fos_hp_bi/cal_b5`: same shape for B5 SKU outputs.
- `code_2026`: sample-specific older/base execution table logic; inspect only when the request explicitly matches that base execution table.

Calculation components may receive params as XML with CDATA-wrapped JSON. Preserve that shape when modifying an existing project, and expose a placeholder JSON equivalent only for generated examples.

## DataSource Pattern

For prepare-data:

- Initialize `GateWayClient(app_key, app_secret)`.
- Use `getHbaseClient(fs_root_dir)` for HBase reads and `getFsClient()` for FS upload.
- Read HBase with `query_df(hbase_table_name=..., columns=..., row_start=period, row_stop=f"{period}Z", row_prefixs=[str(i) for i in range(10)])`.
- Drop the exported `rowkey` column before writing bySKU files.
- Write local `zo_bysku_detail_<period>.csv.gz`, upload with `fs.copy_from_local(local, remote, overwrite=True)`, then remove the local file.

For SKU calculation components:

- List FS files from the bySKU directory with `fs.listdir`.
- Filter filenames by required period lists from runtime `time_range` / SKU calculation range.
- Download with `exists(remote)` then `copy_to_local(remote, local)`.
- Read CSV or gzip with Pandas, use only required columns, and fill missing SKU columns with `"0"`.
- Remove local temp files after reading.

## SKU And Process Pattern

Keep SKU behavior in params/XML-derived config, not hardcoded in processing code:

- `sku_map`: output SKU columns and labels.
- `sku_combo_map`: combo SKU columns built from several source SKU columns.
- `sku_cal_range`: period windows used to compute R6P/R3P/YTD style SKU distribution.
- `sku_ttl_filter`: channel/category filters that turn non-applicable SKU values into `remove`.
- `sku_is_active`: deployment switch for active SKU output.

Some pipelines use `sku_combo_map` to build one output SKU flag from several source SKU columns. Fill every missing source SKU column with `"0"` before combo calculation.

Typical process behavior:

- Build a base store frame from current-period bySKU data.
- Filter invalid stores and excluded chains/headquarters.
- Calculate channel categories such as `Hyper`, `Super`, `Mini`, `CVS`, `Non KA MT`, `TT`, `Chain TTL`, `Non Chain TTL`, and `TTL`.
- Produce detail, summary, and ttl outputs for each configured SKU family when required.
- Enrich geography with `l0_manual_master.mars_geo_adj_mapping` when current-architecture fields are required.

## Storage Pattern

For ClickHouse writes:

- Initialize the project ClickHouse client through the local project pattern, preserving placeholders in generated files.
- For detail/summary/ttl tables, delete old rows by the documented period key, often current `mars_week`, before insert.
- For channel config tables, delete by `sku_type` when the project uses a shared channel table.
- Insert via temporary CSV and `insert_file` when following the sample style, then remove the local temp file.
- After successful table uploads, roll-delete periods older than the latest R13P threshold from `sv_eo_data.mars_calendar`.

Do not claim production equivalence until logs or fake-runtime tests prove:

- selected periods and FS files
- source row counts and missing-column fill behavior
- detail/summary/ttl row counts
- delete target, predicate type, and affected rows for each ClickHouse table (inspect exact SQL in code review or a safe test harness, not INFO logs)
- insert success for each table
- R13P retention cleanup result

## Codegen Guidance

- Use this as a report pipeline. Do not route to `data-sync-codegen` unless the request is only about a standalone table sync.
- If `report_physical_targets` were inferred from PRD text, keep a confirmation checklist in the generated plan.
- Prefer generating or editing one component at a time: `prepare_data` or one SKU calculation component.
- If asked for a full project, generate separate component folders or clearly separated modules so FS prepare and ClickHouse calculation are not mixed into one ambiguous `DataStorage`.
- Emit a `diagnostic_manifest.json` when practical, listing component kind, source reads, FS outputs, ClickHouse targets, delete predicates, retention cleanup, and required log markers.

## Handoff Readiness

Do not start implementation from a bySKU report pipeline plan until these are either present or listed as open questions:

- `component_hints.component_kind = bysku_report_pipeline`
- physical tables for each detail, summary, ttl, or channel output
- field dictionaries mapped to physical tables, not only logical names
- FS bySKU directory and file extension
- XML/params source for SKU config
- ClickHouse delete predicates and retention rule
- period contract including current period/week and manual rerun range
