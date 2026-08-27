# Repository Guidelines

## Repository Role And Layout

This repository packages and releases the PipelineForge Codex plugin. Plugin metadata lives in `.codex-plugin/`, packaged skills live in `skills/`, distribution scripts live in `scripts/`, and the companion website lives in `site_create/`.

For the coordinated maintainer workflow, keep this checkout beside `skill_lab`:

```text
D:\Benny\
├── skill_lab\          Source-of-truth skills
└── pipeline-forge\     Plugin packaging and releases
```

Treat `..\skill_lab\skills` as the source of truth. Use `..\skill_lab\sync_pipeline_forge.ps1` for a guarded one-way mirror and never copy packaged skills back into `skill_lab`.

## PipelineForge Director Workflow

The repository owner is the final authority. A session instructed to act as **PipelineForge Director** is the primary coordinator for work spanning this repository and the sibling `..\skill_lab` repository. Within the user's requested scope, the Director may inspect, plan, edit, validate, and delegate work, while retaining responsibility for integration, review, and the final result.

- Delegate only when the task benefits from independent or parallel work. Every sub-agent must use `gpt-5.6-sol` with reasoning effort `medium` or higher; choose `high` or `xhigh` when task difficulty warrants it. `xhigh` is the maximum allowed effort; do not select `max`. Do not silently downgrade the model or reasoning effort if that configuration is unavailable.
- Give each sub-agent a bounded task, explicit repository scope, acceptance criteria, and required validation. The Director must review sub-agent findings and shared-worktree changes before accepting them.
- Make skill implementation changes in `..\skill_lab` first. Run the relevant deterministic checks, then mirror with `..\skill_lab\sync_pipeline_forge.ps1`; never use this repository's packaged copies as an upstream source.
- Keep packaging, installer, release metadata, changelog, checksum, and website-only changes in this repository. When both repositories change, inspect both diffs, validate source/package parity, and use separate commits. This repository's commit must cite the exact source commit as `data_pipeline_develop_skills@<sha>`; use a shared Issue, PR, or Change-ID for bidirectional correlation instead of circular final-SHA references.
- Authority to coordinate the repositories does not expand a task beyond the user's request. Publishing, destructive operations, credential use, and other external or irreversible actions still require explicit authorization.

## Build And Validation Commands

- `python .\scripts\validate_package.py --source-root ..\skill_lab` validates metadata, versions, assets, helper syntax, and byte-level source parity.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_download_package.ps1` rebuilds the ignored installer ZIP and tracked SHA256 file.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_download_package.ps1` validates installation behavior in an isolated temporary home.
- `python .\scripts\test_archive_safety.py` runs malicious ZIP member regressions without extracting them.
- `python .\scripts\test_publish_validated_release.py` exercises release retry and conflict handling against an offline fake GitHub runner.
- `npm test` from `site_create` builds the companion site and runs rendered HTML tests.
- `npm run lint` from `site_create` runs ESLint.

## Source And Release Rules

Keep all seven packaged skills synchronized with `skill_lab`. Do not hand-edit a packaged skill when the same change belongs in the source repository. Update the plugin manifest, website package metadata, displayed version, changelog, tests, ZIP checksum, and other version sources together according to `VERSIONING.md`.

Use a short imperative subject. For non-trivial changes, include `Why`, `Validation`, and `Related` sections in the commit body. Cite the corresponding source commit as `data_pipeline_develop_skills@<sha>` whenever packaged skills or the cross-repository workflow changes. Before committing a release, run package validation with `--source-root`, rebuild and validate the download archive, and run the site tests. Keep user-visible release history in `CHANGELOG.md` and unresolved work in GitHub Issues; do not maintain a duplicate iteration log.

## Windows And Encoding

Assume Windows PowerShell unless another shell is explicitly confirmed. Read and write text as UTF-8. Quote paths using `-LiteralPath` when they contain spaces, Chinese characters, brackets, or `$`. Before changing source because a command failed, rule out shell syntax, quoting, working-directory, encoding, regex, and permission issues.

## Security

Keep credentials, private hosts, tokens, app keys, internal documents, logs, production samples, and environment-specific paths out of committed files and generated examples. Use placeholders for newly written connection values. Validation and regression scripts must not connect to Gateway, HBase, FS, ClickHouse, MSSQL, or production services.
