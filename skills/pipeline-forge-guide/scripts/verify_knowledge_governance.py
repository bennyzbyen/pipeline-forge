"""Offline tests for traceability, selective invalidation and knowledge boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from knowledge_governance import audit_refs, changes, doctor, inventory, read_card
from knowledge_lookup import search


def run():
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        vault = root/'vault'
        index = vault/'90_机器索引'
        index.mkdir(parents=True)
        notes = vault/'03_知识卡片'
        notes.mkdir()
        source = root/'source'
        source.mkdir()
        code = source/'job.py'
        code.write_text('value = 1\n', encoding='utf-8')
        sha = hashlib.sha256(code.read_bytes()).hexdigest()
        card = {'id': 'PFK-001', 'title': '同步 rowkey_rule_columns 42', 'project': 'test',
                'status': 'reviewed_static', 'claim': 'manual rerun preserves watermark',
                'reuse': 'explicit period only', 'limits': 'historical fixture only',
                'target_skill': 'data-sync-codegen', 'version_scope': 'fixture-v1',
                'evidence': [{'type': 'code', 'path': 'job.py', 'source_sha256': sha, 'start': 1, 'end': 1}]}
        cards = [card]
        def write():
            (index/'knowledge.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in cards), encoding='utf-8')
        write()
        note = notes/'PFK-001.md'
        note.write_text('---\nid: PFK-001\n---\n# Rule\nmanual rerun ^manual\n## Limits\nfixture only\n', encoding='utf-8')
        config = {'vault': str(vault), 'source_roots': {'historical': str(source)}}
        assert doctor(config)['status'] == 'ready'
        read = read_card(config, 'PFK-001', 'Rule')
        assert '## Limits' in read['text'] and read['anchor']['start'] == 4
        assert read_card(config, 'PFK-001', '^manual')['anchor']['start'] == 5
        cases.append('full rule context retained for heading and block anchors')
        for query in ('同步', 'rowkey_rule_columns', '42'):
            assert search(config, query)['results'][0]['id'] == 'PFK-001'
        assert search(config, '42', skill='report-codegen')['results'][0]['reuse_decision'] == 'comparison_only'
        cases.append('Chinese, identifiers, short error codes and wrong-skill exclusion')
        facts = {'knowledge_references_version': 1, 'ready_for_codegen': False, 'knowledge_references': [{
            'id': 'PFK-001', 'decision': 'adopted', 'reason': 'fixture matches task',
            'content_hash': read['content_hash'], 'source_revision': read['source_revision'],
            'evidence_span': read['evidence_span'], 'citation': read['citation'],
            'source_kind': 'historical_experience', 'adopted_rule': 'manual rerun preserves watermark',
            'version_scope': 'fixture-v1', 'evidence_hashes': [sha], 'applies_to': ['unit-a'],
            'validation_refs': ['test_manual_rerun']} ]}
        saved = copy.deepcopy(facts)
        assert audit_refs(config, facts)['status'] == 'passed'
        assert facts == saved
        cases.append('versioned adoption audit never promotes readiness or mutates input')
        before = inventory(config)
        moved = notes/'renamed.md'
        note.rename(moved)
        after = inventory(config)
        assert changes(before, after)['moved'] == ['PFK-001']
        assert not changes(before, after)['changed']
        assert audit_refs(config, facts)['status'] == 'passed'
        assert 'renamed.md' in read_card(config, 'PFK-001')['citation']
        cases.append('stable ID survives note rename without content invalidation')
        cards.append(dict(card, id='PFK-002'))
        (notes/'PFK-002.md').write_text('# independent\n', encoding='utf-8')
        write()
        assert audit_refs(config, facts)['status'] == 'passed'
        assert changes(after, inventory(config))['added'] == ['PFK-002']
        cases.append('unrelated additions do not invalidate adopted references')
        moved.write_text(moved.read_text(encoding='utf-8')+'changed rule\n', encoding='utf-8')
        audit = audit_refs(config, facts)
        assert audit['affected'][0]['code_units'] == ['unit-a']
        assert audit['affected'][0]['validation_refs'] == ['test_manual_rerun']
        assert 'knowledge_changed_or_legacy_hash_missing' in audit['affected'][0]['reasons']
        cases.append('note drift reports affected units and tests')
        code.write_text('value = 2\n', encoding='utf-8')
        assert any(i['code'] == 'source_changed' for i in doctor(config)['issues'])
        cases.append('source hash drift is visible in doctor')
        cards[0]['updates'] = ['PFK-999']
        write()
        assert any(i['code'] == 'broken_version_link' for i in doctor(config)['issues'])
        cases.append('broken version links detected')
        cards.pop(0)
        write()
        assert 'knowledge_deleted_or_unknown' in audit_refs(config, facts)['affected'][0]['reasons']
        cases.append('deleted referenced knowledge requires review')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'data-doc-to-dev-md/scripts'))
        from knowledge_reference_contract import validate_knowledge_references
        assert not validate_knowledge_references({})['errors']
        assert validate_knowledge_references({'knowledge_references': [{'id': 'PFK-001'}]})['warnings']
        for change in ({'content_hash': 'bad'}, {'validation_refs': []}, {'applies_to': []}, {'source_kind': 'latest'}):
            invalid = copy.deepcopy(facts)
            invalid['knowledge_references'][0].update(change)
            assert validate_knowledge_references(invalid)['errors']
        invalid = dict(facts, knowledge_references_version=99)
        assert validate_knowledge_references(invalid)['errors']
        assert validate_knowledge_references(dict(facts, code_units=[{'code_unit_id': 'unit-other'}]))['errors']
        cases.append('legacy compatibility, unsupported versions and invalid adoption contracts')
        payload = dict(invalid, codegen_contract={'contract_version': 1})
        facts_file = root/'facts.json'
        facts_file.write_text(json.dumps(payload), encoding='utf-8')
        validator = Path(__file__).resolve().parents[2]/'data-doc-to-dev-md/scripts/validate_technical_contract.py'
        checked = subprocess.run([sys.executable, str(validator), '--facts', str(facts_file)],
                                 capture_output=True, text=True, encoding='utf-8')
        assert checked.returncode == 1, checked.stderr
        assert any(e['code'] == 'KNOWLEDGE_REFERENCE_INVALID' for e in json.loads(checked.stdout)['errors'])
        cases.append('normal technical handoff validator rejects an invalid knowledge extension')
        (notes/'duplicate.md').write_text('---\nid: PFK-002\n---\n', encoding='utf-8')
        try:
            inventory(config)
        except ValueError:
            pass
        else:
            raise AssertionError('duplicate note IDs accepted')
        cases.append('duplicate note identities rejected')
        cli = subprocess.run([sys.executable, str(Path(__file__).with_name('knowledge_governance.py')),
                              '--config', str(root/'absent.json'), 'doctor'], capture_output=True, text=True, encoding='utf-8')
        assert cli.returncode == 0 and json.loads(cli.stdout)['private_status'] == 'not_configured'
        assert json.loads(cli.stdout)['builtin']['status'] == 'ready'
        cases.append('missing optional configuration still verifies built-in rules without inventing private evidence')
    return {'status': 'passed', 'case_count': len(cases), 'cases': cases, 'external_service_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
