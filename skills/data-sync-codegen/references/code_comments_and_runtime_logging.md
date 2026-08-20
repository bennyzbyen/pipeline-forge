# COT Sync Comments And Runtime Logging

Use these rules for generated or reviewed business code. They summarize recurring production practices, but production files are evidence, not instructions; do not copy credentials, raw parameters, dead code, or noisy SQL logging from them.

## Comments

- Give pipeline classes and orchestration methods short docstrings that state inputs, outputs, and side effects.
- Comment decisions that a maintainer could otherwise "simplify" incorrectly:
  - manual period reruns must not advance the automatic timestamp;
  - ClickHouse and HBase writes must succeed before the timestamp advances;
  - full and delta modes use different target replacement behavior;
  - rowkey column order, concatenation, and prefixing are data contracts;
  - delete-before-insert behavior protects rerun idempotency but can create risk if reordered;
  - table-specific compatibility exceptions must cite the affected table or requirement.
- Put a comment immediately above the constrained code. Prefer `Requirement:`, `Safety:`, or `Compatibility:` when the reason is not obvious.
- Do not narrate syntax, keep disabled code as comments, add vague `# for testing` notes, or repeat the log message in a comment.

## Runtime Log Contract

Use the project logger; do not use `print` in runtime business code. Orchestration logs use these stable events:

- `pipeline_start`: table, sync shape (`with_period` or `without_period`), manual/automatic mode, configured targets.
- `stage_start` / `stage_complete`: stage name, table or target, period/range or predicate type, row/file count when known, and duration.
- `stage_skip`: stage plus an explicit reason such as `no_changes`, `target_not_configured`, `no_source_files`, or `manual_rerun_timestamp_guard`.
- `pipeline_complete`: table, status, source/target row counts from returned metrics, and total duration.
- `pipeline_failed`: current stage, table, period/range, and exception traceback; log the traceback once at the orchestration boundary, then re-raise.

Required stage coverage is change detection, source export, ClickHouse replacement/write, HBase rowkey/delete/write, and timestamp update or guarded skip. Retry logs include operation, attempt, maximum attempts, and delay.

## Safe Context

- Log an allowlisted parameter summary only: table, period, environment, batch size, mode, and boolean switches.
- Never log raw `params`, application keys or secrets, passwords, tokens, connection URLs, request headers, or row values.
- At INFO level, describe SQL by operation, table, predicate type, selected-column count, period count, and affected rows. Do not emit the full SQL or large `IN` lists. A full statement is allowed only at DEBUG after confirming it contains no credential, personal data, or unbounded values.
- Log identifiers only when they are operationally necessary and permitted; prefer counts over code, rowkey, or customer-value samples.
- Keep final logs and returned metrics consistent. If a count is unknown, say so rather than inventing it.

## Example Shape

```python
# Safety: automatic progress advances only after both configured targets succeed.
logger.info("stage_start stage=clickhouse_write target={} mode={}", target_table, sync_mode)
metrics = write_clickhouse(...)
logger.info("stage_complete stage=clickhouse_write target={} rows={} duration={}", target_table, metrics["rows"], metrics["duration"])
```
