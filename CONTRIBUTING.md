# Contributing

Contributions are welcome when they keep PipelineForge focused, portable, and safe for data development work.

## Guidelines

- Keep each module focused on one workflow.
- Do not combine unrelated modules into a single large module.
- Keep examples free of real credentials, private hosts, tokens, app keys, or production data.
- Prefer deterministic scripts and local validation over environment-specific behavior.
- Use clear commit messages that describe the changed module.

## Local Validation

```powershell
python .\scripts\validate_package.py
```

For Python helper changes:

```powershell
Get-ChildItem -LiteralPath 'skills' -Recurse -Filter '*.py' | ForEach-Object { python -m py_compile $_.FullName }
```
