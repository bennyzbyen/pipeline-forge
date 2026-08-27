<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge is a data pipeline development toolkit with a beginner-friendly front door and independent specialist modules. Use the guide for an end-to-end workflow or invoke a focused module directly.

## What It Covers

- Guided intake, routing, blocker handling, generation, and verification for beginners.
- Requirement document extraction for PRD, DataEngine, DataHub, waterline, COT, HBase, ClickHouse, Superview, and report documents.
- Job log diagnosis for DataEngine/DataHub synchronization and report jobs.
- Portable Python synchronization project generation with all-table contract verification and runtime guards.
- Portable Python report pipeline generation with bounded execution contracts and complete output/write verification.
- DataHub/DataEngine Pipeline Export workbook generation and validation.
- Database DDL generation, conversion, and review.

## Installation

Add the public GitHub marketplace source:

```powershell
codex plugin marketplace add bennyzbyen/pipeline-forge --ref v1.1.1
```

Then finish installation from either supported surface:

- Codex CLI: restart the session, enter `/plugins`, choose the PipelineForge source, and install `pipeline-forge`.
- ChatGPT desktop app: restart the app, open **Plugins > Personal**, and install PipelineForge.

For a direct download instead, get the current package from the [PipelineForge website](https://pipeline-forge.bennyzby.chatgpt.site/downloads/pipeline-forge.zip), extract it, and run the included setup helper from the extracted `pipeline-forge` folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-pipeline-forge.ps1
```

The helper copies only this plugin into your personal Codex plugin directory and preserves existing entries in your personal marketplace file. See [INSTALL.md](INSTALL.md) for the manual setup path.

## Repository Layout

```text
pipeline-forge/
  hidden metadata/      package metadata
  assets/               logo and icon assets
  skills/               independent workflow modules
  scripts/              repository validation utilities
```

## Modules

| Module | Use when you need to |
| --- | --- |
| `pipeline-forge-guide` | Move from source files to a verified safe deliverable with step-by-step guidance. |
| `data-doc-to-dev-md` | Extract structured facts and development notes from requirement documents. |
| `data-job-log-debugger` | Diagnose failed data jobs from logs or screenshots. |
| `data-sync-codegen` | Generate or revise synchronization code with all-table contract checks. |
| `report-codegen` | Generate specialized or contract-driven report code with output/write checks. |
| `pipeline-excel-builder` | Fill and validate Pipeline Export Excel workbooks from waterline facts. |
| `db-ddl-generator-skill` | Build or convert DDL for MySQL, SQL Server, ClickHouse, and PostgreSQL. |

Start the guided route with `$pipeline-forge-guide` or: `Guide me from these source files to a verified deliverable.`

## Validation

Run the package validator before publishing changes:

```powershell
python .\scripts\validate_package.py
```

For a deeper local check, compile every Python helper:

```powershell
Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }
```

## Release Notes

PipelineForge follows [Semantic Versioning](VERSIONING.md). The current stable version is `1.1.1`; see [CHANGELOG.md](CHANGELOG.md) for release notes.
