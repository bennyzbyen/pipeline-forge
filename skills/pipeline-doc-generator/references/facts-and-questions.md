# Facts And Questions Contract

`facts.json` is the canonical semantic source for generated Markdown, HTML, PDF, and SVG. Diagram Design's retained HTML/SVG owns presentation only, with a reviewed binding recorded in facts; see `diagram-design-interface.md`. Use `assets/facts.schema.json` for the full interface.

## Stable IDs

Use lowercase ASCII IDs with underscores. Keep an existing ID during renames so conversational edits do not break Pipeline or flow references. Required ID domains are sources, targets, pipelines, fields within a target, and flow nodes/edges.

## Required Facts

- `profile`: `sync` or `report`.
- `document`: title, project name/description, automatically maintained release rows, Project Owner, documentation reference, and sync go-live when applicable. Ask for a missing document author, not for the version or change summary. Developer and Operator are fixed as `数砚工程师` and are not clarification items.
- `requirements.summary`.
- `sources`: confirmed data location/storage type (for example Azure Blob Storage, HBase, MySQL, MSSQL, or another explicit platform), source system, physical table/path, range, fields, and filters/joins. Do not infer the location only from a table or path name; ask when the evidence is absent or ambiguous.
- `targets`: storage/database/table, description, grain, write mode, ordered fields, and processing logic. RowKey remains user-confirmed, never automatically chosen from the sync mode. Legacy target schedules may remain as evidence but are not duplicated in the document.
- `pipelines`: Data Utilization, Pipeline, Task, concise trigger, source IDs, target IDs, steps/write/retry facts. Keep upstream readiness/operational explanations in `schedule_notes`, outside the trigger cell.
- `source_connections`: for Blob use `location` or source references, full `sas_url`, `database` path, and expiry from `se` or confirmed `expires_at`; see `presentation-rules.md` for credential boundaries and mixed connections.
- `resources`: peak-memory estimate and environment.
- `flow`: accessible title/description, nodes, and valid edges.
- `catalog`: applicability and registration facts for both profiles.
- `render_preferences` for sync documents: explicit booleans for the three user-confirmed optional Target columns (`include_target_category`, `include_target_report_type`, and `include_target_range`).
- `render_preferences.last_format`: always `all`; legacy partial values are migrated automatically. Optional `pdf_orientation`: `auto` (default), `portrait`, or `landscape`; reuse on later renders.

## Questions

Use stable IDs:

- `PL-BLOCK-*`: absence prevents a formal document.
- `PL-CONF-*`: a conflict or confirmation is required.
- `PL-OPTION-*`: useful but non-blocking.

Each question has `id`, `severity`, `question`, `status`, optional `answer`, and `source_refs`. Do not ask a resolved question again. `questions.md` is rendered from these records plus deterministic structural gaps.

Legacy `WL-*` question/conflict IDs are normalized to `PL-*` when the facts are processed, preserving their answers, status, and evidence. Do not globally replace text inside requirement documents or user answers. Obsolete blank-form release/naming questions are superseded by the new author/candidate checks.

The obsolete write-flow/sync-logic narrative and output-choice blockers are superseded by the concise three-format contract. This does not confirm any missing write-mode, source, or schedule facts. A verbose trigger or missing Blob connection/expiry gets a specific structural diagnostic; repair presentation from clear evidence before asking the user for facts already available.

## Proposed Names

- First use names explicitly supplied by the user or established in source material. Do not rename an existing platform resource just to fit a new convention.
- Otherwise propose clear lowercase snake_case Data Utilization, Pipeline, and Task names using project/business purpose, processing action, and source/target identity. The helper fills missing names deterministically, but the assistant should improve generic candidates before presenting them.
- For every assistant-proposed name, record its key in `pipelines[].name_confirmation.proposed_fields` (`data_utilization`, `name`, or `task_name`). Present a compact candidate list and ask whether to adopt it. Do not ask an open-ended "what should it be called?" question.
- When accepted, copy the exact accepted values into `name_confirmation.confirmed_values`. Rejecting a proposal means revise it and confirm the replacement. Changed proposed values invalidate the previous acceptance; accepted unchanged values are not asked again. Formal generation waits on `PL-BLOCK-PIPELINE-NAMES-<stable-id>` until acceptance.
- Stable IDs are not display names. Preserve IDs and input/output relationships through renames; update affected flow labels explicitly.

## Automatic Release History

- For a new document with no history, initialize `version = 0.0.1`, `summary = 初始版本`, and the current local date. Obtain the author from confirmed `document.author` or the existing release author; never invent a person's identity.
- For each subsequent content update, the assistant writes a concise factual summary to `change_log`. The renderer increments the last numeric version component (for example `0.0.1` to `0.0.2`) and appends one release row. It uses fresh change-log summaries, or a deterministic summary of changed sections when none was supplied. No version/summary question is needed; the user can correct either afterward.
- `revision_state` stores semantic hashes, the last rendered version, and the consumed change-log count inside `facts.json`. Commit it only after all selected outputs succeed. Repeated rendering, retries, evidence/question-state changes, and switching Markdown/HTML/PDF alone do not create duplicate revisions. Target-column or flow changes count as document edits.
- Preserve existing historical rows. If the assistant/user has already added the current revision, do not append another. For legacy facts without `revision_state`, the first render establishes a baseline without inventing past changes. When revising a legacy document before that first render, compare its original facts in the session and record the real revision yourself using the same automatic version/summary policy.
- This is document versioning only, not permission to publish, email, install, or deploy anything.

## Confirmed Pending Values

Literal `待定`, `TBD`, or equivalent values are not complete by default. Allow them only after the user explicitly confirms that the value should remain pending and add the exact JSON pointer to `confirmed_pending_paths`, for example `/document/go_live`.

## Conversational Revision

1. Identify the stable ID or JSON pointer affected by the user request.
2. Update the value and append a `change_log` entry with timestamp, summary, and `source = user_confirmation`.
3. Update affected flow labels/edges when a source, target, or Pipeline relationship changed.
4. Regenerate all three formats, even when the previous document used a partial output selection.
5. Validate Markdown, HTML, and PDF together so older output cannot silently drift.
