# bySKU Report Document Handoff Rules

Use this reference when input documents describe a bySKU report pipeline, especially HBase -> FS preparation plus ClickHouse detail/summary/ttl outputs. 执行为王 / `execute_king` is only one sample alias for this shape, not the generic project type.

## Project Shape

Treat this document shape as a multi-component report pipeline, not as a COT data-sync project:

- PRD supplies business changes, SKU rules, rolling retention, table-volume expectations, and permission/geography rules.
- DataEngine design supplies source tables, target-management rows, field dictionaries, and pipeline schedules.
- The common implementation split is `prepare_data` plus calculation components such as NPD/B5/SKU calculation jobs. Do not hardcode those component names for unrelated projects.

Do not activate this route from the word `bySKU` or a `zo_bysku_detail_p` COT sync row alone. Require independent evidence of downstream SKU-family calculation, such as NPD/B5/新品 output families, `sku_map`/`sku_cal_range`/TTL parameters, prepare/calculation components, explicit detail-summary-TTL targets, or rolling R13P retention.

## Required Structured Facts

When evidence exists, `structured_facts.json` should expose:

- `component_hints[0].component_kind = "bysku_report_pipeline"`.
- HBase bySKU sources such as `zo_bysku_detail` tables when present.
- FS intermediate contract: bySKU files, gzip/csv format when stated, FS directory questions when not stated.
- ClickHouse physical targets for detail, summary, ttl, or channel tables. If inferred from PRD text rather than Target Management rows, set `requires_confirmation = true`.
- SKU config contract: `sku_map`, `sku_combo_map`, `sku_cal_range`, `sku_ttl_filter`, `sku_is_active`, and whether the source is XML, params JSON, or external config.
- Retention contract: keep latest R13P data; if exact delete SQL is absent, put the delete predicate in `questions.md`.

## Target Mapping Rules

- Split target strings that contain multiple output names. SKU report families often have detail, summary, and ttl outputs.
- Prefer explicit table names from field-section headings, table dictionaries, Target Management rows, or production config evidence.
- If only logical names are present, preserve them but add confirmation questions for physical `database.table`.
- Do not invent SKU formulas or active-SKU lists. Extract or ask.

## Handoff Quality Bar

Before handing off to `report-codegen`, confirm the dev doc or `questions.md` covers:

- component split: HBase-to-FS prepare plus one or more SKU calculation components
- source period behavior: daily current period, manual range, or R13P history
- FS file naming and overwrite behavior
- output table group: detail, summary, ttl, optional channel table
- ClickHouse delete condition for current week and rolling retention
- logs required for source rows, output rows, delete SQL, insert success, and retention cleanup

Also expose handoff readiness signals in prose or structured facts:

- `handoff_readiness` or equivalent checklist should mark missing physical targets, missing source fields, unmapped field dictionaries, unmatched schedules, and missing write predicates.
- Keep Data Utilization rows even when Excel merged cells leave the name blank; the blank row may be the second half of the same target group.
- Keep pipeline rows with blank Data Utilization values when they describe daily export or downstream calculation tasks.
- When a target cell contains several names, split or cross-reference detail, summary, ttl, and optional channel outputs instead of treating it as one output table.
