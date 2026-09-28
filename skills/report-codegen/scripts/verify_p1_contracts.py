"""Offline P1 regression suite: synthetic data, injected adapters, no services."""
import ast
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd

from project_business_examples import (
    dsd_store_days, dtr_quantity, geography_join, grade, o2o_sku,
    rebuild_rollup, target_achievement,
)
from verify_generated_safety import check_source, verify

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


C = load(ROOT / 'report-codegen/assets/minimal_report_project/common_utils/project_contracts.py.template', 'p1_contracts')


def rejects(call, exception=ValueError):
    try:
        call()
    except exception as error:
        return error
    raise AssertionError('expected rejection')


def fail(*args):
    raise RuntimeError('synthetic adapter failure')


def entry_protocols():
    # Execute the actual generated entry loader function for both scaffold families.
    for family, directory in [('report-codegen', 'minimal_report_project'), ('data-sync-codegen', 'minimal_sync_project')]:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            for source in (ROOT / family / 'assets' / directory).rglob('*'):
                if source.is_file():
                    rel = source.relative_to(ROOT / family / 'assets' / directory)
                    target = project / rel.with_name(rel.name.removesuffix('.template'))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes())
            sys.path.insert(0, str(project))
            # Avoid importing production/platform modules: extract only the real loader AST.
            tree = ast.parse((project / 'plugin_main.py').read_text(encoding='utf-8'))
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_load_platform_params')
            namespace = {}
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'entry_fixture', 'exec'), namespace)
            path = project / 'input.json'
            business = {'period': '2026P01', 'params': {'must_remain_nested': True}}
            try:
                for profile, envelope, destination in [
                    ('cot', {'algorithm_io_mode': 'SINGLE', 'params': {'body': {'params': json.dumps(business)}}}, str(path)),
                    ('direct', business, './result.txt'),
                    ('q3', {'algorithm_io_mode': 'SINGLE', 'params': business}, str(path)),
                ]:
                    path.write_text(json.dumps(envelope), encoding='utf-8')
                    actual, output = namespace['_load_platform_params'](str(path), profile)
                    assert actual == business and output == destination
                    # Result destination is consumed by the same write convention as __main__.
                    destination_path = project / output if output == './result.txt' else Path(output)
                    destination_path.write_text(json.dumps({'status': 'completed'}), encoding='utf-8')
                    assert json.loads(destination_path.read_text())['status'] == 'completed'
                    if profile == 'direct':
                        assert json.loads(path.read_text()) == envelope
                path.write_text(json.dumps({'algorithm_io_mode': 'SINGLE', 'params': business}))
                rejects(lambda: namespace['_load_platform_params'](str(path), 'cot'))
                path.write_text(json.dumps({'algorithm_io_mode': 'SINGLE', 'params': {'body': {'params': '[]'}}}))
                rejects(lambda: namespace['_load_platform_params'](str(path), 'cot'))
            finally:
                sys.path.pop(0)
                for key in ['project_contracts', 'common_utils.project_contracts', 'common_utils', 'entry_contract']:
                    sys.modules.pop(key, None)
    # Real scaffolders must carry the adopted profile, and reject unconfirmed overrides.
    from scaffold_report_project import scaffold
    from verify_generic_report_runtime_semantics import build_plan
    sync_scripts = ROOT / 'data-sync-codegen/scripts'
    sys.path.insert(0, str(sync_scripts))
    try:
        from verify_cot_manifest_semantics_regression import facts_for, generate
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            plan = build_plan('standard_report')
            plan['codegen_contract']['entry_contract'] = {'profile': 'q3', 'confirmed': True, 'evidence': ['synthetic entry contract']}
            path = base / 'plan.json'
            path.write_text(json.dumps(plan), encoding='utf-8')
            scaffold(path, base / 'report')
            assert "'q3'" in (base / 'report/entry_contract.py').read_text()
            assert verify(base / 'report')['status'] == 'passed'
            facts = facts_for('fixture_report_p', ['id', 'inksaa_last_modified_timestamp', 'period', 'code'])
            facts['codegen_contract']['entry_contract'] = {'profile': 'direct', 'confirmed': True, 'evidence': ['synthetic entry contract']}
            generate(facts, base / 'sync')
            assert "'direct'" in (base / 'sync/entry_contract.py').read_text()
            assert verify(base / 'sync')['status'] == 'passed'
            plan['codegen_contract']['entry_contract']['confirmed'] = False
            path.write_text(json.dumps(plan), encoding='utf-8')
            rejects(lambda: scaffold(path, base / 'report'))
            assert "'q3'" in (base / 'report/entry_contract.py').read_text()
            facts['codegen_contract']['entry_contract']['confirmed'] = False
            rejects(lambda: generate(facts, base / 'sync'))
    finally:
        sys.path.pop(0)


