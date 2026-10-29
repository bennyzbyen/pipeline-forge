"""Synthetic regressions for immutable template and business/XML publication guards."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree as ET

import pipeline_ooxml
from build_pipeline_excel import build_workbook
from pipeline_preservation import business_snapshot, preservation_errors
from validate_pipeline_excel import validate_workbook
import verify_java_import_regression as regression
import verify_java_source_contract as source_contract
from verify_pipeline_excel_synthetic_regression import build_args


class TemplatePreservation(unittest.TestCase):
    setUp = regression.ImportRegression.setUp
    build = regression.ImportRegression.build
    mutate = regression.ImportRegression.mutate
    edit = source_contract.JavaSourceContract.edit

    def package_edit(self, name, change):
        with zipfile.ZipFile(self.output) as archive:
            infos = archive.infolist()
            parts = {i.filename: archive.read(i.filename) for i in infos}
        parts[name] = change(parts.get(name))
        with zipfile.ZipFile(self.output, 'w') as archive:
            for info in infos:
                archive.writestr(info, parts.pop(info.filename))
            for name, data in parts.items():
                archive.writestr(name, data)

    def arguments(self):
        facts = self.root/'facts.json'
        facts.write_text(json.dumps(self.facts), encoding='utf-8')
        return build_args(self.template, facts, self.root/'questions.md', self.output)

    def test_package_layout_and_readme_drift_rejected(self):
        self.build()
        pristine = self.output.read_bytes()
        for part in ('xl/styles.xml', 'xl/workbook.xml', 'docProps/core.xml',
                     '[Content_Types].xml', 'xl/_rels/workbook.xml.rels'):
            with self.subTest(part=part):
                self.output.write_bytes(pristine)
                self.package_edit(part, lambda raw: raw + b'<!-- changed -->')
                self.assertFalse(validate_workbook(self.output, self.template)['ok'])
        self.output.write_bytes(pristine)
        self.package_edit('unrequested.xml', lambda raw: b'<unexpected/>')
        self.assertTrue(any('added' in e for e in validate_workbook(self.output, self.template)['errors']))
        self.output.write_bytes(pristine)
        self.mutate('Pipeline', lambda root: ET.SubElement(root, pipeline_ooxml.Q('cols')))
        self.assertTrue(any('layout changed' in e for e in validate_workbook(self.output, self.template)['errors']))
        self.output.write_bytes(pristine)
        self.edit('Readme', {'A1': 'Changed explanation'})
        self.assertTrue(any('non-data sheet' in e for e in validate_workbook(self.output, self.template)['errors']))
        self.output.write_bytes(pristine)
        def change_style(root):
            cell = root.find(f"{pipeline_ooxml.Q('sheetData')}/{pipeline_ooxml.Q('row')}[@r='3']/{pipeline_ooxml.Q('c')}[@r='B3']")
            cell.set('s', '1' if cell.get('s', '0') == '0' else '0')
        self.mutate('Pipeline', change_style)
        self.assertTrue(any('business-cell style' in e for e in validate_workbook(self.output, self.template)['errors']))
        self.output.write_bytes(pristine)
        self.mutate('Pipeline', lambda root: root.find(f"{pipeline_ooxml.Q('sheetData')}/{pipeline_ooxml.Q('row')}[@r='20']").set('ht', '40'))
        self.assertTrue(any('row format changed' in e for e in validate_workbook(self.output, self.template)['errors']))

    def test_exact_xml_business_and_null_checks(self):
        self.build()
        reference = self.root/'before.xlsx'
        shutil.copyfile(self.output, reference)
        pristine = self.output.read_bytes()
        for cell, value in [('N3', self.params.replace('><params>', '>\n<params>')),
                            ('N3', self.params.replace('ExecuteReport', 'OtherReport')),
                            ('C3', 'different business description'), ('F3', '')]:
            with self.subTest(cell=cell, value_type=type(value).__name__):
                self.output.write_bytes(pristine)
                self.edit('Pipeline', {cell: value})
                errors = preservation_errors(self.output, reference)
                self.assertTrue(any(f'Pipeline!{cell}' in e for e in errors), errors)
        self.output.write_bytes(pristine)
        self.assertEqual([], preservation_errors(self.output, reference))
        checked = validate_workbook(self.output, self.template, reference)
        self.assertTrue(checked['ok'], checked['errors'])
        self.assertTrue(checked['business_preservation_checked'])

    def test_writer_business_mutation_never_replaces_existing_output(self):
        self.output.write_bytes(b'previous final workbook')
        before = self.output.read_bytes()
        writer = pipeline_ooxml.write_export
        def corrupt(template, output, tables, schema, keys):
            tables['Pipeline'][0]['task1_mlp_params'] = self.params.replace('ExecuteReport', 'OtherReport')
            writer(template, output, tables, schema, keys)
        with patch.object(pipeline_ooxml, 'write_export', corrupt):
            with self.assertRaisesRegex(ValueError, 'Business value/XML changed'):
                build_workbook(self.arguments())
        self.assertEqual(before, self.output.read_bytes())
        self.assertFalse(list(self.root.glob('pipeline_export_*')))

    def test_writer_format_drift_never_replaces_output(self):
        self.output.write_bytes(b'previous final workbook')
        writer = pipeline_ooxml.write_export
        def corrupt(template, output, tables, schema, keys):
            writer(template, output, tables, schema, keys)
            prior = self.output
            self.output = output
            try:
                self.package_edit('xl/styles.xml', lambda raw: raw + b'<!-- formatting drift -->')
            finally:
                self.output = prior
        with patch.object(pipeline_ooxml, 'write_export', corrupt):
            with self.assertRaisesRegex(ValueError, 'Template package part changed'):
                build_workbook(self.arguments())
        self.assertEqual(b'previous final workbook', self.output.read_bytes())

    def test_locked_output_stays_intact(self):
        self.output.write_bytes(b'previous final workbook')
        with patch.object(Path, 'replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                build_workbook(self.arguments())
        self.assertEqual(b'previous final workbook', self.output.read_bytes())
        self.assertFalse(list(self.root.glob('pipeline_export_*')))

    def test_concurrent_destination_edit_is_not_overwritten(self):
        writer = pipeline_ooxml.write_export
        def concurrent(*args):
            writer(*args)
            self.output.write_bytes(b'user edited while generating')
        with patch.object(pipeline_ooxml, 'write_export', concurrent):
            with self.assertRaisesRegex(ValueError, 'Destination changed'):
                build_workbook(self.arguments())
        self.assertEqual(b'user edited while generating', self.output.read_bytes())

    def test_independent_original_template_restores_format(self):
        self.build()
        original = self.root/'original.xlsx'
        shutil.copyfile(self.template, original)
        self.package_edit('xl/styles.xml', lambda raw: raw + b'<!-- drift -->')
        args = self.arguments()
        args.template_xlsx = self.output
        args.out_xlsx = None
        args.original_template_xlsx = original
        before = business_snapshot(self.output)
        build_workbook(args)
        result = validate_workbook(self.output, original)
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(before, business_snapshot(self.output))

    def test_no_template_is_reported_as_unchecked(self):
        self.build()
        self.assertFalse(validate_workbook(self.output)['template_comparison']['performed'])
        self.assertTrue(validate_workbook(self.output, self.template)['template_comparison']['performed'])
        self.assertFalse(validate_workbook(self.output, self.output)['ok'])

    def test_namespaced_production_row_attributes_preserved(self):
        namespace = 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac'
        prior = self.output
        self.output = self.template
        try:
            self.mutate('Pipeline', lambda root: root.find(f"{pipeline_ooxml.Q('sheetData')}/{pipeline_ooxml.Q('row')}[@r='3']").set(f'{{{namespace}}}dyDescent', '0.3'))
        finally:
            self.output = prior
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        row = ET.fromstring(parts[pipeline_ooxml.sheet_paths(parts)['Pipeline']]).find(f"{pipeline_ooxml.Q('sheetData')}/{pipeline_ooxml.Q('row')}[@r='3']")
        self.assertEqual('0.3', row.get(f'{{{namespace}}}dyDescent'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
