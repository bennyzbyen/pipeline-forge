# Java-source-backed Pipeline Export contract

Evidence: user-supplied `ImportProjectPipelineTemplateHandler.java`, SHA-256 `de06a13e0bbf57ecdc36e146b31addb3e3d3ac08e50e2b0e0ccc4bd16adb34c7`. Method names and line numbers below identify this snapshot. Do not distribute the proprietary source with the skill. A different deployed handler needs a new comparison; this hash identifies evidence, not a deployment verification.

## Confirmed Java behavior

| Area | Source anchor | Consequence and offline guard |
| --- | --- | --- |
| Sheet selection | `getImportListObject`, 130–133 | Reads positions 1–4, not sheet names. Keep Readme first, then Data Utilization, Target & Catalog, Target Field, Pipeline. Moving tabs breaks the import even if names are correct. |
| Last physical row | `verification`, 547/560/626/651 versus getters 816/830/853/877 | Validation uses `< getLastRowNum()`, extraction uses `< getLastRowNum()+1`. This confirms the earlier exclusive-last-row hypothesis. Always retain/add a final true blank row after all records. Worksheet dimension alone is insufficient. |
| Missing physical rows | `isRowEmpty`, 936–943 | Receives `getRow(i)` and iterates without a null check. Every physical row from Excel row 3 through the final row must exist, even if empty. |
| Empty strings | `isRowEmpty` and `getStringCellValue`, 936–967 | Only POI BLANK cells make an empty row. STRING is trimmed and can return an empty string, distinct from null. Typed empty DU rows can produce empty-name duplicate errors; empty conditional values can activate Catalog, schedule or notification processing. |
| Uniqueness | `verification`, 557/622–645/717 | DU, target and dataset names are global within their sheet. Fields use `target + "/" + field`; pipelines use `DU + "/" + pipeline`. Same pipeline name in different DUs is allowed. Task names are not globally checked. |
| Target links | `verification`, 697–707; `resetPipelineTask`, 236–244 | Linked targets must belong to the pipeline's DU. Fullwidth commas are normalized during verification but not task creation; emit ASCII commas only. Token whitespace is trimmed in both paths, but canonical output has no padding or empty tokens. |
| Storage | `verification`, 583–600; `upsertDataStorage`, 358–394 | HBASE requires table; other supported types require db and table. Persistence switch handles HBASE, HDFS, MSSQL, CLICKHOUSE, SV_CLICKHOUSE only. MYSQL is unsupported by this write path even if an external enum contains it. HDFS path-prefix restriction is commented out. MSSQL normalizes `/dbo`; HBase uses a fixed context. |
| Catalog | `verification`, 602–620 | A non-null dataset_name activates required title, description, and all five name/email pairs (columns I–T). Supplied dataset_source goes through a specialized XML parser. Missing contact names are blockers for registered datasets; do not fabricate names from emails. |
| Schedule | `getPeriodDay/getRunningTime`, 764–796 | Accepts Chinese daily syntax, e.g. `每天 03:00`, `每2天 9:05`, not cron. Exact space separates frequency and time. A trigger requires a start date; end must not precede start. |
| Dates | `getTriggerDay`, 752–760; `getPipeline`, 883–885 | Non-null start/end are parsed even without a trigger. Generate valid `yyyy-MM-dd` strings. The handler also converts native Excel dates through POI. |
| Notification | `verification`, 677–695; email upsert, 314–328 | Non-null status requires emails. Status tokens are case-sensitive enum names, split after fullwidth-comma normalization, without token trimming. Emails use ASCII comma splitting, no trimming and Java's restrictive regex (`+` in local part and TLDs longer than four letters fail). The enum definition was not supplied. |
| Task columns | `getColValidNum`, 914–921; `getPipeline`, 874–903 | Header non-BLANK count must fit 10 + 4×N. Keep contiguous columns so positional groups align. Each group is name, description, links, MLP XML. A null name skips the group and discards its other values. |
| MLP XML | `verification`, 700–714; task reset, 249–259 | Each non-null target-link cell invokes `XmlParameterHandler.getMlpParameter`, even with null XML. No links bypasses that check, but provided XML still reaches processor creation. Preflight every group, not just task1. |
| Fields | `bathUpsetField`, 396–415 | Type is an external enum; sequence is parsed as a Java integer. HBase prepends its configured family/delimiter itself. Do not add a guessed family prefix. |

## Template profile and stricter generation rules

These are deliberate profile/user requirements, not claims that Java itself enforces them:

