"""Revise execution contracts within an already-confirmed mapping; no new confirmation."""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from code_unit_contract import validate_code_unit_contract, derive_waterlines, evidence_fingerprint, _contract_complete, _combined_execution_contract


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def revise(facts, change, *, require_user_confirmation=False):
    plan = facts.get('code_unit_plan', {})
    if plan.get('status') != 'confirmed' or not plan.get('confirmation_audit'):
        raise ValueError('REVISION_FIRST_CONFIRMATION_REQUIRED')
    first = plan['confirmation_audit'][0]
    if first.get('action') != 'confirmed_code_unit_mapping' or not first.get('actor') or not first.get('mapping'):
        raise ValueError('REVISION_FIRST_CONFIRMATION_INVALID')
    if require_user_confirmation and first['actor'] != 'user':
        raise ValueError('REVISION_EXPLICIT_USER_FIRST_CONFIRMATION_REQUIRED')
    if validate_code_unit_contract(facts)['status'] != 'passed':
        raise ValueError('REVISION_BASE_CONTRACT_INVALID')
    if change.get('base_sha256') != fingerprint(facts):
        raise ValueError('REVISION_STALE_BASE')
    authorization = change.get('authorization', {})
    if not isinstance(authorization, dict) or not all(isinstance(authorization.get(k), str) and authorization[k].strip()
                                                   for k in ('actor', 'evidence', 'reason')):
        raise ValueError('REVISION_AUTHORIZATION_REQUIRED')
    edits = change.get('unit_changes')
    if not isinstance(edits, list) or not edits:
        raise ValueError('REVISION_UNIT_CHANGES_REQUIRED')
    result = copy.deepcopy(facts)
    units = {u['code_unit_id']: u for u in result['code_units']}
    waterlines = {w['waterline_id']: w for w in result['waterlines']}
    affected = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'code_unit_id', 'execution_contract', 'waterline_contracts'}:
            raise ValueError('REVISION_EXECUTION_ONLY; mapping and boundary changes require normal planning')
        ident = edit['code_unit_id']
        if ident not in units or ident in affected:
            raise ValueError('REVISION_UNKNOWN_OR_DUPLICATE_UNIT')
        unit = units[ident]
        contracts = edit['waterline_contracts']
        if not isinstance(contracts, dict) or set(contracts) != set(unit['covered_waterlines']):
            raise ValueError('REVISION_WATERLINE_COVERAGE_MISMATCH')
        for name, contract in contracts.items():
            if not isinstance(contract, dict) or not contract:
                raise ValueError('REVISION_INVALID_EXECUTION_CONTRACT')
            owners = [u for u in units.values() if name in u['covered_waterlines']]
            if len(owners) != 1:
                raise ValueError('REVISION_SHARED_WATERLINE_REQUIRES_EXPLICIT_REPLAN')
            waterlines[name]['execution_contract'] = copy.deepcopy(contract)
        contract = edit['execution_contract']
        if not isinstance(contract, dict) or not contract:
            raise ValueError('REVISION_INVALID_EXECUTION_CONTRACT')
        derived = _combined_execution_contract([{'execution_contract': c} for c in contracts.values()])
        if contract != derived:
            raise ValueError('REVISION_DERIVED_CONTRACT_MISMATCH')
        unit['execution_contract'] = copy.deepcopy(contract)
        for field in ('state', 'retry', 'rerun', 'empty_output_semantics', 'failure_semantics'):
            unit[field] = copy.deepcopy(contract.get(field) or {})
        blockers = list(dict.fromkeys(unit.get('blockers', []) + _contract_complete(contract, unit['codegen_route'])))
        unit['blockers'] = blockers
        unit['readiness'] = {'ready_for_codegen': not blockers, 'blockers': blockers}
        affected.append(ident)
    # Recompute derived evidence without invoking confirm() or rewriting its audit.
    current_fingerprint = evidence_fingerprint(derive_waterlines(result))
    for name in ('code_unit_plan', 'project_contract'):
        result[name]['boundary_evidence_fingerprint'] = current_fingerprint
        for binding in result[name].get('confirmed_mapping', []):
            if binding['code_unit_id'] in affected:
                binding['ready_for_codegen'] = units[binding['code_unit_id']]['readiness']['ready_for_codegen']
    ready = all(u['readiness']['ready_for_codegen'] for u in units.values())
    result['project_contract']['overall_readiness'] = 'ready_for_codegen' if ready else 'partially_blocked'
    if isinstance(result.get('codegen_contract'), dict):
        result['codegen_contract']['ready_for_codegen'] = ready
    impacted = set(affected)
    owner = {w: u['code_unit_id'] for u in units.values() for w in u['covered_waterlines']}
    while True:
        expanded = impacted | {u['code_unit_id'] for u in units.values()
                               if any(owner.get(d, d) in impacted for d in u.get('depends_on', []))}
        if expanded == impacted:
            break
        impacted = expanded
    result.setdefault('revision_audit', []).append({
        'timestamp': datetime.now(timezone.utc).isoformat(), 'authorization': copy.deepcopy(authorization),
        'base_sha256': change['base_sha256'], 'change_sha256': fingerprint(edits),
        'affected_units': affected, 'revalidate_units': sorted(impacted),
        'validation_status': 'pending', 'original_confirmation_preserved': True})
    check = validate_code_unit_contract(result)
    if check['status'] != 'passed':
        raise ValueError('REVISION_INVALID: ' + '; '.join(check['errors']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--change', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--require-user-confirmation', action='store_true', help='Enforce a project rule requiring explicit first user confirmation.')
    args = parser.parse_args()
    try:
        result = revise(json.loads(args.facts.read_text(encoding='utf-8-sig')),
                        json.loads(args.change.read_text(encoding='utf-8-sig')), require_user_confirmation=args.require_user_confirmation)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        stage = args.out.with_name(args.out.name + '.revision.tmp')
        with stage.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        stage.replace(args.out)
        print(json.dumps({'status': 'revised_validation_pending', **result['revision_audit'][-1]}, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
