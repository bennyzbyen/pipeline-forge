# Beginner-Friendly Blocking Questions

Use these translations when a technical decision blocks generation. Adapt wording to the actual evidence and ask no more than three questions at a time.

## Rowkey

- Plain question: Which fields uniquely identify one HBase row, and in what order are they joined?
- Why it matters: A wrong rowkey can overwrite unrelated data or create duplicates.
- Common evidence: Existing production code, `rowkey_config.py`, an HBase design table, or a known rowkey sample.

## With-Period Or Without-Period

- Plain question: Is this table refreshed for a selected business period, or synchronized independently of period?
- Why it matters: It controls runtime parameters, reruns, delete scope, and incremental behavior.
- Common evidence: Current production table lists, scheduler parameters, or a previous year's job configuration.

## Incremental Timestamp

- Plain question: Which source column tells us a row changed, and when may the saved timestamp advance?
- Why it matters: The wrong column or update timing can miss rows after a failed run.
- Common evidence: Source DDL, existing job code, DataEngine params, or successful-run logs.

## Delete, Replace, Or Truncate

- Plain question: Before writing new rows, should the job delete one period, replace matching keys, truncate the table, or only append?
- Why it matters: This determines duplicate and historical-data risk.
- Common evidence: Waterline write strategy, target DDL/engine, existing ClickHouse code, or deployment runbook.

## Report Formula Or Join

- Plain question: What are the exact numerator, denominator, filters, grouping keys, and join direction for this output?
- Why it matters: Code can run successfully while producing the wrong KPI.
- Common evidence: PRD formula table, accepted report sample, SQL, or reconciliation workbook.

## Rerun Scope

- Plain question: When a run fails or must be corrected, do you rerun one period/date, resume from a timestamp, or rebuild everything?
- Why it matters: It controls cleanup, timestamp updates, and whether a rerun is idempotent.
- Common evidence: Scheduler parameters, operations guide, or previous rerun logs.

## Environment Values

- Plain question: Which environment-specific IDs or connection settings will deployment inject, and which values may remain placeholders for local testing?
- Why it matters: Test scaffolds must not accidentally contain production credentials or target the wrong environment.
- Common evidence: Deployment variables, secret manager references, platform application configuration, or an approved parameter template.

When the user does not know the answer, offer a safe way to locate evidence. Do not convert uncertainty into a guessed default.
