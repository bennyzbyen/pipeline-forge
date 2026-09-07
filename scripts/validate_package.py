#!/usr/bin/env python3
"""Validate the PipelineForge repository layout."""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from release_versions import (
    VersionError,
    validate_release_tag as require_matching_release_tag,
    validate_version_consistency as require_consistent_versions,
)


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/bennyzbyen/pipeline-forge"
REPOSITORY_GIT_URL = f"{REPOSITORY_URL}.git"
SOURCE_REPOSITORY_URL = "https://github.com/bennyzbyen/data_pipeline_develop_skills"
SOURCE_REVISION_PATH = ROOT / "SOURCE_REVISION"
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
REQUIRED_SKILLS = {
    "data-doc-to-dev-md",
    "data-job-log-debugger",
    "data-sync-codegen",
    "pipeline-excel-builder",
    "pipeline-doc-generator",
    "pipeline-forge-guide",
    "report-codegen",
    "db-ddl-generator-skill",
}
SOURCE_SKILLS = REQUIRED_SKILLS
GUIDE_REFERENCES = {
    "references/document-to-delivery.md",
    "references/specialized-routes.md",
    "references/beginner-questions.md",
}
GUIDE_STATUSES = {
    "BLOCKED_INPUT",
    "SAFE_SCAFFOLD",
    "VERIFIED_TEST",
    "READY_FOR_DEPLOYMENT_REVIEW",
}
CODEGEN_CONTRACT_FILES = {
    "data-doc-to-dev-md": {
        "scripts/technical_contract.py",
        "scripts/validate_technical_contract.py",
        "scripts/verify_technical_contract_regression.py",
    },
    "data-sync-codegen": {
        "scripts/verify_cot_manifest_semantics.py",
        "scripts/verify_cot_manifest_semantics_regression.py",
        "scripts/verify_cot_runtime_semantics.py",
    },
    "report-codegen": {
        "references/generic_execution_contract.md",
        "scripts/report_contract.py",
        "scripts/verify_generic_report_runtime_semantics.py",
        "scripts/verify_report_plan_semantics.py",
        "scripts/verify_qas_synthetic_acceptance.py",
    },
    "db-ddl-generator-skill": {
        "scripts/verify_clickhouse_deployment_profile.py",
    },
}


