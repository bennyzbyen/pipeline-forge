# bySKU Report Pipeline Failure Modes

Use this reference when DataEngine/DataHub logs mention a bySKU HBase/FS/ClickHouse report pipeline, `prepare_data`, SKU calculation components, NPD, B5, detail/summary/ttl outputs, or sample aliases such as 执行为王 / `datahub_executing_king`.

## Stage Checklist

Classify the failure by the last completed stage:

- Period resolution: `current_date`, `period`, `week`, manual range, R13P range.
- HBase read: source table, columns, `row_start`, `row_stop`, `row_prefixs`, returned rows.
- FS prepare: local gzip/csv file, remote FS path, `copy_from_local`, overwrite behavior.
- FS calculation input: `listdir`, filename filtering by period, `exists`, `copy_to_local`, local temp cleanup.
- SKU config: `sku_map`, `sku_combo_map`, `sku_cal_range`, `sku_ttl_filter`, active SKU list.
- DataProcess: store filters, channel category calculation, combo SKU calculation, detail/summary/ttl row counts.
- Geography enrichment: `l0_manual_master.mars_geo_adj_mapping`, before/current key join, duplicate mapping rows.
- ClickHouse write: delete predicate, insert target, inserted rows, temporary CSV cleanup.
- R13P retention: threshold query from `sv_eo_data.mars_calendar`, target tables, delete result.

## Common Root Causes

- FS file not found because prepare-data did not run for the requested period, or filename period format differs from calculation params.
- Missing SKU columns in older bySKU files. This is expected only when code fills the missing columns with `"0"`.
- XML/params mismatch: `sku_map` includes a column that is absent from `sku_cal_range` or `sku_ttl_filter`.
- Wrong delete predicate: detail/summary/ttl should usually delete by `mars_week`; shared channel tables may delete by `sku_type`.
- R13P retention query returns empty threshold, causing cleanup to skip or delete the wrong period range.
- Geography mapping join duplicates rows because before-key columns are not deduplicated.
- ClickHouse mutation delay after `ALTER TABLE ... DELETE`, especially when insert follows immediately.

## Diagnostic Output

When logs are available, always report whether each of these ran:

- HBase source read
- FS upload or download
- SKU calculation output
- ClickHouse delete
- ClickHouse insert
- R13P cleanup

If a `diagnostic_manifest.json` or `report_codegen_plan.json` is provided, compare the log targets and delete predicates against it before suggesting code changes.
