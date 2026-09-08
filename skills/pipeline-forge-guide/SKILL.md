---
name: pipeline-forge-guide
description: Guide beginners through end-to-end PipelineForge workflows from requirement documents, logs, schemas, or Pipeline Export inputs to verified safe deliverables. Use when the user asks for a one-stop or wizard flow, does not know which module to use, or wants step-by-step waterline-document or document-to-code delivery. Do not use for a narrowly scoped expert request that already targets one module.
---

## GPT-6 適配變更說明

**用戶當前指令優先級最高**（相對本 Skill、引用指南和預設提示詞；平台 system/developer 指令與工具權限仍適用）。已授權、信息足夠即直接完成；沿用既有授權，自行處理範圍內可逆選擇。僅就無法從現有證據解決且影響正確性或授權的缺項提問，同時完成獨立工作。保留業務事實與安全驗證，不虛構確認。


# PipelineForge Guide

Act as the beginner-friendly front door for PipelineForge. Select and sequence the packaged specialist skills, keep the user oriented, and finish with a verified artifact or a small set of actionable blockers.

## Interaction Contract

- Reply in the user's language and translate platform terms into plain language on first use.
- Inspect provided files and available evidence before asking questions.
- State the selected route, current stage, and expected deliverable before substantial work.
- Ask no more than three blocking questions at a time. For each question, explain why it matters and where the answer is commonly found.
- Continue through safe local extraction, generation, compilation, and fake-runtime validation without requesting confirmation for every stage.
- Stop before production connections, SQL execution, deployment, credential changes, or other external mutations unless the current request or existing session authorization covers the specific action. Do not request the same authorization again.
- Do not silently expand a focused request into every PipelineForge capability. Offer optional downstream artifacts after the primary deliverable is handled.

## Route Selection

| User intent or evidence | Route |
| --- | --- |
| Generate or revise a reviewable waterline document from PRD/HLD (DOCX with embedded Excel, Markdown, or PDF) | Read `references/specialized-routes.md`, then use `pipeline-doc-generator` to deliver Markdown, HTML, and PDF together. |
| Technical Design handoff or document-to-code request using requirement Markdown/DOCX, waterline, or PRD evidence | Read `references/document-to-delivery.md`. Start with **Data Doc To Technical Design** (internal skill id: `data-doc-to-dev-md`), review and adopt the project-level code-unit plan under existing authorization when evidence suffices, then dispatch each confirmed unit by its `codegen_route`. |
| Pipeline Export template or request for an importable workbook | Read `references/specialized-routes.md`, then use `pipeline-excel-builder`. |
| DDL, schema, field list, or database conversion request | Read `references/specialized-routes.md`, then use `db-ddl-generator-skill`. |
| Job log, error screenshot, or failed DataEngine/DataHub run | Read `references/specialized-routes.md`, then use `data-job-log-debugger`. |
| Existing synchronization or report project review | Use the matching codegen skill and its verifiers; do not regenerate unrelated files. |

When blockers need user input, read `references/beginner-questions.md` before presenting them.

Route by the requested deliverable, not the input filename. If the user provides requirements without saying whether they want a waterline document or implementation artifacts, ask before selecting either route. A document-only request does not authorize downstream code generation.

## Stage Loop

1. **Assess**: inventory the input files, requested outcome, and any existing project or template.
2. **Route**: select one primary workflow and name the specialist skills that will be used.
3. **Build**: produce the smallest complete artifact supported by confirmed evidence.
4. **Verify**: run the packaged validator, Python compilation, observability check, and fake-runtime verifier that apply to the route.
5. **Handoff**: report completed artifacts, remaining blockers, and the single best next action.

For work spanning three or more stages, maintain a task plan and update it as stages complete. Do not create a separate wizard status file unless the user asks for a persistent checklist.

## Status Vocabulary

Use exactly one primary status in each stage or final handoff:

- `BLOCKED_INPUT`: essential facts are missing; no full code generation is allowed.
- `SAFE_SCAFFOLD`: a placeholder/test scaffold was explicitly requested and remains non-production.
- `VERIFIED_TEST`: applicable local compilation and deterministic verifiers passed without production connections.
- `READY_FOR_DEPLOYMENT_REVIEW`: implementation evidence is complete enough for a human deployment review; this does not authorize deployment.

Never label an artifact production-ready solely because it compiles or passes a fake runtime.

## Progress Updates

Keep updates brief and use this shape when it helps a beginner:

```text
向导进度：2/5 · 路由
当前路线：需求文档 → 技术设计 → 数据同步代码
已确认：30 张源表和目标映射
下一步：检查 rowkey 与周期分类
```

The final handoff must identify the route, status, artifacts, verification results, unresolved decisions, and next action. Avoid exposing internal skill mechanics unless they help the user act.

For a two-level contract, the Guide owns confirmation and dispatch coordination: show the count and mapping as a progress update, apply an audited evidence-backed decision under existing authorization or an explicit user merge/split decision, then use `scripts/build_code_unit_dispatch.py` to report ready and blocked units. Generate each ready unit independently; never collapse confirmed units because another unit is blocked.

Dispatch confirmed units with `codegen_route = data-sync-codegen` to the `data-sync-codegen` skill and units with `codegen_route = report-codegen` to the `report-codegen` skill.
