#!/usr/bin/env python3
"""Offline regression of reviewed SVG binding, edits, portability and vector PDFs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from diagram_design_bridge import digest, local_asset, path_commands, read_bound_asset, validate_design

HERE = Path(__file__).resolve().parent
NS = '{http://www.w3.org/2000/svg}'


def fixture():
    spec = {'title': '示例同步', 'description': '示例同步至数据库', 'nodes': [
        {'id': 'sync', 'label': 'sample_sync', 'kind': 'pipeline'},
        {'id': 'target', 'label': 'sample.table', 'kind': 'hbase'}],
        'edges': [{'id': 'write', 'from': 'sync', 'to': 'target', 'label': '写入'}],
        'platforms': [{'id': 'engine', 'title': 'DataEngine', 'node_ids': ['sync', 'target']}]}
    root = ET.fromstring('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 320" role="img" aria-labelledby="test-title test-desc" data-engine="diagram-design" data-visual-version="1">
    <title id="test-title">示例同步</title><desc id="test-desc">示例同步至数据库</desc>
    <rect x="0" y="0" width="640" height="320" fill="#f5f5f5"/>
    <text x="24" y="28" fill="#2d3142" font-size="20">示例同步</text>
    <g data-platform-id="engine" data-platform-members="sync target" data-bounds="24 48 592 248">
    <rect x="24" y="48" width="592" height="248" fill="#f8eee8" stroke="#eb6c36"/>
    <text x="40" y="80" fill="#2d3142" font-size="20">DataEngine</text></g>
    <g data-edge-ids="write" data-from="sync" data-to="target"><path d="M 240 160 H 360" stroke="#4f5d75" fill="none"/>
    <text x="280" y="140" fill="#2d3142" font-size="16">写入</text></g>
    <g data-node-id="sync" data-bounds="48 112 192 128"><rect x="48" y="112" width="192" height="128" fill="#f5f5f5" stroke="#eb6c36"/>
    <path d="M 60 128 Q 64 116 76 128 H 96 V 144 L 60 144 Z" fill="#ececec" stroke="#4f5d75"/>
    <text x="60" y="176" fill="#2d3142" font-size="16">sample_sync</text></g>
    <g data-node-id="target" data-bounds="360 112 224 128"><rect x="360" y="128" width="224" height="112" fill="#ececec" stroke="#7a8399"/>
    <ellipse cx="472" cy="128" rx="112" ry="16" fill="#f5f5f5" stroke="#7a8399"/>
    <text x="380" y="176" fill="#2d3142" font-size="16">sample.table</text></g></svg>''')
    root.set('data-spec-sha256', digest(spec))
    return root, spec


def rejected(action):
    try:
        action()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError('Invalid design was accepted')


def run_regressions(directory):
    directory.mkdir(parents=True, exist_ok=True)
    root, spec = fixture()
    from diagram_design_bridge import render_diagram, require_bindings
    sentinel = directory / 'untouched.svg'
    sentinel.write_text('approved', encoding='utf-8')
    for preferences in ({}, {'diagrams': {'data_flow': {'engine': 'graphviz'}}}):
        rejected(lambda: render_diagram(spec, sentinel, {'render_preferences': preferences}, directory, 'data_flow'))
        assert sentinel.read_text(encoding='utf-8') == 'approved'
    rejected(lambda: require_bindings({'profile': 'sync'}))
    rejected(lambda: require_bindings({'profile': 'report', 'catalog': {'enabled': True}, 'render_preferences': {'diagrams': {'data_flow': {}}}}))
    validate_design(root, spec)
    for attribute, replacement in [('data-node-id', 'unknown'), ('data-to', 'sync'), ('data-platform-members', 'sync'), ('data-bounds', '700 112 224 128')]:
        changed = copy.deepcopy(root)
        next(e for e in changed.iter() if e.get(attribute)).set(attribute, replacement)
        rejected(lambda: validate_design(changed, spec))
    changed = copy.deepcopy(root)
    next(e for e in changed.iter(NS+'text') if e.text == 'sample.table').text = 'wrong.table'
    rejected(lambda: validate_design(changed, spec))
    for tag, attrs in [('script', {}), ('rect', {'onload': 'alert(1)'}), ('rect', {'fill': 'url(https://example.invalid/a)'}), ('path', {'d': 'M 0 0 a 1 1 0 0 0 8 8'})]:
        changed = copy.deepcopy(root)
        ET.SubElement(changed, NS+tag, attrs)
        rejected(lambda: validate_design(changed, spec))
    changed_spec = copy.deepcopy(spec)
    changed_spec['description'] = 'Changed semantics'
    rejected(lambda: validate_design(root, changed_spec))
    rejected(lambda: local_asset(directory, '../escape.svg'))
    commands = list(path_commands('M 0 0 H 12 V 12 Q 24 12 24 24 Z'))
    assert commands[1] == ('L', [12., 0.]) and commands[2] == ('L', [12., 12.])
    assert commands[3] == ('C', [20., 12., 24., 16., 24., 24.])
    from verify_pipeline_doc_generator import facts
    for profile in ('sync', 'report'):
        work = directory / profile
        work.mkdir(exist_ok=True)
        asset = work / 'approved.svg'
        asset.write_bytes(ET.tostring(root, encoding='utf-8'))
        data = facts(profile, 'Diagram Design '+profile)
        data['flow'] = spec
        config = {'engine': 'diagram-design', 'svg': 'approved.svg', 'sha256': hashlib.sha256(asset.read_bytes()).hexdigest()}
        data['render_preferences']['diagrams'] = {'data_flow': config}
        path = work / 'facts.json'
        if profile == 'report':
            from verify_design_fixtures import write_test_svg
            from render_pipeline_doc import catalog_spec
            catalog = work / 'catalog.svg'
            write_test_svg(catalog_spec(), catalog)
            data['render_preferences']['diagrams']['catalog'] = {'engine': 'diagram-design', 'svg': catalog.name, 'sha256': hashlib.sha256(catalog.read_bytes()).hexdigest()}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        out = work / 'portable'
        def execute(script, *args):
            result = subprocess.run([sys.executable, str(HERE / script), *map(str, args)], capture_output=True, encoding='utf-8')
            assert result.returncode == 0, result.stdout + result.stderr
        execute('render_pipeline_doc.py', '--facts', path, '--out-dir', out)
        execute('validate_pipeline_doc.py', '--facts', out/'facts.json', '--profile', profile, '--markdown', out/('Diagram Design '+profile+'.md'))
        original = (out/'approved.svg').read_bytes()
        data = json.loads((out/'facts.json').read_text(encoding='utf-8'))
        data['requirements']['summary'] = ['更新示例说明，不改变数据流程。']
        (out/'facts.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        execute('render_pipeline_doc.py', '--facts', out/'facts.json', '--out-dir', out)
        assert (out/'approved.svg').read_bytes() == original
        execute('validate_pipeline_doc.py', '--facts', out/'facts.json', '--profile', profile, '--markdown', out/('Diagram Design '+profile+'.md'))
        # A layout-only binding change must invalidate a previously generated PDF.
        from validate_pipeline_pdf import validate_pdf
        altered = copy.deepcopy(data)
        altered['render_preferences']['diagrams']['data_flow']['sha256'] = '0'*64
        errors = []
        validate_pdf(out/('Diagram Design '+profile+'.pdf'), altered, errors, {})
        assert any('diagram binding' in e for e in errors), errors
        asset.write_bytes(asset.read_bytes()+b'\n')
        rejected(lambda: read_bound_asset(spec, config, work))
        asset.unlink()
        rejected(lambda: read_bound_asset(spec, config, work))
    return {'profiles': 2, 'portable_rerender': True, 'prose_edit_preserves_svg': True, 'stale_and_unsafe_rejected': True, 'pdf_binding_checked': True}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='diagram_design_test_') as temporary:
        print(json.dumps(run_regressions(Path(temporary)), indent=2))
