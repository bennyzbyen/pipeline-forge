# Platform Client Usage

Use this reference when generated sync code touches local `gateway/`, `fs/`, or `hbase` packages.

## Gateway Facade

- Inspect the target project first. Existing projects may expose either `Client` or `GateWayClient`; preserve the local class name and import style.
- Business code should call the facade only:

```python
gateway_client = Client(app_key, app_secret, env=env)  # or GateWayClient
hbase_client = gateway_client.getHbaseClient(fs_root_dir=fs_root_dir)
fs_client = gateway_client.getFsClient()
```

- Do not generate business code that calls `gateway.operate.get_authorization`, token/header helpers, `call_get_gateway_api`, `call_post_gateway_api`, or raw `requests`.
- Keep `gateway/`, `fs/`, and `hbase/` as fixed platform packages. Put table-specific behavior in sync modules and config.

## FS Patterns

- Default download pattern: `exists(remote)` -> `copy_to_local(remote, local)` -> Pandas reads local file -> delete the local temp file.
- Default upload pattern: write a local temp CSV/TSV/GZIP file -> `copy_from_local(local, remote, overwrite=True)` -> delete the local temp file.
- `copy_to_local` parameter order is remote first, local second. `copy_from_local` is local first, remote second.
- Use `listdir(dir)` only for documented directories; handle missing/empty remote paths explicitly.
- Avoid generating `open`, `append`, `rename`, `mkdirs`, direct chunk upload, or direct `fs.operate_common` calls unless the existing project already uses that exact pattern.
- Let HBase wrappers manage their own FS export/import/delete temp directories; do not hand-build `fs_root_dir/export`, `fs_root_dir/import`, or `fs_root_dir/delete` paths in business code.

## HBase Read Patterns

- Create HBase clients through the Gateway facade. Pass the configured `fs_root_dir` to `getHbaseClient` when available.
- Prefer `query_df(...)` with the default export mode. Do not set `mode="query"` unless the existing project already uses it.
- Period/range reads normally use `row_start=period`, `row_stop=f"{period}Z"`.
- When rowkey prefixes are required, use `row_prefixs=[str(i) for i in range(10)]`.
- Full dimension reads may omit `row_start`, `row_stop`, and `row_prefixs`; do not treat omitted prefixes as a custom no-prefix mode.
- Use `value_filters` only when the existing project or requirement explicitly uses it, and include filter columns in `columns`.

## HBase Write Patterns

- Prefer `insert_df(df, hbase_table_name, mode="import")` for DataFrame writes.
- Prefer `insert_file(file_path, sep="\x1D", columns=columns, hbase_table_name=table)` for file writes.
- Do not generate `mode="insert"`; the sync wrapper's sync insert path is incomplete or unsupported in samples.
- Do not call `HbaseClient.delete(...)`; use `delete_df(df_with_rowkey, hbase_table_name)` or table-level `truncate(...)` only when the refresh strategy is explicit.
- Do not call `import_df` or `import_file` unless the code also handles the returned async task id.
- Do not manually prefix normal columns with `info:`; project wrappers add the HBase family prefix where needed.

## Rowkey Rules

- Generated COT-style rowkeys usually concatenate `rowkey_rule_columns` in order, then prefix the concatenated key with its last character.
- Insert DataFrames should place the rowkey column first. Wrapper constants may use `HBASE_ROW_KEY` for writes and return `rowkey` for exports.
- File-write paths may use `rowkey` in generated CSVs; wrapper code maps it to `HBASE_ROW_KEY` when required.
- Never guess rowkey fields. Keep uncertain rowkeys in `cot_config/rowkey_config.py` and `questions.md`.

## Avoid By Default

- `mode="insert"`
- `HbaseClient.delete(...)`
- direct Gateway token/header/API calls
- raw `requests` against Gateway endpoints
- direct `fs.operate_common` or `hbase.operate_common` calls from business modules
- `open`, `append`, `rename`, `mkdirs`, direct chunk upload, `get_path_meta`
- `count`, `table_columns`, `table_sample`, `export_gateway_fs`, `insert_gateway_fs` as normal generation paths
