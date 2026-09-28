"""Capture immutable, redacted evidence; validate and relink without original sources."""
import argparse
import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = '90_机器索引/evidence_snapshots.json'
SENSITIVE = re.compile(r'password|passwd|secret|token|api[_-]?key|app[_-]?key|accountkey|connection_string|sas_url|username|user_name|email|owner', re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(evidence):
    fields = ('type', 'path', 'document_id', 'start', 'end', 'locator', 'source_sha256')
    return {**{key: evidence[key] for key in fields if key in evidence}, 'root': evidence.get('root', 'historical')}


def evidence_key(evidence):
    return sha(json.dumps(identity(evidence), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def inside(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute() or re.match(r'^[A-Za-z]:', relative) or relative.startswith(('\\', '//')):
        raise ValueError('relative evidence path required')
    path = (root/relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('evidence path escapes root')
    return path


def load_manifest(vault):
    path = inside(vault, MANIFEST)
    if not path.exists():
        return {'version': 1, 'snapshots': {}}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('snapshots'), dict):
        raise ValueError('invalid snapshot manifest')
    return value


def verify_snapshot(vault, evidence, manifest):
    item = manifest['snapshots'].get(evidence_key(evidence))
    if item is None:
        return None
    if not isinstance(item, dict) or item.get('identity') != identity(evidence):
        return {'verification': 'invalid_snapshot_binding'}
    result = {'verification': 'snapshot_unavailable', 'basis': 'frozen_evidence',
              'source_sha256': evidence.get('source_sha256'), 'snapshot_sha256': item.get('sha256'),
              'scope': item.get('scope'), 'redaction_version': item.get('redaction_version')}
    try:
        if not item['path'].startswith('81_证据快照/') or not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', '')):
            raise ValueError('invalid snapshot path/hash')
        path = inside(Path(vault)/'81_证据快照', item['path'].removeprefix('81_证据快照/'))
        if sha(path.read_bytes()) != item['sha256']:
            result['verification'] = 'snapshot_changed'
        elif item.get('capture_status') != 'baseline_matched_redacted' or item.get('redaction_version') != 1:
            result['verification'] = 'snapshot_not_reviewed'
        else:
            result['verification'] = 'verified'
            result['citation'] = f'[frozen evidence](<{path.as_posix()}:1>)'
    except (OSError, ValueError, KeyError, TypeError):
        result['verification'] = 'snapshot_unavailable_or_unsafe'
    return result


def sensitive_literals(text):
    values = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return values
    for node in ast.walk(tree):
        value = None
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(SENSITIVE.search(ast.unparse(t)) for t in targets):
                value = node.value
        elif isinstance(node, ast.keyword) and SENSITIVE.search(node.arg or ''):
            value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and SENSITIVE.search(str(key.value)) and isinstance(value, ast.Constant) and isinstance(value.value, str):
                    values.add(value.value)
    return {line for value in values for line in value.splitlines() if len(line) >= 4}


def redact(text, secrets=()):
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, '<REDACTED_VALUE>')
    text = re.sub(r'(?i)\b(?:https?|mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://[^\s<>\"\x27)]+', '<REDACTED_URL>', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '<REDACTED_IP>', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<REDACTED_EMAIL>', text)
    text = re.sub(r'(?i)((?:password|passwd|secret|app_key|app_secret|api_key|token|username|user_name)\s*[\"\x27]?\s*[:=]\s*)([\"\x27])[^\r\n]*?\2', r'\1"<REDACTED_VALUE>"', text)
    text = re.sub(r'(?<![\w])[A-Za-z0-9+/]{32,}={0,2}(?![\w])', '<REDACTED_OPAQUE_VALUE>', text)
    return text


def baseline_bytes(path, expected):
    if path.is_file():
        data = path.read_bytes()
        if sha(data) == expected:
            return data, {'kind': 'working_file_hash_match'}
    # Read-only recovery: exact original hash only, never substitute newer source.
    repo = next((p for p in [path.parent, *path.parents] if (p/'.git').exists()), None)
    if repo:
        relative = path.relative_to(repo).as_posix()
        proc = subprocess.run(['git', '-C', str(repo), 'rev-list', '--objects', '--all', '--', relative], capture_output=True, text=True, encoding='utf-8')
        for line in proc.stdout.splitlines() if proc.returncode == 0 else []:
            if not line.endswith(' '+relative):
                continue
            oid = line.split()[0]
            blob = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', oid], capture_output=True)
            if blob.returncode:
                continue
            variants = [('git_blob', blob.stdout), ('git_blob_crlf', blob.stdout.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))]
            for kind, data in variants:
                if sha(data) == expected:
                    return data, {'kind': kind, 'git_blob': oid}
    raise ValueError('original evidence baseline unavailable: '+str(path))


def capture(config):
    vault = Path(config['vault']).resolve()
    manifest = load_manifest(vault)
    cards = [json.loads(line) for line in inside(vault, '90_机器索引/knowledge.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    docs = {d['id']: d for d in json.loads(inside(vault, '90_机器索引/document_manifest.json').read_text(encoding='utf-8'))}
    pending, secrets, sources = [], set(), {}
    # Resolve every missing baseline before persisting anything.
    for card in cards:
        for e in card['evidence']:
            existing = verify_snapshot(vault, e, manifest)
            if existing:
                if existing['verification'] != 'verified':
                    raise ValueError('existing snapshot failed integrity: '+card['id'])
                continue
            key = evidence_key(e)
            if any(row[0] == key for row in pending):
                continue
            relative = e['path'] if e['type'] == 'code' else docs[e['document_id']]['path']
            root = config.get('source_roots', {}).get(e.get('root', 'historical'))
            if not root:
                raise ValueError('source root required only for first capture: '+card['id'])
            path = inside(root, relative)
            cache_key = (str(path), e['source_sha256'])
            if cache_key not in sources:
                sources[cache_key] = baseline_bytes(path, e['source_sha256'])
            data, provenance = sources[cache_key]
            if e['type'] == 'code':
                text = data.decode('utf-8-sig')
                secrets.update(sensitive_literals(text))
                lines = text.splitlines()
                if not (1 <= e['start'] <= e['end'] <= len(lines)):
                    raise ValueError('invalid original evidence lines')
                body = '\n'.join(f'L{i}: {lines[i-1]}' for i in range(e['start'], e['end']+1))
                scope = 'cited_code_excerpt_not_complete_project'
            else:
                directory = inside(Path(vault)/'80_来源证据', e['document_id'])
                files = sorted(directory.rglob('*.md'))
                if not files:
                    raise ValueError('missing sanitized document extraction')
                body = '\n\n'.join('## '+p.relative_to(directory).as_posix()+'\n\n'+inside(directory, p.relative_to(directory).as_posix()).read_text(encoding='utf-8') for p in files)
                scope = 'sanitized_document_extraction_not_original_binary'
                provenance = {**provenance, 'extraction_files': len(files)}
            pending.append((key, e, body, scope, provenance))
    for key, e, body, scope, provenance in pending:
        safe = redact(body, secrets)
        text = '# Frozen evidence\n\nScope: '+scope+'\n\nSource baseline SHA-256: '+e['source_sha256']+'\n\nRedaction: v1; placeholders may remove connection details. Not executable.\n\n'+safe+'\n'
        data = text.encode('utf-8')
        checksum = sha(data)
        relative = '81_证据快照/'+checksum+'.md'
        path = inside(vault, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise ValueError('immutable snapshot collision')
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(data)
        manifest['snapshots'][key] = {'identity': identity(e), 'path': relative, 'sha256': checksum,
            'scope': scope, 'capture_status': 'baseline_matched_redacted', 'redaction_version': 1,
            'captured_at': datetime.now(timezone.utc).isoformat(), 'baseline_recovery': provenance}
    destination = inside(vault, MANIFEST)
    staging = destination.with_suffix('.tmp')
    staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    staging.replace(destination)
    relink(vault, cards, manifest)
    return {'status': 'captured', 'cards': len(cards), 'new_snapshots': len(pending), 'snapshots': len(manifest['snapshots'])}


def relink(vault, cards, manifest):
    for card in cards:
        files = [inside(vault, folder+'/'+card['id']+'.md') for folder in ('03_知识卡片', '04_风险与差异')]
        path = next((p for p in files if p.exists()), None)
        if path is None:
            continue
        links = []
        for i, e in enumerate(card['evidence'], 1):
            result = verify_snapshot(vault, e, manifest)
            if not result or result['verification'] != 'verified':
                raise ValueError('cannot link unverified snapshot')
            item = manifest['snapshots'][evidence_key(e)]
            links.append(f'- [证据 {i}：冻结快照](../{item["path"]})；原版本哈希 `{e["source_sha256"]}`。')
        content = path.read_text(encoding='utf-8')
        section = '## 主要证据（库内快照）\n\n'+ '\n'.join(links)+'\n\n快照只证明收录版本；原代码地址仅供追溯和发现更新，不是使用本卡的必要条件。\n\n'
        content = re.sub(r'\n*## 主要证据（库内快照）\n.*?(?=\n## |\Z)', '', content, flags=re.S)
        # Existing source links remain optional; primary links are portable.
        content = content.replace('## 来源\n', '## 原始来源（可选追溯）\n')
        first_section = content.find('\n## ')
        if first_section >= 0:
            content = content[:first_section].rstrip()+'\n\n'+section.rstrip()+'\n\n'+content[first_section:].lstrip()
        else:
            content += '\n\n'+section
        path.write_text(content, encoding='utf-8')


def validate(vault, check_links=True):
    manifest = load_manifest(vault)
    cards = [json.loads(line) for line in inside(vault, '90_机器索引/knowledge.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    failures = []
    for card in cards:
        pages = [inside(vault, folder+'/'+card['id']+'.md') for folder in ('03_知识卡片', '04_风险与差异')]
        page = next((p for p in pages if p.exists()), None)
        text = page.read_text(encoding='utf-8') if page else ''
        for e in card['evidence']:
            result = verify_snapshot(vault, e, manifest)
            if not result or result['verification'] != 'verified':
                failures.append({'card': card['id'], 'verification': (result or {}).get('verification', 'snapshot_missing')})
            elif check_links and '../'+manifest['snapshots'][evidence_key(e)]['path'] not in text:
                failures.append({'card': card['id'], 'verification': 'primary_snapshot_link_missing'})
    return {'status': 'failed' if failures else 'passed', 'cards': len(cards), 'evidence': sum(len(c['evidence']) for c in cards), 'failures': failures}


def refresh_existing_links(vault):
    """Rebuilders may relink frozen cards, but cannot silently capture new baselines."""
    manifest = load_manifest(vault)
    if not manifest['snapshots']:
        return
    cards = [json.loads(line) for line in inside(vault, '90_机器索引/knowledge.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    frozen = [c for c in cards if all(evidence_key(e) in manifest['snapshots'] for e in c['evidence'])]
    relink(Path(vault), frozen, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['capture', 'validate', 'relink'])
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else {}
    vault = args.vault or config.get('vault')
    if not vault:
        parser.error('--vault or --config required')
    config['vault'] = str(vault)
    if args.command == 'capture':
        result = capture(config)
    else:
        result = validate(vault, check_links=args.command != 'relink')
        if args.command == 'relink' and result['status'] == 'passed':
            cards = [json.loads(line) for line in inside(vault, '90_机器索引/knowledge.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            relink(Path(vault), cards, load_manifest(vault))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(result['status'] == 'failed')


if __name__ == '__main__':
    main()
