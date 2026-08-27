---
name: report-codegen
description: Generate, review, or modify portable Python DataEngine/DataHub report projects from development docs, including KPI outputs, ClickHouse writes, HBase/FS/MSSQL sources, and multi-component prepare pipelines.
---

# Report Codegen

Build report code from `technical_design.md`, using `structured_facts.json` when available. Accept legacy `dev_doc.md` inputs, and generate only the requested, evidence-supported components.

## Design Package Contract

For the standard three-file handoff, read in this order:

1. `structured_facts.json`: inspect `codegen_contract`, component routing, sources, targets, field mappings, provenance, and readiness.
2. `technical_design.md`: use HLD for pipeline/component boundaries and LLD for join/filter/group order, KPI formulas, null/default behavior, output columns, parameters, and write predicates.
3. `questions.md`: stop full generation when `Blocking Code Generation` is non-empty; deployment and non-blocking questions do not prevent scaffolding.

Do not require separate HLD, LLD, manifest, traceability, or persistent codegen-plan files. Generated report plans remain disposable build artifacts. Legacy inputs without `codegen_contract` use the existing evidence checks.

## Shared Contract

- Treat source/target mappings, field order, KPI formulas, filters, joins, grouping, null behavior, and write strategy as requirement facts, not opportunities for invention.
- Keep `gateway/`, `hbase/`, and `fs/` as fixed platform packages; report logic belongs in `data_utils/` and `params_configs/`.
- Do not connect to production systems during generation or local verification.
- Preserve in-scope existing connection values when editing their file. New files, examples, logs, and docs use placeholders unless the user explicitly supplies values for insertion.

## Workflow And Reference Routing

1. When `structured_facts.json` exists, run `scripts/build_report_codegen_plan.py --facts <facts> --out <plan-dir>` and inspect `codegen_contract`, component kind, targets, field mappings, schedules, and readiness.
2. Load only the matching primary pattern:
   - `references/bysku_report_pipeline_patterns.md` for `component_kind = bysku_report_pipeline`.
   - `references/hbase_prepare_pipeline_patterns.md` for `component_kind = hbase_prepare_pipeline`.
   - `references/vehicle_verification_patterns.md` for vehicle/order reconciliation sources or vehicle verification outputs.
   - `references/supervisor_portal_patterns.md` only for supervisor-portal target families.
   - `references/generic_execution_contract.md` for generic `standard_report` and `bysku_report_pipeline` shapes without a named specialized implementation.
   - For other report shapes, rely on the dev doc, normalized execution contract, generated plan, and minimal scaffold without importing unrelated named-project rules.
3. Read `references/code_comments_and_runtime_logging.md` before generating or reviewing business code.
4. Read `references/platform_client_usage.md` only when the project uses Gateway, HBase, or FS.
5. If `codegen_contract.ready_for_codegen = false`, legacy `handoff_readiness.ready_for_full_codegen = false`, or generic `execution_validation.status != passed`, return blockers or generate the requested safe component/checklist. Use `--allow-blocked-scaffold` only for an explicitly requested placeholder scaffold, never a claimed full chain. A blocked scaffold must include `SAFE_SCAFFOLD.json` with `runtime_enabled=false`, and its entrypoint must reject execution; the flag alone must not downgrade an otherwise ready contract.
6. Prefer `scripts/scaffold_report_project.py --plan <plan.json> --target <project-dir>`. Generic full generation requires a validated `execution_contract`; the scaffold script must reject missing or invalid contracts unless review-only generation is explicit. Use `assets/minimal_report_project/` when no structured plan applies.
7. Run `scripts/verify_qas_synthetic_acceptance.py` when changes touch rule thresholds, duration boundaries, required fields, multi-date parameters, cross-period isolation, consecutive-period logic, exact enums, empty outputs, reconciliation, or DataEngine result protocol. Its values are fixture-only, never project defaults.
7. Named specialized projects use their confirmed implementation. Generic contract projects use generated source adapters, the non-eval transformation runtime, exact output projections, and explicit ClickHouse write contracts. A compiling placeholder scaffold is not a complete report.
8. Compile generated Python, run `scripts/verify_report_plan_semantics.py --project-dir <target>` for every output/field/write contract, then run `scripts/verify_codegen_observability.py --project-dir <target>`.
9. Run `scripts/verify_report_runtime_semantics.py` for supported `supervisor_portal`, `vehicle_verification`, and `hbase_prepare` projects. Run `scripts/verify_generic_report_runtime_semantics.py` after changing the generic standard/bySKU contract runtime.

## Hard Constraints

- Do not silently skip failed writes unless the user explicitly wants best-effort behavior.
- HBase-only prepare projects export to FS and may activate a downstream pipeline; do not force a ClickHouse writer into that component.
- Keep bySKU prepare and SKU calculation components separate unless existing code deliberately combines them.
- Do not guess HBase rowkeys. Keep `params_configs/rowkey_config.py` unconfirmed until evidence proves the rule.
- Do not claim completeness for empty DataFrames, planned metrics, `NotImplementedError`, or syntax-only success.
- Do not translate free-form natural-language formulas into executable expressions by guessing. Normalize them into the bounded execution-contract DSL, preserve unresolved rules as blockers, and never use `eval` or `exec`.

## Output-Equivalence Standard

Preserve output tables, column order, source filters, join direction, defaults, formulas, rounding, null behavior, grouping keys, and target replacement predicates. For HBase prepare components, also preserve period derivation, source table and columns, filters, FS naming, pipeline activation, and credential boundaries.

Claim runtime parity only when the matching fake-runtime verifier passes or deployment logs prove equivalent rows, values, column order, and write lifecycle.
