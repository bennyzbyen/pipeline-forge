"""Read optional implementation/function metadata from a private vault; never execute it."""
import ast
import json
import re
import textwrap

from knowledge_snapshots import inside

FUNCTION_LEDGER = '90_机器索引/function_review_ledger.json'
ACTIVE_LIFECYCLES = {'github_verified_snapshot', 'github_linked_local_snapshot'}
HISTORICAL_LIFECYCLE = 'historical_reference'


def load_function_reviews(vault, cards):
    path = inside(vault, FUNCTION_LEDGER)
    if not path.is_file():
        return {}
    ledger = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(ledger, dict) or ledger.get('schema_version') != 1 or not isinstance(ledger.get('functions'), list):
        raise ValueError('unsupported function review ledger')
    by_id = {c['id']: c for c in cards}
    result, seen = {}, set()
    for row in ledger['functions']:
        if not isinstance(row, dict) or row.get('card') not in by_id:
            raise ValueError('function review references an unknown card')
        span = row.get('source_lines')
        if (not isinstance(span, list) or len(span) != 2
                or any(type(i) is not int for i in span) or not 1 <= span[0] <= span[1]):
            raise ValueError('invalid function review span')
        if (not isinstance(row.get('function'), str)
                or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', row['function'])
                or row.get('function_name') != row['function'].split('.')[-1]
                or row.get('review_status') != 'reviewed_static'
                or not isinstance(row.get('observation'), str)
                or not isinstance(row.get('source_id'), str) or not row['source_id']
                or not isinstance(row.get('source_sha256'), str)
                or not re.fullmatch(r'[a-f0-9]{64}', row['source_sha256'])):
            raise ValueError('invalid function review record')
        inside(vault, row.get('evidence'))
        bindings = [e for e in by_id[row['card']]['evidence'] if e.get('path') == row['evidence']]
        bound = False
        for e in bindings:
            p = e.get('provenance', {})
            captured = p.get('source_line_span', [])
            if (p.get('source_id') == row.get('source_id')
                    and p.get('source_sha256') == row.get('source_sha256')
                    and isinstance(captured, list) and len(captured) == 2
                    and captured[0] <= span[0] <= span[1] <= captured[1]):
                bound = True
        key = (row['card'], row['source_id'], *span)
        if not bound or key in seen:
            raise ValueError('unbound or duplicate function review')
        seen.add(key)
        result.setdefault(row['card'], []).append(row)
    return result


def function_details(vault, records, checked):
    """Bind each reviewed function to verified frozen lines, without importing code."""
    if not records:
        return {'status': 'not_recorded', 'count': 0, 'functions': []}
    cache, functions, issues = {}, [], []
    for row in records:
        evidence = next((e for e in checked if e.get('path') == row['evidence']), {})
        try:
            if evidence.get('verification') != 'verified' or evidence.get('basis') != 'frozen_evidence':
                raise ValueError('function evidence not verified')
            if row['evidence'] not in cache:
                text = inside(vault, row['evidence']).read_text(encoding='utf-8-sig')
                cache[row['evidence']] = {int(m.group(1)): (i, m.group(2)) for i, line in enumerate(text.splitlines(), 1)
                                          if (m := re.match(r'L(\d+): (.*)', line))}
            lines = cache[row['evidence']]
            start, end = row['source_lines']
            tree = ast.parse(textwrap.dedent('\n'.join(lines[i][1] for i in range(start, end + 1))))
            if (len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef))
                    or tree.body[0].name != row['function_name'] or tree.body[0].end_lineno != end - start + 1):
                raise ValueError('function body does not match review span')
            path = inside(vault, row['evidence'])
            functions.append({**row, 'citation': f'[{row["function"]}](<{path.as_posix()}:{lines[start][0]}>)',
                              'verification': 'verified_frozen_function_body'})
        except (OSError, ValueError, KeyError, TypeError, SyntaxError, UnicodeError):
            issues.append({'function': row['function'], 'code': 'function_review_not_verified'})
    return {'status': 'review_required' if issues else 'verified_static', 'count': len(records),
            'functions': functions, 'issues': issues, 'deployment': 'not_established_by_static_code'}


def compatibility_profile(vault, cards, reviews, source_roots):
    embedded = [e for c in cards for e in c['evidence']]
    lifecycle_counts = {}
    for c in cards:
        key = c.get('lifecycle') or 'legacy_unspecified'
        lifecycle_counts[key] = lifecycle_counts.get(key, 0) + 1
    return {'lifecycle_counts': lifecycle_counts,
            'evidence_references': len(embedded),
            'default_history_policy': 'exclude_historical_primary_matches; explicit history and linked comparison retained',
            'implementation_contracts': sum(bool(c.get('implementation_contract')) for c in cards),
            'reviewed_function_records': sum(len(rows) for rows in reviews.values()),
            'evidence_mode': 'embedded_vault' if embedded and all(e.get('type') == 'embedded' and e.get('root') == 'vault' for e in embedded) else 'legacy_or_mixed',
            'configured_source_root_names': sorted(source_roots),
            'scope': 'indexed evidence and optional extensions; not business approval or whole-vault audit'}
