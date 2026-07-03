---
name: data-doc-to-dev-md
description: Use when converting one or more PRD, DataEngine, DataHub, waterline, COT, HBase, ClickHouse, Superview, or report requirement DOCX files into implementation-ready development documents for Python data synchronization or report development.
---

# Data Doc To Dev Markdown

Use this skill when the user provides PRD, DataEngine, DataHub, waterline, report, COT, HBase, ClickHouse, or Superview DOCX documents and asks to produce an implementation-ready development document.

## Core Rules

- Do not write production code in this skill.
- Extract facts first; keep uncertain business meaning in `questions.md`.
- Treat DOCX embedded Excel workbooks as primary evidence, not decoration.
- Treat Word正文表格 as primary evidence too, especially Data Source, Data Target, HBase field dictionaries, and logic tables that are not embedded Excel workbooks.
- Preserve original Chinese business terms, field names, table names, and calculation text.
- Never invent field mappings, rowkey rules, credentials, or production paths.
- Existing documents may contain database connection strings, Gateway app keys, app secrets, hosts, ports, URLs, or tokens. Extract them only when they are requirement evidence; do not refuse the task because they exist.
- Do not create new real credentials in generated `dev_doc.md`, `structured_facts.json`, `questions.md`, examples, or copied snippets. Use placeholders when writing new credential-like values, and keep sensitive values out of summaries unless the user explicitly asks to preserve them.

## Inputs

- Required: one or more `.docx` files.
- Optional: project name, supplemental Excel files, screenshots, copied tables, known target project type (`data-sync` or `report`).

## Outputs

Create outputs under a user-provided output folder, or default to `outputs/<project-name>/`:

- `extracted/extracted_document.md`: single-document title, paragraphs, headings, embedded workbook summary.
- `extracted/extracted_tables/*.csv`: single-document CSV exports for embedded Excel sheets.
- `extracted/word_tables/*.csv`: single-document CSV exports for Word正文表格 when present.
- `extracted/doc_###_<name>/...`: per-document extraction folders for multi-DOCX projects.
- `dev_doc/dev_doc.md`: standard implementation-ready development document.
- `dev_doc/structured_facts.json`: machine-readable facts extracted from recognized matrices, with source-document provenance when available.
- `dev_doc/questions.md`: missing or uncertain points requiring user confirmation.

## Standard Dev Doc Sections

The generated `dev_doc.md` must contain these sections in this order:

1. Project Overview
2. Source Tables
3. Target Tables
4. Field Dictionary
5. Field Mapping
6. Data Processing Flow
7. KPI / Calculation Logic
8. Write Strategy
9. Scheduling And Rerun
10. Parameter Design
11. Log Verification Plan
12. Open Questions

## Workflow

1. Inspect the input path and confirm the DOCX exists.
2. Run `scripts/extract_docx_bundle.py`. Use one `--docx` for simple projects:

```powershell
python .\skills\data-doc-to-dev-md\scripts\extract_docx_bundle.py `
  --docx ".\doc\example.docx" `
  --out ".\outputs\example"
```

For PRD + waterline / DataEngine multi-document projects, repeat `--docx` and keep one shared output folder:

```powershell
python .\skills\data-doc-to-dev-md\scripts\extract_docx_bundle.py `
  --docx ".\doc\project PRD.docx" `
  --docx ".\doc\project Data Engine水线文档.docx" `
  --out ".\outputs\project" `
  --project-name "project"
```

3. Review `extracted/extracted_document.md` for single documents, or `extracted/doc_###_<name>/extracted_document.md` for multi-document projects.
4. Review `dev_doc/structured_facts.json` before code generation. For COT-style sync docs, this file should contain source/target report rows, Data Utilization names, target mappings, schedules, and field dictionaries. For multi-document report docs, it should contain `documents`, `report_sources`, `report_targets`, `report_physical_targets`, `report_field_mappings`, `report_schedules`, PRD rule facts, and provenance fields.
5. Use `assets/dev_doc_template.md` as the final document shape.
6. Move ambiguous points into `questions.md`; do not hide uncertainty in prose.

## Quality Bar

- For COT/data-sync documents, `dev_doc.md` is not good enough if it only lists embedded CSV filenames. It must expose the sync matrix: source table, target table, field dictionary, schedule, target prefixes, and unresolved rowkey/table exception questions.
- For COT/data-sync field dictionaries, prefer explicit or nearby正文 table-name context over simple embedded-sheet order. If the extractor only uses order fallback, review mappings with suspicious key fields manually before code generation.
- For report documents, `dev_doc.md` must expose target output fields and calculation/filter/join facts well enough for `report-codegen` to implement output-equivalent logic without reopening the original DOCX. If field rules live in Word正文表格 such as `字段名 / 字段key / 数据源位置 / 数据表 / 数据源对应的字段 / 计算逻辑`, they must be extracted into `report_field_mappings`.
- For PRD + waterline projects, technical facts from the waterline/DataEngine document should drive table, field, storage, and schedule facts; PRD facts should supplement business goals, abnormal rules, KPI logic, and UI aggregation logic. Conflicts belong in `questions.md`.
- Treat `structured_facts.json` as the handoff artifact for codegen skills whenever it exists.
- Before handing off to `data-sync-codegen` or `report-codegen`, verify that `structured_facts.json` contains the recognized tables, field mappings, schedules, target storage, provenance, and conflicts needed for code generation; if not, record the gap in `questions.md`.
- For bySKU / SKU-family / 新品 / B5 PRD + DataEngine document pairs, `structured_facts.json` must expose `component_hints` when the component split is detectable. Use `component_kind = bysku_report_pipeline` for the HBase -> FS bySKU prepare plus ClickHouse calculation chain, and mark inferred physical tables with `requires_confirmation = true` unless the target table is explicit.
- For complex report handoff, include `handoff_readiness` when the extractor can detect blocking gaps such as missing physical targets, unmapped field dictionaries, missing FS/SKU params, or unconfirmed write strategy. Codegen skills should treat blocked readiness as a reason to generate a checklist or one component, not a full production-equivalent project.

## Reference Loading

- Read `references/docx_rules.md` before changing extraction behavior.
- Read `references/bysku_report_doc_rules.md` when documents mention bySKU, SKU-family report pipelines, 新品, B5, NPD, R13P, FS handoff plus ClickHouse outputs, or sample aliases such as 执行为王 / `execute_king`.
- Use `assets/dev_doc_template.md` whenever generating or revising a development document.
