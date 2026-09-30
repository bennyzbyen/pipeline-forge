"""Derive stage views from explicit evidence events without altering historical records."""
import argparse
import json
from datetime import datetime
from pathlib import Path

STAGES = ('codegen', 'local_validation', 'deployment', 'business_acceptance', 'plugin_selftest')
SOURCES = ('tool_report', 'log', 'user_confirmation')


def summarize(payload):
    events = payload.get('events')
    if not isinstance(events, list):
        raise ValueError('EVIDENCE_EVENTS_REQUIRED')
    byid = {}
    replaced = set()
    for event in events:
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k].strip()
                                                for k in ('id', 'subject', 'stage', 'status', 'source', 'evidence', 'observed_at')):
            raise ValueError('EVIDENCE_FIELDS_REQUIRED')
        if event['id'] in byid or event['stage'] not in STAGES or event['source'] not in SOURCES:
            raise ValueError('EVIDENCE_ID_STAGE_OR_SOURCE_INVALID')
        if event['status'] not in ('passed', 'failed', 'blocked', 'unknown'):
            raise ValueError('EVIDENCE_STATUS_INVALID')
        when = datetime.fromisoformat(event['observed_at'])
        if when.tzinfo is None:
            raise ValueError('EVIDENCE_TIMEZONE_REQUIRED')
        if event['source'] == 'user_confirmation' and event['stage'] not in ('deployment', 'business_acceptance'):
            raise ValueError('USER_CONFIRMATION_CANNOT_CERTIFY_TESTS_OR_CONTRACTS')
        prior_ids = event.get('supersedes', [])
        if not isinstance(prior_ids, list):
            raise ValueError('EVIDENCE_SUPERSEDES_LIST_REQUIRED')
        for prior in prior_ids:
            old = byid.get(prior)
            if not old or (old['stage'], old['subject']) != (event['stage'], event['subject']):
                raise ValueError('EVIDENCE_REPLACEMENT_MUST_REFERENCE_PRIOR_SAME_SCOPE')
            if when < datetime.fromisoformat(old['observed_at']):
                raise ValueError('EVIDENCE_REPLACEMENT_PREDATES_ORIGINAL')
            replaced.add(prior)
        byid[event['id']] = event
    active = [event for key, event in byid.items() if key not in replaced]
    stages = {}
    conflicts = []
    for stage in STAGES:
        selected = [e for e in active if e['stage'] == stage]
        subjects = {}
        for event in selected:
            subjects.setdefault(event['subject'], []).append(event)
        ambiguous = [subject for subject, rows in subjects.items() if len({r['status'] for r in rows}) > 1]
        conflicts.extend({'stage': stage, 'subject': subject} for subject in ambiguous)
        states = {e['status'] for e in selected}
        status = ('conflict' if ambiguous else 'not_recorded' if not selected else
                  'failed' if 'failed' in states else 'blocked' if 'blocked' in states else
                  'unknown' if 'unknown' in states else 'passed')
        stages[stage] = {'status': status, 'evidence_ids': [e['id'] for e in selected],
                         'sources': sorted({e['source'] for e in selected})}
    issues = payload.get('issues', [])
    if not isinstance(issues, list):
        raise ValueError('ISSUES_LIST_REQUIRED')
    issue_ids = [i.get('id') for i in issues if isinstance(i, dict)]
    if len(issue_ids) != len(issues) or any(not isinstance(i, str) or not i for i in issue_ids) or len(set(issue_ids)) != len(issue_ids):
        raise ValueError('ISSUE_IDS_INVALID')
    for issue in issues:
        if issue.get('status') not in ('open', 'resolved', 'superseded'):
            raise ValueError('ISSUE_STATUS_INVALID')
        if issue['status'] != 'open':
            evidence = byid.get(issue.get('evidence_id'))
            if not evidence or evidence['id'] in replaced or evidence['status'] != 'passed':
                raise ValueError('ISSUE_CLOSURE_REQUIRES_CURRENT_PASS_EVIDENCE')
            if (issue.get('stage'), issue.get('subject')) != (evidence['stage'], evidence['subject']):
                raise ValueError('ISSUE_CLOSURE_EVIDENCE_SCOPE_MISMATCH')
            if any(c['stage'] == evidence['stage'] and c['subject'] == evidence['subject'] for c in conflicts):
                raise ValueError('ISSUE_CLOSURE_CONFLICTING_EVIDENCE')
            if not issue.get('final_decision') or not issue.get('recurrence_check'):
                raise ValueError('ISSUE_CLOSURE_DECISION_AND_RECURRENCE_CHECK_REQUIRED')
        if issue['status'] == 'superseded' and (issue.get('superseded_by') not in issue_ids or issue['superseded_by'] == issue['id']):
            raise ValueError('ISSUE_REPLACEMENT_INVALID')
    replacements = {i['id']: i['superseded_by'] for i in issues if i['status'] == 'superseded'}
    for ident in replacements:
        seen = set()
        while ident in replacements:
            if ident in seen:
                raise ValueError('ISSUE_REPLACEMENT_CYCLE')
            seen.add(ident)
            ident = replacements[ident]
    return {'status': 'conflict' if conflicts else 'summarized', 'stages': stages, 'conflicts': conflicts,
            'active_issues': [i['id'] for i in issues if i['status'] == 'open'],
            'superseded_evidence_ids': sorted(replaced), 'input_changed': False,
            'basis': 'recorded_evidence_not_independent_execution', 'readiness_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.evidence.read_text(encoding='utf-8-sig')))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        result = {'status': 'invalid', 'error': str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] in ('invalid', 'conflict'))


if __name__ == '__main__':
    raise SystemExit(main())
