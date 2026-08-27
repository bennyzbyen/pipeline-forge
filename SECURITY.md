# Security Policy

PipelineForge is designed to generate and review data development artifacts without requiring live service access.

## Reporting Issues

Please open a private report with the maintainer when you find a security issue. Do not publish secrets, internal hosts, tokens, app keys, passwords, logs, or production samples in public issues.

## Data Handling

- Do not commit private documents, production logs, credentials, tokens, or customer data.
- Keep generated examples generic unless a real project explicitly requires otherwise.
- Replace sensitive values with placeholders before sharing repro cases.

## Distribution Safety

- The release validator verifies the archive checksum and rejects unsafe member paths, duplicate or case-conflicting names, filesystem aliases, special files, and members outside the single `pipeline-forge/` root before extraction.
- The Windows installer serializes updates per Home directory with an operating-system-backed exclusive lock and rolls plugin plus marketplace state back together on failure.
- Release retries never silently replace a published release. Existing published assets must download byte-identically to the current validated build; draft releases reject unexpected assets before verified assets are uploaded and published.
