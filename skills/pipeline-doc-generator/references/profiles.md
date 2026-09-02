# Waterline Profiles

Choose a profile from the actual data work. A filename containing “同步”, “报表”, or “PRD” is supporting evidence only.

## Sync Profile

Use `sync` when the main outcome is one-to-one or parameterized table movement, annual table rollover, or incremental/full replication with little business calculation. Follow `assets/sync_template.md` exactly at H1/H2 level.

Required evidence includes each source's confirmed data location/storage type (such as Blob, HBase, or MySQL), source and target physical identities, source range or watermark, field mapping, full/incremental behavior, write order, schedules, Pipeline/Task mapping, resources, and go-live value. The sync source table must display the confirmed data location as its own column. Keep the H1 title as `3. Target`; do not name storage engines in the heading.

The Target table is a horizontal source-to-target mapping. Render exactly one row per source, always including `原表位置` and `原表名`. Derive the related targets from stable source/target IDs in Pipeline mappings, explicit target source IDs, or target-field source IDs. Add `HBase表名`, `ClickHouse表名`, `MySQL表名`, or equivalent columns only for target storage types actually present in `facts.json`. When one source maps to several storage types, keep them on that source's single row. When it maps to multiple tables in one storage type, preserve target order and separate the values with `<br>`. Do not emit a generic `目标表` column or an unused storage-specific column.

Before the first formal render of each new sync document, ask the user to confirm the three independent optional Target columns: `所属类别`, `报表类型`, and `数据范围`. Record the answers as explicit booleans in `render_preferences.include_target_category`, `render_preferences.include_target_report_type`, and `render_preferences.include_target_range`. Missing or null choices block formal output through `PL-BLOCK-TARGET-OPTIONAL-COLUMNS`; later edits reuse the recorded choices unless the user changes them.

Render `所属类别` or `报表类型` only when its corresponding choice is true. When target range is requested, add one storage-neutral `数据范围` column. Never create separate `HBase数据范围` or `ClickHouse数据范围` columns. For several target storage types, prefix each value with its storage label inside the shared cell. Target Management remains storage-neutral. A user-confirmed literal `待定` is acceptable only when its JSON pointer appears in `confirmed_pending_paths`.

Omit `target前缀` from Target Management and `pipeline前缀` from Pipeline Management. They were spreadsheet formula-helper columns and are not part of generated Markdown, HTML, or PDF, even when legacy `prefix`, `target_prefix`, `hbase_prefix`, or `clickhouse_prefix` values remain in `facts.json`.

After sync Pipeline Management, always render `4.2.4 Catalog Basic Info` using the same Basic Info table columns as the report profile. Ask whether Catalog applies through `catalog.enabled`. When enabled, require at least one `catalog.basic_info` record; derive only Data Item and Title from confirmed target facts when appropriate, and leave unconfirmed owner/email values empty. When disabled, keep the section and write `不适用（已确认）`.

## Report Profile

Use `report` when outputs depend on joins, filters, KPI/abnormal rules, aggregation, feedback updates, or multiple processing stages. Follow `assets/report_template.md` exactly at H1/H2 level.

Required evidence includes source range and joins/filters, every physical target, grain, ordered field logic, Pipeline/Task mapping, schedule, Catalog applicability, and resources. Keep runtime, write, and rerun facts inside target logic or Pipeline descriptions rather than adding unapproved H1 sections.

## Ambiguous Or Mixed Projects

If the same project combines substantial calculation and independent table replication, ask whether the user wants one report-profile document or separate report/sync documents. Do not silently merge the two templates or add top-level sections.

## Stable Section Policy

- Preserve the selected profile’s H1 order and numbering.
- Target-specific and business-group headings may repeat as needed below the approved parent section.
- Omit no required H1. If the user confirms a section is not applicable, retain it and write `不适用（已确认）`.
- Do not reproduce spelling errors from source spreadsheets when the canonical platform term is clear; use `Pipeline Name` consistently.
