---
name: data-sync-codegen
description: Generate, review, or modify portable Python DataEngine/DataHub synchronization projects from development docs, especially COT yearly sync jobs with changing tables, fields, rowkeys, periods, and runtime parameters.
---

# Data Sync Codegen

Build COT/DataEngine synchronization code from `technical_design.md` or equivalent structured requirements. Accept legacy `dev_doc.md` inputs, and prefer `structured_facts.json` when available.

## Design Package Contract

For the standard three-file handoff, read in this order:

1. `structured_facts.json`: inspect the two-level `project_contract`, `code_unit_plan`, and `code_units[]` first, then the legacy-compatible `codegen_contract`, tables, fields, provenance, and readiness.
2. `technical_design.md`: use HLD for flow/component boundaries and LLD for rowkeys, incremental fields, write predicates, parameters, retry, and verification behavior.
3. `questions.md`: stop full generation when `Blocking Code Generation` is non-empty; deployment and non-blocking questions do not prevent scaffolding.

Do not require separate HLD, LLD, manifest, traceability, or persistent codegen-plan files. Legacy inputs without `codegen_contract` use the existing evidence checks.

## Contract

- Use bundled patterns, scaffolds, and verifiers as the portable source of truth; production samples are optional comparison evidence only.
- Keep `gateway/`, `hbase/`, and `fs/` as fixed platform packages. Put table-specific behavior in COT modules and config.
- Do not connect to databases or production services during generation or local verification.
- Preserve in-scope existing connection values when editing their file. New files, examples, logs, and docs use placeholders unless the user explicitly supplies values for insertion.

## Workflow

1. Read `references/cot_sync_patterns.md`.
2. Read `references/code_comments_and_runtime_logging.md` before generating or reviewing business code.
3. Read `references/platform_client_usage.md` when code touches Gateway, HBase, or FS.
4. If `codegen_contract.component_kind` or `component_hints[].component_kind` is `bysku_report_pipeline`, route to `report-codegen`; it is not a COT table-sync shape.
5. For a two-level contract, reject `awaiting_user_confirmation` and select a confirmed sync unit with `scripts/scaffold_cot_sync_project.py --structured-facts <facts> --output-dir <target> --code-unit-id <id> [--extracted-tables <dir>]`. The ID may be omitted only for one confirmed unit. Legacy facts keep the existing command. Each selected unit generates its own entrypoint, config, test, and read-only `CODE_UNIT_CONTRACT.json` snapshot.
6. If `codegen_contract.ready_for_codegen = false`, return its blockers. Use `--allow-blocked-scaffold` only for an explicitly requested safe scaffold, and do not claim full implementation. A blocked scaffold must include `SAFE_SCAFFOLD.json` with `runtime_enabled=false` and keep every table runtime-disabled; the flag alone must not downgrade an otherwise ready contract.
   Its generated contract test must assert the blocked snapshot and safe marker, while a ready unit's test must assert readiness and the absence of that marker.
7. Adapt only confirmed tables, fields, parameters, rowkeys, and exceptions. Keep business-specific variation in config where possible.
8. Compile generated Python, then run `scripts/verify_cot_manifest_semantics.py --project-dir <target>` to check every table against the manifest, runtime config, fields, and rowkey review surface.
9. Run `scripts/verify_codegen_observability.py --project-dir <target>` and `scripts/verify_cot_runtime_semantics.py --project-dir <target>` for scaffold projects. The runtime verifier checks empty/manual period semantics and the final HBase request after wrapper defaults. Use the manifest verifier's `--strict-deployment` mode only when the user is preparing a deployment review.
10. After changing manifest generation or validation logic, run `scripts/verify_cot_manifest_semantics_regression.py` to prove both a valid table and an invalid guarded table behave correctly.

## Output-Equivalence Standard

Generated code may be simpler than a production sample, but it must preserve:

- selected source and HBase/ClickHouse targets
- with-period versus without-period dispatch
- rowkey columns and prefix rule
- ClickHouse delete, drop, or truncate behavior before insert
- manual reruns that do not advance the timestamp
- automatic timestamp updates only after successful target writes
- metrics containing source, targets, row counts, and status

## Hard Constraints

- Do not guess production rowkeys. Keep `cot_config/rowkey_config.py` unconfirmed until docs, code, or logs prove the rule, then synchronize confirmed values to runtime config or params.
- Do not modify fixed platform package implementations or bypass the project Gateway facade.
- Do not add report KPI logic or flatten bySKU report pipelines into table-sync code.
- Do not encode workspace-only `skill_lab`, `doc`, `outputs`, or `prod_code_sample` paths into generated projects.
- Do not claim runtime parity without the fake-runtime verifier or equivalent deployment-log evidence.
- Do not claim full-table coverage from the six-case fake runtime alone; require the all-table manifest verifier as well.
- Keep per-table `runtime_enabled=false` while generated `contract_issues` remain; do not bypass that guard for a review-only scaffold.
- Treat empty period input as automatic incremental mode; normalize non-empty scalar/list input to an ordered deduplicated list and reject invalid non-empty shapes.
- Do not infer environment connection modes from names. Strict deployment requires the declared runtime matrix and target write/recovery contracts.
