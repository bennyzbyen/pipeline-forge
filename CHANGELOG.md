# Changelog

## 2.0.3 - 2026-09-10

- Apply FMOS-validated report waterline document corrections for concise publication layout, full field dictionaries, and stable target-bound Catalog references.
- Preserve new report documents at 0.0.1 during initial drafting and use the standing author default while retaining established release histories.
- Reconcile detailed LLD evidence, dual-storage table identities, and missing evidence before raising clarification blockers.

## 2.0.2 - 2026-09-10

- Preserve independent code units and revalidate affected contracts when requirements change during Astra workflows.

## 2.0.1 - 2026-09-08

- Refine GPT-6 instruction priority and reuse existing authorization for autonomous delivery.
- Remove redundant code-unit and document presentation confirmations while preserving correctness gates and decision audit trails.

## 2.0.0 - 2026-09-07

- BREAKING: remove Graphviz rendering and fallback; Diagram Design is the only supported waterline drawing workflow.
- Migration: install Diagram Design separately and bind reviewed SVGs for data_flow and enabled report catalog diagrams before updating older documents.
- Preserve approved SVG layouts across prose edits; reject missing, modified, or stale diagram assets.
- Always deliver Markdown, interactive HTML, and vector PDF together with concise presentation and canonical content validation.

## 1.4.0 - 2026-09-02

- Add pipeline-doc-generator for editable waterline documents from PRD/HLD, including embedded Excel, Markdown, and PDF evidence.
- Generate Markdown, interactive standalone HTML, and searchable PDF with Graphviz flows, inline tables, clarification gates, and automatic revision summaries.
- Add the waterline-document guide route, proposed Pipeline/Task naming, and validation for all eight packaged skills.

## 1.3.0 - 2026-08-28

- Add evidence-driven project and code-unit contracts with explicit user confirmation before generation.
- Route confirmed code units independently to report or synchronization generators with unit-scoped plans, blockers, safe scaffolds, and tests.
- Extract algorithm, parameter, state, write, deployment, failure, and dependency boundaries from mixed Markdown and DOCX requirements.
- Preserve legacy single-component contracts while adding reference-assisted report parity and provenance gates.

## 1.2.0 - 2026-08-28

- Add first-class Markdown PRD and waterline inputs with mixed Markdown/DOCX extraction.
- Preserve Markdown headings, prose, GFM tables, code fences, and source provenance in the existing three-file technical-design handoff.

## 1.1.2 - 2026-08-27

- Fail closed on contaminated generation contracts and keep explicit safe scaffolds non-runnable.
- Add malformed-input diagnostics and offline regressions for logs, DDL, and Pipeline Export workbooks.
- Harden ZIP extraction, concurrent installation, release retries, and companion-site image handling.
- Split the report scaffolder and DOCX extractor into bounded modules with compatibility and size regressions.

## 1.1.1 - 2026-08-27

- Added deterministic cross-skill regressions for document-to-code routes, log diagnosis, and four-dialect DDL conversion.
- Made release archives reproducible and enforced version-matched immutable marketplace tags.
- Added transactional Windows installation rollback and upgraded website dependencies to eliminate audited vulnerabilities.

## 1.1.0 - 2026-08-27

- Added technical contract v2 with explicit field, source, rule, parameter, runtime, write, conflict, and validation-gate sections while retaining v1 review compatibility.
- Separated code-generation readiness from strict deployment blockers and made warnings non-blocking evidence.
- Added executable parameter-shape semantics, DataEngine result-protocol checks, environment connection matrices, and safe-log requirements.
- Added ClickHouse column/type/wire-format preflight, empty-output protection, and explicit non-atomic replacement acknowledgement.
- Added final HBase request verification after wrapper defaults and normalized COT period scalar/list/empty behavior.
- Promoted the DDL module into the repository source-of-truth set and removed inferred ClickHouse engines, clusters, replication paths, and uniqueness assumptions.
- Added self-contained synthetic QAS acceptance regressions for threshold conflicts, boundaries, required fields, multi-date inputs, period isolation, exact enums, zero output, reconciliation, and result protocol.

## 1.0.2 - 2026-08-21

- Established `1.0.2` as the stable PipelineForge version baseline.
- Adopted Semantic Versioning: PATCH for fixes, MINOR for backward-compatible features, and MAJOR for incompatible changes.
- Removed timestamp build metadata from the public release number and synchronized the plugin manifest, website, and download package version.
- Added automated validation for SemVer syntax and cross-file version consistency.
- Published the GitHub marketplace installation command in the repository and product site.
- Excluded Python caches and compiled bytecode from downloadable archives, with regression validation.

## 0.1.0+codex.20260821151410

- Added a complete downloadable plugin archive, SHA-256 checksum, and repeatable package builder for website distribution.
- Added a Windows setup helper that registers the extracted plugin in the user's Personal plugin source without removing existing entries.
- Kept a GitHub-backed Codex marketplace manifest as an alternate repository distribution path.
- Added repository, website, license, publisher, keyword, and brand metadata to the plugin manifest.
- Updated the companion site so its primary actions download the real plugin ZIP instead of linking to an inert enable action.

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
