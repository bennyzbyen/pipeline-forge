"""Exercise plugin-only installation in a relocated home with no site packages."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from build_builtin_knowledge import validate_bundle
from portable_knowledge import audit_available, read_available


def run():
    validate_bundle()
    cases = []
    with tempfile.TemporaryDirectory(prefix='portable_rules_') as directory:
        root = Path(directory)
        skills = root/'installed plugin'/'skills'
        original = Path(__file__).resolve().parents[2]
        for name in ('pipeline-forge-guide', 'data-doc-to-dev-md'):
            shutil.copytree(original/name, skills/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        scripts = skills/'pipeline-forge-guide/scripts'
        env = dict(os.environ, CODEX_HOME=str(root/'empty-home'), PYTHONUTF8='1')
        config = root/'private.json'
        def cli(script, *args, expected=0):
            command = [sys.executable, '-S', str(scripts/script)]
            if script != 'dependency_doctor.py':
                command += ['--config', str(config)]
            result = subprocess.run(command + list(args), env=env, cwd=root, capture_output=True, text=True, encoding='utf-8')
            assert result.returncode == expected, result.stdout + result.stderr
            return json.loads(result.stdout)
        health = cli('knowledge_lookup.py', 'doctor')
        assert health['status'] == 'ready' and health['builtin']['indexed_cards'] == 9
        assert health['private_status'] == 'not_configured'
        cases.append('relocated plugin-only installation works without private config or third-party Python packages')
        found = cli('knowledge_lookup.py', 'search', '--query', 'watermark', '--project', 'new-project', '--version', 'working', '--role', 'producer')
        assert found['results'][0]['id'] == 'PFB-003' and not found['results'][0]['blockers']
        assert found['results'][0]['knowledge_origin'] == 'builtin'
        cases.append('generic rules work across task projects, years and roles without supplying business values')
        source_read = read_available(root/'missing.json', 'PFB-003')
        relocated = cli('knowledge_governance.py', 'read', '--id', 'PFB-003')
        assert relocated['content_hash'] == source_read['content_hash']
        # Windows runners may supply an 8.3 TEMP alias; the reader resolves it.
        # Compare the full relocated note, rather than the raw temp-directory text.
        expected_note = (skills/'pipeline-forge-guide/assets/builtin-knowledge/03_知识卡片/PFB-003.md').resolve()
        assert relocated['citation'] == f'[PFB-003](<{expected_note.as_posix()}>)'
        facts = {'knowledge_references_version': 1, 'knowledge_references': [{
            'id': 'PFB-003', 'decision': 'adopted', 'reason': 'synthetic matching watermark contract',
            **{f: source_read[f] for f in ('source_revision', 'content_hash', 'version_scope', 'citation', 'evidence_span')},
            'evidence_hashes': [e['expected_sha256'] for e in source_read['evidence']],
            'source_kind': 'target_rule', 'applies_to': ['unit-test'], 'adopted_rule': 'manual rerun preserves watermark',
            'validation_refs': ['verify_manual_rerun']} ]}
        facts_file = root/'facts.json'
        facts_file.write_text(json.dumps(facts), encoding='utf-8')
        assert cli('knowledge_governance.py', 'validate-refs', '--facts', str(facts_file))['status'] == 'passed'
        cases.append('stable evidence hashes and reference audits survive relocation')
        for bad in ('{bad', json.dumps({'vault': str(root/'missing-vault')})):
            config.write_text(bad, encoding='utf-8')
            found = cli('knowledge_lookup.py', 'search', '--query', 'watermark')
            assert found['private_status'] == 'unavailable' and found['results'][0]['id'] == 'PFB-003'
        cases.append('broken optional configuration leaves built-in retrieval intact')
        vault = root/'private-vault'
        index = vault/'90_机器索引'
        index.mkdir(parents=True)
        card = {'id': 'PFK-999', 'title': 'watermark private counterexample', 'project': 'specific', 'claim': 'synthetic alternative',
                'reuse': 'comparison', 'limits': 'specific task only', 'target_skill': 'data-sync-codegen', 'status': 'draft', 'evidence': []}
        (index/'knowledge.jsonl').write_text(json.dumps(card)+'\n', encoding='utf-8')
        config.write_text(json.dumps({'vault': str(vault)}), encoding='utf-8')
        found = cli('knowledge_lookup.py', 'search', '--query', 'watermark', '--detail', 'full')
        assert {r['knowledge_origin'] for r in found['results']} == {'builtin', 'private'}
        assert next(r for r in found['results'] if r['id'] == 'PFK-999')['reuse_decision'] == 'comparison_only'
        assert not (vault/'03_知识卡片').exists()
        cases.append('private evidence augments built-in results without overriding or writing back')
        card['id'] = 'PFB-003'
        (index/'knowledge.jsonl').write_text(json.dumps(card)+'\n', encoding='utf-8')
        found = cli('knowledge_lookup.py', 'search', '--ids', 'PFB-003')
        assert len(found['results']) == 1 and found['results'][0]['knowledge_origin'] == 'builtin'
        cases.append('private cards cannot impersonate built-in IDs')
        assert cli('dependency_doctor.py', '--feature', 'knowledge')['packages'] == []
        assert cli('dependency_doctor.py', '--feature', 'excel', expected=1)['status'] == 'missing_dependency'
        cases.append('feature dependency checks do not require office or test packages for knowledge')
        note = skills/'pipeline-forge-guide/assets/builtin-knowledge/03_知识卡片/PFB-003.md'
        note.write_text('tampered', encoding='utf-8')
        assert cli('knowledge_lookup.py', 'search', '--query', 'watermark')['status'] == 'knowledge_unavailable'
        cases.append('modified bundle is rejected instead of accepted as reviewed knowledge')
        broken = copy.deepcopy(facts)
        broken['knowledge_references'][0]['id'] = 'PFK-999'
        assert audit_available(root/'absent.json', broken)['status'] == 'review_required'
        cases.append('unavailable adopted private evidence never passes using built-in evidence')
    return {'status': 'passed', 'case_count': len(cases), 'cases': cases, 'network_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
