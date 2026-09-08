---
name: data-job-log-debugger
description: Diagnose DataEngine/DataHub Python job failures from logs or screenshots, including platform params, Gateway, HBase, FS, ClickHouse, source-data, rerun, and deployment-stage problems.
---

## GPT-6 適配變更說明

**用戶當前指令優先級最高**（相對本 Skill、引用指南和預設提示詞；平台 system/developer 指令與工具權限仍適用）。已授權、信息足夠即直接完成；沿用既有授權，自行處理範圍內可逆選擇。僅就無法從現有證據解決且影響正確性或授權的缺項提問，同時完成獨立工作。保留業務事實與安全驗證，不虛構確認。


# Data Job Log Debugger

Diagnose the failure and recommend the smallest evidence-backed next step. When the current request or prior session instruction authorizes a fix, inspect the related code, apply the smallest supported correction, and verify it directly. For diagnosis-only requests, report the findings.

## Inputs

Use the fullest available log text or screenshots. Params JSON, related code, `diagnostic_manifest.json`, `report_codegen_plan.json`, environment, rerun period/date, and recent changes improve confidence.

Treat secrets in logs as diagnostic evidence, but do not repeat them unless necessary. Name a missing or invalid configuration key instead of inventing a replacement credential.

## Workflow

1. For a local text log, run `scripts/analyze_data_job_log.py --log <log.txt>` and verify its classification against the full failure context.
2. Identify the causal exception, the final platform symptom, and the last completed data stage. Distinguish confirmed evidence from hypotheses.
3. Read `references/common_failure_modes.md` when DataEngine params, incremental timestamps, Gateway/HBase/FS/ClickHouse behavior, or rerun semantics affect the diagnosis.
4. Read `references/bysku_report_failure_modes.md` only for bySKU, NPD, B5, `prepare_data`, SKU calculation, detail/summary/ttl, or equivalent multi-component pipelines.
5. When a manifest or plan exists, compare expected and observed source reads, targets, delete predicates, row counts, and stage order before recommending code changes.

## Required Result

Report the root cause or highest-confidence hypothesis, impact, minimum fix, verification evidence, and remaining uncertainty. State which HBase, ClickHouse, FS, and timestamp stages did or did not run; for bySKU pipelines, also cover prepare export, FS transfer, SKU calculation, delete, insert, and retention cleanup.

## Constraints

- Do not rewrite substantial code from logs alone.
- Do not treat `no changed rows/periods` as a code defect before checking source conditions, stored timestamps, and manual period/date params.
- Do not recommend a production rerun that may duplicate or delete data until rerun and replacement behavior is known.
- Screenshots may omit causal context; identify the missing evidence when confidence is limited.
