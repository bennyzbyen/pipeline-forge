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

## Build And Validation Commands

- `python .\scripts\validate_package.py --source-root ..\skill_lab` validates metadata, versions, assets, helper syntax, and byte-level source parity.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_download_package.ps1` rebuilds the ignored installer ZIP and tracked SHA256 file.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_download_package.ps1` validates installation behavior in an isolated temporary home.
- `npm test` from `site_create` builds the companion site and runs rendered HTML tests.
- `npm run lint` from `site_create` runs ESLint.

## Source And Release Rules

Keep all seven packaged skills synchronized with `skill_lab`. Do not hand-edit a packaged skill when the same change belongs in the source repository. Update the plugin manifest, website package metadata, displayed version, changelog, tests, ZIP checksum, and other version sources together according to `VERSIONING.md`.

Use a short imperative subject. For non-trivial changes, include `Why`, `Validation`, and `Related` sections in the commit body. Cite the corresponding source commit as `data_pipeline_develop_skills@<sha>` whenever packaged skills or the cross-repository workflow changes. Before committing a release, run package validation with `--source-root`, rebuild and validate the download archive, and run the site tests. Keep user-visible release history in `CHANGELOG.md` and unresolved work in GitHub Issues; do not maintain a duplicate iteration log.

## Windows And Encoding

Assume Windows PowerShell unless another shell is explicitly confirmed. Read and write text as UTF-8. Quote paths using `-LiteralPath` when they contain spaces, Chinese characters, brackets, or `$`. Before changing source because a command failed, rule out shell syntax, quoting, working-directory, encoding, regex, and permission issues.

## Security

Keep credentials, private hosts, tokens, app keys, internal documents, logs, production samples, and environment-specific paths out of committed files and generated examples. Use placeholders for newly written connection values. Validation and regression scripts must not connect to Gateway, HBase, FS, ClickHouse, MSSQL, or production services.
