"""Bounded AST checks for copied historical hazards; never prints source values."""
import argparse
import ast
import json
import re
from pathlib import Path

SECRET = re.compile(r'(password|passwd|secret|token|api_key|app_key|connection_url|mongo_url)', re.I)
PLACEHOLDER = re.compile(r'^(?:<[^>]+>|\$\{[^}]+\}|YOUR_[A-Z_]+|REPLACE_ME)$')
LOG_METHODS = {'debug', 'info', 'warning', 'error', 'exception', 'critical', 'log'}
RAW_PARAMS = {'params', 'execute_params', 'runtime_params'}


def check_source(source):
    tree = ast.parse(source)
    findings = []

    def emit(node, rule):
        findings.append({'line': node.lineno, 'rule': rule})

    def credential(node, key, value):
        if SECRET.search(key) and isinstance(value, ast.Constant) and isinstance(value.value, str):
            text = value.value
            if text and not PLACEHOLDER.fullmatch(text):
                emit(node, 'hardcoded_credential')

    def raw_log(node):
        if isinstance(node, ast.Name):
            return node.id in RAW_PARAMS
        # Scalar selection is permitted; logging the whole object through wrappers is not.
        if isinstance(node, ast.Subscript):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get':
            return False
        return any(raw_log(child) for child in ast.iter_child_nodes(node))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                key = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else ''
                credential(node, key, node.value)
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    credential(node, str(target.slice.value), node.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant):
                    credential(node, str(key.value), value)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Constant):
            emit(node, 'invalid_exception_literal')
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                credential(node, keyword.arg or '', keyword.value)
                if keyword.arg == 'verify' and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                    emit(node, 'tls_verification_disabled')
            is_log = (isinstance(node.func, ast.Name) and node.func.id == 'print') or (isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS)
            if is_log and any(raw_log(arg) for arg in [*node.args, *(k.value for k in node.keywords)]):
                emit(node, 'raw_runtime_params_log')
    return findings


def verify(project_dir):
    findings = []
    for path in sorted(Path(project_dir).rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        try:
            items = check_source(path.read_text(encoding='utf-8-sig'))
        except SyntaxError as error:
            items = [{'line': error.lineno, 'rule': 'invalid_python'}]
        for item in items:
            findings.append({'path': str(path.relative_to(project_dir)), **item})
    return {'status': 'failed' if findings else 'passed', 'findings': findings}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.project_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(result['status'] != 'passed')
