# Versioning

PipelineForge uses [Semantic Versioning](https://semver.org/) in the form `MAJOR.MINOR.PATCH`. The current stable version is `1.1.0`.

## Increment Rules

- Increment PATCH for backward-compatible fixes, documentation updates, prompt refinements, and internal maintenance: `1.1.0` to `1.1.1`.
- Increment MINOR for backward-compatible features, new skills, or newly supported workflows: `1.1.1` to `1.2.0`.
- Increment MAJOR for incompatible changes to plugin structure, configuration, public workflows, or supported contracts: `1.8.4` to `2.0.0`.
- Use prerelease identifiers for test releases: `1.1.0-beta.1`.

Version components do not use decimal carrying. For example, the patch release after `1.0.9` is `1.0.10`, not `1.1.0`.

## Release Checklist

1. Classify the release by compatibility and choose the next version.
2. Mirror the finalized skills from `data_pipeline_develop_skills`, then write that repository's full 40-character commit SHA to `SOURCE_REVISION`.
3. Update `.codex-plugin/plugin.json`, `site_create/package.json`, the root entries in `site_create/package-lock.json`, `site_create/lib/site-content.ts`, and the website version assertion.
4. Add the release at the top of `CHANGELOG.md`.
5. Run `python .\scripts\validate_package.py --source-root ..\skill_lab --require-source-sync` so the pinned source revision, a clean `skills/` worktree, and packaged skill bytes are all enforced. Changes outside `skills/` do not block this release check.
6. Rebuild and validate the downloadable archive with `scripts/build_download_package.ps1` and `scripts/validate_download_package.ps1`; the validator must use the generated `.sha256` file.
7. Run the website tests and lint before publishing.
