# Specialized Routes

Use only the section matching the user's primary request.

## Pipeline Export Workbook

1. Inspect the exported workbook template and the source waterline or structured facts.
2. Use `pipeline-excel-builder` to fill the workbook without redesigning its schema.
3. Run the packaged workbook validator and retain its JSON validation result when requested.
4. Report the workbook path, validation status, unresolved required cells, and whether the file is ready for import review.

Do not invent pipeline IDs, folder IDs, credentials, or environment-specific values.

## Database DDL

1. Identify the source format and target database dialect.
2. Use `db-ddl-generator-skill` to parse, normalize, and generate the requested DDL.
3. Report type mappings, keys, engine choices, and assumptions that need confirmation.
4. Validate syntax structurally, but do not connect to a database or execute the SQL.

If the source is a requirement DOCX with embedded Excel fields, extract the structured schema before generating DDL.

## Job Failure Diagnosis

1. Inspect the complete available log or screenshot before questioning the user.
2. Use `data-job-log-debugger` to classify the failure stage and distinguish root cause from secondary errors.
3. Return evidence, likely cause, the safest next check, and rerun/deployment implications.
4. Diagnose only unless the user also asks to modify code or configuration. Route an authorized code change to the matching codegen skill.

Never claim success because a retry started; require the relevant completion evidence.

## Existing Project Review

1. Determine whether the project is synchronization or report code.
2. Use the matching codegen skill to inspect only in-scope files.
3. Run its compilation, observability, and fake-runtime checks when supported.
4. Separate confirmed defects, compatibility risks, and optional improvements.

Do not replace a working project with a fresh scaffold unless the user explicitly requests regeneration.
