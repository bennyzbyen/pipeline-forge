"""Exact business-value checks, independent of formatting and shared-string indices."""
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

from pipeline_ooxml import Q, column_letter, sheet_paths

DATA_SHEETS = ('Data Utilization', 'Target & Catalog', 'Target Field', 'Pipeline')


def business_snapshot(path: Path):
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    strings = ["".join(t.text or "" for t in item.iter(Q('t')))
               for item in ET.fromstring(parts.get('xl/sharedStrings.xml', b'<sst/>'))]
    result = {}
    for name, part in sheet_paths(parts).items():
        if name not in DATA_SHEETS:
            continue
        rows = {}
        for row in ET.fromstring(parts[part]).find(Q('sheetData')):
            number = int(row.get('r'))
            if number < 3:
                continue
            cells = {}
            for cell in row:
                kind = cell.get('t')
                node = cell.find(Q('v'))
                value = None if node is None else node.text
                if kind == 's' and value is not None:
                    value = strings[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.iter(Q('t')))
                formula = cell.find(Q('f'))
                cells[re.sub(r'\d', '', cell.get('r'))] = (
                    kind, value, None if formula is None else ET.tostring(formula, encoding='unicode'))
            # Retain physical blank-cell presence in every populated/typed row.
            if any(kind is not None or value is not None or formula is not None
                   for kind, value, formula in cells.values()):
                rows[number] = cells
        result[name] = rows
    return result


def preservation_errors(path: Path, reference: Path):
    before, after = business_snapshot(reference), business_snapshot(path)
    errors = []
    for name in before.keys() | after.keys():
        for number in before.get(name, {}).keys() | after.get(name, {}).keys():
            a, b = before.get(name, {}).get(number, {}), after.get(name, {}).get(number, {})
            for column in a.keys() | b.keys():
                if a.get(column) != b.get(column):
                    errors.append(f'Business value/type/blank presence changed: {name}!{column}{number}')
    return sorted(errors)


def assert_expected_business_values(path: Path, tables, schema):
    """Freeze mapped/confirmed rows before writing; formatting may not change them.

    Generation's optional empty values are absence, with template-compatible benign
    empty strings allowed. Format-only repairs use preservation_errors instead,
    which distinguishes absent cells, true blanks and typed empty strings exactly.
    """
    actual = business_snapshot(path)
    for name, rows in tables.items():
        populated = [(number, cells) for number, cells in sorted(actual.get(name, {}).items())
                     if any(value not in (None, '') for _, value, _ in cells.values())]
        if [n for n, _ in populated] != list(range(3, len(rows) + 3)):
            raise ValueError(f'Business row count/order changed during serialization: {name}')
        for (number, cells), expected in zip(populated, rows):
            want = {column_letter(i): str(expected[header])
                    for i, header in enumerate(schema[name], 1)
                    if expected.get(header) not in (None, '')}
            got = {column: value for column, (_, value, _) in cells.items() if value not in (None, '')}
            for column in want.keys() | got.keys():
                if want.get(column) != got.get(column):
                    raise ValueError(f'Business value/XML changed during serialization: {name}!{column}{number}')
