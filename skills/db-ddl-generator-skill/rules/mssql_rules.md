# MSSQL Rules

- Quote identifiers with square brackets.
- Use `CREATE TABLE [schema].[table]` when schema is known; default schema is `dbo`.
- Use `IDENTITY(1,1)` only when source explicitly says auto-increment/identity.
- Use `PRIMARY KEY (...)` as a table constraint.
- Emit indexes after table creation with `CREATE INDEX idx_name ON [schema].[table] ([col]);`.
- Use extended properties for comments:
  `EXEC sp_addextendedproperty @name=N'MS_Description', @value=N'...', ...`.
- Prefer `nvarchar(length)` for text that may contain Chinese; use `nvarchar(max)` for long text.
- Use `datetime2` for timestamp-like fields unless source specifically requires `datetime`.
- Map JSON to `nvarchar(max)` and flag that native JSON type is not available.
