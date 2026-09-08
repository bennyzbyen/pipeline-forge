# GPT-6 適配變更說明

輸出目錄可由現有上下文與項目默認值直接決定；修復請求沿用已有授權，不再逐階段詢問。

# Specialized Routes

Use only the section matching the user's primary request.

## Reviewable Waterline Document

1. Use `pipeline-doc-generator` for a new or revised DataEngine/DataHub waterline document, not an implementation-oriented Technical Design handoff.
2. Reuse the requested output directory, or choose `outputs/<project-name>/` when none is specified; report the chosen path without pausing. Always deliver Markdown, HTML, and PDF together; do not ask for a format choice or preserve a legacy partial-output preference.
3. For first-time waterline drawing or visual redesign, check that the separately installed Diagram Design plugin is available; explain the missing dependency before drawing. PipelineForge does not bundle or automatically install it. Reusing a valid bound SVG or using other specialist routes does not require it. Follow the specialist's evidence, facts, and clarification gates. For an existing generated document, update its canonical `facts.json` instead of reparsing every input or editing rendered files.
4. Validate all selected outputs and report paths plus unresolved questions. Stop at the requested document; propose code or Pipeline Export work only as an optional next step.

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
4. For diagnosis-only requests, report findings. When the current request or prior session instruction authorizes a code/configuration fix, apply it through the matching skill without asking again.

Never claim success because a retry started; require the relevant completion evidence.

## Existing Project Review

1. Determine whether the project is synchronization or report code.
2. Use the matching codegen skill to inspect only in-scope files.
3. Run its compilation, observability, and fake-runtime checks when supported.
4. Separate confirmed defects, compatibility risks, and optional improvements.

Do not replace a working project with a fresh scaffold unless the user explicitly requests regeneration.
