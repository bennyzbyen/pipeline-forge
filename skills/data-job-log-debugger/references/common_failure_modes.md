# DataEngine/DataHub Failure Modes

Use this reference after basic traceback analysis when platform-specific behavior affects the diagnosis.

## Lifecycle and completion evidence

- `skipped_upstream_timeout` means sync did not start; it is not an empty successful sync. Notification failure does not change that status. Manual bypass must be declared in the readiness contract.
- A worker traceback with continuing main-thread logs can mean swallowed parallel failure. Check all futures/joins and block transform/write when any required source fails; preserve failed-source names and exception cause.
- Distinguish missing source, no increment and complete empty snapshot. QAS-like daily clear may be correct for the exact period/date; vehicle skip may be correct for its contract. Do not recommend universal skip or truncate.
- Feedback dry-run produces a candidate watermark only. Writer submission is not mutation completion; do not recommend advancing past pending/failed updates. Same-time updates require a confirmed tie cursor.
- A partial replacement must retain cleared-target and completed/failed-batch evidence without claiming rollback or advancing progress. Re-run/recovery scope comes from the declared strategy.
- Manifest publication, upload, downstream activation and receiver completion are separate evidence. A helper definition or log before the call is not completion proof. Reject mixed factory/batch snapshots and unknown transfer modes; resolve latest to a concrete batch.

## Runtime Parameter Contracts

- DataEngine may wrap params under `algorithm_io_mode == "SINGLE"`; `body.params` may itself be a JSON string that requires parsing.
- COT sync params commonly group `source_informations`, `hbase_informations`, and `clickhouse_information`.
- Check required period/date, source table, target table, rowkey fields, batch size, and receiver values against the active component rather than assuming one universal shape.
- Runtime ClickHouse table params normally use bare table names; configured exceptions may supply legacy database prefixes.
- Placeholder credentials deployed unchanged are configuration failures, not values to replace from logs.

## Data And Incremental State

- A zero-row source can be valid for the selected period, calendar range, timestamp, HBase row range/prefix, or upstream state.
- An FS directory containing only `_SUCCESS`, or files whose period naming does not match params, is not usable report input.
- `no_changed_rows` and `no_changed_periods` are data/timestamp outcomes first, not code defects.
- Manual period reruns must not advance the stored incremental timestamp. Automatic runs update it only after all required writes succeed.

## Gateway, HBase, And ClickHouse

- Gateway authorization, HBase async export/import completion, FS file availability, and ClickHouse mutation completion are separate stages; determine which one actually failed.
- HBase writes require a non-empty unique rowkey. Missing `period`, `code`, `store_code`, `id`, `inksaa_id`, or `salesman_code` commonly surfaces as a rowkey/header failure.
- ClickHouse insert failures often reflect target column order/type mismatch or an incorrect PROD cluster clause.
- With-period full refresh may drop a ClickHouse partition and delete stale HBase rowkeys before insert.
- Without-period sync normally deletes changed ClickHouse keys before insert; only configured exceptions may truncate a table.
- Truncate, partition drop, and broad delete are destructive. Verify the configured table and rerun mode before recommending execution.

## Required Stage Evidence

Report whether the available log proves each applicable stage ran:

- source query and selected period/time range
- FS upload/download or HBase async task completion
- HBase delete/insert
- ClickHouse delete/drop/truncate and insert
- timestamp update
- final DataEngine metrics

When a plan or diagnostic manifest exists, compare observed targets, predicates, row counts, and stage order against it.
