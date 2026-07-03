---
name: data-job-log-debugger
description: Use when diagnosing DataEngine/DataHub Python job failures from full printed logs or screenshots, including sync/report jobs with ClickHouse, HBase, FS, Gateway, MSSQL, MySQL, Blob, encoding, path, parameter, permission, missing data, or deployment environment issues.
---

# Data Job Log Debugger

Use this skill when the user provides complete printed logs, copied traceback text, or screenshots from deployed DataEngine/DataHub jobs and asks for root cause analysis or minimal fix suggestions.

## Scope

- Diagnose before proposing code changes.
- Prefer non-code causes first: path handling, PowerShell parsing, encoding, params, missing files, permissions, environment variables, service access, upstream data absence.
- Then check business logic and code defects.
- Default output is analysis and minimal fix suggestion, not automatic code modification.
- Logs and screenshots may contain database connection strings, Gateway app keys, app secrets, hosts, ports, URLs, or tokens. Use them only as diagnostic evidence; do not refuse the task because they exist, and do not repeat sensitive values unless necessary for the diagnosis.

## Inputs

- Full printed log text, or screenshots if text is unavailable.
- Optional: params JSON, related code path, `diagnostic_manifest.json`, `report_codegen_plan.json`, environment (`uat`/`prod`), rerun period/date, recent code changes.

## Outputs

- Confirmed root cause or highest-confidence hypothesis.
- Impact scope.
- Minimum recommended fix.
- Verification steps using logs or safe local checks.
- Remaining uncertainty.

## Workflow

1. Read `references/common_failure_modes.md`.
2. If the log, params, plan, or path mentions bySKU report pipelines, NPD, B5, `prepare_data`, SKU calculation components, or sample aliases such as 执行为王 / `datahub_executing_king`, read `references/bysku_report_failure_modes.md`.
3. For text logs, run `scripts/analyze_data_job_log.py --log <log.txt>` when a local log file is available. Use its classification as a starting point, then verify against the full log manually.
4. For screenshots, visually extract or OCR the exception line, final failure symptom, params snippet, and the 30-50 lines around the failure before classifying.
5. Extract the first real exception and the final failure symptom.
6. Classify the issue: environment, params, path/encoding, dependency, gateway/HBase/ClickHouse, data absence, or business logic.
7. If a manifest or plan is available, compare actual log stages, source reads, target tables, delete predicates, and row counts against it before recommending code changes.
8. Identify the smallest evidence-backed fix.
9. Ask for code modification only when root cause and target file are clear.

## Output Format

Use these sections:

- Confirmed Issues
- High-Confidence Assumptions
- Uncertain Points
- Recommended Next Steps
- Verification

For deployment jobs, always mention whether the log proves that HBase, ClickHouse, FS, and timestamp update steps did or did not run.

For bySKU report pipeline jobs, always mention whether the log proves the prepare-data HBase export, FS upload/download, SKU calculation, ClickHouse delete, ClickHouse insert, and retention cleanup did or did not run.

## Hard Constraints

- Do not rewrite large code blocks from logs alone.
- Do not assume screenshots contain all context; list missing log lines when needed.
- Do not recommend production retries that can duplicate or delete data unless rerun behavior is known.
- Do not treat "no changed rows/periods" as a code defect until source SQL, timestamp, and manual period/date params are checked.
- Do not invent replacement credentials. If the root cause is an invalid or missing credential, describe the required configuration key or service account, not a new secret value.
