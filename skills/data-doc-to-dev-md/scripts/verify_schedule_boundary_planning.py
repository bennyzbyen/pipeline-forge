#!/usr/bin/env python3
"""Validate project boundary evidence; never impose fixed regression-fixture outcomes."""
import argparse
import copy
import json
from pathlib import Path
from code_unit_contract import apply_proposal, validate_code_unit_contract


def verify(facts):
    candidate = copy.deepcopy(facts)
    if not candidate.get('code_unit_plan'):
        apply_proposal(candidate)
    validation = validate_code_unit_contract(candidate)
    plan = candidate['code_unit_plan']
    errors = [{'code': 'BOUNDARY_CONTRACT_INVALID', 'message': e} for e in validation['errors']]
    if plan.get('confidence') not in ('low', 'medium', 'high'):
        errors.append({'code': 'BOUNDARY_CONFIDENCE_INVALID', 'message': 'Unsupported evidence confidence'})
    blockers = []
    for row in candidate.get('waterlines', []):
        missing = [k for k in ('algorithm_key', 'codegen_route', 'state_boundary', 'write_boundary',
                               'deployment_boundary', 'failure_boundary') if not row.get(k)]
        if missing:
            blockers.append({'code': 'BOUNDARY_EVIDENCE_MISSING', 'waterline_id': row['waterline_id'], 'fields': missing})
    if plan.get('status') != 'confirmed':
        blockers.append({'code': 'MAPPING_NOT_CONFIRMED'})
    for unit in candidate.get('code_units', []):
        if not unit.get('readiness', {}).get('ready_for_codegen'):
            blockers.append({'code': 'UNIT_NOT_READY', 'code_unit_id': unit['code_unit_id']})
    return {'status': 'failed' if errors or blockers else 'passed', 'check_kind': 'project_gate',
            'confidence': plan.get('confidence'), 'proposed_count': plan.get('proposed_count'),
            'errors': errors, 'blockers': blockers, 'blocks_codegen': bool(errors or blockers),
            'input_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.facts.read_text(encoding='utf-8-sig')))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        result = {'status': 'failed', 'check_kind': 'project_gate', 'blocks_codegen': True,
                  'errors': [{'code': 'BOUNDARY_INPUT_INVALID', 'message': str(error)}]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
