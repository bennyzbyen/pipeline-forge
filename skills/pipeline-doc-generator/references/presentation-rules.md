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

For a confirmed Blob source, use exactly `SAS URL | Database / 路径 | 备注`. This applies inside either profile and alongside non-Blob sources; those retain their own connection schema. Set `source_connections[].location` or link it with `source_id`/`source_ids` when mixed inputs would be ambiguous. Never infer storage just from a filename.

- Put the full user-provided SAS URL in `sas_url` and the source directory in `database`. Preserve the URL byte-for-byte, including signature escaping. Never synthesize a token or contact the URL merely to render the document.
- Derive the expiry from the signed URL's `se` parameter, with its timezone, and display it once in `备注`. If no valid expiry is present, obtain `expires_at` or an explicit policy-based expiry explanation. Do not guess an expiration from the creation/start time.
- A missing SAS URL is a clarification item, not an empty Host column. If the user explicitly uses a different Blob authentication method, confirm an appropriate connection layout instead of inventing SAS access.
- Full signed links are access credentials. Their inclusion is limited to the requested local document/facts bundle. Tell the user the bundle contains credentials; never place real links in skill examples, test fixtures, commits, logs, diagrams, release archives, or public previews. Sharing/uploading the resulting bundle requires separate authorization.

## Flow Overview

Show data identities, storage/system categories, meaningful Pipeline/process nodes, and accurate relationships. Put a confirmed physical table/path in the node label or optional `identifiers` list. Node IDs and edge relationships stay stable.

Do not put RowKey, auto-increment rules, field types, TTL, SQL, validation steps, credentials, or execution times in any visible node/edge/group label. Legacy `details` remain in the audited facts/spec but are not displayed. `identifiers` is only for actual identities, not a replacement details field. Never assume RowKey is auto-increment just because a sync is full-refresh.

## Target And Catalog

Neither Target nor Target Management has a `catalog` column, even if legacy target facts still contain that property. Keep Catalog Basic Info in its dedicated section. Existing optional Target column choices and source-to-target row rules remain unchanged.
