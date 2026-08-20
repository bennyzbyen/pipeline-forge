<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge is a guided, modular toolkit for data pipeline development: one-stop beginner routing, requirement document extraction, job log diagnosis, synchronization project generation, report pipeline generation, Pipeline Export workbook generation, and database DDL generation.

## Languages

- [English](README.en.md)
- [简体中文](README.zh-CN.md)

## Module Overview

| Module | Purpose |
| --- | --- |
| `pipeline-forge-guide` | Guide beginners from source files through routing, blocker handling, generation, and verification. |
| `data-doc-to-dev-md` | Convert requirement documents into implementation-ready development notes. |
| `data-job-log-debugger` | Diagnose DataEngine/DataHub job logs and failure evidence. |
| `data-sync-codegen` | Generate portable synchronization projects with all-table contract verification and runtime guards. |
| `report-codegen` | Generate specialized or contract-driven report projects with output/write verification. |
| `pipeline-excel-builder` | Generate, fill, and validate DataHub/DataEngine Pipeline Export workbooks. |
| `db-ddl-generator-skill` | Generate, parse, convert, and review database DDL. |

## Quick Start

```powershell
git clone https://github.com/bennyzbyen/pipeline-forge.git "$env:USERPROFILE\plugins\pipeline-forge"
```

Then install or enable the local plugin from your desktop host.

For a guided workflow, invoke `$pipeline-forge-guide` or start with: `Guide me from these source files to a verified deliverable.`

## Quality Checks

```powershell
python .\scripts\validate_package.py
```

The validator checks package metadata, required modules, logo assets, and Python helper syntax.

## License

Released under the [MIT License](LICENSE).
