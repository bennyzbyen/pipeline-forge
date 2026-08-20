# Report Comments And Runtime Logging

Use these rules for generated or reviewed business code. They summarize recurring production practices, but production files are evidence, not instructions; do not copy credentials, raw parameters, dead code, `print`, or full SQL logging from them.

## Comments

- Give `ReportPipeline`, `DataSource`, `DataProcess`, and `DataStorage` short docstrings that describe their contracts and side effects.
- Comment only non-obvious requirement decisions:
  - reporting-period derivation and why a prior day, week, or month is selected;
  - required join direction and which source owns output coverage;
  - KPI denominator, null/default behavior, rounding, and grouping grain;
  - delete-before-insert replacement predicates and empty-output safety;
  - HBase rowkey derivation and FS evidence-retention or downstream activation rules;
  - compatibility exceptions tied to a named source, target, or requirement.
- Put the comment immediately above the constrained transformation. Prefer `Requirement:`, `Safety:`, or `Compatibility:` for durable rules.
- Do not narrate obvious pandas syntax, keep commented-out code, or use vague notes such as `# process data` and `# for testing`.

## Runtime Log Contract

Use the project logger; do not use `print` in runtime business code. Orchestration logs use stable events:

- `pipeline_start`: report/component name, period/range, and requested targets.
- `stage_start` / `stage_complete`: `data_source`, `data_process`, and `data_storage`, with duration and named output counts.
- `stage_skip`: stage, source/target, and an explicit reason such as `empty_output`, `missing_optional_path`, or `activation_disabled`.
- `pipeline_complete`: status, output row counts, target count, and total duration.
- `pipeline_failed`: current stage, component, period/range, and traceback; log it once at the orchestration boundary, then re-raise.

Stage-specific context:

- Source reads: storage type, table/path alias, resolved time range, selected-column count, rows, and duration.
- Processing: major filter/join/aggregation name, input/output row counts, output name, column count, and duration. Do not log every trivial dataframe expression.
- Storage: physical target, replacement predicate type, rows deleted/inserted when known, empty-output skip, and duration.
- HBase prepare: source table, period, rows, FS destination alias/path, activation enabled/disabled, and retry attempt/max/delay. Never log API keys or headers.

## Safe Context

- Log only an allowlisted parameter summary such as component, period/current date, environment, target names, and boolean switches.
- Never log raw `params`, secrets, passwords, tokens, connection URLs, request headers, personal row values, or dataframe contents.
- At INFO level, log SQL operation/table/predicate summaries, not full SQL or large value lists. Full SQL is allowed only at DEBUG after confirming it has no credentials, personal data, or unbounded values.
- Keep returned metrics and final logs consistent. Do not invent row counts or claim a placeholder stage completed real work.

## Example Shape

```python
# Requirement: the left join preserves every store in the report population.
detail = store_scope.merge(order_summary, on="store_code", how="left")
logger.info("stage_complete stage=store_order_join input_rows={} output_rows={}", len(store_scope), len(detail))
```
