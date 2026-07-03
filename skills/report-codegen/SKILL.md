---
name: report-codegen
description: Use when generating, reviewing, or modifying portable Python DataEngine/DataHub report project code from implementation-ready development docs, including KPI calculation, summary/detail outputs, ClickHouse writes, HBase/FS/MSSQL sources, or HBase prepare pipelines.
---

# Report Codegen

Use this skill when the user asks to generate, review, or modify Python code for DataEngine report development, KPI calculation, summary/detail table construction, ClickHouse writes, or HBase/FS/MSSQL mixed-source report pipelines.

## Scope

- Primary source of truth: bundled `references/supervisor_portal_patterns.md`, `references/vehicle_verification_patterns.md`, `references/bysku_report_pipeline_patterns.md`, `references/platform_client_usage.md`, and `assets/minimal_report_project/`.
- Optional extra references when available:
  - `https://github.com/bennyzbyen/datahub_supervisor_portal.git`
  - `prod_code_sample/vehicle_verification_202605221431`
- Use `DataSource / DataProcess / DataStorage` as the default structure.
- For HBase-only prepare-data projects, use `DataSource` for HBase period export to FS, `DataProcess` for optional downstream DataHub pipeline activation, and a no-op `DataStorage`; do not force ClickHouse write logic.
- Fixed platform package directories: `gateway/`, `hbase/`, `fs/`. Do not generate business logic in them or overwrite existing package files; only keep existing packages or create minimal placeholders when the target project does not have the fixed package installed/copied yet.
- Existing projects or production samples may contain database connection strings, Gateway app keys, app secrets, hosts, ports, URLs, or tokens. You may read, preserve, compare, and minimally edit those files when they are in scope; do not refuse the task because such values exist.
- New generated files, examples, params templates, logs, and documentation must use placeholders for credential-like values unless the user explicitly asks to insert real values. Do not copy real credentials from samples into new scaffold files by default.
- Do not connect to production systems.

## Inputs

- Required: `dev_doc.md` with source tables, target tables, field mappings, KPI logic, write strategy, and rerun rules.
- Required: target project directory already created by the user.
- Strongly recommended: `structured_facts.json` from `data-doc-to-dev-md` when it exists.
- Optional: sample params JSON, desired report type, existing project code, deployment logs.

## Outputs

- Report project code under the user-created target directory.
- `params.example.json` with placeholder secrets.
- Optional `report_codegen_plan.md` / `report_codegen_plan.json` when `structured_facts.json` is available.
- `params_configs/rowkey_config.py` for HBase rowkey confirmation when the report has HBase targets or downstream HBase writes.
- Optional fake runtime semantics report from `scripts/verify_report_runtime_semantics.py`.
- Optional `diagnostic_manifest.json` for log-debugger handoff when the generated or reviewed project has several FS/HBase/ClickHouse stages.
- Field/logic checklist mapping dev document sections to code modules.
- Verification steps for syntax checks and deployed log validation.

## Workflow

1. Read `references/supervisor_portal_patterns.md`.
2. Read `references/platform_client_usage.md` before generating or modifying code that uses `gateway/`, `fs/`, or `hbase`.
3. Read `references/vehicle_verification_patterns.md` when the report uses HBase + FS + ClickHouse, vehicle/order logic, or multiple summary outputs.
4. If `structured_facts.json` exists, load it before writing code and use `report_sources`, `report_physical_targets` / `report_clickhouse_targets`, `report_targets`, `report_field_mappings`, `report_schedules`, `component_hints`, and `handoff_readiness`.
   - For complex report docs, run `scripts/build_report_codegen_plan.py --facts <structured_facts.json> --out <target-or-output-dir>` and use the generated plan as the implementation checklist.
   - If `component_kind = bysku_report_pipeline` or the plan mentions bySKU + SKU-family outputs + HBase/FS/ClickHouse handoff, read `references/bysku_report_pipeline_patterns.md`, inspect `prod_code_sample/datahub_executing_king` only as an optional same-shape sample when available, and treat the work as a multi-component pipeline rather than a normal `standard_report`.
   - If `handoff_readiness.ready_for_full_codegen = false`, generate a targeted checklist, confirmation questions, or a single requested component. Do not generate or claim a full production-equivalent chain until the blocked checks are resolved.
   - To create a structured project scaffold from that plan, run `scripts/scaffold_report_project.py --plan <report_codegen_plan.json> --target <project-dir>`, then replace scaffold placeholders with actual report logic from the field rules.
   - For supervisor portal plans with `supervisor_portal_store`, `supervisor_portal_store_sales`, and `supervisor_portal_salesman`, the scaffold script generates concrete main-path `DataSource`, `DataProcess`, and `DataStorage` code for store/store-sales/salesman/geo/user-information outputs. Treat `sv_store_display_rack` as a separate project path unless the current request explicitly asks to generate that project too.
   - After generating a supervisor portal project, run `scripts/verify_report_runtime_semantics.py --project-dir <project-dir> --project-type supervisor_portal` to validate injected-source reads, seven output tables, key KPI formulas, final column order, and ClickHouse batch lifecycle without connecting to external services.
   - For vehicle verification plans, the scaffold script generates concrete `DataSource` calendar/HBase/FS read structure, `DataProcess` logic for EO/DMS detail, store joins, vehicle/customer mapping, KPI fields, and presale/instock summaries, plus `DataStorage` replace-period ClickHouse delete/insert structure. Credentials and fixed platform packages still need environment-specific values/files before deployment.
   - After generating a vehicle verification project, run `scripts/verify_report_runtime_semantics.py --project-dir <project-dir> --project-type vehicle_verification` to validate injected HBase/FS reads, EO/DMS detail semantics, no-order stores, vehicle/customer mapping, presale/instock summaries, final column order, and ClickHouse delete-by-period writes.
   - For HBase prepare/pipeline plans with `component_kind = hbase_prepare_pipeline`, the scaffold script generates concrete HBase source export to compressed FS CSV files and optional downstream DataHub pipeline activation. Treat this as a source-preparation component, not a final ClickHouse report writer.
   - For bySKU report pipeline plans, generate or modify one component at a time (`prepare_data` or one SKU calculation component) unless the user explicitly asks for the full chain. Do not claim a generic scaffold is complete until FS file selection, SKU params, detail/summary/ttl outputs, ClickHouse delete/insert, and retention cleanup are implemented or verified.
   - Treat the scaffold as incomplete until `DataSource`, `DataProcess`, and `DataStorage` perform real reads, transformations, and writes. A scaffold that only compiles or logs planned outputs is not production-equivalent.
