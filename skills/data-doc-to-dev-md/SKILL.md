---
name: data-doc-to-dev-md
description: Convert one or more PRD, DataEngine, DataHub, waterline, COT, HBase, ClickHouse, Superview, or report requirement DOCX files into AI-readable Technical Design handoffs for data-sync or report code generation.
---

# Data Doc To Technical Design

Extract requirement evidence into a technical-design handoff. Do not generate production code in this skill.

## Contract

- Preserve original Chinese business terms, field names, table names, formulas, and source-document provenance.
- Treat embedded Excel workbooks and Word正文 tables as primary evidence. Do not reduce them to attachment or CSV filename lists.
- Prefer waterline/DataEngine evidence for physical tables, fields, storage, and schedules; use PRD evidence for goals, KPI rules, abnormal rules, and UI aggregation. Record material conflicts in `questions.md`.
- Keep uncertain mappings, rowkeys, formulas, credentials, and production paths unresolved rather than inventing them.
- Existing sensitive values may be extracted when they are requirement evidence. Keep them out of summaries unless requested, and use placeholders for any newly written credential-like values.
- Keep the formal handoff to three files: `technical_design.md`, `structured_facts.json`, and `questions.md`. Extracted evidence remains audit/debug material, not a normal codegen input.
- Treat `technical_design.md` as one concise design document with explicit HLD and component-LLD sections. Do not create separate HLD, LLD, manifest, or traceability files unless the user asks.
- Do not claim that the design is complete or invent missing decisions. Put routing, components, blockers, and `ready_for_codegen` in `structured_facts.json.codegen_contract`.

## Inputs And Outputs

Input is one or more `.docx` files, with optional supplemental Excel, screenshots, copied tables, project name, or known project type.

Write under the user-provided output directory, or `outputs/<project-name>/`:

- `extracted/`: paragraph, embedded-workbook, and Word-table evidence; multi-document projects use per-document subfolders.
- `dev_doc/technical_design.md`: human-readable Technical Design handoff.
- `dev_doc/structured_facts.json`: recognized facts with provenance.
- `dev_doc/questions.md`: questions classified as codegen-blocking, deployment confirmation, or non-blocking.

## Workflow

1. Run `scripts/extract_docx_bundle.py --docx <paths...> --out <output-dir> [--project-name <name>]`. Pass all PRD and waterline documents for the same project in one run.
2. Review extracted evidence and `structured_facts.json`. Check any field-dictionary mapping that fell back to embedded-sheet order.
3. Build `codegen_contract`, then use `assets/technical_design_template.md` as the final HLD + LLD document shape.
4. Put material gaps in the matching `questions.md` category. Only `Blocking Code Generation` prevents full codegen.

## Acceptance Criteria

- COT/data-sync handoffs expose source and target tables, target prefixes, field dictionaries, schedules, and unresolved rowkey or table exceptions.
- Report handoffs expose physical targets, ordered output fields, source fields, filters, joins, calculations, schedules, and write behavior without requiring codegen to reopen the DOCX.
- `structured_facts.json` is the machine-readable handoff. For detectable bySKU pipelines, emit `component_hints[].component_kind = bysku_report_pipeline`; inferred physical targets remain confirmation-required.
- `codegen_contract` exposes `project_type`, `component_kind`, `components`, `ready_for_codegen`, and `blockers` without duplicating separate manifest or traceability files.
- Block full-codegen readiness when physical targets, field mappings, FS/SKU parameters, schedules, write predicates, rowkeys, or rerun behavior required by the project are missing.

## Reference Routing

- Read `references/docx_rules.md` when changing extraction behavior or resolving an unrecognized document shape.
- Read `references/bysku_report_doc_rules.md` only for bySKU, SKU-family, 新品, B5, NPD, R13P, FS-handoff, or equivalent multi-component report documents.
- Use `assets/technical_design_template.md` whenever generating or revising the Technical Design document.