def calendar_periods():
    periods = [f'2025P{p:02d}' for p in range(1, 14)] + ['2026P01', '2026P02']
    assert C.period_window(periods, '2026P01', kind='ytd_with_minimum', count=4) == ['2025P11', '2025P12', '2025P13', '2026P01']
    assert len(C.period_window(periods, '2025P13', kind='ytd_with_minimum', count=4)) == 13
    assert C.period_window(periods, '2026P01', kind='from', start='2025P09') == periods[8:14]
    rejects(lambda: C.period_window(periods, '2026P01', kind='from', start='2024P09'))
    rejects(lambda: C.period_window(['2025P12', '2026P01'], '2026P01', kind='recent', count=2))
    calendar = [dict(date='2025-12-28', period='2025P13', week=4, day=7), dict(date='2026-01-01', period='2026P01', week=1, day=1), dict(date='2026-01-09', period='2026P01', week=2, day=2)]
    assert C.execute_periods(calendar, '2026-01-01', '2026-01-09', backfill_week_day=(2, 2)) == ['2026P01', '2025P13']
    assert C.execute_periods(calendar, '2026-01-01', '2026-01-09') == ['2026P01']
    rejects(lambda: C.execute_periods(calendar, '2026-01-02', '2026-01-09'))
    rejects(lambda: C.execute_periods(calendar[1:], '2026-01-01', '2026-01-09', backfill_week_day=(2, 2)))
    dates = ['2026-01-01', '2026-01-02', '2026-01-03']
    assert len(C.dates_for_table(dates, date_scoped=True)) == 3
    assert C.dates_for_table(dates, date_scoped=False) == [None]
    assert C.period_list(['2026P01', '2026P01', '2026P02'], array_required=True) == ['2026P01', '2026P02']
    rejects(lambda: C.period_list('2026P01', array_required=True))
    rejects(lambda: C.period_list(['2026P14'], array_required=True))
    writes = []
    def run(p, path):
        writes.append((p, path))
        return {'status': 'completed'}
    C.run_periods(['2026P01', '2026P02'], 'fixture-output', run)
    assert writes[0][1] != writes[1][1]
    error = rejects(lambda: C.run_periods(['2026P01', '2026P02'], '.', lambda p, out: {'status': 'completed'} if p.endswith('01') else fail()), C.UnitFailure)
    assert error.unit == '2026P02' and error.completed == ['2026P01']


def dependencies():
    calls = []
    error = rejects(lambda: C.run_stages([('prepare', fail), ('npd', lambda x: calls.append('npd'))]), C.UnitFailure)
    assert not calls and not error.completed
    error = rejects(lambda: C.run_stages([('prepare', lambda x: {'status': 'completed'}), ('activate_b5', lambda x: {'status': 'triggered'})]), C.UnitFailure)
    assert error.completed == ['prepare'] and error.unit == 'activate_b5'
    required = ['df_store', 'df_store_p8']
    artifacts = {name: {'status': 'completed', 'batch': 'fixture-date'} for name in required}
    C.require_artifacts(required, artifacts, batch='fixture-date')
    rejects(lambda: C.require_artifacts(required, {'six_realtime_outputs': {}}, batch='fixture-date'))
    rejects(lambda: C.require_artifacts(required, artifacts, batch='wrong-date'))
    error = rejects(lambda: C.run_stages([('hbase_calculation', lambda x: {'status': 'completed'}), ('mongo_delivery', fail)]), C.UnitFailure)
    assert error.completed == ['hbase_calculation'] and error.unit == 'mongo_delivery'
    # Exercise the existing planner, preserving unresolved schedule/target mappings.
    doc_scripts = ROOT / 'data-doc-to-dev-md/scripts'
    sys.path.insert(0, str(doc_scripts))
    try:
        from code_unit_contract import apply_proposal
        facts = {'report_schedules': [{'schedule': value, 'task_name': f'fixture_{i}'} for i, value in enumerate(['daily 06:30', 'every 15 minutes', 'daily 05:00', 'daily 08:00'])], 'report_targets': [{'table': f'fixture.target_{i}'} for i in range(8)]}
        apply_proposal(facts)
        assert len(facts['report_schedules']) == 4
        assert facts['code_unit_plan']['proposed_count'] == 4
        assert len(facts['waterlines']) == 4
        assert facts['code_unit_plan']['status'] == 'awaiting_user_confirmation'
        assert any(unit['blockers'] for unit in facts['code_units'])
    finally:
        sys.path.pop(0)


