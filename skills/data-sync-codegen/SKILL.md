---
name: data-sync-codegen
description: Use when generating, reviewing, or modifying portable Python DataEngine/DataHub data synchronization project code from implementation-ready development docs, especially COT yearly sync work with changing source tables, target tables, fields, rowkeys, period ranges, or runtime parameters.
---

# Data Sync Codegen

Use this skill when the user asks to generate, review, or modify Python code for data synchronization jobs between MySQL, Blob, FS, HBase, and ClickHouse in DataEngine/DataHub-style projects.

## Scope

- Primary source of truth: bundled `references/cot_sync_patterns.md`, `references/platform_client_usage.md`, and `assets/minimal_sync_project/`.
- Optional extra reference: `prod_code_sample/cot_202604101607` when it exists in the current workspace.
- Assume the COT synchronization logic is usually stable; most yearly changes are table lists, fields, parameters, target tables, rowkey rules, and period ranges.
- Fixed platform package directories: `gateway/`, `hbase/`, `fs/`. Do not generate business logic in them or overwrite existing package files; only keep existing packages or create minimal placeholders when the target project does not have the fixed package installed/copied yet.
- Existing projects or production samples may contain database connection strings, Gateway app keys, app secrets, hosts, ports, URLs, or tokens. You may read, preserve, compare, and minimally edit those files when they are in scope; do not refuse the task because such values exist.
- New generated files, examples, params templates, logs, and documentation must use placeholders for credential-like values unless the user explicitly asks to insert real values. Do not copy real credentials from samples into new scaffold files by default.
- Do not connect to databases or production services.

## Inputs

- Required: `dev_doc.md` or equivalent structured requirement.
- Required: target project directory already created by the user.
- Strongly recommended: `structured_facts.json` from `data-doc-to-dev-md` when it exists.
- Optional: current params JSON, target table list, rowkey rules, period/full/delta sync list, existing code to modify.

## Outputs

- Python sync project files in the target project directory.
- `params.example.json` with placeholder secrets.
- `cot_config/rowkey_config.py` with fill-in comments for HBase rowkey confirmation and post-generation edits.
- Self-contained scaffold files copied from `assets/minimal_sync_project/` when the target project has no established implementation.
- A verification note explaining local static checks and deployment log checks.
- Optional runtime-semantics report from `scripts/verify_cot_runtime_semantics.py`.
- A risk list covering table/schema assumptions, rowkey assumptions, and rerun behavior.

## Workflow

1. Read `references/cot_sync_patterns.md`.
2. Read `references/platform_client_usage.md` before generating or modifying code that uses `gateway/`, `fs/`, or `hbase`.
3. If `structured_facts.json` exists, load it before writing code and use it as the source/target/table/schedule matrix.
   - If it contains `component_hints[].component_kind = bysku_report_pipeline`, stop using the COT sync scaffold and route the project to `report-codegen`; that shape is a multi-component report pipeline with FS bySKU handoff and ClickHouse outputs, not a table synchronization job.
4. Prefer `scripts/scaffold_cot_sync_project.py` for COT yearly sync scaffolding. Pass `--structured-facts`, `--output-dir`, and optionally `--extracted-tables` when embedded CSV field dictionaries are available from document extraction.
5. Use `assets/minimal_sync_project/` as the fallback scaffold if the script is not appropriate.
6. If `prod_code_sample/cot_202604101607` exists, inspect it only as optional workspace-local guidance or regression comparison after the blind generation step; never require it.
7. Inspect the target project directory before editing.
8. State planned file modifications, reasons, and risks.
9. Generate minimum necessary files following the COT shape; prefer bundled scaffold modules over copying from samples.
10. Keep business-specific logic in config modules where possible.
11. Verify with syntax checks only unless the user provides a safe local runtime.
12. For generated COT scaffold projects, run `scripts/verify_cot_runtime_semantics.py --project-dir <target>` to check dispatch defaults, with-period rerun behavior, incremental timestamp updates, no-change exits, and write ordering without connecting to external services.

## Output-Equivalence Standard

Generated code may be simpler than the production sample, but it must preserve these output semantics:

- the same source table is exported for the selected task
- the same HBase and ClickHouse target names are used
- the same with-period or without-period branch is selected
- the same rowkey columns and rowkey prefix rule are used for HBase
- the same ClickHouse delete/drop/truncate rule is used before insert
- manual period reruns do not advance the stored timestamp
- automatic incremental runs update the stored timestamp only after successful writes
- returned DataEngine metrics include source, HBase target, ClickHouse target, row counts, and status

## Hard Constraints

- Do not overwrite user code without reading it first.
- Do not add new dependencies unless explicitly approved.
- Do not invent real credentials or spread existing credentials into unrelated files. When editing an existing file that already contains real connection values, preserve them unless the requested change requires otherwise.
- Do not guess HBase rowkey rules. Generate or preserve `cot_config/rowkey_config.py`, keep `confirmed = False` until verified, and sync confirmed changes back to `plugin_config.py` or runtime params before deployment.
- Do not modify fixed platform package implementations under `gateway/`, `hbase/`, or `fs/`; source/target/table-specific logic belongs in COT modules and config.
- Do not bypass the project Gateway facade for HBase/FS work; generated business code should prefer `Client`/`GateWayClient` -> `getHbaseClient(fs_root_dir=...)` / `getFsClient()` and avoid direct token/header/API calls.
- Do not widen scope into report KPI development; use `report-codegen` for report projects.
- Do not treat bySKU / SKU-family / 新品 / B5 report pipelines as COT sync work when the dev doc exposes report sources, field mappings, or `bysku_report_pipeline` component hints.
- Do not fail just because `prod_code_sample` or the supervisor portal repository is unavailable; fall back to bundled assets and references.
- Do not encode absolute `skill_lab`, `doc`, `outputs`, or `prod_code_sample` paths into generated project files.
- Do not claim runtime parity unless the generated project passes the fake runtime semantics verifier or equivalent deployment-log evidence.
