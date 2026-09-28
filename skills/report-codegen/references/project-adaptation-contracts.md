# Project adaptation contracts

Use the relevant section when requirements involve entry envelopes, business calendars,
multiple output stages, DTR orders, or historical business examples. These capabilities
work without a local knowledge vault. Knowledge IDs below identify the reviewed cases;
they are not approvals to apply a rule to a new project.

## Entry protocol (PFE-001 / PFK-001)

Record `codegen_contract.entry_contract` as
`{"profile":"q3","confirmed":true,"evidence":["requirement section or reviewed entrypoint"]}`.
The report and sync scaffolders generate `entry_contract.py`; the actual entrypoint reads it.
Missing entry_contract retains the existing COT-compatible behavior. A provided but
unconfirmed or unknown contract fails generation before output replacement.

| Profile | Input | Result |
| --- | --- | --- |
| cot | SINGLE: JSON text in params.body.params; otherwise top-level object | SINGLE overwrites input; otherwise ./result.txt |
| direct | Complete top-level object; do not interpret nested params | ./result.txt |
| q3 | SINGLE with object directly in params; other modes rejected | Overwrite input |

The bundled `project_contracts.load_entry` unwraps once and validates object shape.
Never choose a profile by guessing from whether a key named `params` happens to exist.

## Calendar and batch parameters (PFE-008)

Both minimal scaffolds include `project_contracts` (report: `common_utils/`; sync: root).
Wire the selected helpers into the generated project's real orchestration after its
calendar adapter has normalized date/period/week/day fields. They are optional primitives,
not an alternate automatic calendar source.

- `period_window`: chronological contiguous 13P calendar; explicit `recent`,
  `ytd_with_minimum` or `from` policy. Missing history/start P raises an error.
  PFW-005's NPD uses YTD with minimum four periods across years; B5 starts at an
  explicitly supplied business P. Neither is a universal default. PFK-010's `r6p`
  variable actually sliced four periods; preserve this conflict until scope is adopted.
- `execute_periods`: execution date and trigger date are separate. Optional `(2,2)`
  backfill follows the PFW-006 historical algorithm: find the last earlier calendar row
  whose P differs from the execution P. If execution and trigger are in different Ps,
  this may differ from "previous P of trigger"; establish the intended rule and test it.
  No system date fallback when either date is missing from the calendar.
- `dates_for_table`: declare whether dates apply. PFK-009 non-date tables run once;
  date-scoped tables run per supplied date. `None` is passed to the adapter only when
  its existing default date contract permits it.
- `period_list(array_required=True)` for PFW-012 soldto: array only, P01–P13,
  stable deduplication. Other COT entrypoints retain their scalar/list contract.
  `run_periods` isolates each P's output directory; failure records failed P and completed Ps.
  It stops on failure and never claims a retry or rollback. The caller owns run ID and
  per-period idempotent write/watermark contracts.

## Dependencies and delivery (PFE-009)

Use the existing two-level code-unit plan; do not make one unit per output table.
Preserve every schedule and unresolved target mapping. PFK-017 has four schedule
observations and eight targets, which is insufficient evidence for eight code units.

Bind intermediate artifacts to producer, consumer, exact name/path, schema, batch/date,
completion evidence and rerun policy in each unit's existing contract. Verify this at the
consumer entrypoint before processing. `require_artifacts` checks expected names,
completion and batch; schema/hash validation remains the storage adapter's responsibility.

- PFW-013: T-1 produces `df_store`, `df_store_p8`; T+0 has six output groups.
  Do not substitute the six target tables for the two intermediate contracts. Logical
  aliases such as df_t1/df_t2 need an evidenced physical mapping.
- PFK-011: prepare, NPD and B5 remain separately scoped. Failed prepare prevents activation;
  activation acknowledgment is `triggered`, not downstream `completed`.
- PFW-014: HBase calculation and Mongo delivery have separate statuses. `run_stages`
  retains completed stage names in `UnitFailure`; if delivery fails, retain the immutable
  calculation batch and retry only delivery using its confirmed replacement/idempotency
  contract. Do not recompute or clear unrelated periods as automatic compensation.

