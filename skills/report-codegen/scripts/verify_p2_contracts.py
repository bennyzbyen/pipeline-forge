"""P2 regressions for bounded transforms and preservation of framework choices."""
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import pandas as pd

from implementation_contract import require_bundled_layout
from scaffold_report_project import scaffold
from verify_generic_report_runtime_semantics import build_plan


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('expected rejection')


def main():
    doc_scripts = Path(__file__).resolve().parents[2]/'data-doc-to-dev-md/scripts'
    sys.path.insert(0, str(doc_scripts))
    try:
        from verify_code_unit_contract_regression import facts, waterline, confirm_identity
        from code_unit_contract import apply_proposal, confirm_code_unit_plan
        from build_report_codegen_plan import build_plan as plan_from_facts
        source_facts = facts([waterline('daily', 'fixture_algorithm')])
        apply_proposal(source_facts)
        mapping = confirm_identity(source_facts)
        expected = {'mode':'preserve_existing','evidence':['user-selected fixture']}
        mapping['units'][0]['implementation_contract'] = expected
        confirm_code_unit_plan(source_facts, mapping, actor='assistant', note='Synthetic authorized preservation test')
        assert source_facts['code_units'][0]['implementation_contract'] == expected
        assert source_facts['code_unit_plan']['confirmed_mapping'][0]['implementation_contract'] == expected
        assert plan_from_facts(source_facts)['implementation_contract'] == expected
    finally:
        sys.path.pop(0)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan = build_plan('standard_report')
        path = root/'plan.json'
        path.write_text(json.dumps(plan), encoding='utf-8')
        scaffold(path, root/'generated')
        sys.path.insert(0, str(root/'generated'))
        try:
            from data_utils.contract_runtime import execute_contract
            source = {'input':pd.DataFrame([{'id':'synthetic', 'hours':3, 'quantity':2}])}
            contract = {'steps':[{'id':'selected','op':'project','input':'input','columns':['hours','id']}], 'outputs':{'result':{'input':'selected','columns':['id','hours']}}}
            output = execute_contract(source, {}, {}, contract)['result']
            assert list(output.columns)==['id','hours'] and output.to_dict('records')==[{'id':'synthetic','hours':3}]
            invalid=copy.deepcopy(contract);invalid['steps'][0]['op']='execute_python'
            rejects(lambda: execute_contract(source, {}, {}, invalid))
            invalid=copy.deepcopy(contract);invalid['steps'][0]['columns']=['missing']
            rejects(lambda: execute_contract(source, {}, {}, invalid))
            invalid=copy.deepcopy(contract);invalid['outputs']['result']['columns']=['missing']
            rejects(lambda: execute_contract(source, {}, {}, invalid))
            assert list(source['input'].columns)==['id','hours','quantity']
            # A shaped DataFrame can hide absent record keys as nulls. Column presence
            # alone is deliberately not claimed as source-record completeness proof.
            shaped = pd.DataFrame([{'id':'synthetic'}], columns=['id','hours'])
            shaped_output = execute_contract({'input':shaped}, {}, {}, contract)['result']
            assert pd.isna(shaped_output['hours'].iloc[0])
        finally:
            sys.path.pop(0)
        # An explicit native/reference choice must not be overwritten by the generic scaffold.
        target=root/'native';target.mkdir()
        sentinel=target/'plugin_main.py';sentinel.write_text('def main(params):\n    return params\n',encoding='utf-8')
        before=sentinel.read_bytes()
        for mode in ['preserve_existing','native_python']:
            plan['implementation_contract']={'mode':mode,'evidence':['user-selected fixture']}
            path.write_text(json.dumps(plan),encoding='utf-8')
            rejects(lambda: scaffold(path,target))
            assert sentinel.read_bytes()==before and len(list(target.iterdir()))==1
        rejects(lambda: require_bundled_layout({'implementation_contract':{'mode':'unknown'}}))
        migration={'mode':'bundled','confirmed':True,'evidence':['fixture architecture decision'],'reference_supplied':True}
        rejects(lambda: require_bundled_layout({'implementation_contract':migration}))
        migration['migration_requested']=True
        require_bundled_layout({'implementation_contract':migration})
    print(json.dumps({'status':'passed','cases':['valid transform and exact column order','unknown op','missing step field','missing output field','input unchanged','native/reference scaffold refusal without writes','explicit migration guard'],'limitations':'synthetic checks do not prove FMOS usability or production behavior'},indent=2))


if __name__=='__main__':
    main()
