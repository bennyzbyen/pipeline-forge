# Concise Waterline Presentation

These are the owner's standing document preferences, not facts inferred from a sample project. Apply them to sync and report documents. Keep project-specific table names, times, RowKeys, and credentials project-specific.

## One Place For Each Explanation

- Chapter 1 is `需求概述`. In a short paragraph, say what data comes from which systems/storage and goes to which destinations. For complex flows name the source groups, principal processing purpose, and destination groups; do not expand formulas, schedules, retries, or validation steps here. Derive the overview from confirmed facts; do not ask the user to write prose that the evidence already supports.
- Sync documents omit the old `写入流程` and `同步逻辑说明` sections. Retain their legacy facts for audit; lack of those narrative arrays no longer blocks rendering. Confirm the actual write mode in target facts instead.
- Scheduling belongs in Pipeline Management. Target range means data coverage, not update frequency. Target field logic belongs in the field dictionary; avoid repeating it in the parent paragraph and Pipeline description.
- State each explanatory fact once. Use a short section reference where repetition would otherwise be necessary. Exact repeated paragraphs are deduplicated by the renderer; semantic rewordings still need an authoring review.
- Do not confuse repeated explanations with required identities: table names, source-to-target mappings, fields, and names used by different platform tables must remain explicit. Never deduplicate field rows, formulas, or distinct target rules to shorten a document.

## Trigger Cells

`pipelines[].trigger` contains only the confirmed trigger time/frequency, e.g. `每日 06:00 执行`, `每周一 08:00`, or a confirmed cron expression with its timezone. Preserve multiple actual run times. For event/manual jobs, state only the trigger, e.g. `_SUCCESS 事件触发` or `手动触发`; never invent a clock time.

Keep upstream readiness, timeout, validation, and retry facts in `schedule_notes` or other audit properties, not in the cell, diagram, or overview. When migrating a verbose trigger, separate a clearly identified run time from the notes. If multiple times have ambiguous roles, ask rather than guessing which one is the schedule. Missing operational evidence must not be marked confirmed just because it is omitted from the presentation.

## Blob Connections

When a connection section is required (the sync default, or an explicitly requested report extension), use exactly `SAS URL | Database / 路径 | 备注` for a confirmed Blob source. Non-Blob sources retain their own connection schema. The default report body omits connection registration and does not require SAS credentials. Set `source_connections[].location` or link it with `source_id`/`source_ids` when mixed inputs would be ambiguous. Never infer storage just from a filename.

- Put the full user-provided SAS URL in `sas_url` and the source directory in `database`. Preserve the URL byte-for-byte, including signature escaping. Never synthesize a token or contact the URL merely to render the document.
- Derive the expiry from the signed URL's `se` parameter, with its timezone, and display it once in `备注`. If no valid expiry is present, obtain `expires_at` or an explicit policy-based expiry explanation. Do not guess an expiration from the creation/start time.
- A missing SAS URL is a clarification item, not an empty Host column. If the user explicitly uses a different Blob authentication method, confirm an appropriate connection layout instead of inventing SAS access.
- Full signed links are access credentials. Their inclusion is limited to the requested local document/facts bundle. Tell the user the bundle contains credentials; never place real links in skill examples, test fixtures, commits, logs, diagrams, release archives, or public previews. Sharing/uploading the resulting bundle requires separate authorization.

## Flow Overview

Show data identities, storage/system categories, meaningful Pipeline/process nodes, and accurate relationships. Put a confirmed physical table/path in the node label or optional `identifiers` list. Node IDs and edge relationships stay stable.

Do not put RowKey, auto-increment rules, field types, TTL, SQL, validation steps, credentials, or execution times in any visible node/edge/group label. Legacy `details` remain in the audited facts/spec but are not displayed. `identifiers` is only for actual identities, not a replacement details field. Never assume RowKey is auto-increment just because a sync is full-refresh.

## Target And Catalog

Neither Target nor Target Management has a `catalog` column, even if legacy target facts still contain that property. Keep Catalog Basic Info in its dedicated section. Existing optional Target column choices and source-to-target row rules remain unchanged.

## Report Tables And Publication Format

