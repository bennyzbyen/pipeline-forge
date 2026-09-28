"""Synthetic stale dimensions, delayed GAIA headers and binding readiness regression."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

from docx_bundle_ooxml import extract_xlsx_tables, Paragraph
from docx_bundle_facts import build_structured_facts, _map_report_field_dictionaries
from technical_contract import build_contract_v2, build_field_contracts
from verify_docx_bundle_multidoc import make_xlsx


def run():
    with tempfile.TemporaryDirectory(prefix='p0_evidence_') as temp:
        root = Path(temp)
        data = make_xlsx(root/'fixture.xlsx', [['说明'], ['字段名', '类型'], ['id', 'String'], ['code', 'String']])
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, 'w') as target:
            for name in source.namelist():
                raw = source.read(name)
                if name == 'xl/worksheets/sheet1.xml':
                    raw = raw.replace(b'A1:B4', b'A1')
                target.writestr(name, raw)
        tables = extract_xlsx_tables('fixture.xlsx', buffer.getvalue(), root, 1, 100)
        assert tables[0].row_count == 4 and tables[0].dimension == 'A1'
        tables[0].source_doc_name = 'fixture.docx'
        facts = build_structured_facts(tables, [Paragraph('', 'format copy without recognized tables', 2, 'fixture.md')])
        assert facts['field_dictionaries'][0]['first_fields'] == ['id', 'code']
        assert facts['coverage_comparison']['status'] == 'differences_require_review'
        assert facts['extraction_coverage'][1]['recognized_counts']['field_dictionaries'] == 0
        contract = build_contract_v2(facts, {'ready_for_codegen': True})
        assert not contract['ready_for_codegen'] and any('field dictionary' in item for item in contract['blockers'])
        mixed = {'report_targets': [{'target_name': 'out', 'physical_table': 'fixture.out'}], 'inferences': [], 'report_field_mappings': []}
        _map_report_field_dictionaries(mixed, [
            {'csv': 'inferred.csv', 'declared_table': '', 'fields': [{'target_field': 'id', 'source_field': 'id'}]},
            {'csv': 'declared.csv', 'declared_table': 'fixture.out', 'fields': [{'target_field': 'id', 'source_field': 'id'}]},
        ])
        assert mixed['report_field_mappings'][0]['requires_confirmation'] is True
        assert mixed['report_field_mappings'][1]['requires_confirmation'] is False
        assert [x['status'] for x in build_field_contracts(mixed)] == ['needs_confirmation', 'confirmed']
    return {'status': 'passed', 'cases': ['stale_A1', 'delayed_GAIA_header', 'format_coverage_difference', 'unbound_dictionary_blocks', 'mixed_binding_status_preserved']}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
