# Versioning

PipelineForge uses [Semantic Versioning](https://semver.org/) in the form `MAJOR.MINOR.PATCH`. The current stable version is `2.0.1`.

## Increment Rules

- Increment PATCH for backward-compatible fixes, documentation updates, prompt refinements, and internal maintenance: `1.1.0` to `1.1.1`.
- Increment MINOR for backward-compatible features, new skills, or newly supported workflows: `1.1.1` to `1.2.0`.
- Increment MAJOR for incompatible changes to plugin structure, configuration, public workflows, or supported contracts: `1.8.4` to `2.0.0`.
- Use prerelease identifiers for test releases: `1.1.0-beta.1`.

Version components do not use decimal carrying. For example, the patch release after `1.0.9` is `1.0.10`, not `1.1.0`.

## Release Checklist

1. Classify the release by compatibility and choose the next version.
2. Mirror the finalized skills from `data_pipeline_develop_skills`, then write that repository's full 40-character commit SHA to `SOURCE_REVISION`.
3. Run `python .\scripts\bump_version.py <version> --date <YYYY-MM-DD> --note <release-note>` (repeat `--note` for multiple bullets). Preview it first with `--dry-run`; do not hand-edit the version sources independently.
4. Run `python .\scripts\bump_version.py --check` to verify the manifest, website metadata and display, version documents, and latest `CHANGELOG.md` release agree.
5. Run `python .\scripts\validate_package.py --source-root ..\skill_lab --require-source-sync` so the pinned source revision, a clean `skills/` worktree, and packaged skill bytes are all enforced. Changes outside `skills/` do not block this release check.
6. Rebuild the downloadable archive twice with `scripts/build_download_package.ps1`, require identical SHA-256 values, and validate one archive with `scripts/validate_download_package.ps1`; the validator must use that build's generated `.sha256` file and complete member-path/type safety checks before extraction.
7. Run the website tests and lint before publishing.
8. Create a `v<version>` tag. The release workflow rejects any tag that does not exactly match both the manifest and latest changelog version, then publishes only the ZIP and checksum produced and validated in that workflow attempt. A retry may resume a draft or accept an already-published release only when its downloaded assets are byte-identical; unexpected or conflicting assets fail safely.
