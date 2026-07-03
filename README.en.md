<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge is a data pipeline development toolkit built around independent, focused modules. Each module keeps a single responsibility and can be used alone or as part of a document-to-code workflow.

## What It Covers

- Requirement document extraction for PRD, DataEngine, DataHub, waterline, COT, HBase, ClickHouse, Superview, and report documents.
- Job log diagnosis for DataEngine/DataHub synchronization and report jobs.
- Portable Python synchronization project generation.
- Portable Python report pipeline generation.
- Database DDL generation, conversion, and review.

## Installation

Clone the repository into your local plugin folder:

```powershell
git clone https://github.com/bennyzbyen/pipeline-forge.git "$env:USERPROFILE\plugins\pipeline-forge"
```

Enable the local plugin in your desktop host. If your host uses a marketplace file, point it at the cloned `pipeline-forge` directory.

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
| `data-doc-to-dev-md` | Extract structured facts and development notes from requirement documents. |
| `data-job-log-debugger` | Diagnose failed data jobs from logs or screenshots. |
| `data-sync-codegen` | Generate or revise synchronization project code. |
| `report-codegen` | Generate or revise report pipeline project code. |
| `db-ddl-generator-skill` | Build or convert DDL for MySQL, SQL Server, ClickHouse, and PostgreSQL. |

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

See [CHANGELOG.md](CHANGELOG.md).
