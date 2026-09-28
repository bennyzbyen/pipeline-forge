"""Historical patterns never imply current names, cluster or destructive writes."""
import ast
import json

from scaffold_cot_sync_project import build_table_configs, render_plugin_config
from verify_cot_manifest_semantics_regression import facts_for


def assignment(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(node.value)


def run():
    facts = facts_for('supervisor_assist_visit', ['id', 'period', 'code', 'inksaa_last_modified_timestamp'])
    configs, _ = build_table_configs(facts, None)
    assert 'supervisor_assist_visit' in configs
    assert configs['supervisor_assist_visit']['hbase_table'] == 'l2_fixture.supervisor_assist_visit'
    facts['cot_historical_profile'] = {'name': 'cot_2026', 'confirmed': True, 'evidence': 'synthetic task scope'}
    configs, _ = build_table_configs(facts, None)
    assert 'v_supervisor_assist_visit_2026' in configs
    facts['cot_historical_profile']['name'] = 'cot_2027'
    assert 'supervisor_assist_visit' in build_table_configs(facts, None)[0]
    facts = facts_for('wechat_authorization_info', ['id', 'inksaa_last_modified_timestamp'])
    facts['cot_report_tables'][0]['clickhouse_table'] = 'cot_report.wechat_authorization_info'
    facts['cot_report_tables'][0]['source_hbase_table'] = 'l2_cot_exe_report.wechat_authorization_info'
    configs, _ = build_table_configs(facts, None)
    rendered = render_plugin_config(configs, 'fixture')
    assert assignment(rendered, 'ck_truncate_list') == []
    assert assignment(rendered, 'hbase_truncate_list') == []
    facts['cot_report_tables'][0]['truncate_contract'] = {'confirmed': True, 'evidence': 'synthetic scope', 'targets': ['hbase']}
    configs, _ = build_table_configs(facts, None)
    rendered = render_plugin_config(configs, 'fixture')
    assert assignment(rendered, 'ck_truncate_list') == []
    assert assignment(rendered, 'hbase_truncate_list') == ['l2_cot_exe_report.wechat_authorization_info']
    cluster = next(n.value for n in ast.parse(rendered).body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'cluster' for t in n.targets))
    expression = compile(ast.Expression(cluster), '<fixture>', 'eval')
    for env in ('qa', 'uat', 'prod'):
        assert eval(expression, {'environment_profile': {}, 'env': env}) == '<CLICKHOUSE_CLUSTER>'
    assert eval(expression, {'environment_profile': {'clickhouse_cluster': ''}}) == ''
    assert eval(expression, {'environment_profile': {'clickhouse_cluster': 'fixture_cluster'}}) == 'fixture_cluster'
    return {'status': 'passed', 'case_count': 4, 'cases': ['current names preserved', 'explicit historical profile only',
            'separate per-target truncate evidence', 'cluster independent of environment label'], 'external_service_calls': 0}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
