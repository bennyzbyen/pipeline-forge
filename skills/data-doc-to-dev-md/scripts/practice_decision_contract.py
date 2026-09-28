"""Optional practice decisions in existing facts; legacy handoffs remain valid."""
import re


def validate_practice_decisions(payload):
    errors = []
    rows = payload.get('practice_decisions', [])
    version = payload.get('practice_decisions_version')
    if 'practice_decisions' not in payload and version is None: return {'errors': []}
    if type(version) is not int or version != 1 or not isinstance(rows, list):
        return {'errors': ['practice_decisions requires version 1 and a list']}
    units_payload = payload.get('code_units')
    known = {u.get('code_unit_id') for u in units_payload if isinstance(u, dict)} if isinstance(units_payload, list) else None
    seen = set()
    def nonempty(value): return isinstance(value, str) and bool(value.strip())
    def strings(value): return isinstance(value, list) and bool(value) and all(nonempty(v) for v in value)
    def sha(value): return isinstance(value, str) and bool(re.fullmatch('[a-f0-9]{64}', value))
    for row in rows:
        if not isinstance(row, dict):
            errors.append('practice decision must be an object'); continue
        ident = row.get('id')
        if not isinstance(ident, str) or not re.fullmatch('REV-[0-9]{3,}', ident) or ident in seen:
            errors.append('invalid or duplicate practice ID'); continue
        seen.add(ident)
        if row.get('decision') not in ('adopted', 'rejected', 'comparison') or not nonempty(row.get('reason')):
            errors.append(ident + ': decision and reason required')
        if row.get('decision') != 'adopted': continue
        if not sha(row.get('content_hash')) or not nonempty(row.get('knowledge_id')):
            errors.append(ident + ': review hash and anchor knowledge ID required')
        units = row.get('applies_to')
        if not strings(units) or (known is not None and not set(units).issubset(known)):
            errors.append(ident + ': valid code-unit bindings required')
        condition = row.get('condition_review')
        if not isinstance(condition, dict) or condition.get('status') != 'matched' or not all(nonempty(condition.get(k)) for k in ('condition', 'current_task_evidence', 'version_applicability')):
            errors.append(ident + ': explicit condition and version review required')
        validations = row.get('validations')
        if not isinstance(validations, list) or not validations:
            errors.append(ident + ': current-task validations required'); continue
        covered = set()
        for check in validations:
            if not isinstance(check, dict):
                errors.append(ident + ': invalid validation'); continue
            if not nonempty(check.get('report')) or not sha(check.get('sha256')) or not nonempty(check.get('behavior')):
                errors.append(ident + ': report hash and tested behavior required')
            if strings(check.get('applies_to')): covered.update(check['applies_to'])
            artifacts = check.get('artifact_hashes')
            if not isinstance(artifacts, dict) or not artifacts or not all(nonempty(k) and sha(v) for k, v in artifacts.items()):
                errors.append(ident + ': validated artifact hashes required')
        if strings(units) and not set(units).issubset(covered):
            errors.append(ident + ': validations do not cover adopted code units')
    return {'errors': errors}
