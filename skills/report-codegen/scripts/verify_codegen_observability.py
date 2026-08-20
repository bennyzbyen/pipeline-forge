#!/usr/bin/env python3
"""Statically verify comments and safe runtime logging in generated report code."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Iterable


LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
REQUIRED_EVENTS = {"pipeline_start", "stage_start", "stage_complete", "pipeline_complete", "pipeline_failed"}
EXCLUDED_DIRS = {"gateway", "hbase", "fs", "common_utils", "__pycache__"}


def business_files(project_dir: Path) -> Iterable[Path]:
    for path in sorted(project_dir.rglob("*.py")):
        if not any(part in EXCLUDED_DIRS for part in path.relative_to(project_dir).parts):
            yield path


def is_logger_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in LOGGER_METHODS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    )


def direct_name(arg: ast.AST) -> str | None:
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    return None


def verify(project_dir: Path) -> dict:
    errors: list[str] = []
    parsed: dict[Path, tuple[str, ast.Module]] = {}
    logger_calls = 0

    for path in business_files(project_dir):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(project_dir)}:{exc.lineno}: invalid Python: {exc.msg}")
            continue
        parsed[path] = (source, tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                errors.append(f"{path.relative_to(project_dir)}:{node.lineno}: runtime print() is not allowed")
            if not isinstance(node, ast.Call) or not is_logger_call(node):
                continue
            logger_calls += 1
            for arg in node.args:
                name = direct_name(arg)
                if name == "params":
                    errors.append(f"{path.relative_to(project_dir)}:{node.lineno}: raw params must not be logged")
                if name and (name == "sql" or name.endswith("_sql") or name.startswith("query_")):
                    errors.append(f"{path.relative_to(project_dir)}:{node.lineno}: full SQL must not be logged at runtime")
            literal_text = " ".join(
                value.value.lower()
                for value in node.args
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
            for secret_name in ("app_secret", "password", "api_key", "authorization", "connection_url"):
                if secret_name in literal_text:
                    errors.append(f"{path.relative_to(project_dir)}:{node.lineno}: sensitive field appears in log text: {secret_name}")

    main_path = project_dir / "main_execute.py"
    if main_path not in parsed:
        errors.append("missing required business file: main_execute.py")
    else:
        source, tree = parsed[main_path]
        pipeline_class = next(
            (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "ReportPipeline"),
            None,
        )
        if pipeline_class is None:
            errors.append("main_execute.py: missing class ReportPipeline")
        else:
            if not ast.get_docstring(pipeline_class):
                errors.append("main_execute.py: ReportPipeline needs a contract docstring")
            execute_method = next(
                (node for node in pipeline_class.body if isinstance(node, ast.FunctionDef) and node.name == "execute"),
                None,
            )
            if execute_method is None or not ast.get_docstring(execute_method):
                errors.append("main_execute.py: ReportPipeline.execute needs an orchestration docstring")
        missing_events = sorted(event for event in REQUIRED_EVENTS if event not in source)
        if missing_events:
            errors.append(f"main_execute.py: missing orchestration events {missing_events}")

    for class_name, relative_path in (
        ("DataSource", Path("data_utils/data_source.py")),
        ("DataProcess", Path("data_utils/data_process.py")),
        ("DataStorage", Path("data_utils/data_storage.py")),
    ):
        path = project_dir / relative_path
        if path not in parsed:
            errors.append(f"missing required business file: {relative_path.as_posix()}")
            continue
        _source, tree = parsed[path]
        class_node = next(
            (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == class_name),
            None,
        )
        if class_node is None or not ast.get_docstring(class_node):
            errors.append(f"{relative_path.as_posix()}: {class_name} needs a contract docstring")

    result = {
        "project_dir": str(project_dir),
        "business_files": len(parsed),
        "logger_calls": logger_calls,
        "errors": errors,
        "status": "passed" if not errors else "failed",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        parser.error(f"project directory does not exist: {project_dir}")

    result = verify(project_dir)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
