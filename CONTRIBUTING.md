# Contributing

Contributions are welcome when they keep PipelineForge focused, portable, and safe for data development work.

## Guidelines

- Keep each module focused on one workflow.
- Do not combine unrelated modules into a single large module.
- Keep examples free of real credentials, private hosts, tokens, app keys, or production data.
- Prefer deterministic scripts and local validation over environment-specific behavior.
- Use clear commit messages that describe the changed module.

## Versioning and Releases

PipelineForge uses Semantic Versioning. Read [VERSIONING.md](VERSIONING.md) before preparing a release. Do not carry `1.0.9` to `1.1.0` merely because PATCH reached 10; `1.0.10` is the correct next patch release.

Update every version source together and add the new release at the top of `CHANGELOG.md`. The package validator rejects invalid or inconsistent versions.

## Local Validation

```powershell
python .\scripts\validate_package.py
```

For Python helper changes:

```powershell
Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }
```