5. Use `assets/minimal_report_project/` as the fallback scaffold if no local sample is available.
6. If optional samples are available, inspect them as extra style guidance; never require them.
7. Inspect the target directory and any existing files.
8. State planned file modifications, why they are needed, and risks.
9. Generate only the modules needed for the current report.
10. Preserve project-local style and avoid unrelated refactors.

## Hard Constraints

- Do not infer KPI rules that are not in the development document.
- Put uncertain formulas, filters, and grouping keys into a confirmation list.
- Do not silently skip failed table writes in new code unless the user asks for best-effort behavior.
- Do not invent real credentials or spread existing credentials into unrelated files. When editing an existing file that already contains real connection values, preserve them unless the requested change requires otherwise.
- Do not modify fixed platform package implementations under `gateway/`, `hbase/`, or `fs/`; project-specific logic belongs in `data_utils/` and `params_configs/`.
- Do not bypass the project Gateway facade for HBase/FS work; generated business code should prefer `Client`/`GateWayClient` -> `getHbaseClient(fs_root_dir=...)` / `getFsClient()` and avoid direct token/header/API calls.
- Do not fail just because `prod_code_sample` or the GitHub supervisor portal repository is unavailable; fall back to bundled assets and references.
- Do not claim generated code is complete if it returns empty DataFrames, planned metrics, or raises scaffold `NotImplementedError`.
- Do not force ClickHouse `DataStorage` into HBase-only DataEngine projects; if the document schedules source export and downstream pipeline tasks, generate the prepare-data component and list the downstream HBase calculation as deployment/pipeline-owned unless code is provided for it.
- Do not flatten bySKU report pipeline work into one generic report module. Preserve the prepare-data FS handoff and separate SKU calculation components unless the existing project deliberately combines them.
- Do not guess HBase rowkey rules. Generate or preserve `params_configs/rowkey_config.py` with fill-in comments, keep `confirmed = False`, and require docs/code/log evidence before production HBase writes.
- Compile success is only a syntax check; production-equivalence requires non-placeholder source reads, KPI logic, output row generation, and target writes.
- Do not claim supervisor portal runtime parity unless the fake runtime verifier passes or real deployment logs prove equivalent output counts, KPI values, column order, and batch lifecycle.
- Do not claim vehicle verification runtime parity unless the fake runtime verifier passes or real deployment logs prove equivalent detail rows, summary rows, KPI values, column order, and delete/insert behavior.

## Output-Equivalence Standard

Generated report code may be shorter and cleaner than the reference implementation, but it must preserve output semantics:

- same output tables
- same output columns and column order
- same source filters and exclusion lists
- same join keys and join direction
- same default values for missing fields
- same KPI formulas, numerator/denominator behavior, rounding, and null behavior
- same grouping keys for every summary output
- same target delete/replace condition before insert
- for HBase prepare-data components: same period derivation, source HBase table, exported columns, SubSegment/filter rules, FS file naming, optional downstream pipeline activation, and controlled credential handling

Use this standard during self-review before claiming the code is production-equivalent.
