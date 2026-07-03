<p align="center">
  <img src="assets/logo.svg" alt="PipelineForge logo" width="168">
</p>

# PipelineForge

PipelineForge is a modular toolkit for data pipeline development: requirement document extraction, job log diagnosis, synchronization project generation, report pipeline generation, and database DDL generation.

## Languages

- [English](README.en.md)
- [简体中文](README.zh-CN.md)

## Module Overview

| Module | Purpose |
| --- | --- |
| `data-doc-to-dev-md` | Convert requirement documents into implementation-ready development notes. |
| `data-job-log-debugger` | Diagnose DataEngine/DataHub job logs and failure evidence. |
| `data-sync-codegen` | Generate and review portable synchronization project code. |
| `report-codegen` | Generate and review report pipeline project code. |
| `db-ddl-generator-skill` | Generate, parse, convert, and review database DDL. |

## Quick Start

```powershell
git clone https://github.com/bennyzbyen/pipeline-forge.git "$env:USERPROFILE\plugins\pipeline-forge"
```

Then install or enable the local plugin from your desktop host.

## Quality Checks

```powershell
python .\scripts\validate_package.py
```

The validator checks package metadata, required modules, logo assets, and Python helper syntax.

## License

Released under the [MIT License](LICENSE).
