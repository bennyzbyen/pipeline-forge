from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".codex_dev_run",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "local_outputs",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
TEXT_SUFFIXES = {".cfg", ".ini", ".json", ".md", ".py", ".sql", ".toml", ".yaml", ".yml"}
CREDENTIAL_KEYS = {"app_key", "app_secret", "api_key", "password", "token"}
LINE_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?im)^\s*['\"]?(app_key|app_secret|api_key|password|token)['\"]?\s*[:=]\s*['\"]([^'\"]*)['\"]\s*[,#]?\s*$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a provenance-tracked report candidate from an explicit reference project."
    )
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument(
        "--source-dir",
        default="src",
        help="Reference-relative source directory to copy (default: src).",
    )
    parser.add_argument(
        "--include-file",
        action="append",
        default=[],
        help="Additional reference-relative file to copy. Repeat as needed.",
    )
    parser.add_argument("--target", type=Path)
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Validate the selected reference files without copying them.",
    )
    return parser.parse_args()


def ensure_within(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes reference root: {candidate}") from exc
    return resolved


def iter_copy_files(reference_root: Path, source_dir: str, include_files: list[str]) -> list[Path]:
    source_root = ensure_within(reference_root, reference_root / source_dir)
    if not source_root.is_dir():
        raise FileNotFoundError(f"source directory does not exist: {source_dir}")

    files = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(reference_root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        files.append(path)

    for value in include_files:
        path = ensure_within(reference_root, reference_root / value)
        if not path.is_file():
            raise FileNotFoundError(f"included file does not exist: {value}")
        files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(reference_root).as_posix())


def is_placeholder(value: str) -> bool:
    normalized = value.strip()
    upper = normalized.upper()
    return (
        not normalized
        or (normalized.startswith("<") and normalized.endswith(">"))
        or normalized.startswith("${")
        or "PLACEHOLDER" in upper
        or upper.startswith("EXAMPLE_")
        or upper.startswith("YOUR_")
        or upper.startswith("REPLACE_")
        or upper in {key.upper() for key in CREDENTIAL_KEYS}
    )


def is_test_fixture(path: Path, value: str) -> bool:
    normalized_parts = {part.lower() for part in path.parts}
    in_tests = "tests" in normalized_parts or path.name.lower().startswith("test_")
    lowered = value.strip().lower()
    return in_tests and any(marker in lowered for marker in ("test", "mock", "fake", "dummy"))


def iter_json_credentials(value: object, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            current = (*path, str(key))
            if key_text in CREDENTIAL_KEYS and isinstance(item, str):
                yield key_text, item, ".".join(current)
            yield from iter_json_credentials(item, current)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_json_credentials(item, (*path, str(index)))


def iter_python_credentials(text: str):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                for target in targets:
                    if isinstance(target, ast.Name) and target.id.lower() in CREDENTIAL_KEYS:
                        yield target.id.lower(), value_node.value, str(node.lineno)
        elif isinstance(node, ast.Dict):
            for key_node, value_node in zip(node.keys, node.values):
                if (
                    isinstance(key_node, ast.Constant)
                    and isinstance(key_node.value, str)
                    and key_node.value.lower() in CREDENTIAL_KEYS
                    and isinstance(value_node, ast.Constant)
                    and isinstance(value_node.value, str)
                ):
                    yield key_node.value.lower(), value_node.value, str(node.lineno)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (
                    keyword.arg
                    and keyword.arg.lower() in CREDENTIAL_KEYS
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    yield keyword.arg.lower(), keyword.value.value, str(node.lineno)


def credential_literals(path: Path, text: str):
    suffix = path.suffix.lower()
    if suffix == ".py":
        yield from iter_python_credentials(text)
        return
    if suffix == ".json":
        data = json.loads(text)
        yield from iter_json_credentials(data)
        return
    for match in LINE_CREDENTIAL_ASSIGNMENT.finditer(text):
        yield match.group(1).lower(), match.group(2), str(text.count("\n", 0, match.start()) + 1)


def scan_credentials(reference_root: Path, files: list[Path]) -> int:
    findings = []
    assignment_count = 0
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for key, value, location in credential_literals(path, text):
            assignment_count += 1
            relative = path.relative_to(reference_root)
            if not is_placeholder(value) and not is_test_fixture(relative, value):
                findings.append(
                    {
                        "file": relative.as_posix(),
                        "key": key,
                        "location": location,
                    }
                )
    if findings:
        rendered = json.dumps(findings, ensure_ascii=False)
        raise ValueError(f"non-placeholder credential assignments detected: {rendered}")
    return assignment_count


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(reference_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(reference_root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.rstrip("\r\n") if completed.returncode == 0 else ""


def build_manifest(reference_root: Path, target: Path, copied_files: list[Path]) -> dict:
    status_lines = [line for line in git_output(reference_root, "status", "--short").splitlines() if line]
    return {
        "artifact_status": "REFERENCE_ASSISTED_CANDIDATE",
        "reference_assisted": True,
        "reference_repository": reference_root.name,
        "reference_branch": git_output(reference_root, "branch", "--show-current"),
        "reference_commit": git_output(reference_root, "rev-parse", "HEAD"),
        "reference_dirty": bool(status_lines),
        "reference_status_short": status_lines,
        "copied_file_count": len(copied_files),
        "copied_files": [
            {
                "path": path.relative_to(target).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in copied_files
        ],
        "excluded_parts": sorted(EXCLUDED_PARTS),
        "external_services_used": False,
    }


def main() -> int:
    args = parse_args()
    reference_root = args.reference_root.resolve()
    if not reference_root.is_dir():
        raise FileNotFoundError(f"reference root does not exist: {reference_root}")
    if not args.scan_only and args.target is None:
        raise ValueError("--target is required unless --scan-only is used")

    target = args.target.resolve() if args.target else None
    if target is not None and target.exists() and any(target.iterdir()):
        raise FileExistsError(f"target must not exist or must be empty: {target}")

    files = iter_copy_files(reference_root, args.source_dir, args.include_file)
    assignment_count = scan_credentials(reference_root, files)
    if args.scan_only:
        print(f"selected_files: {len(files)}")
        print(f"credential_assignments: {assignment_count}")
        print("credential_scan: passed")
        return 0

    assert target is not None
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in files:
        relative = source.relative_to(reference_root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)

    manifest = build_manifest(reference_root, target, copied)
    manifest_path = target / "REFERENCE_PROVENANCE.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"candidate: {target}")
    print(f"copied_files: {len(copied)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