PIPELINE_DOC_RESOURCES = {
    "agents/openai.yaml",
    "scripts/extract_requirement_evidence.py",
    "scripts/pipeline_doc_authoring.py",
    "scripts/render_pipeline_doc.py",
    "scripts/render_pipeline_pdf.py",
    "scripts/pipeline_diagram_contract.py",
    "scripts/validate_pipeline_doc.py",
    "scripts/validate_pipeline_pdf.py",
    "scripts/verify_pipeline_doc_generator.py",
    "assets/facts.schema.json",
    "assets/flow-spec.schema.json",
    "assets/sync_template.md",
    "assets/report_template.md",
    "assets/diagram-viewer.js",
    "assets/diagram-viewer.css",
    "assets/diagram-viewer.html",
    "references/evidence-rules.md",
    "references/profiles.md",
    "references/facts-and-questions.md",
    "references/pdf-output.md",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_metadata_dir() -> Path:
    candidates = [
        path
        for path in ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith(".")
        and path.name.endswith("-plugin")
        and (path / "plugin.json").is_file()
    ]
    require(len(candidates) == 1, "expected exactly one plugin metadata directory")
    return candidates[0]


def validate_metadata() -> str:
    metadata_dir = find_metadata_dir()
    manifest = json.loads((metadata_dir / "plugin.json").read_text(encoding="utf-8"))
    require(manifest.get("name") == "pipeline-forge", "manifest name must be pipeline-forge")
    require(manifest.get("interface", {}).get("displayName") == "PipelineForge", "display name mismatch")
    require(manifest.get("skills") == "./skills/", "manifest skills path mismatch")
    require(manifest.get("repository") == REPOSITORY_URL, "manifest repository URL mismatch")
    require(manifest.get("license") == "MIT", "manifest license mismatch")
    require(manifest.get("interface", {}).get("websiteURL", "").startswith("https://"), "website URL must use HTTPS")
    version = manifest.get("version")
    require(isinstance(version, str) and SEMVER_PATTERN.fullmatch(version) is not None, "manifest version must be valid SemVer")
    return version


def validate_version_consistency(version: str) -> None:
    try:
        require_consistent_versions(ROOT, expected_version=version)
    except VersionError as exc:
        raise AssertionError(str(exc)) from exc


def validate_release_tag(version: str, release_tag: str) -> None:
    try:
        require_matching_release_tag(version, release_tag)
    except VersionError as exc:
        raise AssertionError(str(exc)) from exc


def validate_marketplace(version: str) -> None:
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    require(marketplace_path.is_file(), "missing repo marketplace manifest")
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    require(marketplace.get("name") == "pipeline-forge", "marketplace name mismatch")
    require(marketplace.get("interface", {}).get("displayName") == "PipelineForge", "marketplace display name mismatch")
    plugins = marketplace.get("plugins")
    require(isinstance(plugins, list) and len(plugins) == 1, "marketplace must expose exactly one plugin")
    entry = plugins[0]
    require(entry.get("name") == "pipeline-forge", "marketplace plugin name mismatch")
    source = entry.get("source", {})
    require(source.get("source") == "url", "root-hosted Git plugin must use url source")
    require(source.get("url") == REPOSITORY_GIT_URL, "marketplace repository URL mismatch")
    require(
        source.get("ref") == f"v{version}",
        "marketplace source ref must pin the immutable plugin version tag",
    )
    require(entry.get("policy", {}).get("installation") == "AVAILABLE", "marketplace installation policy mismatch")
    require(entry.get("policy", {}).get("authentication") == "ON_INSTALL", "marketplace authentication policy mismatch")
    require(entry.get("category") == "Productivity", "marketplace category mismatch")


def validate_assets() -> None:
    for relative in ["assets/logo.svg", "assets/logo.png", "assets/icon.png"]:
        require((ROOT / relative).is_file(), f"missing asset: {relative}")


def validate_distribution_files() -> None:
    for relative in [
        ".github/workflows/release.yml",
        "SOURCE_REVISION",
        "INSTALL.md",
        "CHANGELOG.md",
        "VERSIONING.md",
        "install-pipeline-forge.ps1",
        "scripts/build_download_package.ps1",
        "scripts/build_reproducible_zip.py",
        "scripts/bump_version.py",
        "scripts/publish_validated_release.py",
        "scripts/release_versions.py",
        "scripts/test_archive_safety.py",
        "scripts/test_installer_transaction.ps1",
        "scripts/test_publish_validated_release.py",
        "scripts/validate_archive_safety.py",
        "scripts/validate_download_package.ps1",
    ]:
        require((ROOT / relative).is_file(), f"missing distribution file: {relative}")
    install_text = (ROOT / "install-pipeline-forge.ps1").read_text(encoding="utf-8")
    require("./.codex/plugins/pipeline-forge" in install_text, "installer personal plugin path mismatch")
    require("Where-Object { $_.name -ne 'pipeline-forge' }" in install_text, "installer must preserve other plugin entries")
    require("[System.IO.FileShare]::None" in install_text, "installer must use an exclusive per-home lock")

    download_validator_text = (ROOT / "scripts/validate_download_package.ps1").read_text(
        encoding="utf-8"
    )
    safety_call = download_validator_text.find("validate_archive_safety.py")
    extraction_call = download_validator_text.find("Expand-Archive")
    require(safety_call >= 0, "download validator must invoke archive safety preflight")
    require(
        extraction_call > safety_call,
        "download validator must complete archive safety preflight before extraction",
    )

    release_workflow_text = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    require(
        "publish_validated_release.py" in release_workflow_text,
        "release workflow must use retry-safe validated asset publication",
    )
    require(
        "GITHUB_RUN_ATTEMPT" in release_workflow_text,
        "release workflow must isolate build assets by workflow attempt",
    )


def validate_source_revision() -> str:
    revision = SOURCE_REVISION_PATH.read_text(encoding="utf-8").strip()
    require(
        GIT_SHA_PATTERN.fullmatch(revision) is not None,
        "SOURCE_REVISION must contain exactly one full 40-character lowercase Git commit SHA",
    )
    return revision


def validate_skills() -> None:
    skills_root = ROOT / "skills"
    actual = {path.name for path in skills_root.iterdir() if path.is_dir()}
    require(actual == REQUIRED_SKILLS, f"packaged skill set mismatch: {sorted(actual ^ REQUIRED_SKILLS)}")
    for skill in sorted(REQUIRED_SKILLS):
        skill_md = skills_root / skill / "SKILL.md"
        require(skill_md.is_file(), f"missing SKILL.md for {skill}")
        text = skill_md.read_text(encoding="utf-8")
        require(text.startswith("---\n"), f"missing front matter for {skill}")
        require(f"name: {skill}" in text, f"front matter name mismatch for {skill}")


def relevant_files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def discover_source_repository(explicit_root: Optional[Path]) -> Optional[Path]:
    if explicit_root is not None:
        repository_root = explicit_root.expanduser().resolve()
        require((repository_root / "AGENTS.md").is_file(), f"source repository is missing AGENTS.md: {repository_root}")
        require((repository_root / "skills").is_dir(), f"source repository is missing skills/: {repository_root}")
        return repository_root

    candidates = [ROOT.parent / "skill_lab", ROOT.parents[1]]
    for repository_root in candidates:
        if (repository_root / "AGENTS.md").is_file() and (repository_root / "skills").is_dir():
            return repository_root.resolve()
    return None


def run_git(repository_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise AssertionError("git is required for strict source identity validation") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown git error").strip()
        raise AssertionError(f"unable to read source repository identity: {detail}") from exc
    return result.stdout.strip()


def validate_source_repository_identity(repository_root: Path, expected_revision: str) -> None:
    actual_revision = run_git(repository_root, "rev-parse", "HEAD").lower()
    origin_url = run_git(repository_root, "remote", "get-url", "origin").rstrip("/")
    normalized_origin_url = origin_url.removesuffix(".git")
    require(
        normalized_origin_url == SOURCE_REPOSITORY_URL,
        f"source repository origin mismatch: expected {SOURCE_REPOSITORY_URL}, found {origin_url}",
    )
    require(
        actual_revision == expected_revision,
        f"source repository revision mismatch: expected {expected_revision}, found {actual_revision}",
    )


def validate_clean_source_skills(repository_root: Path) -> None:
    status = run_git(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        "skills",
    )
    require(
        not status,
        f"source repository skills/ worktree must be clean:\n{status}",
    )

    tracked_output = run_git(repository_root, "ls-files", "-z", "--", "skills")
    tracked_files = {path for path in tracked_output.split("\0") if path}
    filesystem_files = {
        path.relative_to(repository_root).as_posix()
        for path in (repository_root / "skills").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    ignored_or_untracked = sorted(filesystem_files - tracked_files)
    require(
        not ignored_or_untracked,
        "source repository skills/ contains files not recorded by HEAD: "
        f"{ignored_or_untracked}",
    )


def validate_source_sync(
    explicit_root: Optional[Path],
    expected_revision: str,
    require_source_sync: bool,
) -> None:
    repository_root = discover_source_repository(explicit_root)
    if repository_root is None:
        require(
            not require_source_sync,
            "source repository is required; pass --source-root pointing to the pinned skill_lab checkout",
        )
        return

    if require_source_sync:
        validate_source_repository_identity(repository_root, expected_revision)
        validate_clean_source_skills(repository_root)
    source_root = repository_root / "skills"

    for skill in sorted(SOURCE_SKILLS):
        source_files = relevant_files(source_root / skill)
        packaged_files = relevant_files(ROOT / "skills" / skill)
        require(source_files.keys() == packaged_files.keys(), f"source/package file set mismatch for {skill}")
        changed = sorted(str(path) for path in source_files if source_files[path] != packaged_files[path])
        require(not changed, f"source/package content mismatch for {skill}: {changed}")


def validate_guide_contract() -> None:
    guide_root = ROOT / "skills" / "pipeline-forge-guide"
    guide_text = (guide_root / "SKILL.md").read_text(encoding="utf-8")
    for relative in sorted(GUIDE_REFERENCES):
        require((guide_root / relative).is_file(), f"missing guide reference: {relative}")
        require(relative in guide_text, f"guide entrypoint does not route to {relative}")
    for skill in sorted(REQUIRED_SKILLS - {"pipeline-forge-guide"}):
        require(skill in guide_text, f"guide entrypoint does not mention packaged route: {skill}")
    for status in sorted(GUIDE_STATUSES):
        require(status in guide_text, f"guide status contract is missing: {status}")


def validate_codegen_contract_tools() -> None:
    skills_root = ROOT / "skills"
    for skill, files in CODEGEN_CONTRACT_FILES.items():
        skill_text = (skills_root / skill / "SKILL.md").read_text(encoding="utf-8")
        for relative in sorted(files):
            require((skills_root / skill / relative).is_file(), f"missing {skill} contract tool: {relative}")
            if Path(relative).name not in {"report_contract.py", "technical_contract.py"}:
                require(relative in skill_text or Path(relative).name in skill_text, f"{skill} does not route to {relative}")
    guide_route = (skills_root / "pipeline-forge-guide" / "references" / "document-to-delivery.md").read_text(encoding="utf-8")
    require("verify_cot_manifest_semantics.py" in guide_route, "guide omits all-table sync verification")
    require("verify_report_plan_semantics.py" in guide_route, "guide omits all-output report verification")


def validate_python_helpers() -> None:
    for path in sorted((ROOT / "skills").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)


def validate_pipeline_doc_resources() -> None:
    skill_root = ROOT / "skills" / "pipeline-doc-generator"
    for relative in sorted(PIPELINE_DOC_RESOURCES):
        require((skill_root / relative).is_file(), f"missing pipeline-doc-generator resource: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Optional skill_lab repository path for byte-level source/package parity validation.",
    )
    parser.add_argument(
        "--require-source-sync",
        action="store_true",
        help=(
            "Require the source repository, verify that its HEAD matches SOURCE_REVISION, "
            "reject changes under source skills/, and enforce byte-level skill parity. "
            "Intended for release validation."
        ),
    )
    parser.add_argument(
        "--release-tag",
        help="Require this v-prefixed release tag to exactly match manifest and changelog versions.",
    )
    args = parser.parse_args()
    version = validate_metadata()
    validate_version_consistency(version)
    if args.release_tag:
        validate_release_tag(version, args.release_tag)
    validate_marketplace(version)
    validate_assets()
    validate_distribution_files()
    source_revision = validate_source_revision()
    validate_skills()
    validate_source_sync(args.source_root, source_revision, args.require_source_sync)
    validate_guide_contract()
    validate_codegen_contract_tools()
    validate_pipeline_doc_resources()
    validate_python_helpers()
    print("PipelineForge package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
