# HBase Prepare Pipeline Patterns

Use this reference only when `component_kind = hbase_prepare_pipeline`: a DataEngine component exports period-scoped HBase source data to FS and may activate a downstream DataHub calculation pipeline. It is not a normal ClickHouse report writer.

## Component Contract

- `DataSource` derives the target period or R13P list from calendar data, reads the configured HBase source range, applies documented filters such as `SubSegmentID in (1,2,3,6,7)`, and performs required pre-export aggregation such as `SelloutAmount` by `StoreID` when the project evidence specifies it.
- `DataSource` writes compressed CSV evidence to FS using the documented filename and overwrite behavior, for example `cmt_sellout_<period>.csv.gz`.
- `DataProcess` may activate downstream DataHub pipeline process UIDs when runtime params request it.
- `DataStorage` may intentionally be a no-op because the downstream pipeline owns the final HBase calculation and write.

Read `platform_client_usage.md` when implementing Gateway, HBase, or FS calls.

## Configurable Inputs

- `export_mode`: `init` for R13P export or `daily` for the previous-period export.
- `specific_range`: explicit period list for manual reruns.
- `hbase_export_cols`: confirmed source columns.
- `is_run_pipeline`: whether to activate the downstream pipeline.
- FS root and process UIDs, using placeholders in newly generated config.

Do not copy app keys, secrets, API keys, process UIDs, or URLs from production samples into new files unless the user explicitly requests those values.

## Rowkey And Verification

Generate or preserve `params_configs/rowkey_config.py` with the exact column order, separator, prefix/hash/salt behavior, date or period formatting, one expected example, and `confirmed = False` until docs, code, or logs prove the rule.

Support injected `hbase_data`, `hbase_client`, `fs_client`, `gateway_client`, and `pipeline_client` for local verification without production access.

Deployment evidence must confirm:

- resolved current date and period list
- HBase source table, row range, and source row counts
- before/after filter or aggregation counts
- generated FS filename and destination
- downstream process UID activation result, when enabled

Do not claim the downstream calculation/write component is implemented when only the prepare export is present.
