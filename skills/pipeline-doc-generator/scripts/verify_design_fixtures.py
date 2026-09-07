"""Synthetic vectors for deterministic tests only; never a document authoring engine."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from diagram_design_bridge import digest
from pipeline_diagram_contract import platform_definitions


def write_test_svg(spec, output):
    ns = '{http://www.w3.org/2000/svg}'
    root = ET.Element(ns+'svg', {'viewBox': f'0 0 1800 {240+len(spec["nodes"])*130}', 'data-engine': 'diagram-design', 'data-visual-version': '1', 'data-spec-sha256': digest(spec), 'role': 'img', 'aria-labelledby': 'fixture-title fixture-desc'})
    ET.SubElement(root, ns+'title', {'id':'fixture-title'}).text=spec['title']
    ET.SubElement(root, ns+'desc', {'id':'fixture-desc'}).text=spec.get('description',spec['title'])
    def text(parent,x,y,value):
        if not str(value).strip(): return
        ET.SubElement(parent,ns+'text',{'x':str(x),'y':str(y),'fill':'#2d3142','font-size':'16'}).text=str(value)
    text(root,20,30,spec['title'])
    platforms=platform_definitions(spec)
    ordered=[]
    for platform in platforms:
        ordered.extend(n for n in spec['nodes'] if n['id'] in platform['node_ids'])
    ordered.extend(n for n in spec['nodes'] if n not in ordered)
    boxes={n['id']:(80,100+i*130,1640,110) for i,n in enumerate(ordered)}
    for platform in platforms:
        ys=[boxes[i][1] for i in platform['node_ids']]; y=min(ys)-35; h=max(ys)+115-y
        g=ET.SubElement(root,ns+'g',{'data-platform-id':platform['id'],'data-platform-members':' '.join(platform['node_ids']),'data-bounds':f'40 {y} 1720 {h}'})
        ET.SubElement(g,ns+'rect',{'x':'40','y':str(y),'width':'1720','height':str(h),'fill':'none','stroke':'#eb6c36'})
        text(g,50,y+20,platform['title'])
    for n in ordered:
        x,y,w,h=boxes[n['id']]
        g=ET.SubElement(root,ns+'g',{'data-node-id':n['id'],'data-bounds':f'{x} {y} {w} {h}'})
        ET.SubElement(g,ns+'rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'fill':'#f5f5f5','stroke':'#eb6c36'})
        text(g,x+10,y+25,n.get('label',''))
        for i,value in enumerate(n.get('identifiers',[])): text(g,x+10,y+48+i*18,value)
    for i,e in enumerate(spec.get('edges',[])):
        g=ET.SubElement(root,ns+'g',{'data-edge-ids':e['id'],'data-from':e['from'],'data-to':e['to']})
        x,y,w,h=boxes[e['from']]; tx,ty,_,_=boxes[e['to']]
        ET.SubElement(g,ns+'path',{'d':f'M {x} {y+50} L {tx} {ty+50}','stroke':'#4f5d75','fill':'none'})
        text(g,20,240+len(ordered)*130-20-i*18,e.get('label',''))
    output.write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))


def bind_test_diagrams(path):
    from render_pipeline_doc import catalog_spec
    from diagram_design_bridge import required_slots
    data=json.loads(path.read_text(encoding='utf-8'))
    bindings=data.setdefault('render_preferences',{}).setdefault('diagrams',{})
    for slot in required_slots(data):
        spec=data['flow'] if slot=='data_flow' else catalog_spec()
        target=path.parent/f'test_{slot}.svg'
        write_test_svg(spec,target)
        bindings[slot]={'engine':'diagram-design','svg':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
