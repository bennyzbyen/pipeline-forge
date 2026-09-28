"""Deterministic role/version retrieval checks; no actual project execution."""
import hashlib
import json
import tempfile
from pathlib import Path
from knowledge_lookup import search


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        index = root/'wiki/90_机器索引'
        index.mkdir(parents=True)
        source = root/'source'
        source.mkdir()
        for name in ('produce.py', 'query.py'):
            (source/name).write_text('# synthetic role evidence\n', encoding='utf-8')
        sha = hashlib.sha256((source/'produce.py').read_bytes()).hexdigest()
        card = dict(id='PFW-025', title='role fixture', project='fixture', claim='producer and consumer', reuse='review role', limits='static only', status='reviewed_static', target_skill='report-codegen', evidence=[{'type':'code','path':name,'source_sha256':sha} for name in ('produce.py','query.py')])
        (index/'knowledge.jsonl').write_text(json.dumps(card)+'\n', encoding='utf-8')
        context = {'review_status':'reviewed_static','version_status':'working_tree','origin':'independent_reference', 'components':[
            {'subject':'ETL output', 'role':'producer','state':'active_static','evidence_bindings':[{'path':'produce.py','sha256':sha}]},
            {'subject':'dashboard result','role':'consumer','state':'active_static','evidence_bindings':[{'path':'query.py','sha256':sha}]}]}
        config = {'vault':str(root/'wiki'),'source_roots':{'historical':str(source)}}
        def save():
            (index/'usage_context.json').write_text(json.dumps({'PFW-025':context}),encoding='utf-8')
        def lookup(role=''):
            return search(config,'PFW-025',role=role)['results'][0]
        assert 'role_not_established' in lookup('producer')['blockers']
        save()
        for role in ('producer','consumer'):
            result = lookup(role)
            assert result['reuse_decision']=='requires_task_contract_review'
            matched = [c for c in result['usage_context']['components'] if c['use']=='requires_task_contract_review']
            assert len(matched)==1 and matched[0]['role']==role
        context['components'][0]['state']='stopped';save()
        assert lookup('producer')['reuse_decision']=='comparison_only'
        assert lookup('consumer')['reuse_decision']=='requires_task_contract_review'
        context['version_status']='archive_unreviewed';save()
        assert lookup()['reuse_decision']=='comparison_only'
        context['version_status']='working_tree';context['review_status']='unreviewed';save()
        assert lookup()['reuse_decision']=='comparison_only'
        context['review_status']='reviewed_static';context['origin']='pipelineforge_generated';save()
        assert 'generated_example_not_independent_architecture_evidence' in lookup()['blockers']
        context['origin']='independent_reference';save()
        (source/'query.py').write_text('# changed\n',encoding='utf-8')
        result=lookup('consumer')
        assert result['reuse_decision']=='comparison_only'
        assert not result['usage_context']['components'][1]['evidence_verified']
        (index/'usage_context.json').write_text('[]',encoding='utf-8')
        try: lookup()
        except ValueError: pass
        else: raise AssertionError('malformed context must fail closed')
    print(json.dumps({'status':'passed','cases':['unknown role','separate producer/consumer','stopped component','unreviewed archive','unreviewed context','generated origin','source drift','malformed context']},indent=2))


if __name__=='__main__':
    main()
