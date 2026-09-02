#!/usr/bin/env python3
"""Render waterline specs with offline Graphviz layout and bright semantic cards."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET

from PIL import ImageFont
from pipeline_doc_common import configure_utf8_stdio

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
PALETTES = {
    "blob": ("#f7f2ff", "#e9daff", "#8b5cf6", "Blob"),
    "hbase": ("#edf9f3", "#bdebd6", "#169b72", "HBase"),
    "pipeline": ("#eff6ff", "#c7e0ff", "#3b82f6", "Pipeline"),
    "clickhouse": ("#fffbef", "#ffe2a3", "#d99011", "ClickHouse"),
    "database": ("#edf9fa", "#c2e9ed", "#168b98", "数据库"),
    "gateway": ("#f7f2ff", "#e9daff", "#8b5cf6", "Gateway"),
    "process": ("#eff6ff", "#c7e0ff", "#3b82f6", "Process"),
    "table": ("#fffbef", "#ffe2a3", "#d99011", "Table"),
}
INK, MUTED, LINE, EDGE = "#203148", "#51627a", "#dce4ed", "#70859e"


def tag(name):
    return f"{{{SVG_NS}}}{name}"


def sub(parent, name, **attrs):
    return ET.SubElement(parent, tag(name), {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def text(parent, x, y, value, size=13, color=INK, weight="400", **attrs):
    node = sub(parent, "text", x=f"{x:.2f}", y=f"{y:.2f}", font_size=size, fill=color, font_weight=weight, **attrs)
    node.text = str(value)
    return node


def validate_spec(spec):
    if not str(spec.get("title") or "").strip() or not spec.get("nodes"):
        raise ValueError("flow spec requires a title and nodes")
    collections = {key: spec.get(key) or [] for key in ("nodes", "edges", "groups")}
    for key, values in collections.items():
        ids = [v.get("id", "") for v in values]
        if any(not isinstance(i, str) or not re.fullmatch(r"[a-z0-9_]+", i) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{key} IDs must be unique lowercase ASCII snake_case")
    nodes = {n["id"]: n for n in collections["nodes"]}
    groups = {g["id"]: g for g in collections["groups"]}
    for node in nodes.values():
        if node.get("kind") not in PALETTES:
            raise ValueError(f"unsupported node kind: {node.get('kind')}")
        if node.get("group") and node["group"] not in groups:
            raise ValueError(f"unknown group on {node['id']}")
        group = groups.get(node.get("group"), {})
        for field in ("column", "order"):
            if field in node and (type(node[field]) is not int or node[field] < 0):
                raise ValueError(f"invalid {field} on {node['id']}")
        if "column" in node and "column" in group and node["column"] != group["column"]:
            raise ValueError(f"node {node['id']} is outside its group column")
        if not isinstance(node.get("details", []), list) or any(not isinstance(d, str) for d in node.get("details", [])):
            raise ValueError("node details must be strings")
    for edge in collections["edges"]:
        if edge.get("from") not in nodes or edge.get("to") not in nodes:
            raise ValueError(f"edge {edge['id']} references an unknown node")
        if edge.get("kind", "output") not in {"source", "pipeline", "output", "control"}:
            raise ValueError(f"unsupported edge kind on {edge['id']}")
    seen, card_ids = set(), set()
    for card in (spec.get("presentation") or {}).get("cards", []):
        members = card.get("node_ids") or []
        if not re.fullmatch(r"[a-z0-9_]+", card.get("id", "")) or card["id"] in card_ids:
            raise ValueError("presentation card IDs must be unique snake_case")
        card_ids.add(card["id"])
        if not members or len(members) != len(set(members)) or set(members) - nodes.keys() or seen.intersection(members):
            raise ValueError("presentation cards require non-overlapping known node_ids")
        if len({nodes[m]["kind"] for m in members}) != 1:
            raise ValueError("a presentation card must contain only one node kind")
        if any(e["from"] in members and e["to"] in members for e in collections["edges"]):
            raise ValueError("connected nodes cannot be collapsed into one presentation card")
        seen.update(members)


class TextLayout:
    """Use font metrics, with conservative CJK widths when no CJK font is available."""
    def __init__(self):
        candidates = [os.environ.get("PIPELINE_GRAPHVIZ_FONT", ""),
                      str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"),
                      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                      "/System/Library/Fonts/PingFang.ttc"]
        self.path = next((p for p in candidates if p and Path(p).is_file()), None)
        self.fonts = {}

    def measure(self, value, size):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(self.path, size=size) if self.path else ImageFont.load_default(size=size)
        if self.path:
            return float(self.fonts[size].getlength(str(value)))
        return sum(size if unicodedata.east_asian_width(c) in {"W", "F", "A"} else max(size * .65, self.fonts[size].getlength(c)) for c in str(value))

    def wrap(self, value, width, size):
        result = []
        for original in str(value or "").splitlines() or [""]:
            rest = original
            if self.measure(rest, size) > width and "." in rest and "/" not in rest:
                namespace, name = rest.split(".", 1)
                if self.measure(namespace + ".", size) <= width and self.measure(name, size) <= width:
                    result.extend([namespace + ".", name]); continue
            while self.measure(rest, size) > width:
                cut = 1
                for end in range(1, len(rest) + 1):
                    if self.measure(rest[:end], size) > width:
                        break
                    cut = end
                boundary = max((m.end() for m in re.finditer(r"[/_.\s-]", rest[:cut])), default=0)
                cut = boundary if boundary >= cut * .5 else cut
                result.append(rest[:cut]); rest = rest[cut:]
            result.append(rest)
        return result


def graphviz_runtime():
    """Resolve a configured runtime, native dot, or the app's offline Viz.js bundle."""
    override = os.environ.get("PIPELINE_GRAPHVIZ_DOT")
    if override:
        return [override, "-Tjson"]
    node, module = os.environ.get("PIPELINE_GRAPHVIZ_NODE"), os.environ.get("PIPELINE_GRAPHVIZ_VIZ")
    if node or module:
        node = node or shutil.which("node")
        if not node:
            raise RuntimeError("PIPELINE_GRAPHVIZ_VIZ requires PIPELINE_GRAPHVIZ_NODE or node on PATH")
        return [node, str(Path(__file__).with_name("graphviz_layout.cjs")), module or "@viz-js/viz"]
    native = shutil.which("dot")
    if native:
        return [native, "-Tjson"]
    roots = [Path(sys.executable).resolve().parent.parent,
             Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"]
    for root in roots:
        for executable in (root / "node/bin/node.exe", root / "node/bin/node"):
            viz = root / "node/node_modules/@viz-js/viz/dist/viz.cjs"
            if executable.is_file() and viz.is_file():
                return [str(executable), str(Path(__file__).with_name("graphviz_layout.cjs")), str(viz)]
    node = shutil.which("node")
    if node:
        return [node, str(Path(__file__).with_name("graphviz_layout.cjs")), "@viz-js/viz"]
    raise RuntimeError("Graphviz is required: provide dot on PATH / PIPELINE_GRAPHVIZ_DOT, or offline Node + @viz-js/viz. No legacy-layout fallback is used.")


def make_cards(spec, measure):
    nodes = {n["id"]: n for n in spec["nodes"]}
    groups = {g["id"]: g for g in spec.get("groups", [])}
    definitions = list((spec.get("presentation") or {}).get("cards", []))
    assigned = {m for c in definitions for m in c["node_ids"]}
    # Only interchangeable leaf inputs/outputs are grouped automatically.
    if (spec.get("presentation") or {}).get("auto_group", True):
        buckets = defaultdict(list)
        for n in nodes.values():
            incoming = tuple(sorted({e["from"] for e in spec.get("edges", []) if e["to"] == n["id"]}))
            outgoing = tuple(sorted({e["to"] for e in spec.get("edges", []) if e["from"] == n["id"]}))
            if n["id"] not in assigned and n["kind"] not in {"pipeline", "process"} and bool(incoming) != bool(outgoing):
                buckets[(n["kind"], n.get("group"), n.get("column"), incoming, outgoing)].append(n["id"])
        for key, members in buckets.items():
            if len(members) >= 3:
                title = f'{PALETTES[key[0]][3]} · {"输入" if key[-1] else "输出"}（{len(members)}）'
                definitions.append({"id": "auto_" + members[0], "title": title, "node_ids": members})
                assigned.update(members)
    definitions.extend({"id": n["id"], "node_ids": [n["id"]]} for n in nodes.values() if n["id"] not in assigned)
    cards = []
    for index, definition in enumerate(definitions):
        members = [nodes[m] for m in definition["node_ids"]]
        first = members[0]
        card = {"id": f"c{index}", "stable_id": definition["id"], "members": members, "kind": first["kind"], "width": 320}
        columns = {n.get("column", groups.get(n.get("group"), {}).get("column")) for n in members}
        if len(columns) != 1:
            raise ValueError("presentation card members must share a column (or omit columns together)")
        card["column"] = next(iter(columns))
        card["order"] = min(n.get("order", 0) for n in members)
        group_titles = list(dict.fromkeys(groups.get(n.get("group"), {}).get("title", "") for n in members))
        eyebrow = " · ".join([PALETTES[card["kind"]][3], *[t for t in group_titles if t]])
        title = definition.get("title") or first.get("label") or first["id"]
        lines, y = [], 23
        for line in measure.wrap(eyebrow, 270, 11):
            lines.append((y, line, 11, "eyebrow", None)); y += 16
        y += 13
        for line in measure.wrap(title, 280, 19):
            lines.append((y, line, 19, "title", None)); y += 26
        card["band_height"] = y - 13
        rows = []
        for member_index, member in enumerate(members):
            if member_index:
                y += 12
            top = y - 10
            if len(members) > 1 or definition.get("title"):
                for line in measure.wrap(member.get("label") or member["id"], 280, 15):
                    lines.append((y, line, 15, "title", member["id"])); y += 22
            for value in member.get("details", []):
                for line in measure.wrap(value, 280, 13):
                    lines.append((y, line, 13, "detail", member["id"])); y += 20
            y = max(y, top + 26)
            rows.append({"id": member["id"], "port": f"p{member_index}", "top": top, "bottom": y})
        card.update(height=y + 14, lines=lines, rows=rows)
        cards.append(card)
    return cards


def graph_model(spec):
    validate_spec(spec)
    measure = TextLayout()
    cards = make_cards(spec, measure)
    membership = {n["id"]: (c, c["rows"][i]) for c in cards for i, n in enumerate(c["members"])}
    buckets = defaultdict(list)
    for edge in spec.get("edges", []):
        source, source_row = membership[edge["from"]]
        target, target_row = membership[edge["to"]]
        source_port = source_row["port"] if len(source["members"]) > 1 else ""
        target_port = target_row["port"] if len(target["members"]) > 1 else ""
        # Equivalent leaves can share a bus. Explicit cards with non-equivalent
        # neighbors retain member-specific ports, including independent Task entries.
        for card, direction in ((source, "out"), (target, "in")):
            sets = []
            for member in card["members"]:
                nid = member["id"]
                ins = {(e["from"], e.get("kind", "output")) for e in spec.get("edges", []) if e["to"] == nid}
                outs = {(e["to"], e.get("kind", "output")) for e in spec.get("edges", []) if e["from"] == nid}
                sets.append((ins, outs))
            equivalent = card["kind"] not in {"pipeline", "process"} and all(s == sets[0] for s in sets)
            if equivalent and direction == "out" and not sets[0][0]:
                source_port = ""
            if equivalent and direction == "in" and not sets[0][1]:
                target_port = ""
        buckets[(source["id"], target["id"], source_port, target_port, edge.get("kind", "output"))].append(edge)
    edges = []
    for index, (key, originals) in enumerate(buckets.items()):
        labels = list(dict.fromkeys(e.get("label", "") for e in originals if e.get("label")))
        lines = [line for label in labels for line in measure.wrap(label, 160, 12)]
        edges.append({"id": f"e{index}", "from": key[0], "to": key[1], "tailport": key[2], "headport": key[3], "kind": key[4], "originals": originals, "lines": lines,
                      "label_width": max([measure.measure(line, 12) + 16 for line in lines] or [0]), "label_height": len(lines) * 18 + 8 if lines else 0})
    dot = ['digraph waterline {', 'graph [rankdir=LR,splines=polyline,nodesep=0.36,ranksep=0.5,pad=0.1,margin=0,outputorder=edgesfirst];', 'node [shape=box,fixedsize=true,label="",margin=0];', 'edge [arrowsize=0.65];']
    columns = defaultdict(list)
    for card in cards:
        cells = [f'<TR><TD WIDTH="{card["width"]}" HEIGHT="{card["rows"][0]["top"]}"> </TD></TR>']
        for i, row in enumerate(card["rows"]):
            bottom = card["rows"][i+1]["top"] if i+1 < len(card["rows"]) else card["height"]
            cells.append(f'<TR><TD PORT="{row["port"]}" WIDTH="{card["width"]}" HEIGHT="{bottom-row["top"]}"> </TD></TR>')
        label = f'<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="0" FIXEDSIZE="TRUE" WIDTH="{card["width"]}" HEIGHT="{card["height"]}">' + ''.join(cells) + '</TABLE>>'
        dot.append(f'{card["id"]} [width={card["width"]/72:.6f},height={card["height"]/72:.6f},label={label}];')
        if card["column"] is not None:
            columns[card["column"]].append(card)
    for column in sorted(columns):
        values = sorted(columns[column], key=lambda c: (c["order"], c["id"]))
        dot.append('{rank=same;' + ';'.join(c["id"] for c in values) + ';}')
        if (spec.get("presentation") or {}).get("preserve_order", False):
            for a, b in zip(values, values[1:]):
                dot.append(f'{a["id"]} -> {b["id"]} [style=invis,weight=80];')
    for edge in edges:
        label = ''
        if edge["lines"]:
            label = f',label=<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="0"><TR><TD WIDTH="{int(edge["label_width"]+1)}" HEIGHT="{edge["label_height"]}"> </TD></TR></TABLE>>'
        ports = ''.join(f',{p}="{edge[p]}:{"e" if p == "tailport" else "w"}"' for p in ("tailport", "headport") if edge[p])
        dot.append(f'{edge["from"]} -> {edge["to"]} [id="{edge["id"]}",weight={1 if edge["kind"]=="control" else 8}{label}{ports}];')
    dot.append('}')
    return cards, edges, '\n'.join(dot) + '\n', measure


def layout(spec):
    cards, edges, dot, measure = graph_model(spec)
    completed = subprocess.run(graphviz_runtime(), input=dot, text=True, capture_output=True, encoding="utf-8", timeout=60, shell=False)
    if completed.returncode:
        raise RuntimeError("Offline Graphviz layout failed: " + completed.stderr[:3000])
    result = json.loads(completed.stdout)
    result.setdefault("engineVersion", "native-dot")
    return cards, edges, dot, result, measure


def render_spec(spec, output: Path):
    cards, edges, dot, result, measure = layout(spec)
    left, bottom, right, top = map(float, result["bb"].split(','))
    graph_width, graph_height = right-left, top-bottom
    width = max(720, graph_width + 64)
    title_lines = measure.wrap(spec["title"], width-64, 25)
    subtitle_lines = measure.wrap(spec.get("description") or "", width-64, 13)
    offset_y = 36 + len(title_lines)*32 + len(subtitle_lines)*20
    height = offset_y + graph_height + 36
    fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    prefix = "wl-" + fingerprint[:12]
    root = ET.Element(tag("svg"), {"viewBox": f"0 0 {width:.2f} {height:.2f}", "width": f"{width:.2f}", "height": f"{height:.2f}", "role": "img", "aria-labelledby": f"{prefix}-title {prefix}-desc", "data-engine": "graphviz", "data-spec-sha256": fingerprint, "style": "color-scheme:light", "font-family": "Microsoft YaHei, Noto Sans CJK SC, Segoe UI, sans-serif"})
    sub(root, "title", id=prefix+"-title").text = spec["title"]
    sub(root, "desc", id=prefix+"-desc").text = spec.get("description") or spec["title"]
    sub(root, "metadata").text = json.dumps({"engine": "graphviz", "version": str(result["engineVersion"]), "spec_sha256": fingerprint, "dot_sha256": hashlib.sha256(dot.encode()).hexdigest()}, ensure_ascii=False)
    sub(root, "rect", width=width, height=height, fill="#ffffff")
    for i, value in enumerate(title_lines):
        text(root, 32, 35+i*32, value, 25, weight="500")
    for i, value in enumerate(subtitle_lines):
        text(root, 32, 35+len(title_lines)*32+i*20, value, 13, MUTED)
    sub(root, "line", x1=32, y1=offset_y-18, x2=width-32, y2=offset_y-18, stroke=LINE)
    defs = sub(root, "defs")
    marker = sub(defs, "marker", id=prefix+"-arrow", markerWidth=9, markerHeight=9, refX=8, refY=4.5, orient="auto", markerUnits="userSpaceOnUse")
    sub(marker, "path", d="M0 0 L9 4.5 L0 9 Z", fill=EDGE)
    shadow = sub(defs, "filter", id=prefix+"-shadow", x="-10%", y="-10%", width="120%", height="125%")
    sub(shadow, "feDropShadow", dx=0, dy=3, stdDeviation=5, flood_color="#102845", flood_opacity=".055")
    point = lambda x, y: (32 + float(x)-left, offset_y+top-float(y))
    objects = {n["name"]: n for n in result.get("objects", []) if "pos" in n}
    boxes = {}
    for card in cards:
        cx, cy = point(*objects[card["id"]]["pos"].split(','))
        boxes[card["id"]] = (cx-card["width"]/2, cy-card["height"]/2, card["width"], card["height"])
    lookup = {e["id"]: e for e in edges}
    label_boxes, curves = [], []
    for edge in result.get("edges", []):
        if edge.get("id") not in lookup:
            continue
        model = lookup[edge["id"]]
        group = sub(root, "g", id=prefix+"-"+model["id"], data_edge_ids=" ".join(e["id"] for e in model["originals"]))
        sub(group, "title").text = "；".join(f'{e["from"]} → {e["to"]}：{e.get("label", "")}' for e in model["originals"])
        for cmd in edge.get("_draw_", []):
            if cmd["op"] not in {"b", "B"}:
                continue
            pts = [point(*p) for p in cmd["points"]]
            d = f'M {pts[0][0]:.2f},{pts[0][1]:.2f}'
            for i in range(1, len(pts), 3):
                d += ' C ' + ' '.join(f'{x:.2f},{y:.2f}' for x, y in pts[i:i+3])
            endpoint = re.search(r'(?:^|\s)e,([\d.-]+),([\d.-]+)', edge.get("pos", ""))
            if endpoint:
                tip = point(endpoint[1], endpoint[2]); d += f' L {tip[0]:.2f},{tip[1]:.2f}'
            sub(group, "path", d=d, fill="none", stroke=EDGE, stroke_width=1.7, stroke_linecap="round", stroke_linejoin="round", stroke_dasharray="5 4" if model["kind"]=="control" else "none", marker_end=f"url(#{prefix}-arrow)")
            curves.append((model, pts))
        if edge.get("lp") and model["lines"]:
            x, y = point(*edge["lp"].split(',')); w, h = model["label_width"], model["label_height"]
            label_boxes.append((x-w/2, y-h/2, w, h))
            sub(group, "rect", x=x-w/2, y=y-h/2, width=w, height=h, rx=4, fill="#ffffff")
            for i, value in enumerate(model["lines"]):
                text(group, x, y-h/2+17+i*18, value, 12, MUTED, text_anchor="middle")
    for card in cards:
        x, y, w, h = boxes[card["id"]]
        surface, band, accent, _ = PALETTES[card["kind"]]
        group = sub(root, "g", id=prefix+"-"+card["id"], data_category=card["kind"], data_members=" ".join(n["id"] for n in card["members"]))
        sub(group, "rect", x=x, y=y, width=w, height=h, rx=11, fill=surface, stroke=LINE, stroke_width=1, filter=f"url(#{prefix}-shadow)", **{"class": "node-surface"})
        clip = sub(defs, "clipPath", id=prefix+"-clip-"+card["id"])
        sub(clip, "rect", x=x, y=y, width=w, height=h, rx=11)
        sub(group, "rect", x=x, y=y, width=w, height=card["band_height"], fill=band, clip_path=f"url(#{prefix}-clip-{card['id']})", **{"class": "node-band"})
        sub(group, "rect", x=x+18, y=y+13, width=3, height=14, rx=1.5, fill=accent)
        row_groups = {}
        for i, row in enumerate(card["rows"]):
            row_groups[row["id"]] = sub(group, "g", data_node_id=row["id"])
            if i:
                sub(group, "line", x1=x+20, y1=y+row["top"]-7, x2=x+w-20, y2=y+row["top"]-7, stroke=LINE)
        for baseline, value, size, role, member in card["lines"]:
            parent = row_groups[member] if member else (row_groups[card["members"][0]["id"]] if len(card["members"])==1 else group)
            text(parent, x+(30 if role=="eyebrow" else 20), y+baseline, value, size, MUTED if role=="detail" else INK, "500" if role in {"title", "eyebrow"} else "400")
            if measure.measure(value, size) > w-(50 if role=="eyebrow" else 40)+.1 or baseline > h-6:
                raise ValueError(f"text would clip in card {card['stable_id']}")
    validate_geometry(boxes, label_boxes, curves)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    output.with_suffix(".dot").write_text(dot, encoding="utf-8")
    output.with_suffix(".layout.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def validate_geometry(boxes, labels, curves):
    def overlaps(a, b):
        return min(a[0]+a[2], b[0]+b[2]) > max(a[0], b[0])+.5 and min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1])+.5
    values = list(boxes.items())
    for i, (name, box) in enumerate(values):
        if any(overlaps(box, other) for _, other in values[i+1:]) or any(overlaps(box, label) for label in labels):
            raise ValueError(f"Graphviz node/label overlap near {name}")
    for i, label in enumerate(labels):
        if any(overlaps(label, other) for other in labels[i+1:]):
            raise ValueError("Graphviz edge labels overlap")
    for model, pts in curves:
        for start in range(0, len(pts)-1, 3):
            p = pts[start:start+4]
            for step in range(41):
                t = step/40
                x, y = [sum(v*p[j][axis] for j, v in enumerate(((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3))) for axis in (0, 1)]
                for name, (bx, by, bw, bh) in boxes.items():
                    if name not in {model["from"], model["to"]} and bx+1 < x < bx+bw-1 and by+1 < y < by+bh-1:
                        raise ValueError(f"Graphviz edge {model['id']} crosses unrelated card {name}")


def validate_svg_safety(root):
    allowed = {"svg", "g", "path", "polyline", "polygon", "rect", "circle", "ellipse", "line", "text", "tspan", "title", "desc", "metadata", "defs", "marker", "clippath", "filter", "fedropshadow"}
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1].lower()
        if name not in allowed:
            raise ValueError(f"unsafe SVG element: {name}")
        for key, value in node.attrib.items():
            key = key.rsplit("}", 1)[-1].lower()
            if key.startswith("on") or (key == "href" and value and not value.startswith("#")):
                raise ValueError("SVG event handlers and external references are not allowed")
            for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)", value, re.IGNORECASE):
                if not url.startswith("#"):
                    raise ValueError("external SVG paint/filter URL is not allowed")


def validate_svg(root, spec=None):
    validate_svg_safety(root)
    if root.tag != tag("svg") or root.get("data-engine") != "graphviz":
        raise ValueError("flow SVG must be generated by Graphviz")
    box = [float(v) for v in root.get("viewBox", "").split()]
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        raise ValueError("invalid SVG viewBox")
    if spec is not None:
        nodes = [n.get("data-node-id") for n in root.iter() if n.get("data-node-id")]
        edges = [e for n in root.iter() for e in n.get("data-edge-ids", "").split()]
        if sorted(nodes) != sorted(n["id"] for n in spec["nodes"]) or sorted(edges) != sorted(e["id"] for e in spec.get("edges", [])):
            raise ValueError("SVG node/edge coverage differs from facts")
        fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if root.get("data-spec-sha256") != fingerprint:
            raise ValueError("SVG is stale relative to the flow spec")


def main():
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    render_spec(json.loads(args.spec.read_text(encoding="utf-8")), args.out)
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