## Business examples (PFE-011 / PFE-012)

`scripts/project_business_examples.py` contains executable synthetic examples, deliberately
outside generated templates. Use `scripts/verify_p1_contracts.py` to exercise them. Adapt
only the relevant example after the project contract is established; they are not a
complete implementation of O2O, q3, DSD or store grading.

| Evidence | Decision preserved by the example |
| --- | --- |
| PFW-002 | Historical O2O OR flags versus working date + data_type != D. Missing data_type is included by the working Mongo $ne predicate; the historical pandas column filter may fail if the column is absent. Null/missing policy and version adoption must be explicit. Source failure is not an empty success. |
| PFK-013 | Geography uses the full composite key, exact duplicate rows may collapse; conflicting duplicate values block without a selection policy. many_to_one validation prevents row multiplication; missing mapping errors or carries degraded status. |
| PFK-015 | Grade after two-decimal Python round; zero denominator yields zero; historical thresholds 60 and 130 are example-only. Do not substitute DTR HALF_UP rounding. |
| PFK-022 | Rebuild affected upper totals after exclusions. The example sums explicitly additive targets; it does not infer all historical exclusion rules. |
| PFW-007 | q3 province/region example uses inner matching at each layer, excludes unmatched actuals and does not synthesize target-only rows. Preserve acuracy_rate spelling, require the column; null values default to 1 in this version. Cap 1.1 then round four decimals. Upper layers must join their own target/accuracy rows, never sum child rates. Zero target behavior still needs the project's rule. |
| PFW-024 | DSD purchase frequency counts distinct store/day; GSV sums all corresponding rows within explicit inclusive bounds. |

## DTR precision, streaming and audit (PFE-013)

PFW-015–017 are separate contracts:

1. Select quantity using confirmed sales/return status, order source and interconnect
   rules. Status `4` means delivered quantity in the sales example and cancellation
   in the return example; EO overrides are supplied explicitly. Conversion-factor join
   keys are independent facts. Do not copy sales routing into returns.
2. `decimal_tdu` takes Decimal/text/integer values, divides quantity by factor and
   multiplies price by factor. Missing/zero factor returns null values; finite inputs
   quantize with Decimal HALF_UP to ten places. It rejects float inputs to avoid
   silently inheriting binary rounding. Target NUMERIC range and negative-factor
   business rules remain project validation.
3. Inject a real server-side cursor into `stream_batches`; fetchmany alone does not prove
   streaming at the driver. Choose batch size from configuration, not the historical
   200000 constant. Transform must be row-local; global aggregates require separate
   accumulator contracts. Write acknowledges durable per-batch commit before counting it.
   Failure carries completed batch count, failed batch and phase; watermark commits only
   at the end. Reconcile an uncertain failed write before replay; completed batches are
   not automatically rolled back.
4. `audited_delete` requires durable recording of the exact old IDs before deletion.
   Read and delete must refer to the same version/snapshot or be protected by a transaction
   or lock; the helper cannot guarantee database concurrency isolation. Retain the audit
   after delete failure and use the project's explicit downstream notification/retention rule.

## File matching and historical hazards (PFE-014 / PFE-016)

`select_file` only accepts the exact table filename or table_YYYYmmddHHMMSS suffix.
Other naming conventions require a declared adapter, not suffix-only fallback. Multiple
candidates require an explicit latest policy and valid timestamps; ties fail. Return the
chosen path as selection evidence; do not use filesystem enumeration order.

`scripts/verify_generated_safety.py --project-dir <generated-project>` checks literal
credentials, `verify=False`, literal raises and raw runtime-parameter logging without
printing source values. Both observability validators also run it. Use external config,
real Exception objects and scoped metrics. Existing in-scope credentials in a user's file
are not silently rewritten: report the finding and distinguish it from newly generated code.
The check is bounded AST inspection, not a complete secret detector or data-flow proof;
manually review aliases, dynamic construction, connection URLs and logging wrappers.

After adapting these primitives, verify actual entrypoint calls with fake adapters and
failure injection. A passing example suite alone does not establish production behavior.
