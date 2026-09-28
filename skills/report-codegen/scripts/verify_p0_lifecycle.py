"""Exercise P0 generated storage, lifecycle adapters, feedback and vehicle versions offline."""
import copy
import importlib
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

from report_contract import validate_execution_contract
from scaffold_report_project import scaffold
from scaffold_templates.vehicle import write_vehicle_data_process
from scaffold_templates.vehicle_source import write_vehicle_data_source
from verify_generic_report_runtime_semantics import build_plan, purge_generated_modules, FakeClickHouseClient


def rejects(action, error=ValueError):
    try:
        action()
    except error:
        return
    raise AssertionError('invalid lifecycle unexpectedly succeeded')


def run():
    cases = []
    with tempfile.TemporaryDirectory(prefix='p0_lifecycle_') as temp:
        root = Path(temp)
        plan = build_plan('standard_report')
        write = plan['execution_contract']['writes']['region_sales']
        write.update(empty_output_policy='clear_slice', empty_snapshot_confirmed=True,
                     predicate={'all': [{'column': 'period', 'value_from': 'time_range.period'},
                                        {'column': 'date', 'value_from': 'params.date'}]})
        bad = copy.deepcopy(plan)
        bad['execution_contract']['writes']['region_sales'].pop('empty_snapshot_confirmed')
        assert validate_execution_contract(bad['execution_contract'], bad['outputs'])['status'] == 'failed'
        path = root/'plan.json'
        path.write_text(json.dumps(plan), encoding='utf-8')
        project = root/'project'
        scaffold(path, project)
        purge_generated_modules()
        sys.path.insert(0, str(project))
        try:
            storage = importlib.import_module('data_utils.data_storage')
            delivery = importlib.import_module('common_utils.delivery_contract')
            feedback = importlib.import_module('common_utils.feedback_contract')
            client = FakeClickHouseClient()
            frame = pd.DataFrame(columns=write['columns'])
            job = storage.DataStorage({'region_sales': frame}, {'period': '2026P01'}, {'date': '2026-01-01', 'clickhouse_client': client})
            assert job.run()[0]['status'] == 'clear_submitted'
            assert len(client.events) == 1
            sql = client.events[0][1]
            assert "period = '2026P01' AND date = '2026-01-01'" in sql
            # Model rows in adjacent slices: both terms must be present to preserve them.
            rows = [('2026P01', '2026-01-01'), ('2026P01', '2026-01-02'), ('2026P02', '2026-01-01')]
            assert [r for r in rows if r != ('2026P01', '2026-01-01')] == rows[1:]
            contract_write = storage.execution_contract['writes']['region_sales']
            for policy in ('skip', 'block_destructive_replace', 'reject'):
                client.events.clear()
                contract_write['empty_output_policy'] = policy
                if policy == 'reject':
                    rejects(job.run)
                else:
                    assert job.run()[0]['status'] == 'skipped_empty'
                assert not client.events
            contract_write['empty_output_policy'] = 'clear_slice'
            rejects(lambda: storage.DataStorage({'region_sales': None}, job.time_range, job.params).run())
            contract_write['predicate'] = {'column': 'sku_type', 'value_from': 'params.sku_type'}
            job.params['sku_type'] = 'boost5'
            job.run()
            assert "sku_type = 'boost5'" in client.events[-1][1] and 'period' not in client.events[-1][1]
            cases.append('PFE-003 empty policies, composite and per-target predicates')

            writes = []
            def batch_writer(batch):
                if batch == 2:
                    raise ValueError('second batch failed')
                writes.append(batch)
            try:
                delivery.replace_batches([1, 2], replacement_confirmed=True, clear=lambda: writes.append('clear'), write=batch_writer, commit=lambda: writes.append('commit'))
            except delivery.PartialWriteError as error:
                assert error.cleared and error.completed_batches == 1 and isinstance(error.__cause__, ValueError)
            else:
                raise AssertionError('partial replacement must fail')
            assert writes == ['clear', 1]

            events = []
            def failure():
                events.append('failed')
                raise ValueError('source fixture')
            def complete():
                events.append('joined')
                return 1
            try:
                delivery.read_all({'orders': failure, 'calendar': complete})
            except delivery.SourceReadError as error:
                assert error.failed_sources == ['orders'] and isinstance(error.__cause__, ValueError)
            else:
                raise AssertionError('partial reads returned success')
            assert set(events) == {'failed', 'joined'}
            gate = {'enabled': True, 'manual_bypass': True, 'timeout_seconds': 1}
            assert delivery.readiness_gate(gate, manual=True, probe=failure)['status'] == 'bypassed_manual'
            assert delivery.readiness_gate(gate, manual=False, probe=lambda timeout: 'timeout', notify=lambda result: failure())['status'] == 'skipped_upstream_timeout'
            cases.append('PFE-005 timeout, bypass, notification failure and worker joins')

            keys = ['period', 'salesman_code']
            current = pd.DataFrame([['P1', 'S1', 'new'], ['P2', 'S1', 'new']], columns=keys+['category'])
            old = pd.DataFrame([['P1', 'S1', 'reviewed'], ['P2', 'S1', 'other']], columns=keys+['feedback'])
            merged = feedback.merge_feedback(current, old, keys=keys, feedback_columns=['feedback'])
            assert merged['feedback'].tolist() == ['reviewed', 'other'] and merged['category'].tolist() == ['new', 'new']
            personnel = pd.DataFrame([['P1', 'S1', 'east'], ['P2', 'S1', 'west']], columns=keys+['region'])
            assert merged.merge(personnel, on=keys)['region'].tolist() == ['east', 'west']
            events.clear()
            def writer(rows):
                assert rows.columns.tolist() == keys+['feedback']
                events.append('write')
                return 'completed'
            kwargs = dict(keys=keys, allowed_columns=['feedback'], writer=writer, commit=lambda value: events.append(('commit', value)), candidate=('2026-01-01', 'S1'))
            assert not feedback.apply_feedback_updates(merged, dry_run=True, **kwargs)['watermark_advanced'] and not events
            rejects(lambda: feedback.apply_feedback_updates(merged, **dict(kwargs, writer=lambda rows: 'submitted')), RuntimeError)
            assert not events
            rejects(lambda: feedback.apply_feedback_updates(merged, **dict(kwargs, writer=lambda rows: failure())), ValueError)
            events.clear()
            assert feedback.apply_feedback_updates(merged, **kwargs)['watermark_advanced']
            assert events == ['write', ('commit', ('2026-01-01', 'S1'))]
            tied = pd.DataFrame({'updated_at': ['2026-01-01'] * 2, 'event_id': ['B', 'A']})
            assert feedback.after_cursor(tied, time_column='updated_at', key_column='event_id', cursor=('2026-01-01', 'A'))['event_id'].tolist() == ['B']
            cases.append('PFE-006 feedback keys, column allowlist, dry-run, failed/submitted/completed writes')

            contract = {'factory': 'F1', 'batch_id': 'B1', 'tables': {'orders': {'keys': ['id'], 'allow_empty': False}}}
            manifest = {'factory': 'F1', 'batch_id': 'B1', 'tables': ['orders'], 'source_mode': 'full_snapshot', 'complete': True}
            frames = {'orders': pd.DataFrame({'id': ['001']})}
            for patch in ({'factory': 'F2'}, {'batch_id': 'B2'}, {'complete': False}, {'tables': []}):
                rejects(lambda patch=patch: delivery.preflight_snapshot(contract, dict(manifest, **patch), frames))
            rejects(lambda: delivery.preflight_snapshot(contract, manifest, {'orders': pd.DataFrame({'id': ['001', '001']})}))
            rejects(lambda: delivery.preflight_snapshot(contract, manifest, {'orders': frames['orders'].iloc[:0]}))
            empty_contract = copy.deepcopy(contract)
            empty_contract['tables']['orders']['allow_empty'] = True
            delivery.preflight_snapshot(empty_contract, manifest, {'orders': frames['orders'].iloc[:0]})
            events.clear()
            publish = dict(reserve_batch=lambda factory, batch: True, write_data=lambda *args: failure(), write_manifest=lambda *args: events.append('manifest'))
            rejects(lambda: delivery.publish_snapshot(contract, manifest, frames, **publish))
            assert 'manifest' not in events
            rejects(lambda: delivery.publish_snapshot(contract, manifest, frames, **dict(publish, reserve_batch=lambda *args: False)))
            events.clear()
            delivery.publish_snapshot(contract, manifest, frames, **dict(publish, write_data=lambda *args: events.append('data')))
            assert events == ['data', 'manifest']
            assert delivery.resolve_batch('latest', lambda: 'B1') == 'B1'
            rejects(lambda: delivery.resolve_batch('latest', lambda: 'latest'))
            events.clear()
            transfer = dict(source_mode='incremental', coverage_mode='merge', upload=lambda item, mode: events.append('upload'), delete=lambda item, mode: events.append('delete'), commit=lambda: events.append('commit'))
            delivery.deliver_files([{'operation': 'upsert'}, {'operation': 'delete'}], **transfer)
            assert events == ['upload', 'delete', 'commit']
            rejects(lambda: delivery.deliver_files([], **dict(transfer, coverage_mode='unknown')))
            events.clear()
            def upload_two(item, mode):
                if events:
                    raise ValueError('second upload failed')
                events.append('first_uploaded')
            rejects(lambda: delivery.deliver_files([{'operation': 'upsert'}, {'operation': 'upsert'}], **dict(transfer, upload=upload_two)))
            assert events == ['first_uploaded']
            cases.append('PFE-007 snapshot preflight, immutable reservation, manifest-last, file channels and commit')

            vehicle_plan = dict(plan, vehicle_profile={'version': 'realtime_eo', 'confirmed': True, 'evidence': 'synthetic'})
            write_vehicle_data_process(project, vehicle_plan)
            sys.modules.pop('data_utils.data_process', None)
            vehicle = importlib.import_module('data_utils.data_process')
            raw = pd.DataFrame({'order_source': ['EO订单', 'ERP订单', 'EO订单', 'EO订单'], 'order_status': [4, 4, 4516, 0],
                                'bmp_eo_order_category': ['X', 'NDT', 'NDT', 'NDT'], 'created_dtr_interconnect_type': [4, 4, 0, 0],
                                'pt_sum_p': [12, 13, 14, 15], 'pt_sum': [99]*4})
            processor = vehicle.DataProcess({'l0_dtr_order.t5_eo_erp_sales_order_line': raw}, {}, {})
            processor.data_clean()
            assert processor._data['eo_line']['pt_sum'].tolist() == [12, 14]
            write_vehicle_data_source(project)
            sys.modules.pop('data_utils.data_source', None)
            vehicle_source = importlib.import_module('data_utils.data_source')
            read_calls = []
            def indexed_reader(table, columns, start, end):
                read_calls.append((table, start, end))
                return raw.loc[:, columns]
            reader = vehicle_source.DataSource({'indexed_order_reader': indexed_reader})
            reader._read_hbase_with_range('l0_dtr_order.t5_eo_erp_sales_order_line', list(raw.columns), {}, {'p_start_date': '2026-01-01', 'p_end_date': '2026-01-28'})
            assert read_calls == [('l0_dtr_order.t5_eo_erp_sales_order_line', '2026-01-01', '2026-01-28')]
            rejects(lambda: reader._read_hbase_with_range('l0_dtr_order.t5_eo_erp_sales_order_line', list(raw.columns), {}, {}))
            cases.append('PFE-010 realtime EO status/category and pt_sum_p version profile')
        finally:
            sys.path.remove(str(project))
            purge_generated_modules()
    return {'status': 'passed', 'cases': cases, 'external_service_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
