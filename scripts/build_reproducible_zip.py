#!/usr/bin/env python3
"""Build the PipelineForge download archive with reproducible ZIP metadata."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import uuid
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PREFIX = "pipeline-forge"
PACKAGE_PATHS = (
    "SOURCE_REVISION",
    ".codex-plugin",
    "assets",
    "skills",
    "install-pipeline-forge.ps1",
    "INSTALL.md",
    "LICENSE",
    "CHANGELOG.md",
    "VERSIONING.md",
    "README.md",
    "README.en.md",
    "README.zh-CN.md",
)
EXCLUDED_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
}
EXCLUDED_FILE_EXTENSIONS = {".pyc", ".pyo", ".pyd"}
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REGULAR_FILE_MODE = stat.S_IFREG | 0o644


def is_excluded(relative_path: Path) -> bool:
    return bool(
        EXCLUDED_DIRECTORY_NAMES.intersection(relative_path.parts)
        or relative_path.suffix.lower() in EXCLUDED_FILE_EXTENSIONS
    )


def collect_package_files(root: Path) -> list[tuple[str, Path]]:
    """Return stable archive-name/source pairs and reject filesystem aliases."""
    files: dict[str, Path] = {}
    for relative in PACKAGE_PATHS:
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(f"Required package path is missing: {relative}")
        if source.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in the package: {relative}")

        candidates = [source] if source.is_file() else source.rglob("*")
        for candidate in candidates:
            if candidate.is_symlink():
                child = candidate.relative_to(root).as_posix()
                raise ValueError(f"Symbolic links are not allowed in the package: {child}")
            if not candidate.is_file():
                continue
            relative_file = candidate.relative_to(root)
            if is_excluded(relative_file):
                continue
            archive_name = f"{PACKAGE_PREFIX}/{relative_file.as_posix()}"
            if archive_name in files:
                raise ValueError(f"Duplicate archive member: {archive_name}")
            files[archive_name] = candidate

    return sorted(files.items(), key=lambda item: item[0])


def build_archive(root: Path, output: Path) -> Path:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    package_files = collect_package_files(root)
    temporary_output = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")

    try:
        with zipfile.ZipFile(
            temporary_output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
            strict_timestamps=True,
        ) as archive:
            for archive_name, source in package_files:
                info = zipfile.ZipInfo(archive_name, date_time=FIXED_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.create_version = 20
                info.extract_version = 20
                info.external_attr = REGULAR_FILE_MODE << 16
                info.internal_attr = 0
                archive.writestr(
                    info,
                    source.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
        os.replace(temporary_output, output)
    finally:
        temporary_output.unlink(missing_ok=True)

    return output


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Plugin repository root.")
    parser.add_argument("--output", type=Path, required=True, help="Destination ZIP path.")
    args = parser.parse_args()
    archive = build_archive(args.root, args.output)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
