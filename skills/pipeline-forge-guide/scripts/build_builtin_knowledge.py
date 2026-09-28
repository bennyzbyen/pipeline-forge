"""Compile only the checked-in public rule catalog, never a user's private vault."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SOURCE = SKILL/'references/builtin-rules.json'
DESTINATION = SKILL/'assets/builtin-knowledge'


def compiled_files():
    source = SOURCE.read_bytes()
    catalog = json.loads(source.decode('utf-8-sig'))
    if catalog.get('version') != 1:
        raise ValueError('unsupported catalog version')
    files, rows, ids = {}, [], set()
    for card in catalog['cards']:
        key = card['id']
        if not re.fullmatch(r'PFB-\d{3,}', key) or key in ids:
            raise ValueError('invalid or duplicate bundled ID')
        ids.add(key)
        for field in ('title', 'claim', 'reuse', 'limits', 'target_skill', 'evaluation'):
            if not isinstance(card.get(field), str) or not card[field].strip():
                raise ValueError('missing rule field: ' + field)
        body = ('---\nid: '+key+'\n---\n# '+card['title']+'\n\n## Rule\n'+card['claim']+
                '\n\n## Applicability\n'+card['reuse']+'\n\n## Limits\n'+card['limits']+
                '\n\n## Verification\n'+card['evaluation']+'\n')
        relative = '03_知识卡片/'+key+'.md'
        data = body.encode('utf-8')
        files[relative] = data
        rows.append({**card, 'project': 'generic', 'kind': 'rule', 'status': 'reviewed_static',
                     'version_scope': 'bundled_generic_rules_v1', 'evidence': [
                         {'type': 'code', 'path': relative, 'start': 1, 'end': len(body.splitlines()),
                          'source_sha256': hashlib.sha256(data).hexdigest()}]})
    files['90_机器索引/knowledge.jsonl'] = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in rows).encode('utf-8')
    files['bundle.json'] = (json.dumps({'version': 1, 'source_sha256': hashlib.sha256(source).hexdigest(),
                                      'origin': catalog['origin'], 'card_count': len(rows)}, indent=2)+'\n').encode('utf-8')
    return files


def validate_bundle():
    files = compiled_files()
    actual = {p.relative_to(DESTINATION).as_posix() for p in DESTINATION.rglob('*') if p.is_file()}
    if actual != set(files):
        raise ValueError('bundled knowledge file set differs from public catalog')
    for name, data in files.items():
        path = DESTINATION/name
        if not path.resolve().is_relative_to(DESTINATION.resolve()) or path.read_bytes() != data:
            raise ValueError('bundled knowledge changed: '+name)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        for name, data in compiled_files().items():
            path = DESTINATION/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    count = validate_bundle()
    print(json.dumps({'status': 'passed', 'files': count, 'private_inputs_read': 0}))


if __name__ == '__main__':
    main()
