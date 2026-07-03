# MySQL Rules

- Quote identifiers with backticks.
- Prefer `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`.
- Use inline column comments: `COMMENT 'text'`.
- Use `AUTO_INCREMENT` only when source explicitly says auto-increment/identity.
- Use `PRIMARY KEY (...)` as a table constraint.
- Emit secondary indexes as `KEY idx_name (col1, col2)`.
- Prefer `datetime` for timestamp-like business fields unless source requires `timestamp`.
- Map booleans to `tinyint(1)` unless user requests `boolean`.
- Keep `json` as `json` for MySQL 5.7+; otherwise flag as risk.
- For long free text, use `text` rather than `varchar(4000+)`.
