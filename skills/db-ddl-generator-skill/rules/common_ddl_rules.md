# Common DDL Rules

## Safety

- Generate SQL only. Do not connect to databases and do not execute SQL.
- Do not request, print, or store credentials.
- Treat destructive statements (`DROP`, `TRUNCATE`, `DELETE`, broad `ALTER`) as out of scope unless the user explicitly asks for generated SQL review.
- Preserve user-provided table and column names unless invalid for the target database.

## Field Extraction

Map common header names to the standard schema:

- Column name: `字段`, `字段名`, `字段英文名`, `英文字段`, `column_name`, `column`, `name`, `field`, `field_name`
- Comment/description: `字段描述`, `字段中文名`, `中文名`, `comment`, `description`, `desc`, `label`, `remarks`, `备注`
- Type: `字段类型`, `字段类型(mysql)`, `字段类型(pg)`, `类型`, `type`, `data_type`, `datatype`, `db_type`
- Length: `长度`, `length`, `len`, `size`
- Precision: `精度`, `precision`
- Scale: `小数位`, `scale`
- Nullable: `是否为空`, `可为空`, `nullable`, `null`, `is_nullable`
- Not null: `非空`, `not_null`, `not null`, `required`, `mandatory`
- Default: `默认值`, `default`, `default_value`
- Primary key: `主键`, `primary_key`, `pk`, `is_pk`
- Index: `索引`, `index`, `key`, `idx`

## Defaults

- Missing type: use a string type for the target database and list the assumption.
- Missing nullable flag: default to nullable except primary key/order key/partition key columns.
- Missing length for variable character types: use 255 for MySQL/MSSQL/PostgreSQL unless the source says `text` or the target is ClickHouse.
- Missing table name: derive from file name only if the user did not provide a table name; list the assumption.
- Missing comments: leave comments out rather than inventing descriptions.
- Default values: preserve exact user-provided default expressions where valid; otherwise list normalization in assumptions.
- In DOCX designs with a Target section and separate data dictionaries, use the Target section's `clickhouse表` as the authoritative ClickHouse database/table name. Then use the matching data-dictionary field sheet for columns.

## Review Checks

- Confirm primary key columns are not nullable.
- Confirm index columns exist.
- Confirm default values are valid for the mapped target type.
- Escape single quotes in comments.
- Quote identifiers only with the target database's normal quoting style.
- For conversions, report non-equivalent features such as auto-increment, clustered indexes, storage engine settings, generated columns, collations, and unsupported JSON/full-text/spatial indexes.
