#!/usr/bin/env python3
"""Reject unsafe PipelineForge ZIP members before any extraction occurs."""

from __future__ import annotations

import argparse
import re
import stat
import sys
import zipfile
from pathlib import Path


ALLOWED_ROOT = "pipeline-forge"
MAX_MEMBERS = 10_000
MAX_MEMBER_SIZE = 128 * 1024 * 1024
MAX_TOTAL_SIZE = 512 * 1024 * 1024
ALLOWED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
REPARSE_POINT_ATTRIBUTE = 0x0400


class ArchiveSafetyError(ValueError):
    """Raised when an archive is unsafe to extract."""


def _normalized_member_name(raw_name: str) -> tuple[str, str, bool]:
    if not raw_name or "\x00" in raw_name:
        raise ArchiveSafetyError("archive member name is empty or contains NUL")
    if any(ord(character) < 32 for character in raw_name):
        raise ArchiveSafetyError(f"archive member contains a control character: {raw_name!r}")

    slash_name = raw_name.replace("\\", "/")
    if slash_name.startswith("/") or DRIVE_PATH_PATTERN.match(slash_name):
        raise ArchiveSafetyError(f"archive member uses an absolute path: {raw_name!r}")

    is_directory = slash_name.endswith("/")
    path_text = slash_name[:-1] if is_directory else slash_name
    parts = path_text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArchiveSafetyError(f"archive member has an unsafe path segment: {raw_name!r}")
    for part in parts:
        if part.endswith((" ", ".")):
            raise ArchiveSafetyError(
                f"archive member has a Windows-ambiguous path segment: {raw_name!r}"
            )
        if ":" in part:
            raise ArchiveSafetyError(
                f"archive member may address a drive or alternate data stream: {raw_name!r}"
            )
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise ArchiveSafetyError(
                f"archive member uses a reserved Windows device name: {raw_name!r}"
            )

    if parts[0] != ALLOWED_ROOT:
        raise ArchiveSafetyError(
            f"archive member is outside the allowed {ALLOWED_ROOT}/ root: {raw_name!r}"
        )
    if len(parts) == 1 and not is_directory:
        raise ArchiveSafetyError(f"archive root must be a directory: {raw_name!r}")

    normalized = "/".join(parts) + ("/" if is_directory else "")
    canonical = "/".join(part.casefold() for part in parts)
    return normalized, canonical, is_directory


def _validate_member_type(info: zipfile.ZipInfo, is_directory: bool) -> None:
    attributes = info.external_attr & 0xFFFFFFFF
    unix_mode = (attributes >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type == stat.S_IFLNK:
        raise ArchiveSafetyError(f"symbolic-link archive member is not allowed: {info.filename!r}")
    if attributes & REPARSE_POINT_ATTRIBUTE:
        raise ArchiveSafetyError(f"reparse-point archive member is not allowed: {info.filename!r}")
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArchiveSafetyError(f"special-file archive member is not allowed: {info.filename!r}")
    if is_directory and file_type == stat.S_IFREG:
        raise ArchiveSafetyError(f"archive directory has regular-file metadata: {info.filename!r}")
    if not is_directory and file_type == stat.S_IFDIR:
        raise ArchiveSafetyError(f"archive file has directory metadata: {info.filename!r}")
    if is_directory and info.file_size != 0:
        raise ArchiveSafetyError(f"archive directory unexpectedly contains data: {info.filename!r}")


def validate_archive(archive_path: Path) -> list[str]:
    """Validate all members without extracting any bytes."""
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise ArchiveSafetyError(f"archive does not exist: {archive_path}")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if not infos:
                raise ArchiveSafetyError("archive is empty")
            if len(infos) > MAX_MEMBERS:
                raise ArchiveSafetyError(
                    f"archive has too many members: {len(infos)} > {MAX_MEMBERS}"
                )

            seen: dict[str, tuple[str, bool]] = {}
            total_size = 0
            normalized_names: list[str] = []
            for info in infos:
                normalized, canonical, is_directory = _normalized_member_name(info.filename)
                previous = seen.get(canonical)
                if previous is not None:
                    previous_name, previous_is_directory = previous
                    collision_kind = (
                        "duplicate"
                        if previous_name == normalized
                        and previous_is_directory == is_directory
                        else "case or type collision"
                    )
                    raise ArchiveSafetyError(
                        f"archive contains a {collision_kind}: {previous_name!r} and {normalized!r}"
                    )
                seen[canonical] = (normalized, is_directory)
                normalized_names.append(normalized)

                _validate_member_type(info, is_directory)
                if info.flag_bits & 0x1:
                    raise ArchiveSafetyError(f"encrypted archive member is not allowed: {info.filename!r}")
                if info.compress_type not in ALLOWED_COMPRESSION:
                    raise ArchiveSafetyError(
                        f"unsupported compression method for archive member: {info.filename!r}"
                    )
                if info.file_size < 0 or info.file_size > MAX_MEMBER_SIZE:
                    raise ArchiveSafetyError(
                        f"archive member exceeds the uncompressed size limit: {info.filename!r}"
                    )
                total_size += info.file_size
                if total_size > MAX_TOTAL_SIZE:
                    raise ArchiveSafetyError(
                        f"archive exceeds the total uncompressed size limit: {MAX_TOTAL_SIZE}"
                    )

            file_keys = {key for key, (_, is_directory) in seen.items() if not is_directory}
            for canonical, (normalized, _) in seen.items():
                parts = canonical.split("/")
                for index in range(1, len(parts)):
                    ancestor = "/".join(parts[:index])
                    if ancestor in file_keys:
                        ancestor_name = seen[ancestor][0]
                        raise ArchiveSafetyError(
                            "archive member is nested below a file member: "
                            f"{ancestor_name!r} and {normalized!r}"
                        )
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ArchiveSafetyError(
                    f"archive member failed CRC validation: {corrupt_member!r}"
                )
    except zipfile.BadZipFile as exc:
        raise ArchiveSafetyError(f"archive is not a valid ZIP file: {exc}") from exc

    return normalized_names


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="ZIP file to inspect.")
    args = parser.parse_args()
    try:
        members = validate_archive(args.archive)
    except (ArchiveSafetyError, OSError) as exc:
        print(f"Archive safety validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Archive safety validation passed ({len(members)} members)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
