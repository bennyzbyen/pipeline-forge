# Target writes and lifecycle contracts

Use for empty snapshots, feedback, readiness, concurrent reads and manifest delivery. These are evidence-backed options, not project defaults. Generated `common_utils/delivery_contract.py` and `feedback_contract.py` provide portable primitives. Wire matching functions into the actual entrypoint and inject platform adapters; definitions alone do not prove execution.

## Target-specific empty behavior

`writes.<target>.empty_output_policy` accepts `skip` (legacy alias `block_destructive_replace`), `reject`, or `clear_slice`. The default preserves data. `clear_slice` requires `mode=replace_where` and `empty_snapshot_confirmed=true`. Missing/unavailable input (`None`) is never an empty snapshot. `clear_submitted` does not prove asynchronous mutation completion.

Composite predicates use `predicate: {"all": [{"column": "period", "value_from": "time_range.period"}, {"column": "date", "value_from": "params.target_date"}]}`. Only non-empty AND equalities are supported. Legacy single `column/value_from` remains valid. Shared SKU tables retain their own SKU predicate instead of inheriting report periods.

DELETE/INSERT and TRUNCATE/parallel INSERT are non-atomic. Existing truncate jobs must report cleared targets, completed/failed batches and partial writes; failures must not advance watermarks. Do not introduce truncate or a recovery strategy from samples alone. Atomic swaps/recovery require a confirmed adapter; the generic writer does not implement them.

## Readiness and concurrency

`readiness_gate` accepts `{enabled: true, manual_bypass: true|false, timeout_seconds: positive_number}`. The probe must enforce the timeout and return `ready` or `timeout`; it owns platform polling. Missing/disabled gates bypass. Manual reruns bypass only when declared. `skipped_upstream_timeout` prevents sync construction, writes and commits. Notification failure remains secondary.

`read_all` joins every future before returning or raising `SourceReadError`. `failed_sources` includes all failures; the cause preserves the first exception in input order. Failed required sources never become empty frames. Vehicle HBase/FS reads use it. FS errors propagate; missing paths are optional only with `optional=true`.

## Feedback and watermarks

Use confirmed keys, including period when personnel mappings change by period. `merge_feedback` preserves existing feedback on recomputed rows. `apply_feedback_updates` projects keys plus allowed feedback columns; classification and other fields never enter updates. Null/duplicate keys fail. Dry-run returns `watermark_candidate` and `watermark_advanced=false` without writer/commit calls.

Writer must return `completed` after checking mutation completion; `submitted` and exceptions never commit. Preserve a confirmed composite cursor (timestamp plus stable key), inclusive boundary with deduplication, or another declared tie strategy. Do not invent timestamp-only cursors for same-time changes.

## Snapshot and file delivery

`preflight_snapshot` checks expected tables, factory, concrete batch ID, `source_mode=full_snapshot`, `complete=true`, keys, required columns and explicit `allow_empty`. Mixed identities, missing tables, null/duplicate keys and unauthorized empties fail before writing.

`publish_snapshot` requires atomic `reserve_batch(factory,batch)` that rejects existing/reserved/completed batches. Write immutable data before a create-only completion manifest. Partial failed batches stay reserved for explicit recovery. Resolve `latest` once, then use that concrete batch throughout. Verify backend atomicity/create-only semantics with the actual adapter before deployment.

`deliver_files` separates source mode (`full_snapshot`/`incremental`) from receiver coverage (`replace`/`merge`), routes `upsert` and `delete` separately, rejects unknown modes, and commits after all calls succeed. `transfer_committed` does not assert receiver completion. Upload, manifest, activation and receiver completion are separate stages. Inspect actual calls rather than success-file helper definitions.

Run `scripts/verify_p0_lifecycle.py` after changes. It checks generated storage/vehicle filtering and lifecycle primitives with synthetic adapters. Also inject failures through each generated project's entrypoint and assert process/write/commit are not called. Fixture success is not adapter-wiring or deployment proof.
