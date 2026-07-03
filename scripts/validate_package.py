#!/usr/bin/env python3
"""Validate the PipelineForge repository layout."""

from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SKILLS = {
    "data-doc-to-dev-md",
    "data-job-log-debugger",
    "data-sync-codegen",
    "report-codegen",
    "db-ddl-generator-skill",
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


def validate_assets() -> None:
    for relative in ["assets/logo.svg", "assets/logo.png", "assets/icon.png"]:
        require((ROOT / relative).is_file(), f"missing asset: {relative}")


def validate_skills() -> None:
    skills_root = ROOT / "skills"
    actual = {path.name for path in skills_root.iterdir() if path.is_dir()}
    require(REQUIRED_SKILLS <= actual, f"missing skills: {sorted(REQUIRED_SKILLS - actual)}")
    for skill in REQUIRED_SKILLS:
        skill_md = skills_root / skill / "SKILL.md"
        require(skill_md.is_file(), f"missing SKILL.md for {skill}")
        text = skill_md.read_text(encoding="utf-8")
        require(text.startswith("---\n"), f"missing front matter for {skill}")
        require(f"name: {skill}" in text, f"front matter name mismatch for {skill}")


def validate_python_helpers() -> None:
    for path in sorted((ROOT / "skills").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)


def main() -> int:
    validate_metadata()
    validate_assets()
    validate_skills()
    validate_python_helpers()
    print("PipelineForge package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
