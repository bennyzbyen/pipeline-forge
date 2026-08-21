#!/usr/bin/env python3
"""Validate the PipelineForge repository layout."""

from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/bennyzbyen/pipeline-forge"
REPOSITORY_GIT_URL = f"{REPOSITORY_URL}.git"
REQUIRED_SKILLS = {
    "data-doc-to-dev-md",
    "data-job-log-debugger",
    "data-sync-codegen",
    "pipeline-excel-builder",
    "pipeline-forge-guide",
    "report-codegen",
    "db-ddl-generator-skill",
}
SOURCE_SKILLS = REQUIRED_SKILLS - {"db-ddl-generator-skill"}
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
    "data-sync-codegen": {
        "scripts/verify_cot_manifest_semantics.py",
        "scripts/verify_cot_manifest_semantics_regression.py",
    },
    "report-codegen": {
        "references/generic_execution_contract.md",
        "scripts/report_contract.py",
        "scripts/verify_generic_report_runtime_semantics.py",
        "scripts/verify_report_plan_semantics.py",
    },
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


def validate_metadata() -> None:
    metadata_dir = find_metadata_dir()
    manifest = json.loads((metadata_dir / "plugin.json").read_text(encoding="utf-8"))
    require(manifest.get("name") == "pipeline-forge", "manifest name must be pipeline-forge")
    require(manifest.get("interface", {}).get("displayName") == "PipelineForge", "display name mismatch")
    require(manifest.get("skills") == "./skills/", "manifest skills path mismatch")
    require(manifest.get("repository") == REPOSITORY_URL, "manifest repository URL mismatch")
    require(manifest.get("license") == "MIT", "manifest license mismatch")
    require(manifest.get("interface", {}).get("websiteURL", "").startswith("https://"), "website URL must use HTTPS")


def validate_marketplace() -> None:
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
    require(source.get("ref") == "main", "marketplace must track main")
    require(entry.get("policy", {}).get("installation") == "AVAILABLE", "marketplace installation policy mismatch")
    require(entry.get("policy", {}).get("authentication") == "ON_INSTALL", "marketplace authentication policy mismatch")
    require(entry.get("category") == "Productivity", "marketplace category mismatch")


def validate_assets() -> None:
    for relative in ["assets/logo.svg", "assets/logo.png", "assets/icon.png"]:
        require((ROOT / relative).is_file(), f"missing asset: {relative}")


def validate_distribution_files() -> None:
    for relative in [
        "INSTALL.md",
        "install-pipeline-forge.ps1",
        "scripts/build_download_package.ps1",
        "scripts/validate_download_package.ps1",
    ]:
        require((ROOT / relative).is_file(), f"missing distribution file: {relative}")
    install_text = (ROOT / "install-pipeline-forge.ps1").read_text(encoding="utf-8")
    require("./.codex/plugins/pipeline-forge" in install_text, "installer personal plugin path mismatch")
    require("Where-Object { $_.name -ne 'pipeline-forge' }" in install_text, "installer must preserve other plugin entries")


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


def validate_source_sync() -> None:
    repository_root = ROOT.parents[1]
    source_root = repository_root / "skills"
    if not (repository_root / "AGENTS.md").is_file() or not source_root.is_dir():
        return

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
            if Path(relative).name != "report_contract.py":
                require(relative in skill_text or Path(relative).name in skill_text, f"{skill} does not route to {relative}")
    guide_route = (skills_root / "pipeline-forge-guide" / "references" / "document-to-delivery.md").read_text(encoding="utf-8")
    require("verify_cot_manifest_semantics.py" in guide_route, "guide omits all-table sync verification")
    require("verify_report_plan_semantics.py" in guide_route, "guide omits all-output report verification")


def validate_python_helpers() -> None:
    for path in sorted((ROOT / "skills").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)


def main() -> int:
    validate_metadata()
    validate_marketplace()
    validate_assets()
    validate_distribution_files()
    validate_skills()
    validate_source_sync()
    validate_guide_contract()
    validate_codegen_contract_tools()
    validate_python_helpers()
    print("PipelineForge package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
