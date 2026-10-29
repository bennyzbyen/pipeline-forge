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
- Follow confirmed facts order; field rows must follow the confirmed dictionary order with matching sequence. Match existing row styles by business key where available.
- Preserve physical row boundaries and styles, adding a final true blank row when necessary. Keep every row shell from row 3 through that final row. Clear unused tail cells to untyped true blanks. See [Java import compatibility](java_import_compatibility.md).
- Always validate the saved candidate against the untouched original export, including metadata, relationships, Readme, headers and worksheet layout. An import-only pass does not establish template equality. Freeze the mapped business rows before the writer and compare exact cell values, including raw XML, before publication.
- For format-only corrections, retain a temporary pre-edit reference and use the validator's `--business-reference-xlsx` together with `--template-xlsx`. Preserve active business cell existence/type/value, including typed empty strings versus null. Never repair formatting by regenerating business values from stale facts or reserializing parameter XML. Validate first, atomically replace the original final filename, verify published bytes, and remove temporary copies.

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
- Register Catalog only where confirmed by the source or user. Do not decide ownership by a name prefix alone. If one data item matches multiple storage targets, require a confirmed Catalog `target_name` binding; otherwise reject duplicate dataset registrations.
- Set `dataset_name` and `dataset_title` to the Catalog Basic Info data item name. Set `dataset_description` to the Catalog Basic Info title/description.
- For owner/name columns, use a confirmed person name. An email address alone does not establish a person's display name; leave the name blank for confirmation.
- Fill email columns with the extracted email address.
- A nonblank dataset_name requires title, description and all five confirmed contact name/email pairs. Missing values block generation. Keep `dataset_source` blank unless the document provides confirmed datasource XML; ordinary URLs or prose are not that XML.
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
- Fill timing columns only from confirmed schedule facts. Without `pipeline_trigger`, keep the timing and notification columns blank, including `pipeline_status_notification`.
- Use `每天 HH:mm` or `每N天 HH:mm`, a required valid start date and optional end not before start. Status tokens have no padding; notifications require ASCII-comma-separated emails matching the Java regex. Without AsyncJobStatusEnum, enum membership remains unverified.
- Preserve explicit confirmed `task1_link_target_names` before considering inference. Missing, duplicate or unknown links block generation; never silently skip a declared pipeline, including execution/helper pipelines.
- Infer `task1_link_target_names` from exact target/table-name evidence, project-prefix-stripped aliases, and clear period groups. For example, a period pipeline links project-owned `_period` targets, and `incr_sync_soldto_details_p` links `clickhouse_soldto_details_p`.
- Store blank timing cells as absent/null cells, not empty string cells.
- Store non-empty workbook text cells as shared strings (`xl/sharedStrings.xml`, `t="s"`), matching platform exports.
- Missing MLP XML for a linked task blocks generation; obtain confirmation instead of a placeholder. Explicit unlinked tasks may leave it blank, with a reported question.
- When supplied, retain MLP XML/CDATA/class/parameter text exactly and validate XML plus embedded JSON. Check runtime class and required keys against confirmed code or contract separately; offline syntax validation does not prove execution compatibility.
- Pipeline uniqueness is per DU; task links must stay in that DU. Multiple tasks use the ordered `tasks` list described in the Java compatibility reference and the template's complete four-column groups.

## Questions

Always write questions for:

- Conflicting target counts.
- Targets without field dictionaries.
- Blank task-target links.
- Blank MLP params.
- Blank owner/email/catalog fields when the target appears to require catalog registration.
