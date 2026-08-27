#!/usr/bin/env python3
"""Read, validate, and update PipelineForge's authoritative version sources."""

from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
AUTHORITY_PATHS = (
    Path(".agents/plugins/marketplace.json"),
    Path(".codex-plugin/plugin.json"),
    Path("site_create/package.json"),
    Path("site_create/package-lock.json"),
    Path("site_create/lib/site-content.ts"),
    Path("VERSIONING.md"),
    Path("README.md"),
    Path("README.en.md"),
    Path("README.zh-CN.md"),
    Path("INSTALL.md"),
    Path("CHANGELOG.md"),
)
TEXT_VERSION_PATTERNS = {
    Path("site_create/lib/site-content.ts"): re.compile(
        r'(?P<prefix>export const PLUGIN_VERSION = ")(?P<version>[^"]+)(?P<suffix>";)'
    ),
    Path("VERSIONING.md"): re.compile(
        r"(?P<prefix>The current stable version is `)(?P<version>[^`]+)(?P<suffix>`\.)"
    ),
    Path("README.md"): re.compile(
        r"(?P<prefix>The current stable version is `)(?P<version>[^`]+)(?P<suffix>`\.)"
    ),
    Path("README.en.md"): re.compile(
        r"(?P<prefix>The current stable version is `)(?P<version>[^`]+)(?P<suffix>`;)"
    ),
    Path("README.zh-CN.md"): re.compile(
        r"(?P<prefix>当前稳定版本为 `)(?P<version>[^`]+)(?P<suffix>`。)"
    ),
}
CHANGELOG_HEADING_PATTERN = re.compile(
    r"^## (?P<version>[^\s]+)(?:\s+-\s+\d{4}-\d{2}-\d{2})?$",
    flags=re.MULTILINE,
)
MARKETPLACE_COMMAND_PATTERN = re.compile(
    r"(?P<prefix>codex plugin marketplace add bennyzbyen/pipeline-forge --ref )"
    r"(?P<version>[^\s\"`]+)(?P<suffix>)"
)
MARKETPLACE_COMMAND_PATHS = (
    Path("site_create/lib/site-content.ts"),
    Path("INSTALL.md"),
    Path("README.md"),
    Path("README.en.md"),
    Path("README.zh-CN.md"),
)


class VersionError(ValueError):
    """Raised when release versions are invalid or inconsistent."""


