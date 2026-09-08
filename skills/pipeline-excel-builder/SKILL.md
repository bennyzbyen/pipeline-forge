---
name: pipeline-excel-builder
description: Generate, fill, or validate DataHub/DataEngine Pipeline Export Excel workbooks from an exported template plus structured waterline or report facts.
---

## GPT-6 適配變更說明

**用戶當前指令優先級最高**（相對本 Skill、引用指南和預設提示詞；平台 system/developer 指令與工具權限仍適用）。已授權、信息足夠即直接完成；沿用既有授權，自行處理範圍內可逆選擇。僅就無法從現有證據解決且影響正確性或授權的缺項提問，同時完成獨立工作。保留業務事實與安全驗證，不虛構確認。


# Pipeline Excel Builder

Create a locally reviewable Pipeline Export workbook. This skill does not connect to DataHub, create platform objects, or import the workbook.

## Required Inputs

- An empty Pipeline Export workbook exported from the target platform/project.
- `structured_facts.json` from `data-doc-to-dev-md`.
- Original waterline/DataEngine documents are recommended for resolving conflicts.

Explicit user-confirmed values override inferred document values. Production exports are schema/style evidence only unless the user authorizes copying specific business values.

## Script-First Workflow

1. If only Markdown or DOCX requirement inputs exist, use `data-doc-to-dev-md/scripts/extract_docx_bundle.py --input <paths...>` to produce `structured_facts.json`.
2. Run `scripts/build_pipeline_excel.py --template-xlsx <workbook> --structured-facts <facts> --questions-out <questions.md> --project-name <name>`. The template is filled in place unless `--out-xlsx` is supplied.
3. Run `scripts/validate_pipeline_excel.py --xlsx <workbook> --json-out <validation.json>`.
4. Review `questions.md` and validation warnings before calling the workbook import-ready.

For ordinary generation, the builder and validator are the source of truth for sheet layout, row placement, cell types, shared strings, fixed field values, blank timing columns, and workbook preservation. Read `references/pipeline_export_schema.md` and `references/fill_rules.md` only when changing mapping behavior, investigating a validation mismatch, or reviewing an unsupported workbook shape.

## Constraints

- Use the exported workbook as the base; do not rebuild it from scratch.
- Do not guess owners, emails, catalog values, MLP params, task-target links, credentials, URLs, platform IDs, or conflicting business mappings. Record unresolved values in `questions.md`.
- Preserve project-owned versus shared/reference-table distinctions and prefer technical waterline facts over PRD inference unless the user confirms an override.
- Do not commit source documents, templates, production exports, or generated workbooks.

## Handoff

Report the workbook path, row counts for the four data sheets, validation result and warning count, intentionally blank fields, and whether the workbook was only generated or also manually reviewed/imported.