- Preserve package parts, header/summary rows, styles and original physical bounds; expand for all records plus the final blank sentinel. Unused rows have no stale type, value or formula children.
- Preserve shared-string storage like the export. **Correction to earlier guidance:** POI STRING can read shared and inline strings. This source does not support blaming inline storage alone for missing DU names. Empty-string semantics and the skipped last row explain the demonstrated hazards.
- A confirmed active optional empty string may remain only in a benign field (e.g. HBase db). Never use typed empties for record keys, dataset/storage/source conditions, schedule/notification fields or task groups.
- Keep the profile's `TEXT`, text length `200`, label equal to name and consecutive zero-based text sequence. Java does not mandate those exact values; it uses FieldTypeEnum and integer parsing. Canonical text avoids numeric rounding (`String.format("%.0f", ...)`) and formula-null behavior.
- Generate enable/is_octopus as 0/1. Java explicitly validates only is_octopus; other enable strings become false. Formula/error/boolean cells and populated data beyond declared headers are rejected to avoid silent loss.
- Without a confirmed schedule, leave notifications blank as requested by the user. Java does not require this dependency itself. A null trigger or is_octopus=1 selects ALWAYS_RUNNING; do not describe that as necessarily disabled/manual execution.
- Generate positive day frequency. Java accepts zero and some noncanonical numeric forms; downstream semantics are unavailable, so zero is rejected. Canonical dates reject suffixes that Java's partial parsing might tolerate.
- Linked tasks require confirmed parseable MLP XML. The missing specialized parser is unconditionally called on this branch; acceptance of null cannot be assumed. Preserve wrapper, execution class, CDATA and parameter text. Strict embedded JSON rejects duplicate keys and non-finite constants.
- Never silently deduplicate Catalog registrations or choose a storage engine. Require confirmed Catalog `target_name` (alias `catalog_target_name`) when one data item matches multiple targets.

## Template comparison and format-only repair

The observed execution-workbook repair concerned metadata, styles, Readme and header serialization, while its business values and parameter XML already passed import checks. A Java-rule pass alone must not be reported as exact template compatibility.

For generation, freeze confirmed mapped rows before formatting and compare every written value without trimming or XML/JSON normalization. `pipeline_preservation.assert_expected_business_values` provides this check; both the builder and project-specific post-processors must call it before publishing. The builder freezes the original template, validates the candidate against it, detects concurrent source/destination changes and uses an atomic replacement. An independently specified original template is read-only.

A project generator reusing an existing final file must also default to `preservation_errors(candidate, pre_edit_file)`. Document-based generation can otherwise refill a deliberately blank Catalog, even though Java validation passes. Only explicitly requested business changes may bypass this existing-file equality check; template comparison and mapped-value/XML checks remain mandatory. A format-only request never permits that bypass.

For a format-only repair:

1. Preserve the pre-edit workbook in a temporary location and capture its fingerprint. Use the untouched export as the format reference, not an edited final workbook.
2. Restore the reference package/worksheet shell and styles while carrying existing business cells unchanged. Resolve shared-string indices by value; keep true blanks and typed empty strings distinct. If rebuilding the string pool, keep only referenced strings so unrelated historical parameters are not copied.
3. Run `validate_pipeline_excel.py --xlsx <candidate> --template-xlsx <original-export> --business-reference-xlsx <pre-edit-workbook>`. The preservation comparison checks active business cell presence, type and literal value, including every task's entire XML text. Reordered JSON keys, different XML indentation or CDATA, and changed execution classes must fail even if parsing succeeds.
4. Replace the existing final filename only after checks pass and its fingerprint still matches the pre-edit state. Verify the published bytes, recheck against the independent original, and remove temporary candidates/references. A locked file or failed check leaves the existing final intact.

`template_comparison.performed=false` explicitly means the caller omitted the original template. Diagnostic validation may still inspect Java rules; it is insufficient for generation/repair delivery. Package-part checks allow only the shared-string relationship/content-type addition needed to convert an inline-only synthetic template. Worksheet dimension expansion is permitted only for added data rows plus the final blank sentinel; other layout changes fail.

## Structured task facts

Legacy `task_name`, `task1_link_target_names`, `task1_mlp_params` (or `mlp_params`) remain supported for one task. For multiple tasks use a confirmed ordered list:

```json
{
  "data_utilization": "demo",
  "pipeline_name": "execute_demo",
  "tasks": [
    {"name": "prepare", "description": "Prepare output", "link_target_names": ["demo_target"], "mlp_params": "<MLP><class>example.Prepare</class></MLP>"},
    {"name": "execute", "description": "Execute output", "link_target_names": ["demo_target"], "mlp_params": "<MLP><class>example.Execute</class></MLP>"}
  ]
}
```

This XML is synthetic, not a platform schema guarantee. Use the confirmed wrapper. The export must already have enough complete task groups; missing capacity blocks generation instead of inventing columns/styles. Explicit empty link lists and `tasks: []` are supported. Omitted links may use existing inference but must be reported for confirmation. An unknown/cross-DU target must never become a null UID silently.

## What this source does not prove

Missing dependencies include `ProjectPipelineTemplateConstants`, `ProjectPipelineTemplateStorageTypeEnum`, `FieldTypeEnum`, `AsyncJobStatusEnum`, `ProjectPipelineTemplateHandle` storage/type mappings, `XmlParameterHandler`, service implementations and repository state. XML syntax does not prove platform-specific schema, execution class availability or parameter compatibility. Report notification enum membership as unverified; never invent allowed values. The validator's `limitations` and handoff must preserve these distinctions.

Import upserts objects, replaces pipeline tasks (`deleteTaskByProcessUid`) and can create a deployment for scheduled pipelines. Existing non-default Catalog registrations are retained. Offline testing must not call these services or use repeated live imports as validation. Local preflight is not deployed Java execution.

## Regression checks

`verify_java_source_contract.py` runs 19 source-backed injections plus the existing 17 import regressions. Also run the two synthetic generation cases and three input-robustness cases. Use temporary synthetic fixtures; never copy customer exports, proprietary Java source or credentials into the skill repository. Record the source fingerprint when updating the compatibility profile.