def o2o_versions():
    row = {'date': 'fixture-date', 'data_type': 'A', 'is_sold': '0'}
    assert not o2o_sku(row, 'fixture-date', version='historical_or', confirmed=True)
    assert o2o_sku(row, 'fixture-date', version='working_date_ne_d', confirmed=True)
    assert not o2o_sku({**row, 'data_type': 'D'}, 'fixture-date', version='working_date_ne_d', confirmed=True)
    assert not o2o_sku(row, 'other-date', version='working_date_ne_d', confirmed=True)
    assert o2o_sku({'date': 'fixture-date'}, 'fixture-date', version='working_date_ne_d', confirmed=True)
    rejects(lambda: o2o_sku({'date': 'fixture-date'}, 'fixture-date', version='historical_or', confirmed=True))
    rejects(lambda: o2o_sku(row, 'fixture-date', version='working_date_ne_d', confirmed=False))


def formulas():
    for value, expected in [(59.99, 'low'), (60, 'qualified'), (129.99, 'qualified'), (130, 'high'), (59.999, 'qualified')]:
        assert grade(value, 1)[1] == expected
    assert grade(100, 0) == (0, 'low')
    details = pd.DataFrame([{'region': 'r', 'province': 'p', 'actual': 3}])
    dimensions = pd.DataFrame([{'region': 'r', 'province': 'p', 'current': 'new'}] * 2)
    assert len(geography_join(details, dimensions, ['region', 'province'], missing='error')) == 1
    bad = pd.DataFrame([{'region': 'x', 'province': 'p', 'current': 'new'}])
    rejects(lambda: geography_join(details, bad, ['region', 'province'], missing='error'))
    assert geography_join(details, bad, ['region', 'province'], missing='degraded')['mapping_status'].iloc[0] == 'degraded'
    actual = pd.DataFrame([{'id': 'a', 'actual': 24}, {'id': 'orphan', 'actual': 99}])
    target = pd.DataFrame([{'id': 'a', 'sku_count_target': 10, 'acuracy_rate': None}, {'id': 'no_actual', 'sku_count_target': 5, 'acuracy_rate': 1}])
    result = target_achievement(actual, target, ['id'])
    assert list(result['id']) == ['a'] and result['achievement_rate'].iloc[0] == 1.1
    rejects(lambda: target_achievement(actual, target.drop(columns='acuracy_rate'), ['id']), KeyError)
    precise = target_achievement(pd.DataFrame([{'id': 'a', 'actual': 1}]), pd.DataFrame([{'id': 'a', 'sku_count_target': 3, 'acuracy_rate': 1}]), ['id'])
    assert precise['achievement_rate'].iloc[0] == 0.3333
    # q3 upper levels aggregate only matched province actuals, then join their own target.
    upper_actual = result.assign(region='r').groupby('region', as_index=False)['actual'].sum()
    upper_target = pd.DataFrame([{'region': 'r', 'sku_count_target': 60, 'acuracy_rate': 0.5}])
    upper = target_achievement(upper_actual, upper_target, ['region'])
    assert upper['actual'].iloc[0] == 24 and upper['achievement_rate'].iloc[0] == 0.2
    children = pd.DataFrame([{'region': 'r', 'id': 'a', 'actual': 10, 'sku_count_target': 20}, {'region': 'r', 'id': 'b', 'actual': 90, 'sku_count_target': 100}])
    rebuilt = rebuild_rollup(children[children['id'] == 'a'], ['region'])
    assert rebuilt['sku_count_target'].iloc[0] == 20 and (rebuilt['actual'] / rebuilt['sku_count_target']).iloc[0] == 0.5
    dsd = dsd_store_days(pd.DataFrame([{'store_id': 'a', 'order_day': d, 'gsv': v} for d, v in [('2026-01-01', 2), ('2026-01-01', 3), ('2026-01-02', 7)]]), '2026-01-01', '2026-01-02')
    assert dsd['purchase_days'].iloc[0] == 2 and dsd['gsv'].iloc[0] == 12
    one_day = dsd_store_days(pd.DataFrame([{'store_id': 'a', 'order_day': '2026-01-01', 'gsv': 2}] * 2), '2026-01-01', '2026-01-01')
    assert one_day['purchase_days'].iloc[0] == 1 and one_day['gsv'].iloc[0] == 4


