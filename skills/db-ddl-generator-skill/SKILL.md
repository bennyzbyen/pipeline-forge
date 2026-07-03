---
name: db-ddl-generator-skill
description: Use when the user asks to generate, parse, convert, or review database CREATE TABLE DDL from schemas, documents, or existing SQL.
---

# DB DDL Generator

## Scope

Use this skill to generate, parse, convert, and validate database table DDL. Keep the work SQL-only: never connect to a database, never execute generated SQL, and never request or store credentials.

Supported targets:

- MySQL
- Microsoft SQL Server / MSSQL
- ClickHouse
- PostgreSQL / PGSQL

## Workflow

1. Classify the input:
   - Excel/CSV field list: run or inspect `scripts/parse_excel_schema.py`.
   - DOCX with embedded Excel or ordinary tables: run or inspect `scripts/parse_docx_schema.py`. For COT/DataEngine-style docs, first extract the Target section's `clickhouse表` list, then bind matching data-dictionary field sheets to those ClickHouse table names.
   - Existing DDL: run or inspect `scripts/parse_existing_ddl.py`.
   - Conversion task: parse source DDL, then generate target DDL with `scripts/convert_ddl.py`.
2. Load only the needed rule files:
   - Always read `rules/common_ddl_rules.md`.
   - Read one target rule file from `rules/mysql_rules.md`, `rules/mssql_rules.md`, `rules/clickhouse_rules.md`, or `rules/postgres_rules.md`.
   - For conversion, also read the relevant file in `mapping/`.
3. Normalize all inputs into the standard schema contract before generating SQL.
4. Generate formatted SQL with target-specific syntax.
5. Report assumptions, type mappings, and risks unless the user asks for SQL only or says "directly give me the statements".

## Standard Schema Contract

Represent extracted schema as JSON with this shape:

```json
{
  "database": "optional_database",
  "schema": "optional_schema",
  "table_name": "target_table",
  "table_comment": "optional table comment",
  "columns": [
    {
      "name": "id",
      "source_type": "bigint",
      "type": "bigint",
      "length": null,
      "precision": null,
      "scale": null,
      "nullable": false,
      "default": null,
      "primary_key": true,
      "index": false,
      "comment": "primary id",
      "remarks": ""
    }
  ],
  "primary_key": ["id"],
  "indexes": [{"name": "idx_table_col", "columns": ["col"]}],
  "partition_by": [],
  "order_by": [],
  "engine": "",
  "settings": {}
}
```

If information is missing, choose the conservative default from `rules/common_ddl_rules.md` and list it under assumptions.

## Script Usage

The scripts are helpers, not mandatory black boxes. Inspect or patch them when a task needs stricter behavior.

For files that may contain Chinese comments or table descriptions, prefer script `--output` arguments instead of shell redirection. The bundled scripts write `--output` artifacts as UTF-8; PowerShell `>` redirection can corrupt Chinese stdout on some systems.

```bash
python scripts/parse_excel_schema.py input.xlsx --table target_table --output schema.json
python scripts/parse_docx_schema.py input.docx --table target_table --output schema.json
python scripts/parse_existing_ddl.py input.sql --output schema.json
python scripts/parse_existing_ddl.py clickhouse_ddl_export.csv --output prod_templates.json
python scripts/generate_clickhouse_from_excel.py dictionary.xlsx --database test --output clickhouse_ddl.sql
python scripts/generate_ddl.py schema.json --target clickhouse --env prod --database db --table table_name --partition-by period --order-by period,code --output table.sql
python scripts/generate_ddl.py docx_schema.json --target clickhouse --env prod --all-tables --cot-period-code-rule --sql-only --output clickhouse_prod.sql
python scripts/convert_ddl.py source.sql --source mysql --target clickhouse --env prod --database db --table table_name
```

## Output Rules

Default response order:

1. Target database `CREATE TABLE` DDL in a SQL code block.
2. Field type mapping notes.
3. Important assumptions.
4. Possible risks.
5. For conversion tasks, source-to-target differences.

If the user asks "only SQL", "directly give me SQL", or "directly give me the statements", output only SQL code blocks and no long explanation.

Keep Chinese notes concise and concrete. Do not hide uncertain conversions; state assumptions explicitly.

## ClickHouse Template Rules

For ClickHouse, distinguish QA and PROD:

- QA usually uses `ReplacingMergeTree(...)`, no `ON CLUSTER`, and simpler partition/order expressions.
- PROD usually uses `ON CLUSTER cl_1shards_2replicas`, `ReplicatedMergeTree` or `ReplicatedReplacingMergeTree`, a ZooKeeper path, `PARTITION BY`, `ORDER BY`, optional `PRIMARY KEY`, and `SETTINGS`.
- For COT/DataEngine dictionaries, prefer `inksaa_last_modified_timestamp` as the ReplacingMergeTree version column when present. Fall back to common update timestamp names, then to another datetime field only if no update timestamp exists.
- Production DDL exported from `system.tables` or similar sources may omit `ON CLUSTER` even when original creation used it. If the user states original production create had `ON CLUSTER cl_1shards_2replicas`, keep that in the extracted reusable PROD template and list it as an assumption.
- Never silently put Nullable columns into `ORDER BY`, `PRIMARY KEY`, or partition keys. Convert those key columns to non-nullable only if source semantics support it; otherwise report the conflict.
- For DOCX Target sections, treat `clickhouse表` as the authoritative destination table name. Use the data dictionary only for columns and comments unless it also supplies stronger type/nullability metadata.
- For COT/DataEngine report tables, when both `period` and `code` fields exist and the user has not supplied explicit keys, use `PARTITION BY period` and `ORDER BY (period, code)`, and generate both fields as non-nullable.

Use `templates/clickhouse_qa_create_table.sql` and `templates/clickhouse_prod_create_table.sql` when building repeatable ClickHouse DDL.

## Resource Map

- `rules/`: target database syntax and review rules.
- `templates/`: reusable CREATE TABLE templates.
- `mapping/`: type and conversion mapping references.
- `scripts/`: parsers and generators for repeatable tasks.
- `examples/`: small generic input samples for quick testing.
