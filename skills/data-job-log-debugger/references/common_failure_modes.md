# Common Data Job Failure Modes

Use this order before proposing code changes.

## 1. Command And Environment

- Wrong working directory.
- Windows path quoting issue.
- `python -c` quoting or encoding problem.
- Missing package in deployment image.
- Different Python version between local and platform.
- `running_env` missing or unexpected.

## 2. Parameter Problems

- DataEngine wrapped `algorithm_io_mode == "SINGLE"` params not unwrapped.
- JSON string inside `body.params` not parsed.
- Missing `period`, `current_date`, `source_informations`, target table, rowkey fields, or receiver emails.
- Empty credentials placeholders deployed by mistake.
- COT sync params should use grouped `source_informations`, `hbase_informations`, and `clickhouse_information`.
- Runtime ClickHouse table params should normally be bare table names; historical database prefixes should be handled by config exceptions.

## 3. Path And Encoding

- Local temp file not removed or reused by concurrent runs.
- FS path exists check uses parent path but reads child path.
- Chinese file names or CSV encoding mismatch.
- CSV separator mismatch: comma, tab, or `\x1D`.
- Gzip file read without compression setting.

## 4. Data Absence

- Source table returns zero rows for the selected period/date.
- Calendar lacks current date or target period.
- HBase row range or row prefix excludes expected rows.
- FS directory exists but contains only `_SUCCESS` or no data files.
- Upstream table changed field names.
- COT "无更新数据", `no_changed_rows`, and `no_changed_periods` are usually data/timestamp conditions first, not code defects.
- Manual period reruns should not advance stored timestamp; automatic incremental runs should update timestamp only after successful writes.

## 5. Gateway / HBase / ClickHouse

- Gateway auth failed.
- HBase export async task not complete.
- HBase insert file missing `rowkey`.
- Duplicate or empty rowkeys.
- ClickHouse mutation still running.
- ClickHouse insert column order/type mismatch.
- Cluster clause missing or wrong for PROD.
- HBase rowkey failures often appear as missing `period`, `code`, `store_code`, `id`, `inksaa_id`, or `salesman_code` in CSV headers.
- COT with-period full refresh should drop CK partition and delete stale HBase rowkeys before insert.
- COT without-period should delete CK rows by key, except configured truncate tables such as `wechat_authorization_info`.
- CK/HBase truncate is destructive; confirm the table is in the configured truncate list before recommending a rerun.

## 6. Business Logic

- Join key mismatch after rename.
- Numeric conversion fails because of blanks or Chinese text.
- Grouping keys produce unexpected duplicates.
- Filter removes all rows.
- KPI denominator is zero or null.
- Expected full-coverage rows are dropped by an inner join or `dropna`.

## Output Format

Always report:

- confirmed issue
- high-confidence assumptions
- uncertain points
- recommended next steps
- verification command or deployment log line to check
- whether HBase, ClickHouse, FS, and timestamp update steps ran before failure
