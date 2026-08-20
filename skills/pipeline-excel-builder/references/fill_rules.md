# Pipeline Export Fill Rules

## Evidence Priority

1. Explicit user-confirmed overrides for this workbook.
2. DataEngine/waterline technical document embedded Excel and Word tables.
3. DataEngine/waterline technical document paragraphs near the embedded table.
4. PRD tables and paragraphs.
5. Production Excel examples, only for schema/style reference unless the user explicitly authorizes copying business values.

## Workbook Write Mode

- Default to filling the user-provided Pipeline Export workbook in place.
- Write a separate workbook only when the user explicitly asks for a copy or the CLI receives `--out-xlsx`.
- Preserve the original workbook structure; only rewrite data rows from row 3 onward in the four data sheets.
- If the provided workbook already has data rows, preserve the existing key order and append newly inferred rows after existing keys.
- Preserve existing blank/null style cells, but do not create new empty optional cells or empty inline-string cells.

## Data Utilization

- Use unique `report_targets[*].data_utilization`.
- Ignore noisy `data_utilizations` rows extracted from unrelated field dictionaries unless they also appear in `report_targets`.
- Fill `data_utilization_description` from a matching `data_utilizations[*].description` row when available.
- If no matching description is available, leave `data_utilization_description` blank and keep the row otherwise valid.

## Target & Catalog

- Use `report_targets` as the target list.
- Merge physical table evidence from `report_physical_targets` by exact physical table, target table suffix, or description.
- Use the `target_name` already present in `report_targets`; do not rename it to the physical table.
- Fill catalog fields from `report_catalog_basic_info` when the current project document contains a Catalog Basic Info table.
- Match catalog rows by physical table suffix, for example `abnormal_monitor.qas_feedback_detail` -> `qas_feedback_detail`.
- Fill catalog registration fields only for project-owned/report output tables. For QAS-style projects this means tables with the project prefix such as `qas_`; shared/reference tables such as `soldto_details_p` keep catalog fields blank even if the document lists catalog evidence.
- Set `dataset_name` and `dataset_title` to the Catalog Basic Info data item name. Set `dataset_description` to the Catalog Basic Info title/description.
- For owner/name columns, prefer a person-style value. If the document only provides an email, derive a name from the email local part, remove digits, and format it as words, for example `tracy.zhang1@effem.com` -> `Tracy Zhang`.
- Fill email columns with the extracted email address.
- Keep `dataset_source` blank unless the document provides source/link text.
- If paragraph text claims a target count that conflicts with extracted target rows, keep extracted rows and add a question.

## Target Field

- Use `report_field_mappings`.
- For duplicate target dictionaries, prefer entries from the DataEngine/waterline document over PRD entries.
- Include only mappings whose target appears in `Target & Catalog`.
- Set:
  - `field_name` from target field/key.
  - `field_label` as the same text as `field_name`.
  - `field_description` from the Chinese/business field name or field description, not from calculation logic.
  - `field_type` as the fixed workbook value `TEXT`, regardless of the source document field type.
  - `field_length` as the fixed workbook text value `200`.
  - `field_sequence` as a text string from 0 in target-local order.
- Do not invent missing fields for targets without a field dictionary; add a question instead.

## Pipeline

- Use `report_schedules`.
- Set `enable = 1`, `is_octopus = 0`.
- Leave all timing columns blank for every pipeline row: `pipeline_trigger`, `pipeline_trigger_start`, and `pipeline_trigger_end`.
- Leave `pipeline_status_notification` blank unless a confirmed workbook/source value must be preserved.
- Keep only pipeline rows with a high-confidence `task1_link_target_names` inference. Skip broad helper pipelines whose target links cannot be inferred.
- Infer `task1_link_target_names` from exact target/table-name evidence, project-prefix-stripped aliases, and clear period groups. For example, a period pipeline links project-owned `_period` targets, and `incr_sync_soldto_details_p` links `clickhouse_soldto_details_p`.
- Store blank timing cells as absent/null cells, not empty string cells.
- Store non-empty workbook text cells as shared strings (`xl/sharedStrings.xml`, `t="s"`), matching platform exports.
- Leave `task1_mlp_params` blank when not explicitly confirmed.

## Questions

Always write questions for:

- Conflicting target counts.
- Targets without field dictionaries.
- Blank task-target links.
- Blank MLP params.
- Blank owner/email/catalog fields when the target appears to require catalog registration.
