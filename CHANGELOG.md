# Changelog

## 0.1.0+codex.20260820110400

- Added all-table COT manifest/runtime/field/rowkey verification and per-table runtime guards for unresolved sync contracts.
- Added a bounded non-eval execution contract for generic standard and bySKU reports, with real source adapters, transformations, exact output projections, and safe ClickHouse writes.
- Added full report plan/field/write verification plus deterministic standard, bySKU, and HBase prepare runtime regressions.
- Updated the beginner guide and package documentation so incomplete generic reports remain explicit review-only scaffolds instead of failing later with hidden placeholders.

## 0.1.0+codex.20260820023155

- Added `pipeline-forge-guide` as a beginner-friendly front door across document-to-code, Pipeline Export, DDL, log diagnosis, and existing-project review workflows.
- Added five-stage progress guidance, plain-language blocker questions, and explicit `BLOCKED_INPUT`, `SAFE_SCAFFOLD`, `VERIFIED_TEST`, and `READY_FOR_DEPLOYMENT_REVIEW` statuses.
- Updated plugin prompts, package validation, multilingual documentation, skill deployment, and the companion site for the seven-module package.

## 0.1.0+codex.20260819163139

- Fixed COT documents containing a normal `zo_bysku_detail_p` sync row being misrouted to `bysku_report_pipeline`.
- Require independent SKU-family calculation evidence such as NPD/B5/新品 outputs, SKU parameters, calculation components, or R13P retention before routing to report codegen.
- Added positive and negative bySKU routing regressions and validated the fix against the COT2026 DataEngine waterline document.

## 0.1.0+codex.20260819141852

- Synced all five repository source-of-truth skills, including the latest three-file technical-design handoff, code-generation observability rules, scripts, references, templates, and agent metadata.
- Added `pipeline-excel-builder` as the sixth packaged module and refreshed the plugin-only DDL module from the current local skill.
- Updated plugin metadata, package validation, documentation, and the product site for the expanded capability set.

## 0.1.0+pf.20260703075507

- Initial public release of PipelineForge.
- Includes five independent modules for document extraction, log diagnosis, synchronization code generation, report code generation, and DDL generation.
- Adds bySKU report pipeline extraction, planning, generation, and diagnosis patterns.
- Includes logo assets and package validation utilities.
