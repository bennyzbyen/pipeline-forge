# Pipeline Export Excel Schema

Pipeline Export workbooks use five fixed sheets. Data starts at row 3; rows 1 and 2 are template/header rows and must be preserved.

The builder should fill the user-provided workbook in place by default. A separate output workbook is only for explicit copy/export requests.

When refilling a workbook that already contains data rows, preserve existing row order by sheet key. Blank cells should remain null/style cells when they already exist in the workbook, but the builder should not create new empty optional cells.

## Sheets

| Sheet | Purpose |
| --- | --- |
| `Readme` | Platform import/export explanation. Do not edit. |
| `Data Utilization` | Data collection items. |
| `Target & Catalog` | Target definitions, storage, and optional catalog registration fields. |
| `Target Field` | Field dictionary for each target. |
| `Pipeline` | Pipeline, task, schedule, notification, target-link, and MLP param rows. |

## Headers

### Data Utilization

| Column | Header | Required |
| --- | --- | --- |
| A | `*data_utilization_name` | yes |
| B | `data_utilization_description` | no |

### Target & Catalog

| Column | Header | Required |
| --- | --- | --- |
| A | `*data_utilization_name` | yes |
| B | `*target_name` | yes |
| C | `target_description` | no |
| D | `data_storage_type` | no |
| E | `db` | no |
| F | `table_name` | no |
| G | `table_description` | no |
| H | `dataset_name` | no |
| I | `dataset_title` | no |
| J | `dataset_description` | no |
| K | `dataset_business_owner` | no |
| L | `dataset_business_owner_email` | no |
| M | `dataset_it_owner` | no |
| N | `dataset_it_owner_email` | no |
| O | `dataset_fe` | no |
| P | `dataset_fe_email` | no |
| Q | `dataset_it_bp` | no |
| R | `dataset_it_bp_email` | no |
| S | `dataset_data_engineer` | no |
| T | `dataset_data_engineer_email` | no |
| U | `dataset_source` | no |

### Target Field

| Column | Header | Required |
| --- | --- | --- |
| A | `*target_name` | yes |
| B | `*field_name` | yes |
| C | `*field_label` | yes |
| D | `field_description` | no |
| E | `*field_type` | yes |
| F | `field_length` | no |
| G | `field_sequence` | no |

### Pipeline

| Column | Header | Required |
| --- | --- | --- |
| A | `*data_utilization_name` | yes |
| B | `*pipeline_name` | yes |
| C | `pipeline_description` | no |
| D | `*enable` | yes |
| E | `*is_octopus` | yes |
| F | `pipeline_trigger` | no |
| G | `pipeline_trigger_start` | no |
| H | `pipeline_trigger_end` | no |
| I | `pipeline_status_notification` | no |
| J | `pipeline_notification_emails` | no |
| K | `task1_name` | no |
| L | `task1_description` | no |
| M | `task1_link_target_names` | no |
| N | `task1_mlp_params` | no |

## Storage Type Mapping

| Evidence | Workbook value |
| --- | --- |
| Superview ClickHouse, SV ClickHouse, `SV_CLICKHOUSE` | `SV_CLICKHOUSE` |
| DataHub ClickHouse, normal ClickHouse | `CLICKHOUSE` |
| HBase | `HBASE` |
| HDFS / FS path | `HDFS` |
| MSSQL | `MSSQL` |
| MySQL | `MYSQL` |

## Field Type

`Target Field.*field_type` is a fixed workbook value. Always write `TEXT` for every field row, regardless of the source document field type.

`Target Field.*field_label` is a fixed workbook convention. Always write the same value as `*field_name`; put Chinese/business text in `field_description`.

`Target Field.field_length` is a fixed workbook value. Always write `200` as a text string for every field row.

`Target Field.field_sequence` should be stored as a text string such as `0`, `1`, `2`, matching production exports and avoiding numeric/date parser branches during import.

Blank optional cells should be absent/null cells in workbook XML, not empty inline string cells like `<c t="inlineStr"></c>`. This is especially important for Pipeline timing columns.

All non-empty text cells should be stored through `xl/sharedStrings.xml` as shared-string references (`t="s"`). Production exports use shared strings, and the platform importer can miss values stored as inline strings (`t="inlineStr"`), including `Data Utilization` names.
