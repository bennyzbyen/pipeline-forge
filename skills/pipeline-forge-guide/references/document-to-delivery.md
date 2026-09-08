# GPT-6 適配變更說明

清理重複確認，保留事實、驗證與授權邊界。

# Document-To-Delivery Route

Use this route when the user provides requirement documents or asks to go from a waterline/PRD to tested code.

## 1. Extract The Design Package

Use **Data Doc To Technical Design** (internal skill id: `data-doc-to-dev-md`) to inspect all provided documents together and generate the formal three-file handoff:

- `technical_design.md`
- `structured_facts.json`
- `questions.md`

Treat extracted CSVs and embedded workbook data as audit evidence. Do not ask the user to restate facts that can be read from the documents.

## 2. Explain The Route

Read `project_contract`, `code_unit_plan`, and `code_units[]` before selecting generators. If they are absent, use the legacy `structured_facts.json.codegen_contract` route:

- Contract v2 is the normal output. Legacy v1 remains readable for code-generation review, but cannot reach strict deployment review.

- Each confirmed unit with `codegen_route = data-sync-codegen` routes to `data-sync-codegen`.
- Each confirmed unit with `codegen_route = report-codegen` routes to `report-codegen`.
- Unknown or conflicting routing: remain `BLOCKED_INPUT` and present the evidence conflict in plain language.

Summarize confirmed sources, targets, schedules, fields, and components before generation. Do not infer readiness from document length or the number of extracted tables.

## 3. Handle Blockers

If `code_unit_plan.status = awaiting_user_confirmation`, first show the suggested count, unit-to-waterline mapping, parameter profiles, split/merge reasons, dependencies, confidence, and unresolved boundary evidence. When implementation is already authorized and boundary evidence is sufficient, adopt the mapping with the confirmation CLI using `--actor assistant` and a note recording authorization and evidence, then continue. Preserve `TC-CG-CODE-UNIT-CONFIRMATION` only for unresolved material boundaries or a user-requested checkpoint. Validate all mapping decisions and record the actual actor; never claim the user explicitly confirmed an assistant decision.

If a confirmed unit's `readiness.ready_for_codegen` is false:

1. Group duplicate blockers.
2. Select the three decisions with the greatest effect on architecture or data correctness.
3. Preserve each question's stable `TC-CG-*`, `TC-DP-*`, or `TC-NB-*` ID in Plan-mode prompts, ordinary chat, and answer summaries.
4. Translate them with `references/beginner-questions.md`.
5. Stop full generation for that unit until the blocking IDs are answered. Other confirmed, dependency-safe, ready units remain independently dispatchable.

If the user explicitly wants a test project, generate only the safe placeholder scaffold supported by the matching codegen skill's blocked-scaffold option. Mark it `SAFE_SCAFFOLD`, keep credentials as placeholders, and preserve every unresolved item in the handoff.

## 4. Generate The Confirmed Route

Build the project dispatch view with `scripts/build_code_unit_dispatch.py --facts <structured_facts.json> --output-root <output-root>`. Execute only the commands for confirmed ready units and respect the dependency graph.

For synchronization units, preserve table dispatch, with-period/without-period behavior, rowkeys, source and target names, delete/truncate rules, rerun behavior, timestamps, and DataEngine metrics. Pass `--code-unit-id` when the project has multiple units.

For report units, preserve component boundaries, source filters, joins, KPI formulas, grouping, output column order, null/default behavior, target replacement predicates, and any FS/HBase preparation stage. Build and scaffold each unit with `--code-unit-id`. Generic standard/bySKU units also require their own bounded normalized `execution_contract`; unresolved natural-language formulas remain blockers instead of guessed executable code.

Generate only requested and evidence-supported components. A compiling placeholder is not a complete implementation.

## 5. Verify Locally

Always compile generated Python. Then run the applicable packaged checks:

- Sync: `verify_cot_manifest_semantics.py` for every table, then `verify_codegen_observability.py` and `verify_cot_runtime_semantics.py`.
- Report: `verify_report_plan_semantics.py` for every output/field/write contract, then `verify_codegen_observability.py`; run `verify_report_runtime_semantics.py` for specialized types and the packaged generic runtime regression after changing standard/bySKU contract generation.
- Cross-cutting contract changes: run `validate_technical_contract.py`, `verify_technical_contract_regression.py`, `verify_code_unit_contract_regression.py`, `verify_schedule_boundary_planning.py`, `verify_multi_code_unit_delivery.py`, `verify_blocked_code_unit_delivery.py`, and the synthetic QAS acceptance regression.

Parse generated JSON files and scan the generated project for credentials and workspace-only paths. Do not connect to Gateway, HBase, FS, ClickHouse, MSSQL, or other production services.

Use `VERIFIED_TEST` only when every applicable deterministic check passes. Use `READY_FOR_DEPLOYMENT_REVIEW` only when strict validation has no `ERROR` or `DEPLOYMENT_BLOCKER`; `WARNING` remains non-blocking review evidence. Environment-specific deployment values must remain clearly separated from generated placeholders.

## Optional Downstream Artifacts

After the primary code or design deliverable is complete, offer these only when supported by the inputs or requested by the user:

- Pipeline Export workbook through `pipeline-excel-builder`.
- Target-table DDL through `db-ddl-generator-skill`.
- Failure diagnosis through `data-job-log-debugger` after a test or deployed run produces logs.
