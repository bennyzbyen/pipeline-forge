# Contributing

Contributions are welcome when they keep PipelineForge focused, portable, and safe for data development work.

## Guidelines

- Keep each module focused on one workflow.
- Do not combine unrelated modules into a single large module.
- Keep examples free of real credentials, private hosts, tokens, app keys, or production data.
- Prefer deterministic scripts and local validation over environment-specific behavior.
- Use a short imperative commit subject. For non-trivial changes, add `Why`, `Validation`, and `Related` sections; cite the corresponding source commit as `data_pipeline_develop_skills@<sha>` when both repositories change.

## Versioning and Releases

PipelineForge uses Semantic Versioning. Read [VERSIONING.md](VERSIONING.md) before preparing a release. Do not carry `1.0.9` to `1.1.0` merely because PATCH reached 10; `1.0.10` is the correct next patch release.

Update every version source together and add the new release at the top of `CHANGELOG.md`. The package validator rejects invalid or inconsistent versions.

Use Git commits and pull requests as the engineering record, `CHANGELOG.md` for user-visible releases, and GitHub Issues for unresolved work. Do not create a second iteration log in this repository.

## Local Validation

For maintainers of both repositories, use sibling checkouts so skill source and plugin packaging remain independent:

```text
D:\Benny\
├── skill_lab\
└── pipeline-forge\
```

Treat `skill_lab\skills` as the source of truth. Mirror only from `skill_lab` into this repository; never copy packaged skills back into the source repository.

From `skill_lab`, preview or run the guarded mirror:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sync_pipeline_forge.ps1
```

From this repository, validate the package and byte-level source parity explicitly:

```powershell
python .\scripts\validate_package.py --source-root ..\skill_lab
```

Standalone plugin clones can omit `--source-root`; package-internal validation still runs.

```powershell
python .\scripts\validate_package.py
```

For Python helper changes:

```powershell
Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }
```
