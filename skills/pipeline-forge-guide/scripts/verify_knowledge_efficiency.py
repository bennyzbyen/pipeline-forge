"""Offline progressive retrieval, scope and I/O regression using synthetic evidence."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import knowledge_lookup as lookup
from knowledge_snapshots import capture, sha


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        vault = root/'vault'
        index = vault/'90_机器索引'
        index.mkdir(parents=True)
        (vault/'03_知识卡片').mkdir()
        sources = root/'sources'
        sources.mkdir()
        source = sources/'fixture.py'
        source.write_text('value = 1\n', encoding='utf-8')
        evidence = dict(type='code', path=source.name, start=1, end=1, source_sha256=sha(source.read_bytes()))
        def card(key, title, project, **extra):
            return dict(id=key, title=title, project=project, claim=title,
                        reuse='confirm task contract', limits='Never assume schema or deployment.',
                        status='reviewed_static', kind='observed', target_skill='data-sync-codegen / report-codegen',
                        evidence=[evidence], **extra)
        cards = [card('PFK-001', '车辆核销 historical vehicle', 'vehicle', supplemented_by=['PFW-001']),
                 card('PFW-001', '车辆核销 realtime vehicle', 'datahub_vehicle_verification', updates=['PFK-001'], source_root='work_code'),
                 card('PFW-002', 'QAS 反馈提交水位', 'datahub_qas'),
                 card('PFW-003', 'FMOS 快照 manifest', 'fmos')]
        (index/'knowledge.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cards), encoding='utf-8')
        (index/'document_manifest.json').write_text('[]', encoding='utf-8')
        (index/'usage_context.json').write_text('{}', encoding='utf-8')
        for c in cards:
            (vault/'03_知识卡片'/f'{c["id"]}.md').write_text('# Fixture\n', encoding='utf-8')
        config = {'vault': str(vault), 'source_roots': {'historical': str(sources)}}
        capture(config)
        # Default frozen retrieval must not open originals, even when configured.
        with patch.object(lookup, 'check_original_evidence', side_effect=AssertionError('original opened')):
            with patch.object(lookup, 'read_json', wraps=lookup.read_json) as reader:
                summary = lookup.search(config, 'vehicle', detail='summary', limit=1, version='working')
                assert sum(Path(call.args[0]).name == 'usage_context.json' for call in reader.call_args_list) == 1
        full = lookup.search(config, 'vehicle', limit=1, version='working')
        assert len(summary['results']) == 2 and summary['linked_count'] == 1
        for small, large in zip(summary['results'], full['results']):
            for key in ('id', 'limits', 'blockers', 'reuse_decision', 'updates', 'supplemented_by'):
                assert small[key] == large[key], key
            assert all(e['origin_verification'] == 'not_checked' for e in small['evidence'])
        assert len(json.dumps(summary)) < len(json.dumps(full))
        exact = lookup.search(config, 'PFW-002', ids=['PFW-002'])
        assert [r['id'] for r in exact['results']] == ['PFW-002']
        strict = lookup.search(config, 'vehicle QAS', project='vehicle', skill='report-codegen', strict_scope=True, limit=1)
        assert {r['id'] for r in strict['results']} == {'PFK-001', 'PFW-001'}
        assert lookup.search(config, 'vehicle', skill='db-ddl-generator-skill', strict_scope=True)['status'] == 'no_match'
        for query, expected in [('QAS 反馈 水位', 'PFW-002'), ('FMOS 快照 manifest', 'PFW-003')]:
            assert lookup.search(config, query)['results'][0]['id'] == expected
        assert lookup.search(config, 'unmatchable_xyz_987')['status'] == 'no_match'
        source.write_text('value = 2\n', encoding='utf-8')
        audited = lookup.search(config, 'PFW-002', ids=['PFW-002'], audit_originals=True)
        assert audited['results'][0]['evidence'][0]['origin']['verification'] == 'source_changed'
        assert audited['results'][0]['evidence'][0]['verification'] == 'verified'
        configuration = root/'config.json'
        configuration.write_text(json.dumps(config), encoding='utf-8')
        def cli(*args):
            run = subprocess.run([sys.executable, '-B', str(Path(lookup.__file__)), '--config', str(configuration), 'search', *args],
                                 capture_output=True, text=True, encoding='utf-8', check=True)
            return json.loads(run.stdout)
        assert cli('--query', 'QAS')['detail'] == 'summary'
        assert cli('--ids', 'PFW-002', '--detail', 'full')['results'][0]['evidence'][0]['citation']
        assert cli('--ids', 'PFW-999')['status'] == 'knowledge_unavailable'
        manifest = json.loads((index/'evidence_snapshots.json').read_text(encoding='utf-8'))
        snapshot = vault/next(iter(manifest['snapshots'].values()))['path']
        snapshot.write_text('corrupt', encoding='utf-8')
        bad = lookup.search(config, 'PFW-002', ids=['PFW-002'], detail='summary')['results'][0]
        assert bad['reuse_decision'] == 'comparison_only'
        assert 'source_evidence_not_verified' in bad['blockers']
    print(json.dumps({'status':'passed', 'cases':['summary preserves constraints and linked versions',
        'exact ID expansion', 'one context load per query', 'no original I/O by default',
        'explicit source drift audit', 'strict project/skill primary scope', 'lexical relevance and no-match',
        'CLI summary/full and unknown IDs', 'corruption remains blocked in summary']}, indent=2))


if __name__ == '__main__':
    main()
