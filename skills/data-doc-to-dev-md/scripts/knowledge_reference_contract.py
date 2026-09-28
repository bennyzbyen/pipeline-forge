"""Versioned optional knowledge evidence in existing structured facts (offline)."""
import re


def validate_knowledge_references(payload):
    """Never promote readiness; legacy records remain readable but unaudited."""
    errors, warnings = [], []
    refs = payload.get('knowledge_references', [])
    version = payload.get('knowledge_references_version')
    if not isinstance(refs, list):
        return {'errors': ['knowledge_references must be a list'], 'warnings': []}
    if version is None:
        if refs:
            warnings.append('Legacy knowledge references are readable but require v1 migration before audited adoption.')
        return {'errors': errors, 'warnings': warnings}
    if type(version) is not int or version != 1:
        return {'errors': ['Unsupported knowledge_references_version'], 'warnings': []}
    seen = set()
    units = payload.get('code_units')
    known_units = {unit.get('code_unit_id') for unit in units if isinstance(unit, dict)} if isinstance(units, list) else None
    for i, ref in enumerate(refs):
        prefix = 'knowledge_references[%d]' % i
        if not isinstance(ref, dict):
            errors.append(prefix + ' must be an object')
            continue
        key = ref.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'PF[BKW]-\d{3,}', key):
            errors.append(prefix + '.id is invalid')
        elif key in seen:
            errors.append(prefix + '.id is duplicated; group unit bindings in applies_to')
        else:
            seen.add(key)
        if ref.get('decision') not in ('adopted', 'comparison', 'rejected'):
            errors.append(prefix + '.decision is invalid')
        for field in ('reason',):
            if not isinstance(ref.get(field), str) or not ref[field].strip():
                errors.append(prefix + '.' + field + ' is required')
        if ref.get('decision') != 'adopted':
            continue
        for field in ('source_revision', 'evidence_span', 'adopted_rule', 'citation', 'version_scope'):
            if not isinstance(ref.get(field), str) or not ref[field].strip():
                errors.append(prefix + '.' + field + ' is required for adoption')
        if not isinstance(ref.get('content_hash'), str) or not re.fullmatch(r'[0-9a-f]{64}', ref['content_hash']):
            errors.append(prefix + '.content_hash must be the returned SHA-256')
        for field in ('applies_to', 'validation_refs', 'evidence_hashes'):
            values = ref.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                errors.append(prefix + '.' + field + ' must be a nonempty string list')
            elif field == 'evidence_hashes' and any(not re.fullmatch(r'[0-9a-f]{64}', v) for v in values):
                errors.append(prefix + '.evidence_hashes contains an invalid SHA-256')
            elif field == 'applies_to' and known_units is not None and any(v not in known_units for v in values):
                errors.append(prefix + '.applies_to names an unknown code unit')
        if ref.get('source_kind') not in ('target_rule', 'observed_state', 'historical_experience'):
            errors.append(prefix + '.source_kind must distinguish target, observed or historical evidence')
    return {'errors': errors, 'warnings': warnings}
