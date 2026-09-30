"""Synthetic regressions for project gates, diagnosis and scoped delivery evidence."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in ('data-doc-to-dev-md', 'data-job-log-debugger', 'report-codegen'):
    sys.path.insert(0, str(ROOT / folder / 'scripts'))
from verify_code_unit_contract_regression import facts, waterline, confirm_identity
from code_unit_contract import apply_proposal, confirm_code_unit_plan
from verify_schedule_boundary_planning import verify
from revise_confirmed_contract import revise, fingerprint
from analyze_data_job_log import analyze_log
from summarize_delivery_evidence import summarize
from verify_report_plan_semantics import validate_generated_files


def rejected(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('invalid input accepted')


def confirmed():
    rows = [waterline('first', 'a'), waterline('second', 'b'), waterline('third', 'c')]
    for row in rows:
        row['dependency_evidence'] = {}
    value = facts(rows)
    apply_proposal(value)
    confirm_code_unit_plan(value, confirm_identity(value), actor='user', note='fixture first confirmation')
    return value


def main():
    # Fixed self-test expectations belong here, never on supplied project facts.
    schedule_fixture = {'report_schedules': [
        {'waterline_id': 'daily_fixture', 'schedule': 'daily'},
        {'waterline_id': 'hourly_fixture', 'schedule': 'hourly'}]}
    apply_proposal(schedule_fixture)
    assert len(schedule_fixture['waterlines']) == 2
    assert schedule_fixture['code_unit_plan']['proposed_count'] == 2
    assert schedule_fixture['code_unit_plan']['confidence'] == 'low'
    assert verify(schedule_fixture)['blocks_codegen']
    for confidence in ('low', 'medium', 'high'):
        value = facts([{**waterline('one', 'a'), 'boundary_confidence': confidence, 'dependency_evidence': {}}])
        apply_proposal(value)
        confirm_code_unit_plan(value, confirm_identity(value))
        before = copy.deepcopy(value)
        assert verify(value)['status'] == 'passed'
        assert value == before
    value = confirmed()
    broken = copy.deepcopy(value)
    broken['waterlines'][0]['state_boundary'] = {}
    assert verify(broken)['blocks_codegen']
    waiting = facts([waterline('one', 'a')])
    apply_proposal(waiting)
    assert verify(waiting)['blocks_codegen']

    log = '''INFO Gateway getFsClient download completed
Traceback (most recent call last):
  File "fixture.py", line 3, in parse
    text.removeprefix("x")
AttributeError: 'str' object has no attribute 'removeprefix'
'''
    diagnosis = analyze_log(log)
    assert diagnosis['primary_classification'] == 'environment'
    assert diagnosis['runtime_version'] == 'unknown'
    assert analyze_log('INFO Gateway getFsClient download completed')['primary_classification'] == 'unknown'
    unknown = analyze_log(log.replace("AttributeError: 'str' object has no attribute 'removeprefix'", 'LookupError: unfamiliar fault'))
    assert unknown['diagnosis_status'] == 'hypothesis' and unknown['primary_classification'] == 'unknown'

    unit = value['code_units'][0]
    new_contract = copy.deepcopy(unit['execution_contract'])
    new_contract['retry']['max_attempts'] = 3
    change = {'base_sha256': fingerprint(value), 'authorization': {'actor': 'assistant', 'evidence': 'fixture request', 'reason': 'authorized retry correction'},
              'unit_changes': [{'code_unit_id': unit['code_unit_id'], 'execution_contract': new_contract,
                                'waterline_contracts': {unit['covered_waterlines'][0]: new_contract}}]}
    before = copy.deepcopy(value)
    result = revise(value, change)
    assert value == before
    assert result['code_unit_plan']['confirmation_audit'] == before['code_unit_plan']['confirmation_audit']
    assert result['code_units'][1:] == before['code_units'][1:]
    assert result['revision_audit'][-1]['validation_status'] == 'pending'
    assert result['code_units'][0]['retry']['max_attempts'] == 3
    for bad in ({**change, 'base_sha256': 'stale'}, {**change, 'authorization': {}},
                {**change, 'unit_changes': [{**change['unit_changes'][0], 'covered_waterlines': ['different']}]}):
        rejected(lambda: revise(value, bad))
    unconfirmed = copy.deepcopy(value)
    unconfirmed['code_unit_plan']['confirmation_audit'] = []
    rejected(lambda: revise(unconfirmed, {**change, 'base_sha256': fingerprint(unconfirmed)}))
    assistant_first = copy.deepcopy(value)
    assistant_first['code_unit_plan']['confirmation_audit'][0]['actor'] = 'assistant'
    rejected(lambda: revise(assistant_first, {**change, 'base_sha256': fingerprint(assistant_first)}, require_user_confirmation=True))
    # Existing downstream dependencies are included without changing downstream units.
    dependent = copy.deepcopy(value)
    dependent['code_units'][1]['depends_on'] = [unit['code_unit_id']]
    revised = revise(dependent, {**change, 'base_sha256': fingerprint(dependent)})
    assert len(revised['revision_audit'][-1]['revalidate_units']) == 2
    assert revised['code_units'][1:] == dependent['code_units'][1:]

    def event(ident, stage, status, source='tool_report', **kw):
        return dict(id=ident, subject='unit-a', stage=stage, status=status, source=source,
                    evidence='fixture evidence', observed_at='2026-09-30T12:00:00+08:00', **kw)
    payload = {'events': [event('code', 'codegen', 'passed'), event('self', 'plugin_selftest', 'failed'),
                          event('deploy-old', 'deployment', 'blocked'),
                          event('deploy-new', 'deployment', 'passed', 'user_confirmation', supersedes=['deploy-old'])]}
    before = copy.deepcopy(payload)
    view = summarize(payload)
    assert payload == before
    assert view['stages']['codegen']['status'] == 'passed'
    assert view['stages']['deployment']['sources'] == ['user_confirmation']
    assert view['stages']['local_validation']['status'] == 'not_recorded'
    contradictory = copy.deepcopy(payload)
    contradictory['events'][-1].pop('supersedes')
    assert summarize(contradictory)['status'] == 'conflict'
    rejected(lambda: summarize({'events': [event('fake', 'local_validation', 'passed', 'user_confirmation')]}))
    rejected(lambda: summarize({'events': [event('later', 'deployment', 'passed', supersedes=['missing'])]}))
    payload['issues'] = [{'id': 'deployment-question', 'stage': 'deployment', 'subject': 'unit-a', 'status': 'resolved',
                          'evidence_id': 'deploy-new', 'final_decision': 'user accepted', 'recurrence_check': 'next deployment'}]
    assert not summarize(payload)['active_issues']
    payload['issues'][0]['stage'] = 'local_validation'
    rejected(lambda: summarize(payload))

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        external = root / 'docs/status.md'
        external.parent.mkdir()
        external.write_text('fixture', encoding='utf-8')
        errors, warnings = [], []
        validate_generated_files(root / 'src', {}, False, errors, warnings, external)
        assert not any('status.md' in e['message'] or 'IMPLEMENTATION_STATUS.md' in e['message'] for e in errors)
        assert errors  # External documentation must not hide missing code files.
        external.unlink()
        errors = []
        validate_generated_files(root / 'src', {}, False, errors, warnings, external)
        assert any('status.md' in e['message'] for e in errors)
    print(json.dumps({'status': 'passed', 'groups': ['confidence and missing-boundary gates', 'root-exception diagnosis',
        'scoped revisions and preserved first confirmation', 'downstream invalidation', 'stage evidence and closure',
        'external status with unchanged code checks'], 'external_calls': 0}))


if __name__ == '__main__':
    main()
