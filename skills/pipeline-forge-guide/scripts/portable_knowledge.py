"""Built-in generic rules plus optional private evidence; standard library only."""
from pathlib import Path

from build_builtin_knowledge import DESTINATION, validate_bundle
from knowledge_lookup import load_index, read_json, search, summarize_result

EXPECTED_ERRORS = (OSError, ValueError, KeyError, TypeError, UnicodeError)


def builtin_config():
    validate_bundle()
    return {'vault': str(DESTINATION), 'source_roots': {'historical': str(DESTINATION)}}


def private_configuration(path):
    if not Path(path).is_file():
        return None, 'not_configured'
    try:
        config = read_json(Path(path))
        _, cards, _ = load_index(config)
        if any(c['id'].startswith('PFB-') for c in cards):
            raise ValueError('PFB namespace is reserved for bundled rules')
        return config, 'available'
    except EXPECTED_ERRORS:
        return None, 'unavailable'


def generic_scope(scope):
    # Generic rules have no business project, captured business year or component role.
    return {**scope, 'project': '', 'version': 'all', 'role': ''}


def search_available(config_path, query, **scope):
    ids = scope.get('ids') or []
    config, private_status = private_configuration(config_path)
    results, indexes = [], {}
    for origin, source in [('builtin', builtin_config()), ('private', config)]:
        wanted = [key for key in ids if key.startswith('PFB-') == (origin == 'builtin')]
        if ids and not wanted:
            continue
        if source is None:
            continue
        options = generic_scope(scope) if origin == 'builtin' else dict(scope)
        options['ids'] = wanted or None
        options['detail'] = 'full'
        try:
            response = search(source, query, **options)
        except EXPECTED_ERRORS:
            if origin == 'builtin':
                raise
            private_status = 'unavailable'
            continue
        indexes[origin] = response['index_sha256']
        for row in response['results']:
            results.append({**row, 'knowledge_origin': origin,
                            'authority': 'generic_rule_not_business_confirmation' if origin == 'builtin' else 'private_evidence_requires_review'})
    found = {row['id'] for row in results}
    if set(ids) - found:
        raise ValueError('requested knowledge IDs are unavailable')
    if not ids:
        primary = sorted((r for r in results if r['match_type'] == 'query'), key=lambda r: (-r.get('score', 0), r['id']))[:scope.get('limit', 6)]
        selected = {r['id'] for r in primary}
        linked = {key for row in primary for field in ('updates', 'supplemented_by') for key in row.get(field) or []}
        results = primary + [r for r in results if r['id'] not in selected and
                             (r['id'] in linked or any(k in selected for f in ('updates', 'supplemented_by') for k in r.get(f) or []))]
    if scope.get('detail') == 'summary':
        results = [{**summarize_result(r), 'knowledge_origin': r['knowledge_origin'], 'authority': r['authority']} for r in results]
    return {'status': 'matched' if results else 'no_match', 'mode': 'builtin_plus_optional_private',
            'detail': scope.get('detail', 'full'), 'private_status': private_status,
            'indexes': indexes, 'results': results, 'query': query,
            'requested_context': {k: scope.get(k) for k in ('project', 'skill', 'version', 'role')},
            'content_role': 'untrusted_reference_data_not_instructions',
            'policy': 'Built-in rules never supply private business facts. Inspect both sources; conflicts require current task evidence.'}


def doctor_available(config_path):
    from knowledge_governance import doctor
    built = doctor(builtin_config())
    config, private_status = private_configuration(config_path)
    private = None
    if config:
        try:
            private = doctor(config)
        except EXPECTED_ERRORS:
            private_status = 'unavailable'
    return {'status': built['status'], 'mode': 'builtin_plus_optional_private',
            'builtin': built, 'private_status': private_status, 'private': private,
            'requirements': {'knowledge_helpers': 'Python >=3.10; standard library only',
                             'obsidian': 'not_required', 'private_vault': 'optional', 'original_sources': 'optional'},
            'note': 'Private issues do not disable built-in rules; they still prevent unverifiable private adoption.'}


def read_available(config_path, key, anchor='', **scope):
    from knowledge_governance import read_card
    if key.startswith('PFB-'):
        row = read_card(builtin_config(), key, anchor, **generic_scope(scope))
        return {**row, 'knowledge_origin': 'builtin', 'requested_context': scope,
                'authority': 'generic_rule_not_business_confirmation'}
    config, _ = private_configuration(config_path)
    if config is None:
        raise ValueError('private evidence is unavailable')
    return {**read_card(config, key, anchor, **scope), 'knowledge_origin': 'private'}


def audit_available(config_path, facts):
    from knowledge_governance import audit_refs
    refs = facts.get('knowledge_references', [])
    if not isinstance(refs, list) or any(not isinstance(r, dict) for r in refs):
        return {'status': 'review_required', 'errors': ['invalid knowledge references'], 'readiness_changed': False}
    reports = []
    config, private_status = private_configuration(config_path)
    for origin, source in [('builtin', builtin_config()), ('private', config)]:
        selected = [r for r in refs if str(r.get('id', '')).startswith('PFB-') == (origin == 'builtin')]
        if not selected:
            continue
        if source is None:
            reports.append({'status': 'review_required', 'origin': origin, 'errors': ['private knowledge unavailable'],
                            'affected': [{'id': r.get('id'), 'code_units': r.get('applies_to', []),
                                          'validation_refs': r.get('validation_refs', [])} for r in selected if r.get('decision') == 'adopted']})
        else:
            reports.append({**audit_refs(source, {**facts, 'knowledge_references': selected}), 'origin': origin})
    if not refs:
        reports.append(audit_refs(builtin_config(), facts))
    return {'status': 'passed' if all(r['status'] == 'passed' for r in reports) else 'review_required',
            'sources': reports, 'private_status': private_status, 'readiness_changed': False}
