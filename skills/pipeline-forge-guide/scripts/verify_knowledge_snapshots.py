"""Offline capture, relocation, drift and tamper tests for frozen knowledge evidence."""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from knowledge_lookup import search
from knowledge_snapshots import capture, evidence_key, load_manifest, refresh_existing_links, sha, validate, verify_snapshot


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        vault = root/'vault'
        idx = vault/'90_机器索引'
        idx.mkdir(parents=True)
        (vault/'03_知识卡片').mkdir()
        sources = root/'sources'
        sources.mkdir()
        code = sources/'job.py'
        code.write_text('password = "fixture-secret-value"\nvalue = 42\nurl = "https://fixture.invalid/private"\n', encoding='utf-8')
        evidence = {'type':'code','path':'job.py','start':1,'end':3,'source_sha256':sha(code.read_bytes())}
        card = {'id':'PFK-001','title':'snapshot fixture','project':'fixture','claim':'value is 42','reuse':'review captured behavior','limits':'frozen version only','status':'reviewed_static','kind':'observed','target_skill':'report-codegen','evidence':[evidence]}
        (idx/'knowledge.jsonl').write_text(json.dumps(card)+'\n',encoding='utf-8')
        (idx/'document_manifest.json').write_text('[]',encoding='utf-8')
        (vault/'03_知识卡片/PFK-001.md').write_text('# Fixture\n\n## 来源\n\nOriginal optional.\n',encoding='utf-8')
        config = {'vault':str(vault),'source_roots':{'historical':str(sources)}}
        assert capture(config)['new_snapshots']==1
        page = vault/'03_知识卡片/PFK-001.md'
        page.write_text('# Fixture\n\n## 来源\n\nRebuilt source link.\n', encoding='utf-8')
        assert validate(vault)['status']=='failed'
        refresh_existing_links(vault)
        assert validate(vault)['status']=='passed'
        relinked = page.read_bytes()
        refresh_existing_links(vault)
        assert page.read_bytes()==relinked
        manifest = load_manifest(vault)
        snapshot_path = vault/manifest['snapshots'][evidence_key(evidence)]['path']
        frozen = snapshot_path.read_bytes()
        assert b'fixture-secret-value' not in frozen and b'fixture.invalid' not in frozen
        assert b'L2: value = 42' in frozen
        def get(config=config):
            return search(config, 'PFK-001', audit_originals=True)['results'][0]
        assert get()['evidence'][0]['basis']=='frozen_evidence'
        code.write_text('value = 99\n',encoding='utf-8')
        result = get()
        assert result['evidence'][0]['origin']['verification']=='source_changed'
        assert result['reuse_decision']=='requires_task_contract_review'
        assert capture(config)['new_snapshots']==0 and snapshot_path.read_bytes()==frozen
        code.unlink()
        assert get()['evidence'][0]['origin']['verification']=='missing_source'
        assert get()['evidence'][0]['verification']=='verified'
        moved = root/'relocated'
        shutil.copytree(vault,moved)
        result=get({'vault':str(moved)})
        assert result['reuse_decision']=='requires_task_contract_review'
        assert str(moved.as_posix()) in result['evidence'][0]['citation']
        assert validate(moved)['status']=='passed'
        snapshot_path.write_bytes(frozen+b'changed')
        assert get()['reuse_decision']=='comparison_only'
        assert validate(vault)['status']=='failed'
        try: capture(config)
        except ValueError: pass
        else: raise AssertionError('must not repair a tampered immutable snapshot silently')
        snapshot_path.write_bytes(frozen)
        malformed=copy.deepcopy(manifest)
        malformed['snapshots'][evidence_key(evidence)]['identity']['start']=2
        assert verify_snapshot(vault,evidence,malformed)['verification']=='invalid_snapshot_binding'
        malformed=copy.deepcopy(manifest)
        malformed['snapshots'][evidence_key(evidence)]['path']='81_证据快照/../../outside.md'
        assert verify_snapshot(vault,evidence,malformed)['verification']!='verified'
        assert len(load_manifest(moved)['snapshots'])==1
    print(json.dumps({'status':'passed','cases':['redacted capture','source drift independent from snapshot','immutable recapture','original deletion','vault relocation without roots','snapshot corruption','binding tamper','path escape']},indent=2))


if __name__=='__main__':
    main()