- The report source chapter contains `2.1 数据列表`, without a connection-information or local sample-check chapter. Preserve physical source identities and business filters. Do not require connection identifiers, credentials, or deployment parameters solely to fill a deleted section.
- In Data Target, use separate `HBase表名` and `ClickHouse表名` columns when those stores actually exist. A table absent from one store is `不适用`, not an invented dual write. Use `targets[].storage_tables` when store-specific names differ; otherwise only explicit storage facts support a shared name. Do not infer HBase physical field types from ClickHouse types.
- Put each complete field dictionary under `3.1.x <表名>`, not under an extra category level or a business-name title. Include compact table metadata (description, storage, grain, write mode, sourced RowKey). Expand common audit fields into each target’s canonical `fields` array, with stable IDs and no duplicate keys.
- The field columns are `字段名 | 字段名称 | 字段类型 | 数据源/来源表 | 字段生成逻辑`. Keep generation/derivation rules once. Remove the duplicate `源字段/计算规则` / `数据源字段` column; preserve its unique source-field information in the logic cell. Do not add a sample-data column by default. Never discard a formula or unique source mapping just to reduce columns.
- Data Dictionary `Column` and `Type`, and Data Storage `Field&Type`, use the same `参见 3.1.x` reference to the full dictionary in this document. Bind by stable `target_id`; after reordering/deleting tables, regenerate references and verify the destination. An external document link or a field-count summary is not a dictionary.
- Project Documentation is exactly `本文档`. Published prose directly states business rules and field meanings; omit local PRD/HLD/LLD names, paths, “字段定义权威”, and “引用模型 LLD §…” boilerplate. Keep actual source systems/tables and internal chapter references. Rewrite from evidence, never remove citations with a global regex that could erase formulas or missing-input qualifications. Audit provenance remains in facts/evidence.
- Resource assessment uses only two paragraphs: `估计峰值<confirmed estimate>` and `资源环境：<confirmed environment>`. Do not add sizing methodology or deployment commentary unless requested. A prior project’s 10G estimate or temporary environment is not another project’s fact.

## Diagram And Pipeline Responsibilities

- Inside DataEngine/DataHub, show one pipeline rectangle per actual pipeline in the current mapping. Label it `pipeline <number> <purpose>`; stages, modules, and code files are not separate pipelines. Do not add “N 个方框” layout commentary or a code-architecture explanation to the diagram.
- Keep the source → processing → result-storage scope; omit downstream dashboards/Web/API nodes unless explicitly requested. Classify calendars and reference data under their evidenced storage, not as an invented external system. Separate HBase and ClickHouse result nodes, with enough whitespace to distinguish write destinations.
- Arrows express actual dependencies. Reduce crossing lines by grouping sources and concise identities, without losing which pipeline reads/writes what. Do not draw independent/parallel branches merely because actual and forecast calculations have different names.
- Before suggesting a split, inspect each pipeline’s physical write targets and replacement scope. Where multiple branches update the same result table and no verified isolation exists, prefer a unified writer or a single pipeline. If the user merges pipelines, update the list, numbering, flow, input/output mapping, downstream dependencies, and write ownership together. Merging does not itself prove safe rowkeys, transactions or reruns; retain real unresolved implementation checks in audit records.

## Scope And Correction Discipline

- Do not append local sample audits, input-readiness matrices, stage-exchange/manifest contracts, recovery/checkpoint chapters, acceptance checklists, unresolved-item ledgers, or development-handoff/code-unit gates to the waterline by default. These were unnecessary additions in the reviewed workflow. Keep necessary unresolved facts in `questions.md`; put requested implementation detail in its own appropriate deliverable. Publication readiness and production/development readiness are different claims.
- Before presenting a missing-fact list, search the supplied PRD/HLD/LLD and authorized existing context for that exact issue. Split a partly answered question into its remaining gap: a known formula with an undelivered input is an input-delivery gap, not an unknown formula. Distinguish business facts from technical implementation choices; do not require the user to design manifests or source-row IDs when evidence supports a local proposal. Reconcile unit conflicts before calculating.
- Treat corrections cumulatively. A later removal of `源字段/计算规则` supersedes its earlier requested inclusion; a later pipeline merge supersedes the original count. Do not promote the assistant’s abandoned design or explanation into standing policy.
- When asked to reuse a reference document’s Owner or Catalog contacts, read and copy that specific record; do not ask for it again or hardcode those people/emails globally. The standing author preference is `张本彦`; project names, contacts, memory estimates, calendar ownership, formulas and pipeline counts remain project-specific.
- Use a stable output stem throughout edits where practical. When explicitly asked to remove obsolete draft artifacts, first validate the current three-format bundle and its referenced assets, then remove only identified superseded outputs within the document directory. Do not make automatic recursive draft deletion a universal workflow or delete canonical facts, evidence, current SVGs or reusable scripts.
