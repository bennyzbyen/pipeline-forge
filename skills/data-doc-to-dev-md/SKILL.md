---
name: data-doc-to-dev-md
description: Convert one or more Markdown or DOCX PRD, DataEngine, DataHub, waterline, COT, HBase, ClickHouse, Superview, or report requirement documents into AI-readable Technical Design handoffs for data-sync or report code generation.
---

# Data Doc To Technical Design

Extract requirement evidence into a technical-design handoff. Do not generate production code in this skill.

## Contract

- Preserve original Chinese business terms, field names, table names, formulas, and source-document provenance.
- Treat Markdown pipe tables, embedded Excel workbooks, and Word正文 tables as primary evidence. Do not reduce them to attachment or CSV filename lists.
- Prefer waterline/DataEngine evidence for physical tables, fields, storage, and schedules; use PRD evidence for goals, KPI rules, abnormal rules, and UI aggregation. Record material conflicts in `questions.md`.
- Keep uncertain mappings, rowkeys, formulas, credentials, and production paths unresolved rather than inventing them.
- Existing sensitive values may be extracted when they are requirement evidence. Keep them out of summaries unless requested, and use placeholders for any newly written credential-like values.
- Keep the formal handoff to three files: `technical_design.md`, `structured_facts.json`, and `questions.md`. Extracted evidence remains audit/debug material, not a normal codegen input.
- Treat `technical_design.md` as one concise design document with explicit HLD and component-LLD sections. Do not create separate HLD, LLD, manifest, or traceability files unless the user asks.
- Do not claim that the design is complete or invent missing decisions. Put routing, components, blockers, and `ready_for_codegen` in `structured_facts.json.codegen_contract`.
- For new handoffs, also create the two-level contract described in `references/code_unit_contract.md`: one `project_contract`, one lifecycle-bearing `code_unit_plan`, and independently validatable `code_units[]`. Waterline count is evidence, never a direct code-count rule.
- Present a code-unit proposal before full generation. Keep it `awaiting_user_confirmation` until the user confirms or overrides the count and mapping. Any changed boundary evidence invalidates the confirmation.
- Give every generated ambiguity a stable semantic ID: `TC-CG-*` for code-generation blockers, `TC-DP-*` for deployment confirmations, and `TC-NB-*` for non-blocking questions. Preserve the same ID in `questions.md`, `codegen_contract.open_questions`, blocker summaries, and user-facing confirmation prompts.

## Inputs And Outputs

Input is one or more `.md`, `.markdown`, or `.docx` files. Markdown and DOCX are equal first-class inputs and may be mixed in one project. Supplemental Excel, screenshots, copied tables, project name, or known project type are optional evidence.

Write under the user-provided output directory, or `outputs/<project-name>/`:

- `extracted/`: paragraph, embedded-workbook, and Word-table evidence; multi-document projects use per-document subfolders.
- `dev_doc/technical_design.md`: human-readable Technical Design handoff.
- `dev_doc/structured_facts.json`: recognized facts with provenance.
- `dev_doc/questions.md`: questions classified as codegen-blocking, deployment confirmation, or non-blocking.

## Workflow

1. Run `scripts/extract_docx_bundle.py --input <paths...> --out <output-dir> [--project-name <name>]`. Pass all Markdown and DOCX PRD/waterline documents for the same project in one run. `--docx` remains a legacy DOCX-only alias.
2. Review extracted evidence and `structured_facts.json`. Check any field-dictionary mapping that fell back to embedded-sheet order.
3. Build the legacy-compatible `codegen_contract`, enrich schedule-derived waterlines through `scripts/code_unit_evidence.py`, then build the code-unit proposal. Link task identity, Data Utilization ownership, temporal grain, targets, rules, sources, write contracts, and dependency evidence. Render its count, waterline bindings, parameter profiles, route candidates, dependencies, reasons, confidence, and blockers in the three-file handoff.
4. Put `TC-CG-CODE-UNIT-CONFIRMATION` in `Blocking Code Generation` until the user confirms the proposal. Apply confirmations or audited merge/split overrides with `scripts/manage_code_unit_plan.py`; reject overrides with incompatible state, write, deployment, failure-isolation, or route boundaries.
5. Use `assets/technical_design_template.md` as the final HLD + LLD document shape. After confirmation, retain the confirmation audit and show real blockers per unit.
6. Run `scripts/validate_technical_contract.py --facts <structured_facts.json>` for normal review and add `--strict-deployment` only for deployment review. Run `scripts/verify_technical_contract_regression.py`, `scripts/verify_code_unit_contract_regression.py`, and `scripts/verify_schedule_boundary_planning.py --facts <structured_facts.json>` after contract or boundary-enrichment changes.

## Acceptance Criteria

- COT/data-sync handoffs expose source and target tables, target prefixes, field dictionaries, schedules, and unresolved rowkey or table exceptions.
- Report handoffs expose physical targets, ordered output fields, source fields, filters, joins, calculations, schedules, and write behavior without requiring codegen to reopen the source documents.
- `structured_facts.json` is the machine-readable handoff. For detectable bySKU pipelines, emit `component_hints[].component_kind = bysku_report_pipeline`; inferred physical targets remain confirmation-required.
- Contract v2 exposes field/source/rule/parameter/runtime/write contracts, stable validation gates, stable open-question IDs, conflicts, `ready_for_codegen`, and deployment blockers. Readers keep v1 compatibility, but strict deployment requires v2.
- Confirmed projects expose `confirmed_count`, confirmed waterline mapping, per-unit route/kind, execution contract, state/watermark, retry/rerun, empty/failure semantics, tests, readiness, and blockers. A blocked unit must not make a different confirmed ready unit look complete or force both into one generic scaffold.
- Proposed units expose dimension-specific blockers before confirmation. Unknown routes remain empty with auditable `codegen_route_candidates[]`; do not inherit a project-level report/sync type silently.
- Block full-codegen readiness when physical targets, field mappings, FS/SKU parameters, schedules, write predicates, rowkeys, or rerun behavior required by the project are missing.

## Reference Routing

- Read `references/markdown_rules.md` for Markdown inputs, parser changes, or an unrecognized Markdown shape.
- Read `references/docx_rules.md` for DOCX inputs, OOXML changes, or an unrecognized DOCX shape.
- Read `references/bysku_report_doc_rules.md` only for bySKU, SKU-family, 新品, B5, NPD, R13P, FS-handoff, or equivalent multi-component report documents.
- Use `assets/technical_design_template.md` whenever generating or revising the Technical Design document.
- Read `references/code_unit_contract.md` whenever planning, confirming, invalidating, routing, or consuming multiple code units.
