<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge 是一套带新手统一入口的数据管线开发工具集合。你可以使用一条龙向导完成从材料识别到验证交付，也可以直接调用职责独立的专业模块。

## 能力范围

- 为新手提供材料识别、路线选择、阻塞问题解释、生成和验证的一条龙向导。
- 从 DOCX（含内嵌 Excel）、Markdown、PDF 格式的 PRD/HLD 生成可会话修改的水线文档，支持 Markdown、交互式 HTML 和 PDF 输出。
- 从 PRD、DataEngine、DataHub、水线、COT、HBase、ClickHouse、Superview、报表类文档中抽取开发事实。
- 诊断 DataEngine/DataHub 同步任务和报表任务日志。
- 生成和审查可移植的 Python 数据同步项目代码，并逐表校验字段、调度形态、rowkey 与运行配置。
- 生成和审查可移植的 Python 报表管线项目代码；通用报表使用受限执行契约并完整校验输出与写入规则。
- 生成、填充和校验 DataHub/DataEngine Pipeline Export Excel 工作簿。
- 生成、转换、解析和审查数据库 DDL。

## 安装

添加公开的 GitHub Marketplace 源：

```powershell
codex plugin marketplace add bennyzbyen/pipeline-forge --ref v1.4.0
```

然后在支持的入口完成安装：

- Codex CLI：重启会话后输入 `/plugins`，选择 PipelineForge 来源并安装 `pipeline-forge`。
- ChatGPT 桌面端：重启应用，打开 **Plugins > Personal** 并安装 PipelineForge。

如果希望直接下载，也可以从 [PipelineForge 网站](https://pipeline-forge.bennyzby.chatgpt.site/downloads/pipeline-forge.zip)获取当前插件包，解压后在 `pipeline-forge` 文件夹中运行包内安装助手：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-pipeline-forge.ps1
```

安装助手只会把本插件复制到个人 Codex 插件目录，并保留个人 marketplace 文件中的其他插件条目。手动安装方式见 [INSTALL.md](INSTALL.md)。

## 仓库结构

```text
pipeline-forge/
  hidden metadata/      插件元数据
  assets/               LOGO 与图标资源
  skills/               独立工作流模块
  scripts/              仓库校验工具
```

## 模块说明

| 模块 | 适用场景 |
| --- | --- |
| `pipeline-forge-guide` | 从源文件开始，逐步完成路线选择、阻塞确认、生成和验证。 |
| `pipeline-doc-generator` | 基于 facts 生成或修改可审阅的水线文档，包含直接展示的表格和 Graphviz 流程图。 |
| `data-doc-to-dev-md` | 从需求文档抽取结构化事实和开发说明。 |
| `data-job-log-debugger` | 根据日志或截图诊断数据任务失败原因。 |
| `data-sync-codegen` | 生成或修改数据同步项目代码，并执行全表契约校验与运行时保护。 |
| `report-codegen` | 生成或修改专业/契约驱动的报表管线，并校验全部输出与写入规则。 |
| `pipeline-excel-builder` | 根据水线事实填充并校验 Pipeline Export Excel 工作簿。 |
| `db-ddl-generator-skill` | 为 MySQL、SQL Server、ClickHouse、PostgreSQL 生成或转换 DDL。 |

新手可以直接调用 `$pipeline-forge-guide`，或输入：`请带我从这些材料开始，一步步生成并验证交付物。`

## 校验

发布前运行仓库校验：

```powershell
python .\scripts\validate_package.py
```

如果需要更完整的本地检查，可以编译所有 Python 辅助脚本：

```powershell
Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }
```

## 版本记录

PipelineForge 遵循[语义化版本规则](VERSIONING.md)，当前稳定版本为 `1.4.0`。发布记录见 [CHANGELOG.md](CHANGELOG.md)。
