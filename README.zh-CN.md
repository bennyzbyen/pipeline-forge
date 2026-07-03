<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge 是一套面向数据管线开发的模块化工具集合。每个模块保持独立职责，可以单独使用，也可以组合成从需求文档到开发实现的工作流。

## 能力范围

- 从 PRD、DataEngine、DataHub、水线、COT、HBase、ClickHouse、Superview、报表类文档中抽取开发事实。
- 诊断 DataEngine/DataHub 同步任务和报表任务日志。
- 生成和审查可移植的 Python 数据同步项目代码。
- 生成和审查可移植的 Python 报表管线项目代码。
- 生成、转换、解析和审查数据库 DDL。

## 安装

将仓库克隆到本地插件目录：

```powershell
git clone https://github.com/bennyzbyen/pipeline-forge.git "$env:USERPROFILE\plugins\pipeline-forge"
```

然后在你的桌面宿主程序中启用这个本地插件。如果宿主程序使用 marketplace 文件，请让条目指向克隆后的 `pipeline-forge` 目录。

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
| `data-doc-to-dev-md` | 从需求文档抽取结构化事实和开发说明。 |
| `data-job-log-debugger` | 根据日志或截图诊断数据任务失败原因。 |
| `data-sync-codegen` | 生成或修改数据同步项目代码。 |
| `report-codegen` | 生成或修改报表管线项目代码。 |
| `db-ddl-generator-skill` | 为 MySQL、SQL Server、ClickHouse、PostgreSQL 生成或转换 DDL。 |

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

见 [CHANGELOG.md](CHANGELOG.md)。
