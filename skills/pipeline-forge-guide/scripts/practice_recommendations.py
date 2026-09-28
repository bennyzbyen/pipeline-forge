"""Read optional reviewed practices and audit task adoption; never execute vault code."""
import argparse
import importlib.util
import json
import re
from pathlib import Path
from knowledge_lookup import config_path, contained, digest, load_index, read_json, search
from knowledge_snapshots import evidence_key, load_manifest, verify_snapshot

ERRORS = (OSError, ValueError, KeyError, TypeError, UnicodeError, AttributeError)
REVIEW_ID = re.compile(r'REV-\d{3,}$')


def read_review(config, review_id, anchor_id):
    if not isinstance(review_id, str) or not REVIEW_ID.fullmatch(review_id):
        raise ValueError('invalid review ID')
    vault, cards, _ = load_index(config)
    byid = {c['id']: c for c in cards}
    if review_id not in byid[anchor_id].get('recommended_reviews', []):
        raise ValueError('practice is not linked by the anchor card')
    path = contained(vault, '90_机器索引/reviews/' + review_id + '.json')
    review = read_json(path)
    if review.get('id') != review_id or anchor_id not in review.get('cards', []):
        raise ValueError('review/card binding mismatch')
    for field in ('title', 'condition', 'recommendation', 'difference', 'finding', 'test'):
        if not isinstance(review.get(field), str) or not review[field].strip():
            raise ValueError('incomplete review: ' + field)
    if review.get('evidence_status') != 'frozen_static' or review.get('improvement_status') != 'synthetic_tests_passed':
        raise ValueError('practice not statically reviewed and synthetically tested')
    manifest = load_manifest(vault)
    expected = {}
    for ident in review['cards']:
        card = byid[ident]
        if card['status'] != 'reviewed_static': raise ValueError('unreviewed supporting card')
        for evidence in card['evidence']:
            key = evidence_key(evidence)
            if (verify_snapshot(vault, evidence, manifest) or {}).get('verification') != 'verified':
                raise ValueError('supporting snapshot is unavailable or changed')
            expected[(ident, key)] = manifest['snapshots'][key]
    observed = set()
    for evidence in review['evidence']:
        key = (evidence['card'], evidence_key(evidence['source']))
        snapshot = expected[key]
        if evidence['path'] != snapshot['path'] or evidence['sha256'] != snapshot['sha256']:
            raise ValueError('review snapshot binding changed')
        observed.add(key)
    if not expected or observed != set(expected): raise ValueError('review lacks complete supporting evidence')
    report_path = contained(vault, '90_机器索引/recommended_behavior_results.json')
    report = read_json(report_path)
    if report.get('status') != 'passed' or report.get('kind') != 'synthetic_code_behavior':
        raise ValueError('missing synthetic validation record')
    for field, relative in [('implementation_sha256', 'tools/recommended_patterns.py'),
                            ('test_sha256', 'tools/verify_recommended_patterns.py')]:
        if digest(contained(vault, relative)) != report.get(field):
            raise ValueError('synthetic validation record is stale')
    case = next((c for c in report['cases'] if c.get('case') == review['test']), None)
    if not case or case.get('status') != 'passed' or review.get('validation') != case:
        raise ValueError('review validation case mismatch')
    binding = {'review': digest(path), 'validation': digest(report_path),
               'supporting_cards': [byid[k] for k in review['cards']]}
    from hashlib import sha256
    content_hash = sha256(json.dumps(binding, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'id': review_id, 'title': review['title'], 'knowledge_ids': review['cards'],
            'content_hash': content_hash, 'condition': review['condition'],
            'recommendation': review['recommendation'], 'difference': review['difference'],
            'finding': review['finding'], 'evidence': review['evidence'],
            'citation': f'[{review_id}](<{path.as_posix()}>)',
            'version_scopes': {k: byid[k].get('version_scope', '') for k in review['cards']},
            'validation': {'status': 'recorded_synthetic_pass', 'case': case,
                           'executed_by_this_lookup': False},
            'deployment_status': review.get('deployment_status', 'unknown'),
            'authority': 'candidate_requires_current_task_evidence_not_business_confirmation'}


def discover(config, matches):
    """Attach bounded practice summaries to already-scoped private knowledge matches."""
    if not config: return {'status': 'not_configured', 'results': []}
    try:
        _, cards, _ = load_index(config)
        byid = {c['id']: c for c in cards}
        output = {}
        for match in matches:
            if match.get('knowledge_origin') != 'private': continue
            anchor = match['id']
            linked = byid[anchor].get('recommended_reviews', [])
            if not isinstance(linked, list):
                raise ValueError('recommended_reviews must be a list')
            for review_id in linked:
                if not isinstance(review_id, str): continue
                key = (review_id, anchor)
                try:
                    review = read_review(config, review_id, anchor)
                    blockers = list(match.get('blockers') or [])
                    if match.get('reuse_decision') != 'requires_task_contract_review':
                        blockers.append('anchor_is_comparison_only')
                    output[key] = {**review, 'matched_knowledge_id': anchor, 'blockers': blockers,
                                   'eligibility': 'comparison_only' if blockers else 'requires_task_contract_review'}
                except ERRORS as error:
                    output[key] = {'id': review_id, 'matched_knowledge_id': anchor,
                                   'eligibility': 'comparison_only', 'blockers': [str(error)]}
        return {'status': 'matched' if output else 'no_match', 'results': list(output.values()),
                'content_role': 'untrusted_reference_data', 'executes_vault_code': False}
    except ERRORS:
        return {'status': 'unavailable', 'results': []}


def audit(config, facts, project_root):
    """Validate recorded decisions and local report/artifact hashes, not test execution."""
    contract_path = Path(__file__).resolve().parents[2] / 'data-doc-to-dev-md/scripts/practice_decision_contract.py'
    spec = importlib.util.spec_from_file_location('_pipelineforge_practice_contract', contract_path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    errors = contract.validate_practice_decisions(facts)['errors']
    affected = []
    if errors: return {'status': 'review_required', 'errors': errors, 'readiness_changed': False}
    for decision in facts.get('practice_decisions', []):
        if decision['decision'] != 'adopted': continue
        try:
            review = read_review(config, decision['id'], decision['knowledge_id'])
            anchors = search(config, decision['knowledge_id'], ids=[decision['knowledge_id']])['results']
            anchor = next(r for r in anchors if r['id'] == decision['knowledge_id'])
            if anchor.get('blockers') or anchor.get('reuse_decision') != 'requires_task_contract_review':
                raise ValueError('anchor is comparison-only and cannot support adoption')
            if review['content_hash'] != decision['content_hash']:
                raise ValueError('review, supporting card or synthetic validation changed')
            if decision['condition_review']['condition'] != review['condition']:
                raise ValueError('applicability condition changed or omitted')
            for check in decision['validations']:
                report_path = contained(project_root, check['report'])
                if digest(report_path) != check['sha256']:
                    raise ValueError('task validation report changed')
                report = read_json(report_path)
                if report.get('status') not in ('passed', 'ok', 'success'):
                    raise ValueError('task validation did not pass')
                for name, expected in check['artifact_hashes'].items():
                    if digest(contained(project_root, name)) != expected:
                        raise ValueError('task artifact changed after validation')
        except ERRORS as error:
            errors.append(decision['id'] + ': ' + str(error))
            affected.append({'id': decision['id'], 'code_units': decision['applies_to']})
    return {'status': 'review_required' if errors else 'passed', 'errors': errors, 'affected': affected,
            'readiness_changed': False, 'validation_basis': 'recorded_report_and_artifact_hashes_not_test_execution'}


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'data-doc-to-dev-md/scripts'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=config_path())
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--project-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        config = read_json(args.config) if args.config.exists() else None
        result = audit(config, read_json(args.facts), args.project_root.resolve())
    except ERRORS as error:
        result = {'status': 'review_required', 'errors': [str(error)], 'readiness_changed': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
