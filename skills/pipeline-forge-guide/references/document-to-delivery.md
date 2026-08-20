# Document-To-Delivery Route

Use this route when the user provides requirement documents or asks to go from a waterline/PRD to tested code.

## 1. Extract The Design Package

Use `data-doc-to-dev-md` to inspect all provided documents together and generate the formal three-file handoff:

- `technical_design.md`
- `structured_facts.json`
- `questions.md`

Treat extracted CSVs and embedded workbook data as audit evidence. Do not ask the user to restate facts that can be read from the documents.

## 2. Explain The Route

Read `structured_facts.json.codegen_contract` before selecting a generator:

- `project_type = data-sync` or `component_kind = cot_table_sync`: use `data-sync-codegen`.
- `project_type = report` or report component kinds such as `standard_report`, `bysku_report_pipeline`, or `hbase_prepare_pipeline`: use `report-codegen`.
- Unknown or conflicting routing: remain `BLOCKED_INPUT` and present the evidence conflict in plain language.

Summarize confirmed sources, targets, schedules, fields, and components before generation. Do not infer readiness from document length or the number of extracted tables.

## 3. Handle Blockers

If `ready_for_codegen` is false:

1. Group duplicate blockers.
2. Select the three decisions with the greatest effect on architecture or data correctness.
3. Translate them with `references/beginner-questions.md`.
4. Stop full generation until they are answered.

If the user explicitly wants a test project, generate only the safe placeholder scaffold supported by the matching codegen skill's blocked-scaffold option. Mark it `SAFE_SCAFFOLD`, keep credentials as placeholders, and preserve every unresolved item in the handoff.

## 4. Generate The Confirmed Route

For synchronization projects, preserve table dispatch, with-period/without-period behavior, rowkeys, source and target names, delete/truncate rules, rerun behavior, timestamps, and DataEngine metrics.

For report projects, preserve component boundaries, source filters, joins, KPI formulas, grouping, output column order, null/default behavior, target replacement predicates, and any FS/HBase preparation stage. Generic standard/bySKU projects also require the bounded normalized `execution_contract`; unresolved natural-language formulas remain blockers instead of guessed executable code.

Generate only requested and evidence-supported components. A compiling placeholder is not a complete implementation.

## 5. Verify Locally

Always compile generated Python. Then run the applicable packaged checks:

- Sync: `verify_cot_manifest_semantics.py` for every table, then `verify_codegen_observability.py` and `verify_cot_runtime_semantics.py`.
- Report: `verify_report_plan_semantics.py` for every output/field/write contract, then `verify_codegen_observability.py`; run `verify_report_runtime_semantics.py` for specialized types and the packaged generic runtime regression after changing standard/bySKU contract generation.

Parse generated JSON files and scan the generated project for credentials and workspace-only paths. Do not connect to Gateway, HBase, FS, ClickHouse, MSSQL, or other production services.

Use `VERIFIED_TEST` only when every applicable deterministic check passes. Use `READY_FOR_DEPLOYMENT_REVIEW` only after blockers are resolved and environment-specific deployment values remain clearly separated from generated placeholders.

## Optional Downstream Artifacts

After the primary code or design deliverable is complete, offer these only when supported by the inputs or requested by the user:

- Pipeline Export workbook through `pipeline-excel-builder`.
- Target-table DDL through `db-ddl-generator-skill`.
- Failure diagnosis through `data-job-log-debugger` after a test or deployed run produces logs.
