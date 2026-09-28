"""Synthetic private-vault practice discovery/adoption regression; no external services."""
import copy
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'data-doc-to-dev-md/scripts'))
from knowledge_lookup import digest
from knowledge_snapshots import capture, evidence_key, load_manifest
from practice_recommendations import audit, discover, read_review
from portable_knowledge import search_available
from practice_decision_contract import validate_practice_decisions


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


def run():
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); vault = root / 'vault'; source = root / 'source'
        source.mkdir(); (source / 'job.py').write_text('value = 1\n', encoding='utf-8')
        evidence = dict(type='code', path='job.py', start=1, end=1, source_sha256=digest(source / 'job.py'))
        card = dict(id='PFK-001', title='watermark fixture', claim='synthetic history', reuse='review first', limits='fixture only',
                    project='fixture', kind='observed', status='reviewed_static', target_skill='report-codegen',
                    version_scope='fixture_version', evidence=[evidence], recommended_reviews=['REV-001'])
        idx = vault / '90_机器索引'; idx.mkdir(parents=True)
        (idx / 'knowledge.jsonl').write_text(json.dumps(card) + '\n', encoding='utf-8')
        write(idx / 'document_manifest.json', [])
        note = vault / '03_知识卡片/PFK-001.md'; note.parent.mkdir(); note.write_text('# fixture\n', encoding='utf-8')
        config = {'vault': str(vault), 'source_roots': {'historical': str(source)}}
        capture(config)
        (vault / 'tools').mkdir()
        for name in ('recommended_patterns.py', 'verify_recommended_patterns.py'):
            (vault / 'tools' / name).write_text("raise RuntimeError('lookup must never execute this')\n", encoding='utf-8')
        validation = {'case': 'watermark', 'status': 'passed', 'assertions': ['fixture boundary']}
        report = {'status': 'passed', 'kind': 'synthetic_code_behavior', 'cases': [validation],
                  'implementation_sha256': digest(vault / 'tools/recommended_patterns.py'),
                  'test_sha256': digest(vault / 'tools/verify_recommended_patterns.py')}
        write(idx / 'recommended_behavior_results.json', report)
        snap = load_manifest(vault)['snapshots'][evidence_key(evidence)]
        review = dict(id='REV-001', cards=['PFK-001'], title='fixture', condition='writer acknowledges completion',
                      recommendation='commit watermark last', difference='explicit order', finding='partial failure possible', test='watermark',
                      evidence_status='frozen_static', improvement_status='synthetic_tests_passed', deployment_status='not_deployed',
                      evidence=[dict(card='PFK-001', path=snap['path'], sha256=snap['sha256'], source=evidence)], validation=validation)
        review_path = idx / 'reviews/REV-001.json'; write(review_path, review)
        cfg = root / 'config.json'; write(cfg, config)
        found = search_available(cfg, 'watermark', ids=['PFK-001'], detail='summary', version='all')
        practice = found['recommended_practices']['results'][0]
        assert practice['eligibility'] == 'requires_task_contract_review' and 'evidence' not in practice
        assert practice['validation']['executed_by_this_lookup'] is False
        cases.append('automatic practice discovery preserves summary limits and never executes vault code')
        match = dict(id='PFK-001', knowledge_origin='private', reuse_decision='comparison_only', blockers=['version_mismatch'])
        assert discover(config, [match])['results'][0]['eligibility'] == 'comparison_only'
        cases.append('comparison and version blockers never become adoptable practice matches')
        project = root / 'project'; project.mkdir()
        (project / 'job.py').write_text('value = 2\n', encoding='utf-8')
        write(project / 'validation.json', {'status': 'passed'})
        decision = dict(id='REV-001', knowledge_id='PFK-001', decision='adopted', reason='current explicit fixture contract',
                        content_hash=practice['content_hash'], applies_to=['unit-a'],
                        condition_review=dict(condition=review['condition'], status='matched', current_task_evidence='current fixture specification', version_applicability='fixture version'),
                        validations=[dict(behavior='manual refresh leaves watermark unchanged', applies_to=['unit-a'], report='validation.json',
                                          sha256=digest(project / 'validation.json'), artifact_hashes={'job.py': digest(project / 'job.py')})])
        facts = dict(practice_decisions_version=1, practice_decisions=[decision], code_units=[{'code_unit_id': 'unit-a'}], codegen_contract={'ready_for_codegen': False})
        before = copy.deepcopy(facts)
        assert audit(config, facts, project)['status'] == 'passed' and facts == before
        cases.append('task evidence and report bindings pass without changing readiness or input facts')
        for key in ('validations', 'condition_review'):
            broken = copy.deepcopy(facts); del broken['practice_decisions'][0][key]
            assert audit(config, broken, project)['status'] == 'review_required'
        broken = copy.deepcopy(facts); broken['practice_decisions'][0]['applies_to'] = ['unknown']
        assert audit(config, broken, project)['status'] == 'review_required'
        cases.append('missing applicability, missing project validation and unknown code units are rejected')
        (project / 'job.py').write_text('value = 3\n', encoding='utf-8')
        assert audit(config, facts, project)['affected'][0]['code_units'] == ['unit-a']
        (project / 'job.py').write_text('value = 2\n', encoding='utf-8')
        write(project / 'validation.json', {'status': 'failed'})
        broken = copy.deepcopy(facts); broken['practice_decisions'][0]['validations'][0]['sha256'] = digest(project / 'validation.json')
        assert audit(config, broken, project)['status'] == 'review_required'
        write(project / 'validation.json', {'status': 'passed'})
        cases.append('stale artifacts and failed task reports invalidate adopted practice')
        broken = copy.deepcopy(facts); broken['practice_decisions'][0]['validations'][0]['report'] = '../outside.json'
        assert audit(config, broken, project)['status'] == 'review_required'
        assert discover(config, [{**match, 'id': 'PFK-001'}])['results']
        try:
            read_review(config, '../escape', 'PFK-001')
            raise AssertionError('unsafe path accepted')
        except ValueError: pass
        cases.append('review IDs and task report paths cannot escape configured roots')
        review['condition'] = 'changed condition'; write(review_path, review)
        assert audit(config, facts, project)['status'] == 'review_required'
        review['condition'] = 'writer acknowledges completion'; write(review_path, review)
        snap_path = vault / snap['path']; saved = snap_path.read_bytes(); snap_path.write_bytes(b'changed')
        assert discover(config, [match])['results'][0]['eligibility'] == 'comparison_only'
        snap_path.write_bytes(saved)
        (vault / 'tools/recommended_patterns.py').write_text('# changed implementation\n', encoding='utf-8')
        assert 'stale' in discover(config, [match])['results'][0]['blockers'][0]
        cases.append('changed review, damaged evidence and stale synthetic records block adoption')
        assert validate_practice_decisions({}) == {'errors': []}
        assert validate_practice_decisions({'practice_decisions': {}})['errors']
        rejected = {'practice_decisions_version': 1, 'practice_decisions': [{'id': 'REV-001', 'decision': 'rejected', 'reason': 'wrong task scope'}]}
        assert audit(None, rejected, project)['status'] == 'passed'
        no_private = search_available(root / 'missing.json', 'watermark', detail='summary')
        assert no_private['recommended_practices']['status'] == 'not_configured' and no_private['results']
        cases.append('legacy handoffs, rejected decisions and plugin-only installations remain usable')
    return {'status': 'passed', 'case_count': len(cases), 'cases': cases, 'external_service_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