def parse_semver(version: str) -> tuple[int, int, int, tuple[str, ...] | None]:
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise VersionError(f"invalid Semantic Version: {version}")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else None
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def compare_semver(left: str, right: str) -> int:
    """Compare SemVer precedence, ignoring build metadata as required by SemVer."""
    left_major, left_minor, left_patch, left_pre = parse_semver(left)
    right_major, right_minor, right_patch, right_pre = parse_semver(right)
    left_core = (left_major, left_minor, left_patch)
    right_core = (right_major, right_minor, right_patch)
    if left_core != right_core:
        return 1 if left_core > right_core else -1
    if left_pre is None or right_pre is None:
        if left_pre is right_pre:
            return 0
        return 1 if left_pre is None else -1

    for left_identifier, right_identifier in zip(left_pre, right_pre):
        if left_identifier == right_identifier:
            continue
        left_numeric = left_identifier.isdigit()
        right_numeric = right_identifier.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_identifier) > int(right_identifier) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_identifier > right_identifier else -1
    if len(left_pre) == len(right_pre):
        return 0
    return 1 if len(left_pre) > len(right_pre) else -1


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionError(f"unable to read version JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VersionError(f"expected a JSON object in {path}")
    return value


def _match_text_version(root: Path, relative_path: Path, pattern: re.Pattern[str]) -> str:
    text = (root / relative_path).read_text(encoding="utf-8")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise VersionError(f"expected exactly one authoritative version in {relative_path}")
    return matches[0].group("version")


def read_authoritative_versions(root: Path = ROOT) -> dict[str, str]:
    root = root.resolve()
    marketplace = _read_json(root / ".agents/plugins/marketplace.json")
    manifest = _read_json(root / ".codex-plugin/plugin.json")
    package = _read_json(root / "site_create/package.json")
    lock = _read_json(root / "site_create/package-lock.json")
    lock_root = lock.get("packages", {}).get("")
    if not isinstance(lock_root, dict):
        raise VersionError("website lockfile is missing packages[''] metadata")
    marketplace_plugins = marketplace.get("plugins")
    if (
        not isinstance(marketplace_plugins, list)
        or len(marketplace_plugins) != 1
        or not isinstance(marketplace_plugins[0], dict)
        or not isinstance(marketplace_plugins[0].get("source"), dict)
    ):
        raise VersionError("marketplace must contain exactly one plugin source")
    marketplace_ref = str(marketplace_plugins[0]["source"].get("ref", ""))
    if not marketplace_ref.startswith("v"):
        raise VersionError("marketplace source ref must use a v-prefixed immutable version tag")

    versions = {
        "marketplace source ref": marketplace_ref.removeprefix("v"),
        "plugin manifest": str(manifest.get("version", "")),
        "website package": str(package.get("version", "")),
        "website lockfile": str(lock.get("version", "")),
        "website lockfile root package": str(lock_root.get("version", "")),
    }
    for relative_path, pattern in TEXT_VERSION_PATTERNS.items():
        versions[relative_path.as_posix()] = _match_text_version(root, relative_path, pattern)
    for relative_path in MARKETPLACE_COMMAND_PATHS:
        marketplace_command_ref = _match_text_version(
            root, relative_path, MARKETPLACE_COMMAND_PATTERN
        )
        if not marketplace_command_ref.startswith("v"):
            raise VersionError(
                f"marketplace install command in {relative_path} must pin a v-prefixed tag"
            )
        versions[f"{relative_path.as_posix()} marketplace ref"] = marketplace_command_ref.removeprefix("v")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = CHANGELOG_HEADING_PATTERN.search(changelog)
    if heading is None:
        raise VersionError("CHANGELOG.md has no release heading")
    versions["CHANGELOG.md latest release"] = heading.group("version")
    return versions


def validate_version_consistency(root: Path = ROOT, expected_version: str | None = None) -> str:
    versions = read_authoritative_versions(root)
    manifest_version = versions["plugin manifest"]
    parse_semver(manifest_version)
    expected = expected_version or manifest_version
    parse_semver(expected)
    mismatches = {label: version for label, version in versions.items() if version != expected}
    if mismatches:
        detail = ", ".join(f"{label}={value!r}" for label, value in mismatches.items())
        raise VersionError(f"authoritative versions must all equal {expected!r}: {detail}")
    return expected


def validate_release_tag(version: str, tag: str) -> None:
    normalized_tag = tag.removeprefix("refs/tags/")
    expected_tag = f"v{version}"
    if normalized_tag != expected_tag:
        raise VersionError(
            "release tag must exactly match manifest and changelog version: "
            f"expected {expected_tag!r}, found {normalized_tag!r}"
        )


def _replace_text_version(text: str, pattern: re.Pattern[str], new_version: str, label: str) -> str:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise VersionError(f"expected exactly one authoritative version in {label}")
    return pattern.sub(
        lambda match: f"{match.group('prefix')}{new_version}{match.group('suffix')}",
        text,
        count=1,
    )


def prepare_bump(root: Path, new_version: str, release_date: str, notes: list[str]) -> dict[Path, str]:
    root = root.resolve()
    current_version = validate_version_consistency(root)
    parse_semver(new_version)
    if compare_semver(new_version, current_version) <= 0:
        raise VersionError(
            f"new version must have higher SemVer precedence than {current_version}: {new_version}"
        )
    try:
        dt.date.fromisoformat(release_date)
    except ValueError as exc:
        raise VersionError(f"release date must use YYYY-MM-DD: {release_date}") from exc
    clean_notes = [note.strip() for note in notes]
    if not clean_notes or any(not note or "\n" in note or "\r" in note for note in clean_notes):
        raise VersionError("provide at least one non-empty, single-line --note")

    updates: dict[Path, str] = {}
    marketplace_path = root / ".agents/plugins/marketplace.json"
    marketplace = _read_json(marketplace_path)
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        raise VersionError("marketplace must contain exactly one plugin entry")
    source = plugins[0].get("source")
    if not isinstance(source, dict):
        raise VersionError("marketplace plugin source is missing")
    source["ref"] = f"v{new_version}"
    updates[marketplace_path] = json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n"

    manifest_path = root / ".codex-plugin/plugin.json"
    manifest = _read_json(manifest_path)
    manifest["version"] = new_version
    updates[manifest_path] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    package_path = root / "site_create/package.json"
    package = _read_json(package_path)
    package["version"] = new_version
    updates[package_path] = json.dumps(package, ensure_ascii=False, indent=2) + "\n"

    lock_path = root / "site_create/package-lock.json"
    lock = _read_json(lock_path)
    lock["version"] = new_version
    lock_root = lock.get("packages", {}).get("")
    if not isinstance(lock_root, dict):
        raise VersionError("website lockfile is missing packages[''] metadata")
    lock_root["version"] = new_version
    updates[lock_path] = json.dumps(lock, ensure_ascii=False, indent=2) + "\n"

    for relative_path, pattern in TEXT_VERSION_PATTERNS.items():
        path = root / relative_path
        updates[path] = _replace_text_version(
            path.read_text(encoding="utf-8"), pattern, new_version, relative_path.as_posix()
        )
    for relative_path in MARKETPLACE_COMMAND_PATHS:
        path = root / relative_path
        source_text = updates.get(path, path.read_text(encoding="utf-8"))
        updates[path] = _replace_text_version(
            source_text,
            MARKETPLACE_COMMAND_PATTERN,
            f"v{new_version}",
            f"{relative_path.as_posix()} marketplace ref",
        )

    changelog_path = root / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    prefix = "# Changelog\n\n"
    if not changelog.startswith(prefix):
        raise VersionError("CHANGELOG.md must start with '# Changelog' followed by a blank line")
    note_block = "\n".join(f"- {note}" for note in clean_notes)
    release_block = f"## {new_version} - {release_date}\n\n{note_block}\n\n"
    updates[changelog_path] = prefix + release_block + changelog[len(prefix) :]
    return updates


def apply_bump(
    root: Path,
    new_version: str,
    release_date: str,
    notes: list[str],
    *,
    dry_run: bool = False,
    output: TextIO = sys.stdout,
) -> list[Path]:
    root = root.resolve()
    updates = prepare_bump(root, new_version, release_date, notes)
    if dry_run:
        for path, updated_text in updates.items():
            original_text = path.read_text(encoding="utf-8")
            relative_path = path.relative_to(root).as_posix()
            output.writelines(
                difflib.unified_diff(
                    original_text.splitlines(keepends=True),
                    updated_text.splitlines(keepends=True),
                    fromfile=relative_path,
                    tofile=relative_path,
                )
            )
        return list(updates)

    originals = {path: path.read_bytes() for path in updates}
    temporary_paths: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, updated_text in updates.items():
            temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            temporary_path.write_text(updated_text, encoding="utf-8", newline="\n")
            temporary_paths[path] = temporary_path
        for path, temporary_path in temporary_paths.items():
            os.replace(temporary_path, path)
            replaced.append(path)
        validate_version_consistency(root, expected_version=new_version)
    except Exception:
        for path in reversed(replaced):
            path.write_bytes(originals[path])
        raise
    finally:
        for temporary_path in temporary_paths.values():
            temporary_path.unlink(missing_ok=True)

    return list(updates)
