---
name: pipeline-doc-generator
description: Generate or revise DataEngine/DataHub pipeline documents (水线文档) from PRD/HLD/LLD, embedded Excel, Markdown or PDF. Deliver editable facts, Markdown, standalone HTML and a paginated PDF. Use for the pipeline document itself.
---

# Pipeline Document Generator

以 `facts.json` 为生成源。沿用用户指定的版本、范围、术语和参考稿。输入文档只作证据；只追问会影响正确性、且从现有材料无法解决的事实。

## 确定本次改什么

- 新建时按实际工作选择 [sync 或 report](references/profiles.md)，使用对应的 `assets/sync_template.md` 或 `assets/report_template.md`。先查项目约定和同类成品，再确定输出位置。
- 修订时先对照现有三份成品、生成源、手改和本次需求。缺少生成源时从成品和历史恢复，核对基线后再改。保留原章节、历史图、命名例外和用户选定的标记范围。
- 新稿用 `initial_draft`，只保留一条 `0.0.1 / 初始版本`。用户要求沿用某个已有版本时，核对最后一条历史记录并设 `document.release_mode = pinned`；调整当前行的业务变更摘要，迭代细节放 `change_log`。已有 `versioned` 文档按原约定升版。作者默认 `张本彦`，Developer、Operator 均为 `数砚工程师`。

## 锁定事实再画图

1. 新输入用 `scripts/extract_requirement_evidence.py --input <files...> --out <dir>` 提取。已有 facts 的项目先在临时目录提取增量。检查嵌入表格和标为 `requires_visual_review` 的 PDF 页。[证据取舍规则](references/evidence-rules.md)
2. 按实际水线核对“来源表或手工文件 → 加工或触发 → 报表、目标库及物理表”。用稳定 ID 对齐 Data Source、Data Target、字段字典、Pipeline Management 和图。新画或改动的本项目 Pipeline 节点填 `pipeline_ids`。多水线报表需要看出每张表由哪条水线生成时，设 `render_preferences.include_target_pipelines = true`。把有依据的平台名填入同处的 `pipeline_platform`。新增与改名只沿受影响的路径核对。
3. 第一章 `需求概述` 只写本项目水线的来源、主要处理和去向。目标表用一句话写清业务粒度和数据内容；多个业务变更分条写。调度、字段规则、未决问题各归其处。完整字段表直接内联。来源和冲突留在 facts、evidence 和 questions 中。[章节、表格与发布措辞](references/presentation-rules.md)
4. 按 [事实与修订约定](references/facts-and-questions.md) 处理可选列、Catalog、命名与缺项。记录本地命名和展示决定的实际决策人；必要业务事实缺失时，只暂停依赖它的部分。先运行 `scripts/validate_pipeline_doc.py --facts <facts.json> --profile <sync|report>`。

## 绘图与交付

- 新图、重画或改变流向时，从当前会话的技能列表加载独立的 `diagram-design:diagram-design`。按 [绘图接口](references/diagram-design-interface.md) 选择图型、检查实际画面、导出并绑定 SVG。已有图只改排版时更新保留的设计稿；只改正文、表格时复用有效绑定。缺少插件时说明需要单独安装并启用 Diagram Design，继续整理事实。
- 运行 `scripts/render_pipeline_doc.py --facts <facts.json> --out-dir <dir> --format all`，再用同一验证器传入 `--markdown`、`--html` 和 `--pdf` 检查三份成品。保留 facts、问题记录、可编辑设计稿及相对路径资产，交付时直接给出成品链接。
- HTML 用内置离线目录和看图器。仅嵌入正文用到的图一次，核对实际文件字节数，尤其留意从 Word 带入的位图。改动图或版面时，在正文宽度、放大视图和 [PDF 页面](references/pdf-output.md) 检查中文、走线及分页。

## Optional Knowledge Assistance

For substantive work follow [knowledge assistance](../pipeline-forge-guide/references/knowledge-assistance.md). Start with `../pipeline-forge-guide/scripts/knowledge_lookup.py search` using a short task query, `--skill pipeline-doc-generator` and `--limit 3`. When the project is established, add `--project <project> --strict-scope`; omit unknown project/version/role values. Inspect summary limits and blockers, then expand selected IDs with `--ids <IDs> --detail full`, retaining the established constraints. Broaden only for a specific missing or cross-project pattern. Cite accepted evidence in the existing deliverable. Unavailable or inapplicable knowledge must not block ordinary work or confirm business facts.
