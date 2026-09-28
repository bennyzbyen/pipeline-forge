"""Offline regression for optional retrieval, provenance and entrypoint hooks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from knowledge_lookup import search


def run():
    script = Path(__file__).with_name('knowledge_lookup.py')
    cases = []
    with tempfile.TemporaryDirectory(prefix='knowledge_lookup_') as temporary:
        root = Path(temporary)
        vault = root/'wiki'
        index = vault/'90_机器索引'
        index.mkdir(parents=True)
        cards_dir = vault/'03_知识卡片'
        cards_dir.mkdir()
        source = root/'sources'
        source.mkdir()
        code = source/'job.py'
        code.write_text('# synthetic fixture\nvalue = 1\n', encoding='utf-8')
        sha = hashlib.sha256(code.read_bytes()).hexdigest()
        evidence = {'type': 'code', 'path': 'job.py', 'start': 1, 'end': 2, 'source_sha256': sha}
        old = {'id': 'PFK-001', 'title': '车辆核销 vehicle 写入', 'project': 'vehicle', 'claim': 'old source rule', 'reuse': 'compare source version',
               'limits': 'historical only', 'status': 'reviewed_static', 'kind': 'observed', 'target_skill': 'report-codegen',
               'version_scope': 'initial_production_sample_or_document_snapshot', 'evidence': [evidence], 'supplemented_by': ['PFW-001']}
        new = dict(old, id='PFW-001', project='datahub_vehicle_verification', title='vehicle realtime', claim='new working rule',
                   source_root='work_code', version_scope='working_tree_snapshot_not_deployment_proof', evidence=[dict(evidence, root='work_code')], updates=['PFK-001'], supplemented_by=[])
        rows = [old, new]
        def write_index():
            (index/'knowledge.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
            for row in rows:
                (cards_dir/(row['id']+'.md')).write_text(row['title'], encoding='utf-8')
        write_index()
        config = {'vault': str(vault), 'source_roots': {'historical': str(source), 'work_code': str(source)}}
        result = search(config, 'PFK-001', skill='report-codegen', project='车辆核销', version='working', limit=1)
        assert {r['id'] for r in result['results']} == {'PFK-001', 'PFW-001'}
        by_id = {r['id']: r for r in result['results']}
        assert by_id['PFK-001']['reuse_decision'] == 'comparison_only'
        assert by_id['PFW-001']['reuse_decision'] == 'requires_task_contract_review'
        assert by_id['PFW-001']['evidence'][0]['verification'] == 'verified'
        assert ':1>' in by_id['PFW-001']['evidence'][0]['citation']
        cases.append('related versions, Chinese project alias and verified citations')
        code.write_text('# edited source\nvalue = 2\n', encoding='utf-8')
        changed = search(config, 'vehicle')
        assert all(r['reuse_decision'] == 'comparison_only' for r in changed['results'])
        assert all(r['evidence'][0]['verification'] == 'source_changed' for r in changed['results'])
        cases.append('source drift never silently refreshes knowledge')
        assert search(config, 'unmatchable_xyz_987')['status'] == 'no_match'
        rows.append(dict(old, id='PFK-999', title='new_unique_fixture', supplemented_by=[]))
        write_index()
        assert search(config, 'new_unique_fixture')['results'][0]['id'] == 'PFK-999'
        cases.append('no-match and newly indexed cards without plugin reload')
        rows[-1]['evidence'] = [dict(evidence, path='../outside.py')]
        write_index()
        assert search(config, 'PFK-999')['results'][0]['evidence'][0]['verification'] == 'unreadable_or_unsafe_source'
        rows[-1]['evidence'] = [dict(evidence, path='missing.py')]
        rows[-1]['status'] = 'unreviewed'
        write_index()
        bad = search(config, 'PFK-999')['results'][0]
        assert 'knowledge_not_reviewed' in bad['blockers'] and bad['evidence'][0]['verification'] == 'missing_source'
        cases.append('unsafe paths, unavailable sources and unreviewed cards')
        config_file = root/'config.json'
        def cli():
            result = subprocess.run([sys.executable, str(script), '--config', str(config_file), 'search', '--query', 'vehicle', '--out', str(root/'result.json')], capture_output=True, text=True, encoding='utf-8')
            assert result.returncode == 0, result.stderr
            data = json.loads(result.stdout)
            assert data == json.loads((root/'result.json').read_text(encoding='utf-8'))
            return data
        assert cli()['private_status'] == 'not_configured'
        config_file.write_text('{broken', encoding='utf-8')
        assert cli()['private_status'] == 'unavailable'
        config_file.write_text(json.dumps(dict(config, vault=str(root/'missing'))), encoding='utf-8')
        assert cli()['private_status'] == 'unavailable'
        config_file.write_text(json.dumps(config), encoding='utf-8')
        (index/'knowledge.jsonl').write_text('{bad index', encoding='utf-8')
        assert cli()['private_status'] == 'unavailable'
        cases.append('no knowledge base, bad config, missing vault and corrupt index all degrade gracefully')
        (index/'knowledge.jsonl').write_text('[]\n', encoding='utf-8')
        assert cli()['private_status'] == 'unavailable'
        write_index()
        no_sources = search({'vault': str(vault)}, 'vehicle')
        assert all(r['reuse_decision'] == 'comparison_only' for r in no_sources['results'])
        cases.append('vault-only setup remains usable for comparisons')
    skills_root = script.parents[2]
    entries = list(skills_root.glob('*/SKILL.md'))
    assert len(entries) == 8
    for path in entries:
        text = path.read_text(encoding='utf-8')
        assert 'Optional Knowledge Assistance' in text and 'must not block' in text and 'knowledge_lookup.py search' in text, path
    cases.append('all eight skills have optional lookup and fallback routing')
    return {'status': 'passed', 'case_count': len(cases), 'cases': cases, 'external_service_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