def dtr_batches():
    assert C.decimal_tdu('24', '2', '12') == (Decimal('2.0000000000'), Decimal('24.0000000000'))
    assert C.decimal_tdu('1', '1', '0') == (None, None)
    assert C.decimal_tdu('1', '1', None) == (None, None)
    assert C.decimal_tdu('0.00000000005', '1', '1')[0] == Decimal('0.0000000001')
    row = dict(status='4', ordered=24, delivered=12, shipped=9, partial=6, received=8, stored=10)
    assert dtr_quantity(row, kind='sales', eo_actual_types=[]) == 12
    assert dtr_quantity(row, kind='return', eo_actual_types=[]) == 0
    assert dtr_quantity({**row, 'status': '3'}, kind='return', eo_actual_types=[]) == 10
    assert dtr_quantity({**row, 'source': 'EO订单', 'interconnect': 'fixture-type'}, kind='return', eo_actual_types=['fixture-type']) == 24
    class Cursor:
        def __init__(self):
            self.rows = list(range(7))
        def fetchmany(self, size):
            result, self.rows = self.rows[:size], self.rows[size:]
            return result
    for size in (1, 3, 10):
        output, committed = [], []
        def write(rows):
            output.extend(rows)
            return 'completed'
        C.stream_batches(Cursor(), size, lambda rows: [r * 2 for r in rows], write, lambda: committed.append(True))
        assert output == list(range(0, 14, 2)) and committed == [True]
    calls, committed = [], []
    def second_fails(rows):
        calls.append(rows)
        return 'completed' if len(calls) == 1 else fail()
    error = rejects(lambda: C.stream_batches(Cursor(), 3, list, second_fails, lambda: committed.append(True)), C.BatchFailure)
    assert error.completed_batches == 1 and error.failed_batch == 2 and not committed
    saved, old = [], [11, 12]
    def record(ids):
        saved.extend(ids)
        return 'completed'
    def delete(ids):
        assert tuple(saved) == ids
        old.clear()
        return 'completed'
    C.audited_delete(old, record=record, delete=delete)
    assert saved == [11, 12] and old == []
    rejects(lambda: C.audited_delete([13], record=fail, delete=lambda ids: calls.append(ids)), RuntimeError)
    assert len(calls) == 2
    rejects(lambda: C.audited_delete([13], record=lambda ids: 'submitted', delete=delete))


def files():
    rejects(lambda: C.select_file(['other_table.csv'], table='ATDPERSONPAYCODE', suffix='.csv'))
    rejects(lambda: C.select_file([], table='target', suffix='.csv'))
    paths = ['target_20260101010101.csv', 'target_20260201010101.csv', 'other_20260301010101.csv']
    rejects(lambda: C.select_file(paths, table='target', suffix='.csv'))
    assert C.select_file(paths, table='target', suffix='.csv', latest=True) == paths[1]
    rejects(lambda: C.select_file(['a/target_20260101010101.csv', 'b/target_20260101010101.csv'], table='target', suffix='.csv', latest=True))
    rejects(lambda: C.select_file(['target_20261301010101.csv'], table='target', suffix='.csv', latest=True))


def safety():
    cases = [('password = "fixture-only-secret"', 'hardcoded_credential'), ('client(verify=False)', 'tls_verification_disabled'), ('raise "failure"', 'invalid_exception_literal'), ('logger.info(f"{params}")', 'raw_runtime_params_log'), ('logger.info(json.dumps(execute_params))', 'raw_runtime_params_log')]
    for source, rule in cases:
        result = check_source(source)
        assert any(item['rule'] == rule for item in result)
        assert 'fixture-only-secret' not in json.dumps(result)
    assert not check_source('password = os.environ["PASSWORD"]\nlogger.info("period=%s", params.get("period"))\nraise ValueError("invalid contract")')
    assert not check_source('password = "<PASSWORD>"')


def main():
    groups = {'PFE-001': entry_protocols, 'PFE-008': calendar_periods, 'PFE-009': dependencies, 'PFE-011': o2o_versions, 'PFE-012': formulas, 'PFE-013': dtr_batches, 'PFE-014': files, 'PFE-016': safety}
    for test in groups.values():
        test()
    report = ROOT / 'report-codegen/assets/minimal_report_project/common_utils/project_contracts.py.template'
    sync = ROOT / 'data-sync-codegen/assets/minimal_sync_project/project_contracts.py.template'
    assert report.read_bytes() == sync.read_bytes()
    assert (ROOT / 'report-codegen/scripts/verify_generated_safety.py').read_bytes() == (ROOT / 'data-sync-codegen/scripts/verify_generated_safety.py').read_bytes()
    print(json.dumps({'status': 'passed', 'groups': list(groups), 'scope': 'synthetic offline; not production acceptance'}, indent=2))


if __name__ == '__main__':
    main()
