#!/usr/bin/env python3
"""Publish only locally validated assets, safely handling GitHub Release retries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ARCHIVE_NAME = "pipeline-forge.zip"
CHECKSUM_NAME = "pipeline-forge.zip.sha256"
CHECKSUM_PATTERN = re.compile(
    rf"^(?P<hash>[0-9a-fA-F]{{64}})\s+\*?{re.escape(ARCHIVE_NAME)}\r?\n?$"
)
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class ReleasePublishError(RuntimeError):
    """Raised when release state cannot be reconciled safely."""


@dataclass(frozen=True)
class LocalAssets:
    root: Path
    archive: Path
    checksum: Path
    digests: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_filesystem_alias(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_attribute)


def validate_local_assets(asset_root: Path, archive: Path, checksum: Path) -> LocalAssets:
    try:
        root = asset_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ReleasePublishError(f"validated asset root is unavailable: {asset_root}") from exc
    if not root.is_dir() or _is_filesystem_alias(root):
        raise ReleasePublishError(f"validated asset root must be a real directory: {root}")

    resolved_assets: dict[str, Path] = {}
    for expected_name, candidate in ((ARCHIVE_NAME, archive), (CHECKSUM_NAME, checksum)):
        if candidate.name != expected_name:
            raise ReleasePublishError(
                f"release asset must be named {expected_name!r}, found {candidate.name!r}"
            )
        if _is_filesystem_alias(candidate):
            raise ReleasePublishError(f"release asset may not be a filesystem alias: {candidate}")
        try:
            resolved = candidate.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ReleasePublishError(f"release asset is unavailable: {candidate}") from exc
        if not resolved.is_file() or resolved.parent != root:
            raise ReleasePublishError(
                f"release asset must be a direct file in the validated asset root: {resolved}"
            )
        resolved_assets[expected_name] = resolved

    checksum_text = resolved_assets[CHECKSUM_NAME].read_text(encoding="utf-8")
    checksum_match = CHECKSUM_PATTERN.fullmatch(checksum_text)
    if checksum_match is None:
        raise ReleasePublishError("release checksum file has an invalid format")
    archive_digest = _sha256(resolved_assets[ARCHIVE_NAME])
    expected_digest = checksum_match.group("hash").lower()
    if archive_digest != expected_digest:
        raise ReleasePublishError(
            f"release archive checksum mismatch: expected {expected_digest}, found {archive_digest}"
        )

    return LocalAssets(
        root=root,
        archive=resolved_assets[ARCHIVE_NAME],
        checksum=resolved_assets[CHECKSUM_NAME],
        digests={
            ARCHIVE_NAME: archive_digest,
            CHECKSUM_NAME: _sha256(resolved_assets[CHECKSUM_NAME]),
        },
    )


def run_gh(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise ReleasePublishError("GitHub CLI is required to publish a release") from exc


def _command_detail(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()


def _require_success(
    result: subprocess.CompletedProcess[str], operation: str
) -> subprocess.CompletedProcess[str]:
    if result.returncode != 0:
        raise ReleasePublishError(f"{operation} failed: {_command_detail(result)}")
    return result


def _parse_release(result: subprocess.CompletedProcess[str]) -> dict:
    _require_success(result, "reading GitHub Release state")
    try:
        release = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReleasePublishError("GitHub Release state was not valid JSON") from exc
    if not isinstance(release, dict) or not isinstance(release.get("isDraft"), bool):
        raise ReleasePublishError("GitHub Release state is missing isDraft")
    assets = release.get("assets")
    if not isinstance(assets, list) or any(
        not isinstance(asset, dict) or not isinstance(asset.get("name"), str)
        for asset in assets
    ):
        raise ReleasePublishError("GitHub Release state contains invalid asset metadata")
    return release


def _view_arguments(tag: str, repository: str) -> list[str]:
    return [
        "release",
        "view",
        tag,
        "--repo",
        repository,
        "--json",
        "isDraft,assets",
    ]


def _download_and_verify(
    tag: str,
    repository: str,
    local_assets: LocalAssets,
    runner: CommandRunner,
) -> None:
    with tempfile.TemporaryDirectory(prefix="pipeline-forge-release-verify-") as temporary_directory:
        download_root = Path(temporary_directory)
        result = runner(
            ["release", "download", tag, "--repo", repository, "--dir", str(download_root)]
        )
        _require_success(result, "downloading GitHub Release assets for verification")
        downloaded = list(download_root.iterdir())
        if any(not path.is_file() or _is_filesystem_alias(path) for path in downloaded):
            raise ReleasePublishError("downloaded release assets contain a non-regular entry")
        downloaded_names = {path.name for path in downloaded}
        if downloaded_names != set(local_assets.digests):
            raise ReleasePublishError(
                "downloaded release asset set mismatch: "
                f"expected {sorted(local_assets.digests)}, found {sorted(downloaded_names)}"
            )
        for path in downloaded:
            digest = _sha256(path)
            if digest != local_assets.digests[path.name]:
                raise ReleasePublishError(
                    f"downloaded release asset differs from this run's validated build: {path.name}"
                )


def publish_release(
    *,
    repository: str,
    tag: str,
    title: str,
    asset_root: Path,
    archive: Path,
    checksum: Path,
    runner: CommandRunner = run_gh,
) -> str:
    """Create or reconcile one release and return ``published`` or ``already-published``."""
    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ReleasePublishError(f"invalid GitHub repository name: {repository!r}")
    if not tag.startswith("v") or any(character.isspace() for character in tag):
        raise ReleasePublishError(f"invalid release tag: {tag!r}")
    local_assets = validate_local_assets(asset_root, archive, checksum)

    view_result = runner(_view_arguments(tag, repository))
    if view_result.returncode != 0:
        create_result = runner(
            [
                "release",
                "create",
                tag,
                "--repo",
                repository,
                "--verify-tag",
                "--generate-notes",
                "--title",
                title,
                "--draft",
            ]
        )
        if create_result.returncode != 0:
            retry_view = runner(_view_arguments(tag, repository))
            if retry_view.returncode != 0:
                raise ReleasePublishError(
                    "unable to read or safely create the GitHub Release: "
                    f"view={_command_detail(view_result)}; "
                    f"create={_command_detail(create_result)}; "
                    f"retry={_command_detail(retry_view)}"
                )
            view_result = retry_view
        else:
            view_result = runner(_view_arguments(tag, repository))

    release = _parse_release(view_result)
    asset_names = [asset["name"] for asset in release["assets"]]
    expected_names = set(local_assets.digests)
    if len(asset_names) != len(set(asset_names)):
        raise ReleasePublishError("GitHub Release contains duplicate asset names")

    if not release["isDraft"]:
        if set(asset_names) != expected_names:
            raise ReleasePublishError(
                "published GitHub Release has an unexpected asset set; refusing to mutate it: "
                f"expected {sorted(expected_names)}, found {sorted(asset_names)}"
            )
        _download_and_verify(tag, repository, local_assets, runner)
        return "already-published"

    unexpected_assets = set(asset_names) - expected_names
    if unexpected_assets:
        raise ReleasePublishError(
            "draft GitHub Release contains unexpected assets; refusing to delete or publish them: "
            f"{sorted(unexpected_assets)}"
        )

    # Re-read and hash immediately before upload so only this validated build can be selected.
    local_assets = validate_local_assets(asset_root, archive, checksum)
    upload_result = runner(
        [
            "release",
            "upload",
            tag,
            str(local_assets.archive),
            str(local_assets.checksum),
            "--repo",
            repository,
            "--clobber",
        ]
    )
    _require_success(upload_result, "uploading validated GitHub Release assets")
    _download_and_verify(tag, repository, local_assets, runner)
    publish_result = runner(
        ["release", "edit", tag, "--repo", repository, "--draft=false"]
    )
    _require_success(publish_result, "publishing verified GitHub Release draft")
    return "published"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name.")
    parser.add_argument("--tag", required=True, help="Existing immutable release tag.")
    parser.add_argument("--title", required=True, help="Release title for first creation.")
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    args = parser.parse_args()
    try:
        outcome = publish_release(
            repository=args.repository,
            tag=args.tag,
            title=args.title,
            asset_root=args.asset_root,
            archive=args.archive,
            checksum=args.checksum,
        )
    except (ReleasePublishError, OSError) as exc:
        print(f"Release publication failed safely: {exc}", file=sys.stderr)
        return 1
    print(f"Release publication outcome: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
