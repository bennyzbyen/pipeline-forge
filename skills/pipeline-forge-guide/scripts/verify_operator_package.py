"""Compare an actual operator ZIP with the selected unit's private deployment files offline."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, ZipFile


PLATFORM_DIRS = ("gateway", "hbase", "fs")


def member_name(value):
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or PureWindowsPath(value).drive or "\\" in value
            or ".." in path.parts or path.as_posix() != value):
        raise ValueError("Expected a canonical ZIP-relative file path")
    return value


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.digest()


def verify(archive, unit_root, configs, platform_root=None, entrypoint="plugin_main.py"):
    if not configs:
        raise ValueError("Select at least one unit configuration file")
    expected = {member_name(name): unit_root / name for name in [entrypoint, *configs]}
    if platform_root is not None:
        for directory in PLATFORM_DIRS:
            files = [p for p in (platform_root / directory).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}]
            if not files:
                raise ValueError(f"Missing fixed package in reference: {directory}")
            for path in files:
                name = path.relative_to(platform_root).as_posix()
                if name in expected:
                    raise ValueError(f"Ambiguous reference for {name}")
                expected[name] = path

    with ZipFile(archive) as package:
        files = {}
        seen = set()
        for entry in package.infolist():
            name = member_name(entry.filename.removesuffix("/"))
            if name.casefold() in seen:
                raise ValueError(f"Duplicate ZIP member: {name}")
            seen.add(name.casefold())
            if not entry.is_dir():
                files[name] = entry
        for name, path in expected.items():
            if name not in files or not path.is_file():
                raise ValueError(f"Required file missing from ZIP or reference: {name}")
            with package.open(files[name]) as packed, path.open("rb") as source:
                if digest(packed) != digest(source):
                    raise ValueError(f"ZIP differs from its selected reference: {name}")
        if platform_root is not None:
            for name in files:
                if name.split("/")[0].casefold() in PLATFORM_DIRS and name not in expected:
                    raise ValueError(f"Unexpected fixed-package member: {name}")
    return {"status": "passed", "files_compared": len(expected)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--unit-root", required=True, type=Path)
    parser.add_argument("--config", required=True, action="append", help="Unit-relative runtime config, repeat as needed.")
    parser.add_argument("--platform-root", type=Path, help="Authoritative source containing gateway/, hbase/ and fs/.")
    parser.add_argument("--entrypoint", default="plugin_main.py")
    args = parser.parse_args()
    try:
        result = verify(args.zip, args.unit_root, args.config, args.platform_root, args.entrypoint)
    except (OSError, BadZipFile, ValueError) as error:
        parser.exit(1, f"Operator ZIP verification failed: {error}\n")
    print(json.dumps(result))
