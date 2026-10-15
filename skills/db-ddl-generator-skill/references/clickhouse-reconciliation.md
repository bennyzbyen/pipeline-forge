# ClickHouse reconciliation

Use this workflow when preparing new QA/PROD tables from current source DDL and an older ClickHouse export. It remains offline: generate SQL, compare contracts, and record evidence without connecting or executing.

## Evidence and scope

- Current MySQL SHOW CREATE TABLE supplies field names, order, signedness, precision, nullability, comments, defaults, and source-only update behavior. A requirement dictionary may explain intent; report conflicts rather than overwriting physical source facts silently.
- The target mapping supplies create/skip decisions. An upstream report without a ClickHouse destination is not automatically a table to create.
- An explicitly identified QA or PROD export supplies that environment's matching table configuration. Environment labels alone do not imply local/replicated engines or sorting keys. Never select an arbitrary row; database and table must match exactly and be unique.
- `system.tables` exports may omit original ON CLUSTER creation scope. Preserve explicit clusters and report absence as unknown unless the user confirms it. Do not claim a CSV export proves server readiness.
- Additional import audit fields require an explicit `columns[]` contract. Do not automatically add a timestamp or select it as a replacement version.

User-run metadata collection examples:

```sql
SHOW CREATE TABLE `source_database`.`source_table`;
SELECT database, name AS table_name, engine, create_table_query AS ddl
FROM system.tables
WHERE database = 'previous_report_db'
ORDER BY name;
```

Record which environment the user exported. CSV parsing supports quoted multiline DDL and UTF-8 BOM. Non-table rows are reported as warnings; missing, duplicate, or conflicting requested tables fail.

## Profile contract and generation

`settings.clickhouse_profiles.<env>` accepts `engine`, `version_column`, `cluster`, `replication_path`, `replica_expression`, `partition_by`, `order_by`, `primary_key`, `table_settings`, and provenance `source`. `table_settings` is an object of SQL expressions, for example `{"index_granularity": "4096"}`. Empty lists/objects are explicit absence. Do not borrow fields from the other environment.

Use explicit CLI options before profile values, then existing ClickHouse schema configuration. Use the requested COT convention only if no key configuration exists. Preserve source nullability and require the explicit coercion flag plus a documented justification for nullable target keys. Confirm the replacement grain and provide source NULL checks before import.

```powershell
python scripts/parse_existing_ddl.py source.sql --output current_schema.json
python scripts/generate_ddl.py current_schema.json --target clickhouse --env qa --database new_report_db --deployment-export qa_ddl.csv --profile-database previous_report_db --sql-only --output qa.sql
```

The export binds by each current schema's exact table name, without replacing its current columns. For replicated profiles targeting a new database, supply an explicit new `--replication-path`; an old path must not be carried forward automatically. An explicit source-to-target table rename requires a separately prepared profile; do not infer correspondence.

To limit a multi-table schema, pass `--scope-json scope.json`. Supply exactly one decision per input database/table; duplicate or missing decisions fail. Example:

```json
{"tables": [
  {"database": "source_db", "table_name": "report_result", "action": "create", "reason": "explicit ClickHouse destination"},
  {"database": "source_db", "table_name": "upstream_detail", "action": "skip", "reason": "target mapping says no creation"}
]}
```

## Independent artifact reconciliation

For each proposed table, regenerate expected target field semantics from current source DDL plus the bound profile. Supply target-only fields through `--audit-schema` (a JSON object with `columns[]`) using their approved types, defaults, comments, and nullability. The helper does not infer those definitions from the target it is checking.

```powershell
python scripts/review_clickhouse_ddl.py --source source.sql --target qa.sql --baseline qa_ddl.csv --baseline-database previous_report_db --env qa --audit-schema audit_columns.json --output review.json
```

Use `--allow-key-nullability-coercion`, `--cluster`, and `--replication-path` only for the same explicitly documented choices used during generation. A NULL-check example, generated with the actual source keys, is:

```sql
SELECT count(*) AS null_key_rows
FROM `source_database`.`source_table`
WHERE `period` IS NULL OR `code` IS NULL OR `data_source` IS NULL;
```

The review records source/audit/target counts, exact column coverage/order, target type and signedness, precision, nullability, defaults/comments, engine/version, partition/sorting/primary keys, SETTINGS, baseline changes, input hashes, and export warnings. It exits 0 for an offline match, 1 for contract differences, and 2 for unresolved/invalid inputs. Review one table per SQL input. Unsupported parsing and unknown deployment facts remain review items; do not represent an offline match as source-value or server compatibility verification.

## Delivery status

- Design draft: unresolved assumptions remain visible; not ready to claim environment verification.
- Offline reconciled: field and profile comparison passed; source NULL/value checks and server version/settings still require separate evidence.
- Executed and verified: use this wording only when a separately authorized execution workflow supplies server evidence. This skill does not execute SQL.

Prefer plain CREATE TABLE when preparing new tables. IF NOT EXISTS can hide a conflicting existing structure and does not verify it. Keep QA and PROD scripts, records, and provenance distinguishable; include only artifacts requested or needed for the actual task.
