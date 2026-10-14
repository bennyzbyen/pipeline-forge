"""Offline regressions for self-contained lifecycle, implementation and function metadata."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import knowledge_lookup as lookup
from knowledge_governance import doctor, inventory, changes
from knowledge_snapshots import evidence_key, identity, sha
from portable_knowledge import doctor_available


def run():
    cases = []
    with tempfile.TemporaryDirectory(prefix='knowledge_extensions_') as temporary:
        root = Path(temporary)
        vault = root/'vault'
        index = vault/'90_机器索引'
        index.mkdir(parents=True)
        (vault/'03_知识卡片').mkdir()
        (vault/'81_证据快照').mkdir()
        source = 'def aggregate_rows(items):\n    return sum(items)\n'
        text = '# Synthetic frozen evidence\n\nL10: def aggregate_rows(items):\nL11:     return sum(items)\n'
        checksum = sha(text.encode())
        frozen = '81_证据快照/'+checksum+'.md'
        (vault/frozen).write_text(text, encoding='utf-8', newline='\n')
        provenance = {'source_id':'SRC-synthetic', 'source_sha256':sha(source.encode()),
                      'source_line_span':[10,11], 'source_state':'local_modified_from_github'}
        evidence = {'type':'embedded','root':'vault','path':frozen,'start':1,'end':4,
                    'source_sha256':checksum,'provenance':provenance}
        manifest = {'version':1,'snapshots':{evidence_key(evidence):{'identity':identity(evidence),
                    'path':frozen,'sha256':checksum,'capture_status':'baseline_matched_redacted','redaction_version':1}}}
        contract = {'inputs':['items'],'outputs':['sum'],'reuse_steps':['validate','aggregate','verify']}
        base = {'id':'PFW-001','title':'current aggregation','project':'fixture','claim':'observed sum',
                'reuse':'validate inputs','limits':'not business approval','kind':'observed','status':'reviewed_static',
                'target_skill':'report-codegen','version_scope':'repository_bound_local','evidence':[evidence],
                'lifecycle':'github_linked_local_snapshot','module':'aggregation','applicability':'synthetic only',
                'risks':['missing values'],'implementation_contract':contract,'updates':['PFK-001']}
        old = {**base,'id':'PFK-001','title':'archived_exclusive','lifecycle':'historical_reference',
               'source_root':'work_code','updates':[], 'supplemented_by':['PFW-001']}
        remote = {**base,'id':'PFW-002','title':'matched_remote','lifecycle':'github_verified_snapshot','updates':[]}
        unknown = {**base,'id':'PFK-002','title':'future lifecycle','lifecycle':'future_unknown','updates':[]}
        cards = [base,old,remote,unknown]
        row = {'card':'PFW-001','function':'Aggregator.aggregate_rows','function_name':'aggregate_rows',
               'source_id':provenance['source_id'],'source_sha256':provenance['source_sha256'],
               'source_lines':[10,11],'evidence':frozen,'review_status':'reviewed_static',
               'observation':'sum the supplied items'}
        ledger = {'schema_version':1,'functions':[row]}
        def write(name, value):
            (index/name).write_text(json.dumps(value),encoding='utf-8')
        def save():
            (index/'knowledge.jsonl').write_text('\n'.join(json.dumps(c) for c in cards)+'\n',encoding='utf-8')
            write('function_review_ledger.json',ledger)
        save()
        write('evidence_snapshots.json',manifest)
        for c in cards:
            (vault/'03_知识卡片'/f'{c["id"]}.md').write_text('# Synthetic card\n',encoding='utf-8')
        config = {'vault':str(vault),'source_roots':{}}
        def exact(key, **scope):
            return next(r for r in lookup.search(config,key,ids=[key],**scope)['results'] if r['id']==key)
        assert lookup.search(config,'archived_exclusive')['status']=='no_match'
        current = lookup.search(config,'current aggregation')['results']
        assert next(r for r in current if r['id']=='PFK-001')['match_type']=='linked_version'
        assert exact('PFK-001')['reuse_decision']=='comparison_only'
        write('usage_context.json', {'PFK-001':{'review_status':'reviewed_static','version_status':'working_tree',
              'components':[{'subject':'synthetic','role':'producer','state':'active_static',
                             'evidence_bindings':[{'path':frozen,'sha256':checksum}]}]}})
        assert 'historical_reference_comparison_only' in exact('PFK-001')['blockers']
        assert all(c['use']=='comparison_only' for c in exact('PFK-001')['usage_context']['components'])
        cases.append('history excluded from default primary results and blocked despite absent or active role metadata')
        for options in [{'include_historical':True},{'version':'historical'}]:
            assert any(r['id']=='PFK-001' for r in lookup.search(config,'archived_exclusive',**options)['results'])
        assert lookup.search(config,'PFK-001')['results'][0]['id']=='PFK-001'
        assert exact('PFW-002',version='working')['source_version']=='working'
        assert exact('PFW-002',version='working')['reuse_decision']=='requires_task_contract_review'
        assert 'unknown_lifecycle_comparison_only' in exact('PFK-002')['blockers']
        cases.append('explicit history, linked versions and both current snapshot lifecycles retain distinct semantics')
        full = lookup.search(config,'aggregate_rows')['results'][0]
        small = lookup.search(config,'aggregate_rows',detail='summary')['results'][0]
        assert full['id']=='PFW-001' and full['function_review']['status']=='verified_static'
        assert full['function_review']['functions'][0]['citation'].endswith(':3>)')
        for field in ['module','applicability','risks','implementation_contract','lifecycle']:
            assert small[field]==full[field]==base[field]
        assert small['function_review']['count']==1 and len(json.dumps(small))<len(json.dumps(full))
        cases.append('function-name search verifies frozen bodies; summary retains reusable contracts and risks')
        with patch.object(lookup,'check_original_evidence',side_effect=AssertionError('external source accessed')):
            audited = exact('PFW-001',audit_originals=True)
            assert audited['evidence'][0]['origin']['verification']=='not_applicable_embedded_evidence'
        cases.append('embedded evidence never requests originals, including explicit original-audit mode')
        before = inventory(config)
        ledger['functions'][0]['observation']='reviewed observation changed'
        save()
        assert changes(before,inventory(config))['changed']==['PFW-001']
        cases.append('function-review changes invalidate only affected adoption hashes')
        ledger['functions'][0].update(function='Aggregator.other',function_name='other')
        save()
        assert exact('PFW-001')['reuse_decision']=='comparison_only'
        assert doctor(config)['status']=='review_required'
        config_path = root/'config.json'
        config_path.write_text(json.dumps(config),encoding='utf-8')
        health = doctor_available(config_path)
        assert health['status']=='ready' and health['private_health']=='review_required'
        cases.append('mismatched function bodies block reuse and private health independently of built-in readiness')
        ledger['functions']=[copy.deepcopy(row)]
        # row is shared with the ledger; restore its reviewed function identity.
        ledger['functions'][0].update(function='Aggregator.aggregate_rows',function_name='aggregate_rows')
        save()
        health = doctor(config)['compatibility']
        assert health['evidence_mode']=='embedded_vault' and health['reviewed_function_records']==1
        assert health['lifecycle_counts']['historical_reference']==1
        process = subprocess.run([sys.executable,'-B',str(Path(lookup.__file__)),'--config',str(config_path),
                                  'search','--query','archived_exclusive','--include-historical'],capture_output=True,text=True,encoding='utf-8')
        assert process.returncode==0 and any(r['id']=='PFK-001' for r in json.loads(process.stdout)['results'])
        (index/'function_review_ledger.json').unlink()
        assert exact('PFW-001')['function_review']['status']=='not_recorded'
        assert exact('PFW-001')['reuse_decision']=='requires_task_contract_review'
        cases.append('CLI history flag, compatibility diagnostics and optional-ledger absence are backward compatible')
    return {'status':'passed','case_count':len(cases),'cases':cases,'external_service_calls':0}


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
